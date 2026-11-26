import uuid

from sqlalchemy import func, select

from app.auth import SESSION_COOKIE
from app.models import AuditLog
from tests.conftest import TEST_PASSWORD, make_token, session_headers


def _email(code):
    return f"{code.lower()}@example.com"  # what make_staff gives each person


def _phone(db, code):
    from app.models import Staff

    return db.scalar(select(Staff.phone).where(Staff.email == (code if "@" in code else _email(code)).lower()))


def _login(client, code, password=TEST_PASSWORD, phone=None, db=None):
    """Sign in with the email, the mobile and the password. `code` is the label make_staff was given."""
    if phone is None:
        phone = _phone(db, code) if db is not None else "9000000000"
    username = code if "@" in code else _email(code)
    return client.post("/api/auth/login", json={"username": username, "phone": phone, "password": password})


def test_login_sets_httponly_cookie_and_me_works(client, make_staff, db):
    make_staff("EMP001")
    r = _login(client, "EMP001@EXAMPLE.COM", db=db)  # the email is case-insensitive
    assert r.status_code == 200
    assert r.json()["email"] == "emp001@example.com"
    cookie = r.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=strict" in cookie.lower()
    assert "Path=/api" in cookie
    # TestClient keeps the cookie for later requests.
    assert client.get("/api/me").json()["email"] == "emp001@example.com"


def test_wrong_password_and_unknown_code_look_the_same(client, make_staff, db):
    make_staff("EMP001")
    a = _login(client, "EMP001", "wrong-password", db=db)
    b = _login(client, "nobody@example.com", "wrong-password")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_inactive_staff_cannot_log_in(client, make_staff, db):
    make_staff("EMP009", active=False)
    assert _login(client, "EMP009", db=db).status_code == 401


def test_lockout_after_five_failures(client, make_staff, db):
    make_staff("EMP001")
    for _ in range(5):
        assert _login(client, "EMP001", "nope", db=db).status_code == 401
    # Even the right password is refused while locked.
    assert _login(client, "EMP001", db=db).status_code == 429
    failures = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "LOGIN_FAILED"))
    assert failures == 5


def test_logout_clears_cookie(client, make_staff, db):
    make_staff("EMP001")
    _login(client, "EMP001", db=db)
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/me").status_code == 401


def test_requires_session(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/customers").status_code == 401


def test_rejects_forged_or_expired_or_unknown_sessions(client, make_staff):
    staff, _ = make_staff("A1")
    forged = make_token(staff.id, secret="some-other-secret-some-other-secret-1234")
    expired = make_token(staff.id, exp_in=-10)
    unknown = make_token(uuid.uuid4())
    for token in (forged, expired, unknown, "garbage"):
        assert client.get("/api/me", headers=session_headers(token)).status_code == 401


def test_deactivated_staff_lose_access_immediately(client, make_staff, db):
    staff, headers = make_staff("A1")
    assert client.get("/api/me", headers=headers).status_code == 200
    staff.is_active = False
    db.commit()
    assert client.get("/api/me", headers=headers).status_code == 401


# --- DEV_AUTO_LOGIN (testing-only switch) -------------------------------------


def test_dev_auto_login_skips_sign_in(client, make_staff, monkeypatch):
    from app.config import get_settings

    make_staff("DEV001")
    monkeypatch.setattr(get_settings(), "dev_auto_login", "DEV001@example.com")
    r = client.get("/api/me")
    assert r.status_code == 200 and r.json()["email"] == "dev001@example.com"


def test_dev_auto_login_ignores_inactive_staff(client, make_staff, monkeypatch):
    from app.config import get_settings

    make_staff("DEV001", active=False)
    monkeypatch.setattr(get_settings(), "dev_auto_login", "dev001@example.com")
    assert client.get("/api/me").status_code == 401


def test_dev_auto_login_refused_in_production():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://x/y", jwt_secret="s", cookie_secure=True, dev_auto_login="DEV001")


def test_sign_in_needs_the_right_mobile(client, make_staff, db):
    make_staff("EMP001")
    phone = _phone(db, "EMP001")
    # the right email and password, but another person's / a wrong mobile: refused with the same answer
    wrong = _login(client, "EMP001", phone="9111111111")
    none = _login(client, "EMP001", phone="12345")
    assert wrong.status_code == none.status_code == 401 and wrong.json() == none.json()
    # the mobile may be typed with +91 and spaces
    ok = _login(client, "EMP001", phone=f"+91 {phone[:5]} {phone[5:]}")
    assert ok.status_code == 200 and ok.json()["email"] == "emp001@example.com"


def test_staff_without_a_mobile_cannot_sign_in(client, make_staff, db):
    from app.models import Staff

    staff, _ = make_staff("EMP002")
    staff.phone = None
    db.commit()
    assert _login(client, "EMP002", phone="9000000000").status_code == 401


def test_while_testing_any_10_digit_mobile_is_accepted(client, make_staff, db, monkeypatch):
    from app.config import get_settings

    make_staff("EMP003")
    monkeypatch.setattr(get_settings(), "login_check_phone", False)
    assert _login(client, "EMP003", phone="9874566545").status_code == 200  # not the person's own mobile
    assert _login(client, "EMP003", phone="12345").status_code == 401  # but it must still be 10 digits


def test_phone_check_cannot_be_switched_off_in_production():
    import pytest

    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(database_url="postgresql+psycopg://x/y", jwt_secret="s", cookie_secure=True, login_check_phone=False)
