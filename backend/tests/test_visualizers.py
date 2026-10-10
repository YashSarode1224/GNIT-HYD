from fastapi.testclient import TestClient

from app.main import app
from app.visualizers import ClassroomDemo, diagnose, hospital_snapshot


def test_classroom_demo_exact_shortage_and_isolated_reset():
    with TestClient(app) as client:
        normal = client.post("/api/v1/visualizers/classrooms", json={"action": "normal"}).json()
        assert normal["capacity_w"] == 8000
        assert normal["served_w"] == 8000
        scanned = client.post("/api/v1/visualizers/classrooms", json={"action": "scan", "classroom_id": "CR1"}).json()
        assert scanned["capacity_w"] == 8000 and scanned["served_w"] == 8000
        overloaded = client.post("/api/v1/visualizers/classrooms", json={"action": "overload"}).json()
        assert overloaded["capacity_w"] == 3400
        assert overloaded["served_w"] == 3400
        scanned = overloaded
        assert scanned["requested_w"] == 8000
        assert scanned["selected_classroom_id"] == "CR1"
        rooms = {room["id"]: room for room in scanned["rooms"]}
        assert all(load["served"] for load in rooms["CR1"]["loads"])
        assert all(load["served"] for room in ("CR2", "CR3") for load in rooms[room]["loads"] if load["essential"])
        assert all(not load["served"] for room in ("CR2", "CR3") for load in rooms[room]["loads"] if not load["essential"])
        assert client.post("/api/v1/visualizers/classrooms", json={"action": "reset"}).json()["selected_classroom_id"] is None
        # The six-service production snapshot remains independently owned.
        assert client.get("/api/v1/snapshot").status_code == 200


def test_classroom_demo_validation_and_constraints():
    with TestClient(app) as client:
        assert client.post("/api/v1/visualizers/classrooms", json={"action": "scan", "classroom_id": "CR4"}).status_code == 422
        assert client.post("/api/v1/visualizers/classrooms", json={"action": "scan"}).status_code == 422
        assert client.post("/api/v1/visualizers/classrooms", json={"action": "normal", "extra": True}).status_code == 422
        assert client.post("/api/v1/visualizers/classrooms", json={"action": "normal", "classroom_id": "CR1"}).status_code == 422
        client.post("/api/v1/visualizers/classrooms", json={"action": "reset"})
        snapshot = client.post("/api/v1/visualizers/classrooms", json={"action": "overload"}).json()
        assert snapshot["selected_classroom_id"] is None
        assert snapshot["served_w"] <= snapshot["capacity_w"]


def test_hospital_diagnosis_uses_sensor_values_only():
    overload = diagnose(100, 130, 70, 230, 220, True)
    cooling = diagnose(100, 45, 91, 230, 220, False)
    upstream = diagnose(100, 0, 40, 90, 20, True)
    missing = diagnose(100, None, 55, 230, 220, True)
    assert overload["code"] == "OVERLOAD"
    assert cooling["code"] == "COOLING_FAILURE"
    assert upstream["code"] == "UPSTREAM_LOSS"
    assert missing["code"] == "UNKNOWN"



def test_classroom_restoration_uses_time_not_snapshot_count():
    now = [0.0]
    demo = ClassroomDemo(lambda: now[0])
    initial = demo.snapshot()
    assert initial["served_w"] == 8000
    demo.act("scan", "CR1")
    assert demo.snapshot()["served_w"] == 8000
    demo.act("overload", None)
    assert demo.snapshot()["served_w"] == 3400
    demo.act("normal", None)
    for _ in range(100):
        waiting = demo.snapshot()
        assert waiting["served_w"] == 3400
    assert any(load["reason"] == "Waiting for simulated restoration delay"
               for room in waiting["rooms"] for load in room["loads"] if not load["served"])
    now[0] = 2.99
    assert demo.snapshot()["served_w"] == 3400
    now[0] = 5.0
    first = demo.snapshot()["served_w"]
    assert first > 3400
    for _ in range(100):
        assert demo.snapshot()["served_w"] == first
    now[0] = 6.0
    assert demo.snapshot()["served_w"] > first


def test_hospital_faults_are_local_except_upstream_loss():
    for scenario, expected in (("overload", "OVERLOAD"), ("cooling_failure", "COOLING_FAILURE"), ("missing_sensor", "UNKNOWN")):
        transformers = hospital_snapshot(scenario)["transformers"]
        assert [t["diagnosis"]["code"] for t in transformers] == ["NORMAL", expected, "NORMAL"]
    upstream = hospital_snapshot("upstream_loss")["transformers"]
    assert [t["diagnosis"]["code"] for t in upstream] == ["UPSTREAM_LOSS"] * 3
    assert [t["zone"] for t in upstream] == ["ICU", "Theatre", "Wards"]


