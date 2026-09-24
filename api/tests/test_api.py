from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

UTC = timezone.utc


@pytest.fixture
def client(tmp_path, monkeypatch):
    import _bootstrap
    monkeypatch.setattr(_bootstrap, "DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setattr(_bootstrap, "EVENT_LOG_PATH", str(tmp_path / "e.jsonl"))
    monkeypatch.setattr(_bootstrap, "STATE_LOG_PATH", str(tmp_path / "s.jsonl"))
    import main
    with TestClient(main.app) as c:
        yield c


def _slot(hours_ahead=2):
    start = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(hours=hours_ahead)
    return start, start + timedelta(minutes=30)


def test_members_and_machines(client):
    members = client.get("/api/members").json()
    assert {m["id"] for m in members} >= {"m-ada", "m-cy"}
    machines = client.get("/api/machines").json()
    assert [m["id"] for m in machines] == ["treadmill-1", "treadmill-2"]


def test_slots_grid_shape(client):
    rows = client.get("/api/slots", params={"member_id": "m-ada"}).json()
    assert rows and all(len(r["cells"]) == 2 for r in rows)
    assert all(c["state"] in {"open", "booked", "mine", "past"}
               for r in rows for c in r["cells"])


def test_create_then_cancel_booking(client):
    start, end = _slot()
    r = client.post("/api/bookings", json={
        "machine_id": "treadmill-1", "member_id": "m-ada",
        "start": start.isoformat(), "end": end.isoformat(),
    })
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["member_name"] == "Ada Reyes"

    # shows up in the grid as "mine"
    rows = client.get("/api/slots", params={"member_id": "m-ada"}).json()
    states = [c["state"] for row in rows for c in row["cells"]]
    assert "mine" in states

    d = client.delete(f"/api/bookings/{booking['id']}")
    assert d.status_code == 200
    assert d.json()["status"] == "cancelled"


def test_create_booking_rejects_basic_member(client):
    start, end = _slot()
    r = client.post("/api/bookings", json={
        "machine_id": "treadmill-1", "member_id": "m-cy",
        "start": start.isoformat(), "end": end.isoformat(),
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "member_not_premium"


def test_create_booking_rejects_overlap(client):
    start, end = _slot()
    body = {"machine_id": "treadmill-1", "member_id": "m-ada",
            "start": start.isoformat(), "end": end.isoformat()}
    assert client.post("/api/bookings", json=body).status_code == 201
    body["member_id"] = "m-bo"
    r = client.post("/api/bookings", json=body)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "slot_unavailable"


def test_suggest_returns_a_reserved_machine(client):
    r = client.post("/api/bookings/suggest",
                    json={"member_id": "m-ada", "duration_minutes": 30})
    assert r.status_code == 200
    assert r.json()["machine_id"] in {"treadmill-1", "treadmill-2"}


def test_floor_reflects_simulated_camera(client):
    floor = client.get("/api/floor").json()
    assert len(floor["machines"]) == 2
    assert all(m["verdict"] == "no_camera" for m in floor["machines"])

    client.post("/api/sim/occupancy", json={"machine_id": "treadmill-1", "occupied": True})
    floor = client.get("/api/floor").json()
    t1 = next(m for m in floor["machines"] if m["machine_id"] == "treadmill-1")
    assert t1["camera"]["occupied"] is True
    assert t1["verdict"] == "unbooked_use"


def test_nudge_fires_and_lands_in_activity(client):
    # booking starts inside the default 3-minute nudge window
    start = datetime.now(UTC) + timedelta(minutes=2)
    client.post("/api/bookings", json={
        "machine_id": "treadmill-1", "member_id": "m-ada",
        "start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat(),
    })
    client.post("/api/sim/occupancy", json={"machine_id": "treadmill-1", "occupied": True})

    floor = client.get("/api/floor").json()
    t1 = next(m for m in floor["machines"] if m["machine_id"] == "treadmill-1")
    assert t1["verdict"] == "nudge"

    types = [e["type"] for e in client.get("/api/activity").json()]
    assert "nudge_fired" in types
    assert "booking_created" in types
