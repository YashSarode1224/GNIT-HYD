import asyncio
import os
import json
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, Request, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from app.schemas.snapshot import (
    HealthResponse, ModelStatusResponse, ActivityObservationResponse, ReplayActionResponse, CrossRouteContract,
    WebSocketMessageEnvelope, HardwareAckRequest, HardwareAckResponse,
    SystemSnapshot, ClassroomDemoResponse, HospitalDemoResponse, HardwareStatusResponse,
    SiteIdentityResponse, HardwareLinkStatus,
    AllocationPolicyResponse, AllocationPolicyUpdateResponse,
    RfidScanRequest,
    RfidScanResponse,
    RfidEventType,
    CapacityChangeRequest,
    CapacityChangeResponse,
    ClassroomLoadRequest,
    ClassroomLoadResponse,
    FeederChangeRequest,
    FeederChangeResponse,
    ActivityObservationRequest,
    ReplayActionRequest,
    SiteScenarioRequest,
    SiteScenarioResponse,
    SiteScenariosResponse,
)
from app.core.state import CLASSROOMS, GridState
from app.core.active_site import CATALOG
from app.api.history import attach_history, register_history
from app.api.demo import register_demo
from app.api.power_system import register_power_system
from app.forecast import DemandForecast
from app.core.control_loop import ControlLoop
from app.core.site import SCENARIOS, AuditUnavailable, SiteAuthority
from app.hardware.board_b_direct import BoardBDirectTransport
from app.hardware.gateway import GatewayBridge, GatewayThread, SerialTransport
from app.core.policy import AllocationPolicy
from app.simulation.electrical import ElectricalInput, ElectricalStudyResponse, solve as solve_electrical, diagnose_study
from app.activity.model import FEATURES
from app.visualizers import hospital_snapshot, CAPACITY_RANGE_W as CLASSROOM_CAPACITY_RANGE_W, ClassroomDemo, HospitalPriorityDemo

# Request enums follow the active site profile (#26); the default campus keeps the published contract.
CLASSROOM_IDS = tuple(c["id"] for c in CLASSROOMS)
ClassroomId = Literal[CLASSROOM_IDS]
HospitalZoneId = Literal[CATALOG.hospital_zones]
CLASSROOM_ID_ERROR = f"classroom_id must be one of {', '.join(CLASSROOM_IDS)}"


class ClassroomDemoAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["scan", "unscan", "set_capacity", "normal", "overload", "reset",
                    "replay_pause", "replay_resume", "replay_step"]
    classroom_id: ClassroomId | None = None
    capacity_w: StrictInt | None = None
    event_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    observed_at: datetime | None = None
    run_id: StrictStr | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_session_identity(self):
        session_action = self.action in ("scan", "unscan")
        identity_present = all((self.event_id, self.observed_at, self.run_id))
        identity_partial = any((self.event_id, self.observed_at, self.run_id))
        if session_action and not identity_present:
            raise ValueError("scan and unscan require run_id, event_id and observed_at")
        if not session_action and identity_partial:
            raise ValueError("session identity fields are only valid for scan and unscan")
        return self

class HospitalDemoAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["scan", "unscan", "set_capacity", "normal", "overload", "reset", "replay_pause", "replay_resume", "replay_step",
                    "inject_fault", "clear_fault"] | None = None
    zone_id: HospitalZoneId | None = None
    capacity_w: StrictInt | None = None
    fault: Literal["overload", "cooling_failure", "overload_cooling", "upstream_loss", "sensor_dropout", "stuck_sensor"] | None = None
    # Preserve the live scenario alias; rehearsals use isolated diagnostic fixtures.
    scenario: Literal["normal", "overload", "cooling_failure", "upstream_loss", "missing_sensor"] | None = None
    rehearsal: Literal["normal", "overload", "cooling_failure", "overload_cooling", "upstream_loss", "missing_sensor", "stuck_sensor"] | None = None


