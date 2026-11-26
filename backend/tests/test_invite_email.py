"""Creating an account: email is required, the code is generated, and the set-password link is emailed."""

from __future__ import annotations

import pytest

from app.models import StaffRole
from app.services import mailer


def _create(client, headers, **body):
    return client.post("/api/users", json={"full_name": "Asha Rao", "phone": "9111111111", "email": "asha@example.com", **body}, headers=headers)


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda cfg: True)
    monkeypatch.setattr(mailer, "send", lambda cfg, msg: sent.append(msg) or None)
    return sent


def test_email_is_required(client, make_staff):
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    assert _create(client, admin, email=None).status_code == 422
    assert _create(client, admin, email="not-an-email").status_code == 422
    assert client.post("/api/users", json={"full_name": "X", "phone": "9111111112"}, headers=admin).status_code == 422


def test_no_employee_code_is_asked_for_or_returned(client, make_staff, outbox):
    _, sup = make_staff("SU1", role=StaffRole.SUPER_ADMIN)
    r = _create(client, sup)
    assert r.status_code == 201 and "employee_code" not in r.json()
    assert r.json()["email"] == "asha@example.com"


def test_creating_an_account_emails_the_link_to_that_address(client, make_staff, outbox):
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    r = _create(client, admin)
    assert r.status_code == 201
    email = r.json()["invite"]["email"]
    assert email == {"sent": True, "to": "asha@example.com", "error": None}
    assert len(outbox) == 1 and outbox[0]["To"] == "asha@example.com"
    text = outbox[0].get_body(("plain",)).get_content()
    assert "Hi Asha Rao" in text and "/set-password?token=" in text and "72 hours" in text
    # the link in the email is the same single link the screen can show as a fallback
    assert r.json()["invite"]["token"] in text


def test_a_failed_email_does_not_fail_the_account_and_the_link_is_still_returned(client, make_staff, monkeypatch):
    monkeypatch.setattr(mailer, "configured", lambda cfg: True)
    monkeypatch.setattr(mailer, "send", lambda cfg, msg: "The mail account refused the login. Check the app password.")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    r = _create(client, admin)
    assert r.status_code == 201
    inv = r.json()["invite"]
    assert inv["email"]["sent"] is False and "app password" in inv["email"]["error"] and inv["token"]


def test_with_no_mail_settings_the_link_is_shown_instead(client, make_staff):
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    inv = _create(client, admin).json()["invite"]
    assert inv["email"]["sent"] is False and "not set up" in inv["email"]["error"] and inv["token"]


def test_the_set_password_link_can_be_emailed_again(client, make_staff, outbox):
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    uid = _create(client, admin).json()["id"]
    r = client.post(f"/api/users/{uid}/invite", headers=admin)
    assert r.status_code == 200 and r.json()["email"]["sent"] is True and len(outbox) == 2


def test_a_duplicate_email_is_refused_clearly(client, make_staff, outbox):
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    assert _create(client, admin).status_code == 201
    r = _create(client, admin, phone="9222222222")
    assert r.status_code == 409 and "already used" in r.json()["detail"]


def test_the_smtp_code_logs_in_and_sends_over_tls_and_never_leaks_the_password(monkeypatch):
    import smtplib

    from app.config import Settings

    log = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            log.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            log.append(("tls",))

        def login(self, user, password):
            log.append(("login", user))
            if password == "wrong":
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials secret-detail")

        def send_message(self, msg):
            log.append(("send", msg["To"], msg["From"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    cfg = Settings(database_url="x", jwt_secret="y" * 40, smtp_host="smtp.example.com", smtp_user="noreply@capitabel.example", smtp_password="app-pass", smtp_from_name="CapScout")
    msg = mailer.build_invite(cfg, "a@example.com", "Asha", "/set-password?token=t", 72)
    assert mailer.send(cfg, msg) is None
    assert log == [("connect", "smtp.example.com", 587), ("tls",), ("login", "noreply@capitabel.example"), ("send", "a@example.com", "CapScout <noreply@capitabel.example>")]

    bad = Settings(database_url="x", jwt_secret="y" * 40, smtp_host="smtp.example.com", smtp_user="u@example.com", smtp_password="wrong")
    err = mailer.send(bad, msg)
    assert err and "app password" in err and "wrong" not in err and "secret-detail" not in err


def test_the_test_suite_can_never_send_real_email():
    from app.config import get_settings

    assert not mailer.configured(get_settings())