class StubModel:
    """Maps a CO2 reading straight to a state so ranking tests don't depend on the trained weights."""

    def predict(self, features):
        co2 = features.get("co2_ppm")
        if co2 is None:
            return {"state": "UNKNOWN", "score": None, "reason": "missing", "model_version": "stub"}
        score = min(co2 / 1000, 1.0)
        return {"state": "ACTIVE" if score >= 0.6 else "INACTIVE" if score <= 0.4 else "UNKNOWN",
                "score": score, "reason": "stub", "model_version": "stub"}

    def status(self):
        return {"ready": True, "model_version": "stub"}


def stub_replay(**co2_by_room):
    rows = {"CR1": [500], "CR2": [500], "CR3": [500]}
    rows.update(co2_by_room)
    return {cid: [{"temperature_c": 21.0, "humidity_pct": 30.0, "co2_ppm": co2, "humidity_ratio": 0.004}
                  for co2 in values] for cid, values in rows.items()}


def served_rooms(snapshot):
    """Rooms whose optional (non-essential) loads are all served."""
    return {room["id"] for room in snapshot["rooms"]
            if all(load["served"] for load in room["loads"] if not load["essential"])}


def test_several_rooms_can_be_scanned_and_unscanned():
    demo = ClassroomDemo(lambda: 0.0, StubModel(), stub_replay())
    demo.act("scan", "CR1")
    snap = demo.act("scan", "CR2")
    assert snap["scanned_classroom_ids"] == ["CR1", "CR2"]
    assert {r["id"] for r in snap["rooms"] if r["rfid_active"]} == {"CR1", "CR2"}
    assert snap["selected_classroom_id"] == "CR2"
    snap = demo.act("unscan", "CR1")
    assert snap["scanned_classroom_ids"] == ["CR2"]
    assert demo.act("reset")["scanned_classroom_ids"] == []


def test_model_ranks_scanned_rooms_under_a_tight_supply():
    # Essentials take 2,100 W; the remaining 1,300 W fits exactly one room's optional loads.
    now = [0.0]
    demo = ClassroomDemo(lambda: now[0], StubModel(), stub_replay(CR1=[300], CR2=[900]))
    demo.act("scan", "CR1")
    demo.act("scan", "CR2")
    snap = demo.act("set_capacity", capacity_w=3400)
    assert snap["priority_order"] == ["CR2", "CR1"]  # CR2 ACTIVE outranks CR1 INACTIVE despite scan order
    assert {r["id"]: r["priority_rank"] for r in snap["rooms"]} == {"CR1": 2, "CR2": 1, "CR3": None}
    assert served_rooms(snap) == {"CR2"}
    assert snap["served_w"] <= snap["capacity_w"]


def test_ties_keep_scan_order_and_unknown_sits_between():
    demo = ClassroomDemo(lambda: 0.0, StubModel(), stub_replay(CR1=[500], CR2=[500], CR3=[200]))
    for cid in ("CR3", "CR2", "CR1"):
        demo.act("scan", cid)
    assert demo.snapshot()["priority_order"] == ["CR2", "CR1", "CR3"]


def test_replay_steps_change_the_ranking():
    now = [0.0]
    demo = ClassroomDemo(lambda: now[0], StubModel(), stub_replay(CR1=[900, 300], CR2=[300, 900], CR3=[500, 500]))
    demo.act("scan", "CR1")
    demo.act("scan", "CR2")
    assert demo.snapshot()["priority_order"] == ["CR1", "CR2"]
    demo.act("replay_pause")
    now[0] = 60.0
    assert demo.snapshot()["replay"]["index"] == 0
    assert demo.act("replay_step")["priority_order"] == ["CR2", "CR1"]


def test_capacity_slider_validation():
    with TestClient(app) as client:
        url = "/api/v1/visualizers/classrooms"
        client.post(url, json={"action": "reset"})
        ok = client.post(url, json={"action": "set_capacity", "capacity_w": 5000}).json()
        assert ok["capacity_w"] == 5000 and ok["served_w"] <= 5000
        assert client.post(url, json={"action": "set_capacity"}).status_code == 422
        assert client.post(url, json={"action": "set_capacity", "capacity_w": 9001}).status_code == 422
        assert client.post(url, json={"action": "set_capacity", "capacity_w": -1}).status_code == 422
        assert client.post(url, json={"action": "set_capacity", "capacity_w": True}).status_code == 422
        assert client.post(url, json={"action": "normal", "capacity_w": 5000}).status_code == 422
        assert client.post(url, json={"action": "unscan"}).status_code == 422
        both = [client.post(url, json={"action": "scan", "classroom_id": cid}).json() for cid in ("CR1", "CR2")][-1]
        assert both["scanned_classroom_ids"] == ["CR1", "CR2"]
        assert all(room["activity"]["state"] in ("ACTIVE", "INACTIVE", "UNKNOWN") for room in both["rooms"])
        client.post(url, json={"action": "reset"})


def test_score_noise_within_a_state_does_not_reorder_rooms():
    demo = ClassroomDemo(lambda: 0.0, StubModel(), stub_replay(CR1=[300], CR2=[100]))
    demo.act("scan", "CR2")
    demo.act("scan", "CR1")
    assert demo.snapshot()["priority_order"] == ["CR2", "CR1"]