SCENARIO_FAULTS = {"overload": "overload", "cooling_failure": "cooling_failure", "upstream_loss": "upstream_loss",
                   "missing_sensor": "sensor_dropout"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


def load_replay():
    try:
        data = json.loads(REPLAY_PATH.read_text())
        return {cid: rows for cid, rows in data.items() if cid in CLASSROOM_IDS and isinstance(rows, list)}
    except (OSError, ValueError):
        return {}

def with_site(data: dict, identity: dict) -> dict:
    data = dict(data)
    data["site"] = identity
    return data


def session_event_time(value):
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "observed_at must include a UTC offset")
    value = value.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if value < now - timedelta(seconds=30) or value > now + timedelta(seconds=2):
        raise HTTPException(422, "observed_at must be within 30 seconds of server time")
    return value


def check_session_run(requested_run_id, site, event_id, observed_at):
    if requested_run_id is None or event_id is None or observed_at is None:
        raise HTTPException(422, "run_id, event_id and observed_at are required for session commands")
    if requested_run_id is not None and requested_run_id != site.run_id:
        raise HTTPException(409, "session event belongs to a previous site run")

REPLAY_PATH = Path(__file__).resolve().parents[1] / "models" / "replay.json"


def initialize_state(app: FastAPI):
    from app.api.district import initialize_district
    initialize_district(app)
    app.state.manager = ConnectionManager()
    app.state.replay_data = load_replay()
    app.state.grid = GridState()
    app.state.grid.replay_length = max((len(rows) for rows in app.state.replay_data.values()), default=0)
    app.state.classroom_demo = ClassroomDemo(model=app.state.grid.model, replay=app.state.replay_data)
    app.state.classroom_demo.bind_sessions(app.state.grid.active_sessions, app.state.grid.set_classroom_load)
    app.state.hospital_demo = HospitalPriorityDemo(model=app.state.grid.model, replay=app.state.replay_data)
    app.state.site = SiteAuthority(app.state.grid, app.state.classroom_demo, app.state.hospital_demo)
    attach_history(app.state.grid, app.state.site.run_id)
    app.state.replay_generation = 0
    app.state.replay_task = None
    app.state.electrical_study_lock = asyncio.Lock()
    app.state.gateway = None  # (GatewayBridge, GatewayThread) once board A is connected
    async def publish():
        if app.state.manager.active_connections:
            snapshot = campus_snapshot(app.state.site, app)
            await app.state.manager.broadcast(socket_payload(snapshot, app.state.site))
    app.state.demand_forecast = DemandForecast()
    def observe_demand():
        snapshot, identity = app.state.site.read(app.state.grid.build_snapshot)
        demand_w = sum(service.watts for service in snapshot.services if service.requested)
        app.state.demand_forecast.observe(identity["run_id"], demand_w)
    app.state.control_loop = ControlLoop([app.state.site.tick, observe_demand], publish=publish)


def campus_snapshot(site, app=None):
    snapshot, identity = site.read(site.grid.build_snapshot)
    if snapshot is not None and app is not None:
        hw = hardware_status(app)
        if hw["link"] != "NOT_CONFIGURED":  # physical board B state, applied at read time only
            snapshot.hardware_link = HardwareLinkStatus.CONNECTED if hw["link"] == "CONNECTED" else HardwareLinkStatus.ERROR
            snapshot.indicator_command_mask = hw["commanded_mask"]
            snapshot.indicator_confirmed_mask = hw["confirmed_mask"]
    if snapshot is not None:
        snapshot.site = SiteIdentityResponse.model_validate(identity)
        snapshot.contract = snapshot.contract.model_copy(update={"identity": snapshot.contract.identity.model_copy(update={"run_id": site.run_id, "state_revision": site.revision, "observation_time": snapshot.generated_at.isoformat()})})
    return snapshot


# ---- board A gateway (physical card reader, buttons, and board B's LEDs) ----
ROOM_TO_CLASSROOM = {c["hardware_room"]: c["id"] for c in CLASSROOMS if c["hardware_room"]}
CLASSROOM_LED_BIT = {c["id"]: c["led_bit"] for c in CLASSROOMS}


def led_mask(classroom: dict) -> int:
    """Board B lights a room's LED when the room has a session (card or fallback) and all its loads are served."""
    mask = 0
    for room in classroom.get("rooms", []):
        if room["rfid_active"] and all(load["served"] for load in room["loads"]):
            mask |= 1 << CLASSROOM_LED_BIT[room["id"]]
    return mask


def desired_led_mask(app) -> int:
    data, _ = app.state.site.read(app.state.classroom_demo.snapshot)
    return led_mask(data)


