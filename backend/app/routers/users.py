"""User management: who may create, change and deactivate which accounts.

  SUPER_ADMIN  creates / promotes / deactivates ADMINs (and may manage SMs too). Also sees customers and dashboards, read-only, like an Admin.
  ADMIN        creates / deactivates SMs and resets their passwords. Cannot touch another ADMIN.
  SM           has no access here.

There is no public sign-up. A new account has no usable password: the admin passes on a
one-time set-password link (valid 72 hours; it stops working once the password is set).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import _ALGORITHM, DbSession, UserAdmin, _mobile, hash_password
from app.config import get_settings
from app.models import AuditLog, Staff, StaffRole
from app.services import mailer

router = APIRouter(prefix="/users", tags=["users"])
public_router = APIRouter(prefix="/auth", tags=["auth"])

INVITE_HOURS = 72
MIN_PASSWORD = 8


# --- who may manage whom -------------------------------------------------------------------

def can_manage(actor: Staff, target_role: StaffRole) -> bool:
    """May `actor` create, change, deactivate or reset an account that has `target_role`?"""
    if target_role == StaffRole.SUPER_ADMIN:
        return False  # only ever created with the server script
    if actor.role == StaffRole.SUPER_ADMIN:
        return True
    if actor.role == StaffRole.ADMIN:
        return target_role == StaffRole.SM  # an Admin cannot create or touch another Admin
    return False


def _forbidden(message: str | None = None) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message or "You are not allowed to do this.")


def _out(s: Staff) -> dict:
    return {
        "id": str(s.id),
        "full_name": s.full_name,
        "email": s.email,
        "phone": s.phone,
        "role": s.role.value,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _audit(db, actor: Staff, action: str, target: Staff, details: dict | None = None) -> None:
    db.add(
        AuditLog(
            staff_id=actor.id,
            action=action,
            entity_type="staff",
            entity_id=str(target.id),
            details={"email": target.email, "role": target.role.value, **(details or {})},
        )
    )


# --- the set-password link -----------------------------------------------------------------

def _fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def make_invite_token(staff: Staff) -> str:
    claims = {
        "sub": str(staff.id),
        "purpose": "set-password",
        "fp": _fingerprint(staff.password_hash),  # changes when the password is set: the link works once
        "exp": datetime.now(UTC) + timedelta(hours=INVITE_HOURS),
    }
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=_ALGORITHM)


def _invite_out(staff: Staff) -> dict:
    token = make_invite_token(staff)
    return {"token": token, "path": f"/set-password?token={token}", "valid_hours": INVITE_HOURS}


def _unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


# --- endpoints -----------------------------------------------------------------------------

class UserIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # required: the link is sent here
    role: StaffRole = StaffRole.SM


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    role: StaffRole | None = None
    is_active: bool | None = None


@router.get("")
def list_users(actor: UserAdmin, db: DbSession) -> dict:
    """Admins see the SMs. The Super Admin sees everyone except itself being editable."""
    roles = [StaffRole.SM] if actor.role == StaffRole.ADMIN else [StaffRole.SM, StaffRole.ADMIN]
    rows = db.scalars(select(Staff).where(Staff.role.in_(roles)).order_by(Staff.role, Staff.full_name)).all()
    return {"items": [{**_out(s), "manageable": can_manage(actor, s.role) and s.id != actor.id} for s in rows]}


def _with_email(invite: dict, staff: Staff) -> dict:
    """Try to email the link; the screen shows whether it worked (and the link as a fallback)."""
    return {**invite, "email": mailer.send_invite(get_settings(), staff.email, staff.full_name, invite["path"], invite["valid_hours"])}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: UserIn, actor: UserAdmin, db: DbSession) -> dict:
    if not can_manage(actor, body.role):
        raise _forbidden("Only the Super Admin can create an Admin." if body.role == StaffRole.ADMIN else "You are not allowed to create this account.")
    phone = _mobile(body.phone)
    if phone is None:
        raise HTTPException(status_code=422, detail="The mobile must be exactly 10 digits.")
    staff = Staff(
        full_name=body.full_name.strip(),
        phone=phone,
        email=body.email.strip().lower(),
        role=body.role,
        password_hash=_unusable_password_hash(),
    )
    db.add(staff)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email or mobile is already used.") from None
    _audit(db, actor, "USER_CREATED", staff)
    db.commit()
    db.refresh(staff)
    return {**_out(staff), "invite": _with_email(_invite_out(staff), staff)}


def _target(db, user_id: uuid.UUID) -> Staff:
    staff = db.get(Staff, user_id)
    if staff is None:
        raise HTTPException(status_code=404, detail="Not found")
    return staff


@router.patch("/{user_id}")
def update_user(user_id: uuid.UUID, body: UserPatch, actor: UserAdmin, db: DbSession) -> dict:
    target = _target(db, user_id)
    if not can_manage(actor, target.role):
        raise _forbidden("Only the Super Admin can change an Admin." if target.role == StaffRole.ADMIN else None)
    if target.id == actor.id and (body.role is not None or body.is_active is False):
        raise _forbidden("You cannot change your own role or deactivate yourself.")
    changes: dict = {}
    if body.role is not None and body.role != target.role:
        # A promotion or demotion involves an Admin role, so the target AND the new role must both be manageable.
        if not can_manage(actor, body.role):
            raise _forbidden("Only the Super Admin can promote someone to Admin.")
        changes["role"] = [target.role.value, body.role.value]
        target.role = body.role
    if body.full_name is not None:
        target.full_name = body.full_name.strip()
    if body.phone is not None:
        phone = _mobile(body.phone)
        if phone is None:
            raise HTTPException(status_code=422, detail="The mobile must be exactly 10 digits.")
        target.phone = phone
    if body.email is not None:
        target.email = body.email.strip().lower() or None
    if body.is_active is not None and body.is_active != target.is_active:
        changes["is_active"] = body.is_active
        target.is_active = body.is_active
    _audit(db, actor, "USER_UPDATED", target, {"changes": changes})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email or mobile is already used.") from None
    db.refresh(target)
    return _out(target)


@router.post("/{user_id}/invite")
def new_invite(user_id: uuid.UUID, actor: UserAdmin, db: DbSession) -> dict:
    """A new set-password link, for a lost password or an account that was never activated."""
    target = _target(db, user_id)
    if not can_manage(actor, target.role) or target.id == actor.id:
        raise _forbidden()
    _audit(db, actor, "USER_INVITE_REISSUED", target)
    db.commit()
    return _with_email(_invite_out(target), target)


class SetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=2000)
    password: str = Field(min_length=1, max_length=200)


@public_router.post("/set-password")
def set_password(body: SetPasswordIn, db: DbSession) -> dict:
    bad = HTTPException(status_code=400, detail="This link is not valid any more. Ask your admin for a new one.")
    try:
        claims = jwt.decode(body.token, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]})
        if claims.get("purpose") != "set-password":
            raise bad
        staff = db.get(Staff, uuid.UUID(claims["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise bad from None
    if staff is None or not staff.is_active or claims.get("fp") != _fingerprint(staff.password_hash):
        raise bad
    if len(body.password) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"The password must be at least {MIN_PASSWORD} characters.")
    staff.password_hash = hash_password(body.password)
    db.add(AuditLog(staff_id=staff.id, action="PASSWORD_SET", entity_type="staff", entity_id=str(staff.id), details={}))
    db.commit()
    return {"ok": True, "email": staff.email}
