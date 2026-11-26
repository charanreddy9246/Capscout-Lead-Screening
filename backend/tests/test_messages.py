"""Messages: a draft from the Next Action, a log of what was sent, who may do what."""

from __future__ import annotations

from app.models import StaffRole


def _customer(client, headers, **values):
    r = client.post("/api/customers", json={"values": {"promoter": "Ravi Kumar", "mobile": "9876501234", **values}}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_the_draft_follows_the_next_action_and_uses_the_name_and_sm(client, make_staff):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm, next_action="Document collection")
    d = client.get(f"/api/customers/{cid}/messages/draft", headers=sm).json()
    assert d["next_action"] == "Document collection" and d["mobile"] == "9876501234"
    assert d["text"].startswith("Hi Ravi,") and "pending documents" in d["text"] and "Staff SM1" in d["text"]
    other = _customer(client, sm, mobile="9876501235", next_action="Sanction")
    assert "sanction" in client.get(f"/api/customers/{other}/messages/draft", headers=sm).json()["text"]


def test_a_customer_with_no_next_action_gets_a_plain_follow_up_draft(client, make_staff):
    _, sm = make_staff("SM1")
    cid = _customer(client, sm)
    assert "following up on our meeting" in client.get(f"/api/customers/{cid}/messages/draft", headers=sm).json()["text"]


def test_sending_is_logged_and_the_log_is_readable_by_an_admin(client, make_staff):
    _, sm = make_staff("SM1")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    cid = _customer(client, sm)
    r = client.post(f"/api/customers/{cid}/messages", json={"channel": "WHATSAPP", "body": "Hello Ravi"}, headers=sm)
    assert r.status_code == 201 and r.json()["by"] == "Staff SM1"
    items = client.get(f"/api/customers/{cid}/messages", headers=admin).json()["items"]
    assert [(i["channel"], i["body"]) for i in items] == [("WHATSAPP", "Hello Ravi")]
    # an Admin cannot draft or send, and a made-up channel or empty text is refused
    assert client.get(f"/api/customers/{cid}/messages/draft", headers=admin).status_code == 403
    assert client.post(f"/api/customers/{cid}/messages", json={"channel": "SMS", "body": "x"}, headers=admin).status_code == 403
    assert client.post(f"/api/customers/{cid}/messages", json={"channel": "FAX", "body": "x"}, headers=sm).status_code == 422
    assert client.post(f"/api/customers/{cid}/messages", json={"channel": "SMS", "body": ""}, headers=sm).status_code == 422


def test_other_sms_customers_are_not_reachable(client, make_staff):
    _, a = make_staff("SM1")
    _, b = make_staff("SM2")
    cid = _customer(client, a)
    assert client.get(f"/api/customers/{cid}/messages/draft", headers=b).status_code == 404
    assert client.post(f"/api/customers/{cid}/messages", json={"channel": "SMS", "body": "hi"}, headers=b).status_code == 404