def handle_gateway_event(app, action: str, room) -> bool:
    """Board A input -> one site command. Shortage = deprived-of-kW preset, restore = normal supply."""
    cid = ROOM_TO_CLASSROOM.get(room)
    commands = {"START_SESSION": ("scan", cid), "END_SESSION": ("unscan", cid), "SIMULATE_SHORTAGE": ("overload", None),
                "RESTORE": ("normal", None), "RESET_SESSION": ("reset", None)}
    if action not in commands or (action in ("START_SESSION", "END_SESSION") and cid is None):
        return False
    name, arg = commands[action]
    demo = app.state.classroom_demo
    if action == "START_SESSION" and cid in demo.snapshot()["scanned_classroom_ids"]:
        name = "unscan"  # pressing a room button (or tapping its card) again ends that room's session
    app.state.site.command(f"board_a.{action.lower()}", lambda: demo.act(name, arg, source="HARDWARE"), {"action": action, "room": room})
    return True


def hardware_status(app) -> dict:
    gateway = getattr(app.state, "gateway", None)
    if gateway is None:
        return {"link": "NOT_CONFIGURED", "commanded_mask": None, "confirmed_mask": None}
    bridge, thread = gateway
    status = bridge.status()
    status["port_error"] = thread.error
    return status


def connect_gateway(app, port: str, transport=None, board: str = "A"):
    """board "A": board A's USB gateway. board "B": board B alone on USB, with a software stand-in for A."""
    disconnect_gateway(app)
    if transport is None:
        transport = BoardBDirectTransport(port) if board == "B" else SerialTransport(port)
    bridge = GatewayBridge(transport, lambda action, room: handle_gateway_event(app, action, room),
                           lambda: desired_led_mask(app))
    thread = GatewayThread(bridge)
    thread.start()
    app.state.gateway = (bridge, thread)


def disconnect_gateway(app):
    gateway = getattr(app.state, "gateway", None)
    if gateway is not None:
        gateway[1].stop()
        ser = getattr(gateway[0].t, "ser", None)
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        app.state.gateway = None


def socket_payload(snapshot, site):
    snapshot.site = SiteIdentityResponse.model_validate(site.identity())
    return WebSocketMessageEnvelope(type="snapshot", payload=snapshot,
        sent_at=datetime.now(timezone.utc)).model_dump_json()


async def run_replay(app, generation):
    grid, replay_data = app.state.grid, app.state.replay_data
    while grid.replay_running and generation == app.state.replay_generation:
        max_len = max((len(rows) for rows in replay_data.values()), default=0)
        if not max_len:
            grid.replay_running = False
            return
        index = grid.replay_index % max_len
        for cid, rows in replay_data.items():
            if not rows:
                continue
            row = rows[index % len(rows)]
            features = {key: row.get(key) for key in FEATURES}
            rev = grid.record_activity(cid, features, datetime.now(timezone.utc), "RECORDED_REPLAY", row.get("observed_at"))
            try:
                pred = await asyncio.to_thread(grid.model.predict, features)
            except Exception as exc:
                pred = {"state": "UNKNOWN", "score": None, "reason": f"inference failed: {type(exc).__name__}", "model_version": "unavailable"}
            if generation != app.state.replay_generation or not grid.replay_running:
                return
            grid.apply_prediction(cid, rev, pred)
        grid.replay_index = (index + 1) % max_len
        app.state.site.tick()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_state(app)
    app.state.site.tick()  # capture the initial canonical publication before serving reads
    app.state.control_loop.start()
    if os.environ.get("BLACKOUT_GATEWAY_PORT"):
        try:
            connect_gateway(app, os.environ["BLACKOUT_GATEWAY_PORT"], board=os.environ.get("BLACKOUT_GATEWAY_BOARD", "A"))
        except Exception as exc:
            print(f"Board A gateway not connected: {exc}")
    try:
        yield
    finally:
        disconnect_gateway(app)
        await app.state.control_loop.stop()
        if app.state.replay_task:
            app.state.replay_task.cancel()
            try:
                await app.state.replay_task
            except asyncio.CancelledError:
                pass
        for connection in list(app.state.manager.active_connections):
            await connection.close()
        app.state.manager.active_connections.clear()
        app.state.grid.storage.engine.dispose()
        if app.state.grid.history:
            app.state.grid.history.store.engine.dispose()


