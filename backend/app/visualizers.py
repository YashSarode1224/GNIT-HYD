"""Independent synthetic classroom and hospital demos."""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.restoration import RestorationGate

ROOMS = ("CR1", "CR2", "CR3")
LOADS = {
    "CR1": [("lighting", "Lighting", 100, True), ("computers", "Computers", 600, True), ("fans", "Fans", 100, False), ("projector", "Projector", 200, False), ("ac", "Air conditioning", 1000, False)],
    "CR2": [("lighting", "Lighting", 100, True), ("computers", "Computers", 600, True), ("fans", "Fans", 100, False), ("projector", "Projector", 200, False), ("ac", "Air conditioning", 1000, False)],
    "CR3": [("lighting", "Lighting", 100, True), ("computers", "Computers", 600, True), ("fans", "Fans", 100, False), ("projector", "Projector", 200, False), ("ac", "Air conditioning", 1000, False), ("instruments", "Instruments", 2000, False)],
}
LOAD_KEYS = tuple((room, item[0]) for room in ROOMS for item in LOADS[room])
ZONES = ("ICU", "Theatre", "Wards")


NORMAL_CAPACITY_W = 8000
OVERLOAD_CAPACITY_W = 3400
CAPACITY_RANGE_W = (0, 8000)
REPLAY_STEP_S = 5.0
ACTIVITY_RANK = {"ACTIVE": 0, "UNKNOWN": 1, "INACTIVE": 2}
REPLAY_PATH = Path(__file__).resolve().parents[1] / "models" / "replay.json"


def load_replay(path=REPLAY_PATH):
    try:
        data = json.loads(Path(path).read_text())
        return {cid: rows for cid, rows in data.items() if cid in ROOMS and isinstance(rows, list) and rows}
    except (OSError, ValueError):
        return {}


