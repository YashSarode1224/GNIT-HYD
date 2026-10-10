"""Export API responses used as frontend component-test fixtures (#16).

    PYTHONPATH=backend python backend/scripts/export_frontend_fixtures.py

backend/tests/test_frontend_contract.py fails if the API shape drifts from these fixtures.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "fixtures"
VOLATILE = {"generated_at", "sent_at", "run_id", "last_tick_at", "timestamp", "observed_at", "recorded_at",
            "server_epoch", "event_id", "command_id", "decision_id", "last_restored", "last_shed", "stable_since", "now_s", "observation_time"}


def scrub(value):
    """Replace volatile identity/time fields so fixtures are deterministic."""
    if isinstance(value, dict):
        return {k: ("<volatile>" if k in VOLATILE and v is not None else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def build() -> dict:
    from fastapi.testclient import TestClient

    import app.main as main
    with TestClient(main.app) as client:
        post = lambda path, body: client.post(path, json=body)
        post("/api/v1/visualizers/classrooms", {"action": "reset"})
        post("/api/v1/visualizers/classrooms", {"action": "replay_pause"})
        run_id = client.get("/api/v1/snapshot").json()["site"]["run_id"]
        for classroom_id in ("CR1", "CR2"):
            post("/api/v1/visualizers/classrooms", {"action": "scan", "classroom_id": classroom_id,
                 "run_id": run_id, "event_id": str(uuid.uuid4()),
                 "observed_at": datetime.now(timezone.utc).isoformat()})
        classrooms = post("/api/v1/visualizers/classrooms", {"action": "set_capacity", "capacity_w": 3000}).json()
        post("/api/v1/visualizers/hospital", {"action": "reset"})
        hospital = client.get("/api/v1/visualizers/hospital").json()
        abstained = post("/api/v1/visualizers/hospital", {"rehearsal": "missing_sensor"}).json()
        stuck = post("/api/v1/visualizers/hospital", {"rehearsal": "stuck_sensor"}).json()
        campus = client.get("/api/v1/snapshot").json()
        city = client.get("/api/v1/demo?source=SYNTHETIC_REPLAY").json()
        power_system = client.get("/api/v1/power-system").json()
        post("/api/v1/simulation/feeder", {"feeder": "A", "available": False})
        post("/api/v1/simulation/capacity", {"capacity_w": 6000})
        power_system_fault = client.get("/api/v1/power-system").json()
        post("/api/v1/simulation/feeder", {"feeder": "A", "available": True})
        post("/api/v1/simulation/capacity", {"capacity_w": 14000})
        post("/api/v1/visualizers/classrooms", {"action": "reset"})
    return {name: scrub(data) for name, data in
            {"classrooms": classrooms, "hospital": hospital, "hospital_missing_sensor": abstained, "campus": campus,
             "city": city, "hospital_stuck_sensor": stuck, "power_system": power_system,
             "power_system_fault": power_system_fault}.items()}


def main():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in build().items():
        (FIXTURE_DIR / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", FIXTURE_DIR / f"{name}.json")


if __name__ == "__main__":
    main()
