import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.state import GridState

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    grid = GridState()
    with grid._lock:
        grid.source_capacity_w = 14000
        grid.feeder_limits_w = {"A": 6000, "B": 8000}
        grid.feeder_available = {"A": True, "B": True}
        grid.control_revision = 0
        grid.fault_diagnosis = None
        grid.active_classroom_ids = set()
        grid.proposed_mask = 0

def test_feeder_a_kill():
    # Kill Feeder A
    response = client.post("/api/v1/simulation/feeder", json={"feeder": "A", "available": False})
    assert response.status_code == 200
    
    snap = client.get("/api/v1/snapshot").json()
    assert snap["fault_diagnosis"]["has_fault"] is True
    assert "Feeder A disconnected" in snap["fault_diagnosis"]["diagnosis"]
    
    # Check that appliances on Feeder A are shed
    l0_appliances = [a for a in snap["appliances"] if a["room"] in ("ICU", "Theatre", "Wards")]
    for app in l0_appliances:
        assert app["modeled_served"] is False
        assert "Feeder A unavailable" in app["model_reason"]

def test_capacity_drop():
    # Drop capacity to 1000W
    response = client.post("/api/v1/simulation/capacity", json={"capacity_w": 1000})
    assert response.status_code == 200
    
    snap = client.get("/api/v1/snapshot").json()
    assert snap["fault_diagnosis"]["has_fault"] is True
    assert "capacity reduced" in snap["fault_diagnosis"]["diagnosis"].lower()
    
    # Check that shedding occurred
    l0_appliances = [a for a in snap["appliances"] if a["room"] in ("ICU", "Theatre", "Wards")]
    served = [a for a in l0_appliances if a["modeled_served"]]
    shed = [a for a in l0_appliances if not a["modeled_served"]]
    
    # L0 is 2000W, so if capacity is 1000W, it must be shed!
    assert len(served) == 0
    assert len(shed) > 0
