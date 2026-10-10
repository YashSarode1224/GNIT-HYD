import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.state import GridState
from app.core.restoration import RestorationGate
import time

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    """Reset the singleton GridState before each test."""
    grid = GridState()
    with grid._lock:
        grid.source_capacity_w = 14000
        grid.feeder_limits_w = {"A": 6000, "B": 8000}
        grid.feeder_available = {"A": True, "B": True}
        grid.control_revision = 0
        grid.active_classroom_id = None
        grid.recent_rfid_scan = None
        grid.last_rfid_scan_time = None
        grid.last_rfid_uid = None
        grid.classroom_load_events = {"CR1": False, "CR2": False, "CR3": False}
        grid.indicator_confirmed_mask = None
        grid.software_mode = False
        grid.replay_running = False
        grid.replay_index = 0
        grid.activity_tokens = {"CR1": 0, "CR2": 0, "CR3": 0}
        grid.activity_received_monotonic = {"CR1": None, "CR2": None, "CR3": None}
        grid.last_allocation_mask = 0
        grid.last_allocation_key = None
        grid.proposed_mask = 0
        grid.restoration_gate = RestorationGate(time.monotonic)
        grid.restoration_gate.update(0b111111, (14000, (("A", 6000), ("B", 8000)), (("A", True), ("B", True))), range(6))
    yield

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_snapshot_backward_compatibility():
    response = client.get("/api/v1/snapshot")
    assert response.status_code == 200
    data = response.json()
    
    # Must have the original fields
    assert "services" in data
    assert "requested_mask" in data
    assert "modeled_mask" in data
    assert "indicator_command_mask" in data
    assert "hardware_link" in data

    services = data["services"]
    assert len(services) == 6
    ids = [s["id"] for s in services]
    assert ids == ["L0", "L1", "L2", "L3", "L4", "L5"]
    
    # Check L0 details (T1, 2000W, Feeder A)
    l0 = next(s for s in services if s["id"] == "L0")
    assert l0["tier"] == "T1"
    assert l0["watts"] == 2000
    assert l0["feeder"] == "A"

def test_hospital_rooms_follow_l0():
    response = client.get("/api/v1/snapshot")
    data = response.json()
    
    # Hospital should have 3 rooms
    rooms = data["zones"]["hospital"]["rooms"]
    assert len(rooms) == 3
    assert all(r["lighting_service"] == "L0" for r in rooms)
    
    # At 14000W capacity, L0 should be served (mask bits 0,1,2 = ON)
    cmd_mask = data["indicator_command_mask"]
    assert (cmd_mask & 0b111) == 0b111  # bits 0, 1, 2 are 1

def test_rfid_registered_card_selection():
    # Scan Card 1 (CR1)
    response = client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    assert response.status_code == 200
    assert response.json()["active_classroom_ids"] == ["CR1"]
    assert response.json()["event_type"] == "CARD_RECOGNIZED"
    
    # Check snapshot
    snap = client.get("/api/v1/snapshot").json()
    assert snap["zones"]["classroom"]["active_classroom_ids"] == ["CR1"]

def test_rfid_unknown_card_clears_selection():
    client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    
    # Scan unknown card
    response = client.post("/api/v1/rfid/scan", json={"uid": "UNKNOWN_CARD_UID"})
    assert response.status_code == 200
    assert response.json()["active_classroom_ids"] == []
    assert response.json()["event_type"] == "UNKNOWN_CARD"
    
    snap = client.get("/api/v1/snapshot").json()
    assert snap["zones"]["classroom"]["active_classroom_ids"] == []

def test_duplicate_scan_suppressed():
    r1 = client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    assert r1.json()["accepted"] is True
    
    r2 = client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    assert r2.json()["accepted"] is False
    assert r2.json()["event_type"] == "DUPLICATE_SUPPRESSED"

def test_classroom_led_isolation():
    # 1. Scan Card 1 (CR1)
    client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    
    # A card scan alone does NOT turn on the LED (load event is false)
    snap = client.get("/api/v1/snapshot").json()
    cmd_mask = snap["indicator_command_mask"]
    # Classroom bits (3,4,5) should be 0
    assert (cmd_mask & 0b111000) == 0
    
    # 2. Activate load for CR1
    client.post("/api/v1/simulation/classroom-load", json={"classroom_id": "CR1", "active": True})
    
    snap = client.get("/api/v1/snapshot").json()
    cmd_mask = snap["indicator_command_mask"]
    # Only CR1 LED (bit 3) should be ON among classrooms
    assert (cmd_mask & 0b111000) == 0b001000  # bit 3 is 1, bits 4,5 are 0
    
    # 3. Scan Card 2 (CR2) -> Switches selection. CR1 LED must turn OFF, CR2 LED evaluated
    client.post("/api/v1/rfid/scan", json={"uid": "CARD_2_UID"})
    snap = client.get("/api/v1/snapshot").json()
    cmd_mask = snap["indicator_command_mask"]
    # CR1 LED is now OFF because it's no longer the active classroom. 
    # CR2 LED is OFF because its load event is false.
    assert (cmd_mask & 0b111000) == 0

def test_classroom_led_shed_condition():
    # CR1 selected and load active
    client.post("/api/v1/rfid/scan", json={"uid": "CARD_1_UID"})
    client.post("/api/v1/simulation/classroom-load", json={"classroom_id": "CR1", "active": True})
    
    snap = client.get("/api/v1/snapshot").json()
    assert (snap["indicator_command_mask"] & 0b111000) == 0b001000 # LED 3 ON
    
    # Feeder B goes down -> L3 (CR1) shed -> LED must turn OFF
    client.post("/api/v1/simulation/feeder", json={"feeder": "B", "available": False})
    
    snap = client.get("/api/v1/snapshot").json()
    # L3 is shed
    l3 = next(s for s in snap["services"] if s["id"] == "L3")
    assert l3["modeled_served"] is False
    # LED 3 is OFF
    assert (snap["indicator_command_mask"] & 0b111000) == 0

def test_priority_allocation_constraints():
    # Drop capacity to 6000W
    client.post("/api/v1/simulation/capacity", json={"capacity_w": 6000})
    snap = client.get("/api/v1/snapshot").json()
    
    services = {s["id"]: s for s in snap["services"]}
    
    # Total served must not exceed 6000
    total_served = sum(s["watts"] for s in snap["services"] if s["modeled_served"])
    assert total_served <= 6000
    
    # Priority check: T1s (L0, L1) must be served over T3 (L5)
    assert services["L0"]["modeled_served"] is True
    assert services["L1"]["modeled_served"] is True
    
    # Since L0 (2000) + L1 (1000) = 3000, 3000 remains.
    # Next is T2: L2 (3000), L3 (2000), L4 (2000). 
    # The greedy allocator (sorted by watts asc within tier) will pick L3 (2000).
    # Then 1000 remains. Neither L2 (3000) nor L4 (2000) fit.
    # L5 (4000) T3 definitely doesn't fit.
    # Total served: L0(2000) + L1(1000) + L3(2000) = 5000 <= 6000.
    
    assert services["L5"]["modeled_served"] is False

def test_hardware_confirmation_truth():
    snap = client.get("/api/v1/snapshot").json()
    # Indicator confirmed mask should be None (never fabricate a confirmation)
    assert snap["indicator_confirmed_mask"] is None