def get_grid_state(request: Request) -> GridState:
    return request.app.state.grid


router = APIRouter()
ELECTRICAL_TIMEOUT_S = 5


@router.get("/api/v1/health", response_model=HealthResponse)
async def health_check(request: Request):
    control_loop = request.app.state.control_loop
    return {
        "status": "degraded" if request.app.state.grid.storage.degraded else "ok",
        "application": "PriorityGrid",
        "control_loop": control_loop.health(),
        "storage": {"status": "DEGRADED" if request.app.state.grid.storage.degraded else "HEALTHY",
                    "degraded_reason": request.app.state.grid.storage.degraded_reason},
    }


async def audit_unavailable_handler(request: Request, exc: AuditUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})

@router.get("/api/v1/snapshot", response_model=SystemSnapshot)
async def get_snapshot(request: Request):
    site = request.app.state.site
    snapshot = campus_snapshot(site, request.app)
    if snapshot is None:
        raise HTTPException(503, "control state not published yet")
    return snapshot

@router.get("/api/v1/model/status", response_model=ModelStatusResponse)
async def model_status(request: Request):
    grid = request.app.state.grid
    return grid.model.status()

@router.get("/api/v1/visualizers/classrooms", response_model=ClassroomDemoResponse)
async def get_classroom_demo(request: Request):
    site = request.app.state.site
    classroom_demo = request.app.state.classroom_demo
    return visualizer_snapshot(site, classroom_demo) | {"hardware": hardware_status(request.app)}


class GatewayConnect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: str
    board: Literal["A", "B"] = "A"


@router.get("/api/v1/hardware", response_model=HardwareStatusResponse)
async def get_hardware(request: Request):
    return hardware_status(request.app)


@router.post("/api/v1/hardware/connect", response_model=HardwareStatusResponse)
async def post_hardware_connect(request: Request, req: GatewayConnect):
    try:
        request.app.state.site.command("hardware.connect", lambda: connect_gateway(request.app, req.port, board=req.board), {})
    except Exception as exc:
        raise HTTPException(409, f"could not open {req.port}: {exc}")
    return hardware_status(request.app)


@router.post("/api/v1/hardware/disconnect", response_model=HardwareStatusResponse)
async def post_hardware_disconnect(request: Request):
    request.app.state.site.command("hardware.disconnect", lambda: disconnect_gateway(request.app))
    return hardware_status(request.app)

@router.post("/api/v1/visualizers/classrooms", response_model=ClassroomDemoResponse)
async def act_classroom_demo(request: Request, req: ClassroomDemoAction):
    site = request.app.state.site
    classroom_demo = request.app.state.classroom_demo
    if (req.action in ("scan", "unscan")) != (req.classroom_id is not None):
        raise HTTPException(422, "classroom_id is required only for scan and unscan")
    observed_at = session_event_time(req.observed_at)
    if req.action in ("scan", "unscan"):
        check_session_run(req.run_id, site, req.event_id, req.observed_at)
    if (req.action == "set_capacity") != (req.capacity_w is not None):
        raise HTTPException(422, "capacity_w is required only for set_capacity")
    low, high = CLASSROOM_CAPACITY_RANGE_W
    if req.capacity_w is not None and not low <= req.capacity_w <= high:
        raise HTTPException(422, f"capacity_w must be between {low} and {high}")
    try:
        _, receipt = site.command(f"classroom.{req.action}",
                                  lambda: classroom_demo.act(req.action, req.classroom_id, req.capacity_w,
                                                             event_id=req.event_id, event_time=observed_at),
                                  {"action": req.action, "classroom_id": req.classroom_id,
                                   "capacity_w": req.capacity_w, "event_id": req.event_id, "run_id": req.run_id})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    data, identity = site.read(classroom_demo.snapshot)
    return with_contract(data, site) | {"command": receipt}

@router.get("/api/v1/visualizers/hospital", response_model=HospitalDemoResponse)
async def get_hospital_demo(request: Request):
    site = request.app.state.site
    hospital_demo = request.app.state.hospital_demo
    return visualizer_snapshot(site, hospital_demo)

