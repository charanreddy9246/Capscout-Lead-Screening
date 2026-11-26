"""Staff login, session cookie and the current-staff dependency.

Staff sign in with employee code + password. The backend sets an httpOnly
session cookie (a signed JWT) that page JavaScript cannot read. Every data
query is then scoped to that staff member in `app.access`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, Staff, StaffRole

SESSION_COOKIE = "fm_session"
_ALGORITHM = "HS256"
_hasher = PasswordHasher()
# Verified against when the employee code is unknown, so response time does
# not reveal which codes exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def issue_session_token(staff: Staff) -> str:
    now = datetime.now(UTC)
    settings = get_settings()
    return jwt.encode(
        {"sub": str(staff.id), "iat": now, "exp": now + timedelta(hours=settings.session_hours)},
        settings.jwt_secret,
        algorithm=_ALGORITHM,
    )


class LoginLocked(Exception):
    pass


def _mobile(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) > 10:
        digits = digits[2:] if digits.startswith("91") else digits.lstrip("0")
    return digits if len(digits) == 10 else None


def authenticate(
    db: Session, username: str, phone: str, password: str, request: Request | None = None
) -> Staff | None:
    """Return the staff member for valid credentials, else None. Records the attempt.

    All three must belong to the same person: the email, the 10-digit mobile, and the
    password. Whatever is wrong, the answer is the same, so nothing tells an outsider which part failed.
    """
    settings = get_settings()
    code = username.strip().lower()  # the email, as it is stored
    since = datetime.now(UTC) - timedelta(minutes=settings.login_lockout_minutes)
    failures = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "LOGIN_FAILED", AuditLog.entity_id == code, AuditLog.created_at >= since)
    )
    if failures >= settings.login_max_failures:
        raise LoginLocked()

    staff = db.scalar(select(Staff).where(Staff.email == code))
    ok = _verify(staff.password_hash if staff else _DUMMY_HASH, password)
    entered = _mobile(phone)
    if entered is None:  # always needs a 10-digit mobile
        ok = False
    elif settings.login_check_phone and staff is not None and staff.phone != entered:
        ok = False  # the mobile must be this person's own (switched off only while testing)
    ip = request.client.host if request and request.client else None
    if not ok or staff is None or not staff.is_active:
        db.add(AuditLog(action="LOGIN_FAILED", entity_type="staff_email", entity_id=code, details={"ip": ip}))
        db.commit()
        return None

    if _hasher.check_needs_rehash(staff.password_hash):
        staff.password_hash = _hasher.hash(password)
    db.add(AuditLog(staff_id=staff.id, action="LOGIN", details={"ip": ip}))
    db.commit()
    return staff


def _staff_from_session(db: Session, session: str | None) -> Staff | None:
    if not session:
        return None
    try:
        claims = jwt.decode(
            session, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]}
        )
        staff_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
    staff = db.get(Staff, staff_id)
    # Deactivated staff lose access immediately, even with an unexpired session.
    return staff if staff is not None and staff.is_active else None


def get_current_staff(
    db: Annotated[Session, Depends(get_db)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Staff:
    staff = _staff_from_session(db, session)
    if staff is not None:
        return staff
    code = get_settings().dev_auto_login
    if code:
        # Testing only (see Settings.dev_auto_login): act as this staff member.
        staff = db.scalar(select(Staff).where(Staff.email == code.strip().lower()))
        if staff is not None and staff.is_active:
            return staff
    raise _UNAUTHORIZED


CurrentStaff = Annotated[Staff, Depends(get_current_staff)]


def require_roles(*roles: StaffRole):
    """A dependency that lets only these roles through (403 for everyone else)."""

    def check(staff: Annotated[Staff, Depends(get_current_staff)]) -> Staff:
        if staff.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this.")
        return staff

    return check


# Field work (meetings, follow-ups, messages, converting) is open to every role. Role is one rule; OWNERSHIP is a
# separate one: a person can only change customers they own (see access.get_own_customer).
FieldStaff = Annotated[Staff, Depends(require_roles(StaffRole.SM, StaffRole.ADMIN, StaffRole.SUPER_ADMIN))]
# Managing accounts.
UserAdmin = Annotated[Staff, Depends(require_roles(StaffRole.ADMIN, StaffRole.SUPER_ADMIN))]
DbSession = Annotated[Session, Depends(get_db)]