class ClassroomDemo:
    """Several rooms may be scanned at once. The activity model ranks scanned rooms from
    recorded sensor observations; the rank orders optional loads only, never essentials."""

    def __init__(self, clock=time.monotonic, model=None, replay=None):
        if model is None:
            from app.activity.model import ActivityModel
            model = ActivityModel()
        self.model = model
        self.replay = load_replay() if replay is None else replay
        self.replay_length = min((len(rows) for rows in self.replay.values()), default=0)
        self.capacity = NORMAL_CAPACITY_W
        self.scanned: list[str] = []   # scan order; the last entry is the most recent card
        self.gate = RestorationGate(clock)
        self.replay_running = self.replay_length > 0
        self.replay_base = 0
        self.replay_anchor = clock()
        self._predictions: dict[tuple[str, int], dict] = {}
        initial = (1 << len(LOAD_KEYS)) - 1
        self.gate.update(initial, self._signature(self._room_order()), range(len(LOAD_KEYS)))

    # ---- recorded sensor replay and model evidence ----
    def replay_index(self):
        if not self.replay_length:
            return 0
        steps = int((self.gate.clock() - self.replay_anchor) // REPLAY_STEP_S) if self.replay_running else 0
        return (self.replay_base + steps) % self.replay_length

    def activity(self, cid):
        if not self.replay_length or cid not in self.replay:
            return {"state": "UNKNOWN", "score": None, "reason": "no recorded sensor evidence",
                    "model_version": "unavailable", "evidence": {}}
        index = self.replay_index()
        cached = self._predictions.get((cid, index))
        if cached is None:
            row = self.replay[cid][index]
            evidence = {key: row.get(key) for key in ("temperature_c", "humidity_pct", "co2_ppm", "humidity_ratio")}
            try:
                prediction = self.model.predict(evidence)
            except Exception as exc:
                prediction = {"state": "UNKNOWN", "score": None, "model_version": "unavailable",
                              "reason": f"inference failed: {type(exc).__name__}"}
            cached = {**prediction, "evidence": evidence}
            self._predictions[(cid, index)] = cached
        return cached

    # ---- allocation ----
    def _room_order(self):
        """Scanned rooms ranked by model state, then scan order; unscanned rooms after.
        Raw scores are not compared: small score noise would reorder rooms on every reading."""
        def key(cid):
            return (ACTIVITY_RANK.get(self.activity(cid).get("state"), 1), self.scanned.index(cid))
        return sorted(self.scanned, key=key) + [r for r in ROOMS if r not in self.scanned]

    def _signature(self, order):
        return (self.capacity, tuple(r for r in order if r in self.scanned))

    def _priority(self, order):
        # Essentials in every room first, then scanned rooms' optional loads in model rank, then the rest.
        result = [(r, item) for r in order for item in LOADS[r] if item[3]]
        result += [(r, item) for r in order for item in LOADS[r] if not item[3] and r in self.scanned]
        result += [(r, item) for r in ROOMS for item in LOADS[r] if not item[3] and r not in self.scanned]
        return result

    def snapshot(self):
        order = self._room_order()
        priority = self._priority(order)
        target: set[tuple[str, str]] = set()
        remaining = self.capacity
        for room, item in priority:
            key = (room, item[0])
            if item[2] <= remaining:
                target.add(key)
                remaining -= item[2]
        proposed = sum(1 << LOAD_KEYS.index(key) for key in target)
        bit_order = [LOAD_KEYS.index((room, item[0])) for room, item in priority]
        applied = self.gate.update(proposed, self._signature(order), bit_order)
        current = {key for bit, key in enumerate(LOAD_KEYS) if applied & (1 << bit)}
        rooms = []
        for cid in ROOMS:
            loads = []
            for lid, name, watts, essential in LOADS[cid]:
                key = (cid, lid)
                on = key in current
                reason = ("served by classroom demo" if on else
                          "Waiting for simulated restoration delay" if key in target else
                          "Insufficient capacity for essential load" if essential else
                          "Shed by classroom demo policy")
                loads.append({"id": lid, "name": name, "watts": watts, "essential": essential,
                              "served": on, "reason": reason})
            act = self.activity(cid)
            rooms.append({"id": cid, "name": f"Classroom {cid[-1]}", "rfid_active": cid in self.scanned,
                          "priority_rank": order.index(cid) + 1 if cid in self.scanned else None,
                          "activity": {key: act.get(key) for key in ("state", "score", "reason", "model_version", "evidence")},
                          "loads": loads})
        requested = sum(x[2] for rows in LOADS.values() for x in rows)
        served_w = sum(x[2] for r in ROOMS for x in LOADS[r] if (r, x[0]) in current)
        status = self.model.status() if hasattr(self.model, "status") else {}
        return {"capacity_w": self.capacity, "capacity_range_w": list(CAPACITY_RANGE_W),
                "requested_w": requested, "served_w": served_w, "shortfall_w": requested - served_w,
                "selected_classroom_id": self.scanned[-1] if self.scanned else None,
                "scanned_classroom_ids": [r for r in ROOMS if r in self.scanned],
                "priority_order": [r for r in order if r in self.scanned],
                "rooms": rooms, "mode": "SIMULATED",
                "model": {"ready": bool(status.get("ready")), "model_version": status.get("model_version", "unavailable"),
                          "fallback_reason": status.get("fallback_reason")},
                "replay": {"running": self.replay_running, "index": self.replay_index(),
                           "length": self.replay_length, "step_s": REPLAY_STEP_S},
                "policy": "Classroom-only: lighting and computers in every room first. Scanned rooms' other "
                          "equipment next, ranked by the activity model (ACTIVE, then UNKNOWN, then INACTIVE; "
                          "earlier scan first within a state). Unscanned rooms' optional loads last."}

    def act(self, action: str, classroom_id: str | None = None, capacity_w: int | None = None):
        if action == "scan":
            if classroom_id not in self.scanned:
                self.scanned.append(classroom_id)
        elif action == "unscan":
            if classroom_id in self.scanned:
                self.scanned.remove(classroom_id)
        elif action == "set_capacity":
            self.capacity = capacity_w
        elif action == "normal":
            self.capacity = NORMAL_CAPACITY_W
        elif action == "overload":
            self.capacity = OVERLOAD_CAPACITY_W
        elif action == "replay_pause":
            self.replay_base, self.replay_running = self.replay_index(), False
        elif action == "replay_resume":
            if self.replay_length:
                self.replay_base, self.replay_anchor, self.replay_running = self.replay_index(), self.gate.clock(), True
        elif action == "replay_step":
            if self.replay_length:
                self.replay_base, self.replay_anchor = (self.replay_index() + 1) % self.replay_length, self.gate.clock()
        elif action == "reset":
            self.__init__(self.gate.clock, self.model, self.replay)
        return self.snapshot()


def diagnose(rated_current_a, current_a, temperature_c, input_voltage_v, output_voltage_v, cooling_ok):
    """Classify only provided synthetic sensor observations and configured rating."""
    missing = [name for name, value in (("current", current_a), ("temperature", temperature_c),
               ("input voltage", input_voltage_v), ("output voltage", output_voltage_v), ("cooling", cooling_ok)) if value is None]
    evidence = []
    if current_a is not None:
        evidence.append(f"Current {current_a:.1f} A; overload threshold {rated_current_a * 1.1:.1f} A (110% of rating).")
    if temperature_c is not None:
        evidence.append(f"Temperature {temperature_c:.1f} °C; hot threshold 80 °C.")
    if cooling_ok is not None:
        evidence.append(f"Cooling {'operational' if cooling_ok else 'failed'}.")
    if input_voltage_v is not None and output_voltage_v is not None:
        evidence.append(f"Input {input_voltage_v:.1f} V; output {output_voltage_v:.1f} V; low-input threshold 180 V.")
    if missing:
        return {"code": "UNKNOWN", "cause": "Insufficient sensor evidence", "severity": "unknown", "evidence": evidence + ["Missing: " + ", ".join(missing)], "recommendation": "Restore sensor telemetry before diagnosing."}
    if input_voltage_v < 180 and output_voltage_v < 100:
        return {"code": "UPSTREAM_LOSS", "cause": "Possible upstream supply loss", "severity": "critical", "evidence": evidence, "recommendation": "Check the upstream supply and incoming connections."}
    if current_a > rated_current_a * 1.1:
        return {"code": "OVERLOAD", "cause": "Current exceeds the configured rating threshold", "severity": "high", "evidence": evidence, "recommendation": "Review connected demand and verify with qualified protection equipment."}
    if temperature_c >= 80 and not cooling_ok:
        return {"code": "COOLING_FAILURE", "cause": "Elevated temperature with cooling reported failed", "severity": "high", "evidence": evidence, "recommendation": "Inspect cooling equipment and temperature using approved procedures."}
    if temperature_c >= 80:
        return {"code": "HIGH_TEMPERATURE", "cause": "Elevated transformer temperature", "severity": "medium", "evidence": evidence, "recommendation": "Check loading, ventilation and sensor readings."}
    return {"code": "NORMAL", "cause": "No configured demo threshold exceeded", "severity": "normal", "evidence": evidence, "recommendation": "Continue monitoring."}


NORMAL_SENSORS = (45.0, 58.0, 230.0, 220.0, True)
HOSPITAL_FAULT_FIXTURES = {
    "overload": (130.0, 72.0, 230.0, 218.0, True),
    "cooling_failure": (45.0, 91.0, 230.0, 220.0, False),
    "missing_sensor": (None, 55.0, 230.0, 220.0, True),
}



HOSP_ZONES = ("ICU", "Theatre", "Wards")
HOSP_LOADS = {
    "ICU": [("ventilator", "Ventilator", 300, True), ("monitor", "Patient Monitor", 100, True), ("infusion", "Infusion Pump", 50, True), ("lights", "Emergency Lights", 50, True), ("oxygen", "O2 System", 500, True)],
    "Theatre": [("surgical_light", "Surgical Light", 500, True), ("anesthesia", "Anesthesia Unit", 200, True), ("esu", "Electrosurgical", 800, True), ("monitor", "Vital Monitor", 100, True), ("ac", "Climate Control", 1400, False)],
    "Wards": [("bed_lights", "Bed Lights", 200, False), ("nurse_call", "Nurse Call", 100, True), ("fans", "Ceiling Fans", 500, False), ("tv", "Patient TV", 200, False), ("ac", "Air Conditioning", 2000, False)],
}
HOSP_LOAD_KEYS = tuple((zone, item[0]) for zone in HOSP_ZONES for item in HOSP_LOADS[zone])

class HospitalPriorityDemo(ClassroomDemo):
    def __init__(self, clock=None, model=None, replay=None):
        import time
        super().__init__(clock or time.monotonic, model, replay)
        self.capacity = 7000
        initial = (1 << len(HOSP_LOAD_KEYS)) - 1
        self.gate.update(initial, self._signature(self._room_order()), range(len(HOSP_LOAD_KEYS)))

    def _room_order(self):
        act = {z: self.activity(z) for z in HOSP_ZONES}
        def sort_key(z):
            state = act[z].get("state")
            state_rank = 0 if state == "ACTIVE" else 1 if state == "UNKNOWN" else 2
            scan_rank = self.scanned.index(z) if z in self.scanned else 999
            return (state_rank, scan_rank, HOSP_ZONES.index(z))
        return sorted(HOSP_ZONES, key=sort_key)

    def _priority(self, order):
        essentials = [(z, item) for z in order for item in HOSP_LOADS[z] if item[3]]
        optionals = [(z, item) for z in order for item in HOSP_LOADS[z] if not item[3]]
        return essentials + optionals

    def snapshot(self):
        order = self._room_order()
        priority = self._priority(order)
        target = set()
        remaining = self.capacity
        for z, item in priority:
            key = (z, item[0])
            if item[2] <= remaining:
                target.add(key)
                remaining -= item[2]
        proposed = sum(1 << HOSP_LOAD_KEYS.index(key) for key in target)
        bit_order = [HOSP_LOAD_KEYS.index((z, item[0])) for z, item in priority]
        applied = self.gate.update(proposed, self._signature(order), bit_order)
        current = {key for bit, key in enumerate(HOSP_LOAD_KEYS) if applied & (1 << bit)}
        
        transformers = []
        for i, z in enumerate(HOSP_ZONES):
            loads = []
            for lid, name, watts, essential in HOSP_LOADS[z]:
                key = (z, lid)
                on = key in current
                reason = ("served" if on else "waiting" if key in target else "shed")
                loads.append({"id": lid, "name": name, "watts": watts, "essential": essential, "served": on, "reason": reason})
            act = self.activity(z)
            transformers.append({
                "id": f"TX{i+1}", "name": f"Transformer {i+1}", "zone": z,
                "rated_current_a": 100.0, "sensors": {"cooling_ok": True},
                "diagnosis": {"code": "NORMAL", "severity": "normal"},
                "energized": any(l["served"] for l in loads),
                "rfid_active": z in self.scanned,
                "priority_rank": order.index(z) + 1 if z in self.scanned else None,
                "activity": {key: act.get(key) for key in ("state", "score", "reason", "model_version", "evidence")},
                "loads": loads
            })
            
        requested = sum(x[2] for rows in HOSP_LOADS.values() for x in rows)
        served_w = sum(x[2] for z in HOSP_ZONES for x in HOSP_LOADS[z] if (z, x[0]) in current)
        status = self.model.status() if hasattr(self.model, "status") else {}
        return {
            "capacity_w": self.capacity, "capacity_range_w": [0, 7000],
            "requested_w": requested, "served_w": served_w, "shortfall_w": requested - served_w,
            "selected_zone_id": self.scanned[-1] if self.scanned else None,
            "scanned_zone_ids": [z for z in HOSP_ZONES if z in self.scanned],
            "priority_order": [z for z in order if z in self.scanned],
            "transformers": transformers, "mode": "SIMULATED",
            "model": {"ready": bool(status.get("ready")), "model_version": status.get("model_version", "unavailable"), "fallback_reason": status.get("fallback_reason")},
            "replay": {"running": self.replay_running, "index": self.replay_index(), "length": self.replay_length, "step_s": 5.0},
            "policy": "Hospital: Essential life-saving equipment always prioritized. Scanned wards' optional equipment next."
        }
        
    def act(self, action: str, zone_id: str | None = None, capacity_w: int | None = None):
        if action == "scan":
            if zone_id not in self.scanned:
                self.scanned.append(zone_id)
        elif action == "unscan":
            if zone_id in self.scanned:
                self.scanned.remove(zone_id)
        elif action == "set_capacity":
            self.capacity = capacity_w
        elif action == "normal":
            self.capacity = 7000
        elif action == "overload":
            self.capacity = 3000
        elif action == "reset":
            self.__init__(self.gate.clock, self.model, self.replay)
        return self.snapshot()


def hospital_snapshot(scenario="normal", zone="Theatre"):
    target_i = 2
    if zone == "ICU":
        target_i = 1
    elif zone == "Wards":
        target_i = 3

    transformers = []
    for i in range(1, 4):
        fixture = ((0.0, 40.0, 90.0, 20.0, True) if scenario == "upstream_loss"
                   else HOSPITAL_FAULT_FIXTURES.get(scenario, NORMAL_SENSORS) if i == target_i
                   else NORMAL_SENSORS)
        current, temp, vin, vout, cooling = fixture
        sensors = {"current_a": current, "temperature_c": temp, "input_voltage_v": vin,
                   "output_voltage_v": vout, "cooling_ok": cooling}
        diagnosis = diagnose(100.0, **sensors)
        zname = ZONES[i - 1]
        energized = vout is not None and vout >= 100.0
        
        loads = []
        for eq_id, essential in HOSPITAL_LOADS[zname]:
            # Default to energized status
            served = energized
            # If we are in overload, non-scanned zones shed their non-essential loads
            if scenario == "overload" and zname != zone and not essential:
                served = False
            loads.append({"id": eq_id, "served": served})
            
        transformers.append({"id": f"TX{i}", "name": f"Transformer {i}", "zone": zname,
                             "rated_current_a": 100.0, "sensors": sensors, "diagnosis": diagnosis,
                             "energized": energized, "loads": loads})
    return {"mode": "SIMULATED", "transformers": transformers,
            "summary": "Synthetic sensor diagnosis for demonstration; thresholds are not certified protection settings."}