@router.post("/api/v1/visualizers/hospital", response_model=HospitalDemoResponse)
async def act_hospital_demo(request: Request, req: HospitalDemoAction):
    site = request.app.state.site
    hospital_demo = request.app.state.hospital_demo
    if req.rehearsal is not None:
        if any(value is not None for value in (req.action, req.fault, req.scenario, req.zone_id, req.capacity_w)):
            raise HTTPException(422, "rehearsal cannot be combined with live controls")
        return with_contract(hospital_snapshot(req.rehearsal), site)
    action, fault = req.action, req.fault
    if req.scenario is not None:
        if action is not None or fault is not None:
            raise HTTPException(422, "scenario cannot be combined with action or fault")
        action, fault = ("clear_fault", None) if req.scenario == "normal" else ("inject_fault", SCENARIO_FAULTS[req.scenario])
    if action is None:
        raise HTTPException(422, "either action or scenario must be provided")
    if (action == "inject_fault") != (fault is not None):
        raise HTTPException(422, "fault is required with inject_fault and only allowed with it")
    if req.capacity_w is not None:
        low, high = hospital_demo.snapshot()["capacity_range_w"]
        if not (low <= req.capacity_w <= high):
            raise HTTPException(422, f"capacity_w must be between {low} and {high}")
    _, receipt = site.command(f"hospital.{action}", lambda: hospital_demo.act(action, req.zone_id, req.capacity_w, fault),
                              {"action": action, "zone_id": req.zone_id, "capacity_w": req.capacity_w, "fault": fault})
    data, identity = site.read(hospital_demo.snapshot)
    return with_contract(data, site) | {"command": receipt}

@router.post("/api/v1/activity/observations", response_model=ActivityObservationResponse)
async def post_activity_observation(request: Request, req: ActivityObservationRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    if req.classroom_id not in CLASSROOM_IDS:
        raise HTTPException(422, CLASSROOM_ID_ERROR)
    if req.source not in ("RECORDED_REPLAY", "SIMULATED"):
        raise HTTPException(422, "source must be RECORDED_REPLAY or SIMULATED")
    try:
        observed_at = datetime.fromisoformat(req.observed_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "observed_at must be an ISO timestamp")
    if observed_at.tzinfo is None:
        raise HTTPException(422, "observed_at must include a UTC offset")
    now = datetime.now(timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc)
    if observed_at < now - timedelta(minutes=10) or observed_at > now + timedelta(seconds=30):
        raise HTTPException(422, "observed_at must be within the last 10 minutes and no more than 30 seconds ahead")
    bounds = {"temperature_c": (-10, 60), "humidity_pct": (0, 100), "co2_ppm": (250, 10000), "humidity_ratio": (0, 0.05)}
    features = {key: getattr(req, key) for key in FEATURES}
    for key, value in features.items():
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or not bounds[key][0] <= value <= bounds[key][1]):
            raise HTTPException(422, f"{key} is outside its accepted range")
    revision, receipt = site.command("campus.activity_observation",
        lambda: grid.record_activity(req.classroom_id, features, observed_at, req.source),
        {"classroom_id": req.classroom_id, "source": req.source,
         "observed_at": observed_at.isoformat(), "features": features})
    try:
        prediction = await asyncio.to_thread(grid.model.predict, features)
    except Exception as exc:
        prediction = {"state": "UNKNOWN", "score": None, "reason": f"inference failed: {type(exc).__name__}", "model_version": "unavailable"}
    applied = grid.apply_prediction(req.classroom_id, revision, prediction)
    site.complete_command(receipt, "campus.activity_observation")
    return {"accepted": True, "applied": applied, "revision": revision,
            "activity": grid.activity[req.classroom_id]}

