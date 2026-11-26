"""Role-based access: Super Admin, Admin and SM, and who may do what."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Customer, Staff, StaffRole
from tests.conftest import TEST_PASSWORD
from tests.test_access import _create


def _new_user(client, headers, code="NEW01", role="SM", phone="9111111101", **extra):
    return client.post(
        "/api/users",
        json={"full_name": f"Person {code}", "phone": phone, "email": f"{code.lower()}@example.com", "role": role, **extra},
        headers=headers,
    )


@pytest.fixture
def people(make_staff):
    _, sm = make_staff("SM1")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    _, admin2 = make_staff("AD2", role=StaffRole.ADMIN)
    _, sup = make_staff("SU1", role=StaffRole.SUPER_ADMIN)
    return {"sm": sm, "admin": admin, "admin2": admin2, "super": sup}


# --- who sees customer data -----------------------------------------------------------------

def test_sm_sees_own_admin_and_super_admin_see_all(client, make_staff, people):
    _, sm_b = make_staff("SM2")
    mine = _create(client, people["sm"], promoter="Mine").json()["id"]
    _create(client, sm_b, promoter="Theirs")

    assert [i["promoter"] for i in client.get("/api/customers", headers=people["sm"]).json()["items"]] == ["Mine"]
    assert sorted(i["promoter"] for i in client.get("/api/customers", headers=people["admin"]).json()["items"]) == ["Mine", "Theirs"]
    assert client.get(f"/api/customers/{mine}", headers=people["admin"]).status_code == 200
    # the Super Admin sees everything an Admin sees
    assert sorted(i["promoter"] for i in client.get("/api/customers", headers=people["super"]).json()["items"]) == ["Mine", "Theirs"]
    assert client.get(f"/api/customers/{mine}", headers=people["super"]).status_code == 200


def test_every_role_can_record_its_own_customers(client, people):
    """Role decides what you may SEE; ownership decides what you may CHANGE. Everyone does field work on their own."""
    for who in ("sm", "admin", "super"):
        r = client.post("/api/customers", json={"values": {"promoter": f"Own of {who}"}}, headers=people[who])
        assert r.status_code == 201, (who, r.text)
        assert client.post("/api/leads/new", json={"meeting": {}}, headers=people[who]).status_code != 403


def test_nobody_changes_a_customer_they_do_not_own_but_admins_can_still_read_it(client, people):
    mine = _create(client, people["sm"], promoter="SM's customer").json()["id"]
    for who in ("admin", "super"):
        h = people[who]
        assert client.get(f"/api/customers/{mine}", headers=h).status_code == 200  # reading: by role
        # changing: by ownership, enforced on the server
        assert client.get(f"/api/customers/{mine}/messages/draft", headers=h).status_code == 403
        assert client.post(f"/api/customers/{mine}/messages", json={"channel": "SMS", "body": "x"}, headers=h).status_code == 403
        assert client.get(f"/api/customers/{mine}/convert-form", headers=h).status_code == 403
        assert client.post(f"/api/customers/{mine}/convert", headers=h).status_code == 403
        assert client.post("/api/follow-ups", json={"customer_id": mine, "due_at": "2030-01-01T10:00:00+05:30"}, headers=h).status_code == 403
        body = {"id": str(uuid.uuid4()), "started_at": "2026-01-01T10:00:00+05:30", "ended_at": "2026-01-01T10:30:00+05:30", "gps_unavailable_reason": "x", "values": {}}
        assert client.post(f"/api/customers/{mine}/meetings", json=body, headers=h).status_code == 403


def test_an_admin_continues_meetings_on_their_own_customer(client, people):
    own = client.post("/api/customers", json={"values": {"promoter": "Admin's own"}}, headers=people["admin"]).json()["id"]
    body = {"id": str(uuid.uuid4()), "started_at": "2026-01-01T10:00:00+05:30", "ended_at": "2026-01-01T10:30:00+05:30", "gps_unavailable_reason": "x", "values": {"urgency": "Immediate"}}
    assert client.post(f"/api/customers/{own}/meetings", json=body, headers=people["admin"]).status_code == 201
    # and the SM cannot see it at all
    assert client.get(f"/api/customers/{own}", headers=people["sm"]).status_code == 404


def test_mine_filters_an_admins_lists_to_their_own_customers(client, people):
    _create(client, people["sm"], promoter="Theirs", mobile="9876500001")
    _create(client, people["admin"], promoter="Mine", mobile="9876500002")
    names = lambda url: sorted(i["promoter"] for i in client.get(url, headers=people["admin"]).json()["items"])  # noqa: E731
    assert names("/api/customers") == ["Mine", "Theirs"]
    assert names("/api/customers?mine=true") == ["Mine"]
    assert client.get("/api/customers/-/summary?mine=true", headers=people["admin"]).json()["not_converted"] == 1
    assert client.get("/api/customers/-/summary", headers=people["admin"]).json()["not_converted"] == 2
    # an SM asking for mine=false/true sees only their own either way
    assert [i["promoter"] for i in client.get("/api/customers", headers=people["sm"]).json()["items"]] == ["Theirs"]


# --- who may manage whom -------------------------------------------------------------------

def test_super_admin_creates_admins_and_admin_cannot(client, people):
    assert _new_user(client, people["super"], "ADM9", "ADMIN").status_code == 201
    r = _new_user(client, people["admin"], "ADM8", "ADMIN", phone="9111111102")
    assert r.status_code == 403 and "Super Admin" in r.json()["detail"]
    assert _new_user(client, people["sm"], "ADM7", "ADMIN", phone="9111111103").status_code == 403


def test_admin_and_super_admin_create_sms_sms_cannot(client, people):
    assert _new_user(client, people["admin"], "SMA", "SM", phone="9111111104").status_code == 201
    assert _new_user(client, people["super"], "SMB", "SM", phone="9111111105").status_code == 201
    assert _new_user(client, people["sm"], "SMC", "SM", phone="9111111106").status_code == 403


def test_nobody_creates_a_super_admin_through_the_api(client, people):
    assert _new_user(client, people["super"], "SUP2", "SUPER_ADMIN", phone="9111111107").status_code == 403


def test_admin_cannot_touch_another_admin(client, people, db):
    other = db.scalar(select(Staff).where(Staff.email == "ad2@example.com"))
    url = f"/api/users/{other.id}"
    assert client.patch(url, json={"is_active": False}, headers=people["admin"]).status_code == 403
    assert client.patch(url, json={"full_name": "Hacked"}, headers=people["admin"]).status_code == 403
    assert client.post(f"{url}/invite", headers=people["admin"]).status_code == 403
    # the Super Admin can
    assert client.patch(url, json={"is_active": False}, headers=people["super"]).status_code == 200


def test_admin_manages_sms_and_only_super_admin_promotes(client, people, db):
    sm = db.scalar(select(Staff).where(Staff.email == "sm1@example.com"))
    url = f"/api/users/{sm.id}"
    assert client.patch(url, json={"is_active": False}, headers=people["admin"]).status_code == 200
    assert client.patch(url, json={"phone": "9222222222"}, headers=people["admin"]).json()["phone"] == "9222222222"
    # promoting to Admin is the Super Admin's call
    assert client.patch(url, json={"role": "ADMIN"}, headers=people["admin"]).status_code == 403
    assert client.patch(url, json={"role": "ADMIN"}, headers=people["super"]).json()["role"] == "ADMIN"


def test_nobody_can_lock_themselves_out_or_become_super_admin(client, people, db):
    me = db.scalar(select(Staff).where(Staff.email == "ad1@example.com"))
    assert client.patch(f"/api/users/{me.id}", json={"is_active": False}, headers=people["admin"]).status_code == 403
    sm = db.scalar(select(Staff).where(Staff.email == "sm1@example.com"))
    assert client.patch(f"/api/users/{sm.id}", json={"role": "SUPER_ADMIN"}, headers=people["super"]).status_code == 403
    sup = db.scalar(select(Staff).where(Staff.email == "su1@example.com"))
    assert client.patch(f"/api/users/{sup.id}", json={"is_active": False}, headers=people["super"]).status_code == 403


def test_user_list_depends_on_who_asks(client, people):
    admin_view = {u["role"] for u in client.get("/api/users", headers=people["admin"]).json()["items"]}
    super_view = {u["role"] for u in client.get("/api/users", headers=people["super"]).json()["items"]}
    assert admin_view == {"SM"} and super_view == {"SM", "ADMIN"}
    assert client.get("/api/users", headers=people["sm"]).status_code == 403


def test_duplicate_code_or_mobile_is_refused_politely(client, people):
    assert _new_user(client, people["admin"], "DUP1", phone="9333333301").status_code == 201
    assert _new_user(client, people["admin"], "DUP1", phone="9333333302").status_code == 409
    assert _new_user(client, people["admin"], "DUP2", phone="9333333301").status_code == 409
    assert _new_user(client, people["admin"], "DUP3", phone="12345").status_code == 422


# --- the set-password link ------------------------------------------------------------------

def test_invite_link_sets_the_password_once_and_the_person_can_sign_in(client, people):
    created = _new_user(client, people["admin"], "FRESH", email="Fresh@Example.com", phone="9444444401").json()
    token = created["invite"]["token"]
    # no password yet: nobody can sign in
    assert client.post("/api/auth/login", json={"username": "FRESH", "phone": "9444444401", "password": "anything-at-all"}).status_code == 401

    assert client.post("/api/auth/set-password", json={"token": token, "password": "short"}).status_code == 422
    ok = client.post("/api/auth/set-password", json={"token": token, "password": TEST_PASSWORD})
    assert ok.status_code == 200
    # the same link cannot be used twice
    assert client.post("/api/auth/set-password", json={"token": token, "password": "another-password-1"}).status_code == 400

    login = client.post("/api/auth/login", json={"username": "fresh@example.com", "phone": "9444444401", "password": TEST_PASSWORD})
    assert login.status_code == 200 and login.json()["role"] == "SM"


def test_bad_or_deactivated_invite_is_refused(client, people, db):
    assert client.post("/api/auth/set-password", json={"token": "x" * 40, "password": TEST_PASSWORD}).status_code == 400
    created = _new_user(client, people["admin"], "GONE", phone="9555555501").json()
    client.patch(f"/api/users/{created['id']}", json={"is_active": False}, headers=people["admin"])
    assert client.post("/api/auth/set-password", json={"token": created["invite"]["token"], "password": TEST_PASSWORD}).status_code == 400


def test_a_deactivated_account_loses_access_at_once(client, make_staff, people, db):
    sm = db.scalar(select(Staff).where(Staff.email == "sm1@example.com"))
    assert client.get("/api/me", headers=people["sm"]).status_code == 200
    client.patch(f"/api/users/{sm.id}", json={"is_active": False}, headers=people["admin"])
    assert client.get("/api/me", headers=people["sm"]).status_code == 401


# --- the dashboard ---------------------------------------------------------------------------

def _dash(client, who, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/dashboard?{q}", headers=who)


def test_dashboard_numbers_and_who_sees_whose(client, make_staff, people, db):
    from datetime import UTC, datetime

    from tests.test_meetings import _meeting, _post

    sm_a, sm_b = db.scalar(select(Staff).where(Staff.email == "sm1@example.com")), None
    _, b_headers = make_staff("SM2")
    sm_b = db.scalar(select(Staff).where(Staff.email == "sm2@example.com"))
    today = datetime.now(UTC).date().isoformat()

    a1 = _create(client, people["sm"], promoter="A1", next_action="Document collection", next_action_date=today).json()["id"]
    _create(client, people["sm"], promoter="A2", status="Reject")
    _create(client, b_headers, promoter="B1", next_action="Login", next_action_date="2020-01-01")
    _post(client, people["sm"], a1, _meeting({"urgency": "Immediate"}, started=f"{today}T00:10:00+05:30"))
    _post(client, people["sm"], a1, _meeting({"urgency": "Flexible"}, gps=None, reason="Switched off", started=f"{today}T00:20:00+05:30"))

    me = _dash(client, people["sm"], period="month", today=today).json()
    assert me["scope"] == "me" and me["person"]["full_name"] == "Staff SM1"
    t = me["totals"]
    assert (t["meetings"], t["new_prospects"], t["no_gps"], t["follow_ups_today"], t["overdue"]) == (2, 2, 1, 1, 0)
    assert t["open_customers"] == 1  # the rejected one is not open
    # an SM cannot look at someone else: the staff_id is simply ignored
    sneaky = _dash(client, people["sm"], period="month", today=today, staff_id=sm_b.id).json()
    assert sneaky["person"]["full_name"] == "Staff SM1" and sneaky["totals"] == t

    team = _dash(client, people["admin"], period="month", today=today).json()
    assert team["scope"] == "team" and team["totals"]["new_prospects"] == 3 and team["totals"]["overdue"] == 1
    rows = {m["full_name"]: m for m in team["members"]}
    assert rows["Staff SM1"]["meetings"] == 2 and rows["Staff SM1"]["no_gps"] == 1
    assert rows["Staff SM2"]["meetings"] == 0 and rows["Staff SM2"]["overdue"] == 1

    one = _dash(client, people["admin"], period="month", today=today, staff_id=sm_a.id).json()
    assert one["scope"] == "person" and one["totals"] == t and "members" not in one


def test_super_admin_gets_the_team_dashboard_and_ids_are_checked(client, people, db):
    assert _dash(client, people["super"]).json()["scope"] == "team"
    other_admin = db.scalar(select(Staff).where(Staff.email == "ad2@example.com"))
    me = db.scalar(select(Staff).where(Staff.email == "ad1@example.com"))
    # an Admin cannot ask for another admin's "dashboard", but can see their own numbers
    assert _dash(client, people["admin"], staff_id=other_admin.id).status_code == 404
    assert _dash(client, people["admin"], staff_id=me.id).json()["scope"] == "person"
    assert _dash(client, people["admin"], period="year").status_code == 422


def test_admin_can_list_one_sms_customers_but_an_sm_cannot_widen_the_list(client, make_staff, people, db):
    _, other = make_staff("SM2")
    sm1 = db.scalar(select(Staff).where(Staff.email == "sm1@example.com"))
    _create(client, people["sm"], promoter="One")
    _create(client, other, promoter="Two")
    names = lambda who, **q: sorted(  # noqa: E731
        i["promoter"] for i in client.get("/api/customers", params=q, headers=who).json()["items"]
    )
    assert names(people["admin"], staff_id=str(sm1.id)) == ["One"]
    assert names(people["admin"]) == ["One", "Two"]
    assert names(people["sm"], staff_id=str(db.scalar(select(Staff.id).where(Staff.email == "sm2@example.com")))) == ["One"]
