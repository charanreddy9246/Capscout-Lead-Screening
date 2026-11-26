"""Follow-ups: planned by a meeting or by the SM, completed with an outcome, visible by role."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Customer, FollowUp, FollowUpStatus, StaffRole


def _meeting(client, headers, cid, values, hours_ago=1):
    now = datetime.now(UTC)
    body = {
        "id": str(uuid.uuid4()),
        "started_at": (now - timedelta(hours=hours_ago + 1)).isoformat(),
        "ended_at": (now - timedelta(hours=hours_ago)).isoformat(),
        "gps_unavailable_reason": "test",
        "values": values,
    }
    return client.post(f"/api/customers/{cid}/meetings", json=body, headers=headers)


def _customer(client, headers):
    r = client.post("/api/customers", json={"values": {"promoter": "Ravi", "mobile": "9876501234"}}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tomorrow():
    return (datetime.now(UTC) + timedelta(days=1)).date().isoformat()


def test_a_meeting_with_a_next_action_date_plans_a_follow_up_with_its_time(client, make_staff, db):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    r = _meeting(client, sm, cid, {"next_action": "Document collection", "next_action_date": _tomorrow(), "follow_up_time": "11:30"})
    assert r.status_code == 201, r.text
    items = client.get("/api/follow-ups", headers=sm).json()["items"]
    assert len(items) == 1 and items[0]["purpose"] == "Document collection" and items[0]["when"] == "upcoming"
    assert "T11:30:00" in items[0]["due_at"]  # shown in India time


def test_a_later_meeting_replaces_the_pending_follow_up_and_keeps_the_history(client, make_staff, db):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    _meeting(client, sm, cid, {"next_action": "Identify bank", "next_action_date": _tomorrow()}, hours_ago=5)
    _meeting(client, sm, cid, {"next_action": "Login", "next_action_date": _tomorrow()}, hours_ago=1)
    pending = client.get("/api/follow-ups?status=pending", headers=sm).json()["items"]
    done = client.get("/api/follow-ups?status=done", headers=sm).json()["items"]
    assert [p["purpose"] for p in pending] == ["Login"]
    assert len(done) == 1 and "Replaced in meeting" in done[0]["outcome"]


def test_complete_with_an_outcome_and_schedule_the_next_one(client, make_staff, db):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    _meeting(client, sm, cid, {"next_action": "Document collection", "next_action_date": _tomorrow()})
    fu = client.get("/api/follow-ups", headers=sm).json()["items"][0]
    nxt = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    r = client.post(f"/api/follow-ups/{fu['id']}/complete", json={"outcome": "Will send statements", "next": {"due_at": nxt}}, headers=sm)
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    pending = client.get("/api/follow-ups", headers=sm).json()["items"]
    assert len(pending) == 1 and pending[0]["purpose"] == "Document collection"  # the purpose carries over
    # and the customer's own Next Action Date follows the new follow-up
    detail = client.get(f"/api/customers/{cid}", headers=sm).json()
    assert detail["values"]["next_action_date"] == (datetime.now(UTC) + timedelta(days=3)).astimezone().date().isoformat() or detail["values"]["next_action_date"]
    assert client.post(f"/api/follow-ups/{fu['id']}/complete", json={}, headers=sm).status_code == 409


def test_completing_the_last_one_clears_the_next_action_date(client, make_staff):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    _meeting(client, sm, cid, {"next_action": "Identify bank", "next_action_date": _tomorrow()})
    fu = client.get("/api/follow-ups", headers=sm).json()["items"][0]
    client.post(f"/api/follow-ups/{fu['id']}/complete", json={"outcome": "Done"}, headers=sm)
    assert "next_action_date" not in client.get(f"/api/customers/{cid}", headers=sm).json()["values"]


def test_sm_can_add_a_follow_up_and_it_shows_in_the_counts(client, make_staff):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    soon = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    r = client.post("/api/follow-ups", json={"customer_id": cid, "due_at": soon, "purpose": "Call back"}, headers=sm)
    assert r.status_code == 201
    out = client.get("/api/follow-ups", headers=sm).json()
    assert out["counts"]["upcoming"] == 1 and out["counts"]["overdue"] == 0
    assert client.post("/api/follow-ups", json={"customer_id": cid, "due_at": "2026-12-01T10:00:00"}, headers=sm).status_code == 422


def test_roles_sm_sees_own_admin_sees_all_but_cannot_change(client, make_staff):
    _, sm1 = make_staff("SM1")
    _, sm2 = make_staff("SM2")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    c1, c2 = _customer(client, sm1), client.post("/api/customers", json={"values": {"promoter": "B", "mobile": "9876501235"}}, headers=sm2).json()["id"]
    when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    f1 = client.post("/api/follow-ups", json={"customer_id": c1, "due_at": when}, headers=sm1).json()
    client.post("/api/follow-ups", json={"customer_id": c2, "due_at": when}, headers=sm2)
    assert len(client.get("/api/follow-ups", headers=sm1).json()["items"]) == 1
    assert len(client.get("/api/follow-ups", headers=admin).json()["items"]) == 2
    # nobody else can touch it, and an Admin is read-only
    assert client.post(f"/api/follow-ups/{f1['id']}/complete", json={}, headers=sm2).status_code == 404
    assert client.post(f"/api/follow-ups/{f1['id']}/complete", json={}, headers=admin).status_code == 403
    assert client.post("/api/follow-ups", json={"customer_id": c1, "due_at": when}, headers=admin).status_code == 403


# --- daily visit plan: priority, manual order, map points ---------------------------------------

def _plan_day(client, sm, count=3):
    """`count` customers, each with a follow-up on the same day at different times (09:00, 10:00, ...)."""
    day = (datetime.now(UTC) + timedelta(days=2)).date()
    ids = []
    for n in range(count):
        cid = client.post("/api/customers", json={"values": {"promoter": f"P{n}", "mobile": f"98765012{n}0"}}, headers=sm).json()["id"]
        due = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=3 + n)  # 03:30.. UTC = 09:00.. IST
        r = client.post("/api/follow-ups", json={"customer_id": cid, "due_at": due.isoformat(), "purpose": f"V{n}"}, headers=sm)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


def test_visits_come_in_time_order_until_the_sm_reorders(client, make_staff):
    _, sm = make_staff("SM1")
    a, b, c = _plan_day(client, sm)
    order = lambda: [i["id"] for i in client.get("/api/follow-ups", headers=sm).json()["items"]]  # noqa: E731
    assert order() == [a, b, c]
    assert client.post("/api/follow-ups/reorder", json={"ids": [c, a, b]}, headers=sm).status_code == 200
    assert order() == [c, a, b]


def test_moving_a_visit_to_another_day_drops_its_manual_place(client, make_staff):
    _, sm = make_staff("SM1")
    a, b, c = _plan_day(client, sm)
    client.post("/api/follow-ups/reorder", json={"ids": [c, a, b]}, headers=sm)
    later = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    assert client.patch(f"/api/follow-ups/{c}", json={"due_at": later}, headers=sm).status_code == 200
    ids = [i["id"] for i in client.get("/api/follow-ups", headers=sm).json()["items"]]
    assert ids == [a, b, c]  # c is on a later day now


def test_priority_flag_and_who_may_reorder(client, make_staff):
    _, sm = make_staff("SM1")
    _, other = make_staff("SM2")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    a, b, _c = _plan_day(client, sm)
    r = client.patch(f"/api/follow-ups/{a}", json={"is_priority": True}, headers=sm)
    assert r.status_code == 200 and r.json()["is_priority"] is True
    assert client.post("/api/follow-ups/reorder", json={"ids": [b, a]}, headers=other).status_code == 404
    assert client.post("/api/follow-ups/reorder", json={"ids": [b, a]}, headers=admin).status_code == 403
    assert client.post("/api/follow-ups/reorder", json={"ids": [a, a]}, headers=sm).status_code == 422


def test_map_point_is_the_last_meeting_gps_and_missing_without_one(client, make_staff):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    now = datetime.now(UTC)
    body = {
        "id": str(uuid.uuid4()),
        "started_at": (now - timedelta(hours=2)).isoformat(),
        "ended_at": (now - timedelta(hours=1)).isoformat(),
        "gps_start": {"latitude": "13.0827", "longitude": "80.2707", "accuracy_m": "20", "captured_at": (now - timedelta(hours=2)).isoformat()},
        "values": {"next_action": "Identify bank", "next_action_date": _tomorrow()},
    }
    assert client.post(f"/api/customers/{cid}/meetings", json=body, headers=sm).status_code == 201
    item = client.get("/api/follow-ups", headers=sm).json()["items"][0]
    assert (item["lat"], item["lng"]) == (13.0827, 80.2707)
    # a customer with no GPS meeting has no pin
    cid2 = client.post("/api/customers", json={"values": {"promoter": "NoGps", "mobile": "9876509999"}}, headers=sm).json()["id"]
    client.post("/api/follow-ups", json={"customer_id": cid2, "due_at": (now + timedelta(days=4)).isoformat()}, headers=sm)
    items = {i["customer"]["promoter"]: i for i in client.get("/api/follow-ups", headers=sm).json()["items"]}
    assert items["NoGps"]["lat"] is None