@router.post("/api/v1/replay", response_model=ReplayActionResponse)
async def replay_action(request: Request, req: ReplayActionRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    replay_data = request.app.state.replay_data
    if req.action not in ("start", "pause", "reset"):
        raise HTTPException(422, "action must be start, pause, or reset")
    max_len = max((len(rows) for rows in replay_data.values()), default=0)
    if req.action == "start" and not max_len:
        raise HTTPException(409, "recorded replay data is unavailable")
    def apply_replay_action():
        if req.action == "reset":
            request.app.state.replay_generation += 1
            if request.app.state.replay_task and not request.app.state.replay_task.done():
                request.app.state.replay_task.cancel()
            grid.replay_index = 0
            grid.replay_running = False
            for cid in CLASSROOM_IDS:
                grid.set_classroom_load(cid, True)
                grid.activity_tokens[cid] += 1
                grid.activity_received_monotonic[cid] = None
                grid.activity_guard.reset(cid)
                grid.activity[cid] = {"state": "UNKNOWN", "score": None, "reason": "replay reset; awaiting evidence",
                                      "source": None, "observed_at": None, "recorded_at": None,
                                      "model_version": "unavailable", "priority": "UNKNOWN",
                                      "evidence": {key: None for key in FEATURES}}
        elif req.action == "pause":
            request.app.state.replay_generation += 1
            grid.replay_running = False
        elif not grid.replay_running:
            for cid in CLASSROOM_IDS:
                grid.set_classroom_load(cid, True)
            grid.replay_running = True
            request.app.state.replay_generation += 1
            request.app.state.replay_task = asyncio.create_task(run_replay(request.app, request.app.state.replay_generation))
        grid.replay_length = max_len
    site.command(f"campus.replay_{req.action}", apply_replay_action, {"action": req.action})
    return {"running": grid.replay_running, "index": grid.replay_index, "length": max_len}

@router.post("/api/v1/rfid/scan", response_model=RfidScanResponse)
async def process_rfid_scan(request: Request, req: RfidScanRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    observed_at = session_event_time(req.observed_at)
    check_session_run(req.run_id, site, req.event_id, req.observed_at)
    try:
        evt_type, class_id, class_name, service_id = site.command(
            "campus.rfid_scan", lambda: grid.process_rfid_scan(req.uid, req.event_id, observed_at),
            {"source": "HTTP", "event_id": req.event_id, "run_id": req.run_id})[0]
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return RfidScanResponse(
        accepted=True if evt_type != RfidEventType.DUPLICATE_SUPPRESSED.value else False,
        active_classroom_id=class_id,
        classroom_name=class_name,
        service_id=service_id,
        event_type=evt_type
    )

@router.post("/api/v1/simulation/capacity", response_model=CapacityChangeResponse)
async def change_capacity(request: Request, req: CapacityChangeRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    site.command("campus.capacity", lambda: grid.set_capacity(req.capacity_w), {"capacity_w": req.capacity_w})
    return CapacityChangeResponse(
        accepted=True,
        new_capacity_w=req.capacity_w,
        control_revision=grid.control_revision
    )

@router.post("/api/v1/simulation/classroom-load", response_model=ClassroomLoadResponse)
async def change_classroom_load(request: Request, req: ClassroomLoadRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    if req.classroom_id not in CLASSROOM_IDS:
        raise HTTPException(422, CLASSROOM_ID_ERROR)
    observed_at = session_event_time(req.observed_at)
    check_session_run(req.run_id, site, req.event_id, req.observed_at)
    try:
        site.command("campus.classroom_load",
                     lambda: grid.set_classroom_load(req.classroom_id, req.active, "UI", req.event_id, observed_at),
                     {"classroom_id": req.classroom_id, "active": req.active,
                      "event_id": req.event_id, "run_id": req.run_id})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return ClassroomLoadResponse(
        accepted=True,
        classroom_id=req.classroom_id,
        load_event_active=req.active
    )

@router.post("/api/v1/simulation/feeder", response_model=FeederChangeResponse)
async def change_feeder(request: Request, req: FeederChangeRequest):
    grid = request.app.state.grid
    site = request.app.state.site
    if req.feeder not in ("A", "B"):
        raise HTTPException(422, "feeder must be A or B")
    site.command("campus.feeder", lambda: grid.set_feeder(req.feeder, req.available),
                 {"feeder": req.feeder, "available": req.available})
    return FeederChangeResponse(
        accepted=True,
        feeder=req.feeder,
        available=req.available,
        control_revision=grid.control_revision
    )

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    site = websocket.app.state.site
    manager = websocket.app.state.manager
    await manager.connect(websocket)
    snapshot = campus_snapshot(site, websocket.app)
    if snapshot is not None:
        await websocket.send_text(socket_payload(snapshot, site))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def _site_scenarios(site):
    scenarios = [{"name": name, **settings} for name, settings in SCENARIOS.items()]
    return {"active": site.scenario, "scenarios": scenarios, "site": site.identity()}


@router.get("/api/v1/site/scenarios", response_model=SiteScenariosResponse)
async def read_site_scenarios(request: Request):
    site = request.app.state.site
    return site.read(lambda: _site_scenarios(site))[0]


@router.post("/api/v1/site/scenario", response_model=SiteScenarioResponse)
async def switch_site_scenario(request: Request, req: SiteScenarioRequest):
    """Switch the whole site to a named scenario: one command, one revision on every route (#33)."""
    site = request.app.state.site
    if req.scenario not in SCENARIOS:
        raise HTTPException(422, f"unknown scenario {req.scenario!r}; choose one of {sorted(SCENARIOS)}")
    receipt = site.apply_scenario(req.scenario)
    return {**site.read(lambda: _site_scenarios(site))[0], "command": receipt}


@router.post("/api/v1/site/new-run", response_model=SiteIdentityResponse)
async def create_new_run(request: Request):
    """Start a completely new identity generation run."""
    site = request.app.state.site
    site.new_run()
    return site.identity()


@router.get("/api/v1/allocation/policy", response_model=AllocationPolicyResponse)
async def read_allocation_policy(request: Request):
    grid = request.app.state.grid
    site = request.app.state.site
    return site.read(lambda: grid.policy.model_dump())[0]

@router.put("/api/v1/allocation/policy", response_model=AllocationPolicyUpdateResponse)
async def change_allocation_policy(request: Request, policy: AllocationPolicy):
    grid = request.app.state.grid
    site = request.app.state.site
    def apply():
        with grid._lock:
            grid.policy = policy
            grid.control_revision += 1
            grid.add_event("POLICY_CHANGE", policy.model_dump_json())
    _, receipt = site.command("allocation_policy", apply, policy.model_dump())
    return {"policy": policy.model_dump(), "receipt": receipt}

@router.post("/api/v1/studies/electrical", response_model=ElectricalStudyResponse)
async def electrical_study(request: Request, inputs: ElectricalInput):
    site = request.app.state.site
    electrical_study_lock = request.app.state.electrical_study_lock
    if electrical_study_lock.locked():
        raise HTTPException(503, "Electrical study busy; retry later")
    await electrical_study_lock.acquire()
    identity = site.identity()
    async def work():
        try:
            return await asyncio.to_thread(solve_electrical, inputs)
        finally:
            electrical_study_lock.release()
    task = asyncio.create_task(work())
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=ELECTRICAL_TIMEOUT_S)
    except TimeoutError:
        raise HTTPException(504, "Electrical study timed out; no control or restoration applied")
    if site.identity() != identity:
        raise HTTPException(409, "Site run/revision changed during study; discard and retry")
    return {"site": identity, "result": result.model_dump(), "diagnosis": diagnose_study(result)}

def with_contract(data, site):
    data = with_site(data, site.identity())
    data["contract"] = {"identity": {**site.grid.identity(), "run_id": site.run_id,
        "state_revision": site.revision}, "zone_totals": {}}
    return data


def visualizer_snapshot(site, demo):
    with site._lock:
        return with_contract(demo.snapshot(), site)


@router.post("/api/v1/hardware/ack", response_model=HardwareAckResponse)
async def hardware_ack(request: Request, req: HardwareAckRequest):
    try:
        request.app.state.site.command("hardware_ack", lambda: request.app.state.grid.record_ack(
            req.device_boot, req.sequence, req.session, req.confirmed_mask, req.provenance),
            {"device_boot": req.device_boot, "sequence": req.sequence, "session": req.session,
             "confirmed_mask": req.confirmed_mask, "provenance": req.provenance})
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"accepted": True}


def create_app():
    application = FastAPI(title="PriorityGrid API", version="1.0.0", lifespan=lifespan)
    application.add_exception_handler(AuditUnavailable, audit_unavailable_handler)
    application.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    application.include_router(router)
    application.include_router(register_history(lambda request: request.app.state.site))
    application.include_router(register_demo(campus_snapshot, hardware_status))
    application.include_router(register_power_system(hardware_status))
    from app.api.district import register_district
    application.include_router(register_district())
    return application


app = create_app()
