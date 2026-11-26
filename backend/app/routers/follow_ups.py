"""Follow-ups: the SM plans and completes them; Admins and the Super Admin see everyone's, read-only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.access import get_own_customer, get_visible_customer, scope_customers
from app.auth import CurrentStaff, DbSession, FieldStaff
from app.models import Customer, FollowUp, FollowUpStatus, Meeting, StaffRole
from app.services import follow_ups as svc
from app.services.customers import audit

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


class _Aware(BaseModel):
    @field_validator("due_at", check_fields=False)
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("must include a timezone")
        return v


class NewFollowUp(_Aware):
    customer_id: uuid.UUID
    due_at: datetime
    purpose: str | None = None


class FollowUpPatch(_Aware):
    due_at: datetime | None = None
    purpose: str | None = None
    is_priority: bool | None = None


class ReorderIn(BaseModel):
    ids: list[uuid.UUID]


class NextOne(_Aware):
    due_at: datetime
    purpose: str | None = None


class CompleteIn(BaseModel):
    outcome: str | None = None
    next: NextOne | None = None


def _when(fu: FollowUp, now: datetime) -> str:
    if fu.status == FollowUpStatus.DONE:
        return "done"
    today = svc.local(now).date()
    day = svc.local(fu.due_at).date()
    if fu.due_at < now and day < today:
        return "overdue"
    if day == today:
        return "today"
    return "upcoming"


def _place(db, customer_ids) -> dict:
    """Where each customer is: the GPS point of their most recent meeting that has one."""
    if not customer_ids:
        return {}
    rows = db.execute(
        select(Meeting.customer_id, Meeting.start_latitude, Meeting.start_longitude)
        .where(Meeting.customer_id.in_(customer_ids), Meeting.start_latitude.is_not(None))
        .order_by(Meeting.started_at.desc())
    ).all()
    out: dict = {}
    for cid, lat, lng in rows:
        out.setdefault(cid, (float(lat), float(lng)))
    return out


def _day_key(fu: FollowUp):
    """By day; inside a day the SM's own order first, then anything not yet placed by time."""
    return (svc.local(fu.due_at).date(), 0 if fu.sort_order is not None else 1, fu.sort_order or 0, fu.due_at)


def _out(fu: FollowUp, now: datetime, place: dict | None = None) -> dict:
    c = fu.customer
    vals = c.current_values or {}
    at = (place or {}).get(c.id)
    return {
        "id": str(fu.id),
        "is_priority": fu.is_priority,
        "lat": at[0] if at else None,
        "lng": at[1] if at else None,
        "location": vals.get("location"),
        "customer": {
            "id": str(c.id),
            "business_name": vals.get("business_name"),
            "promoter": vals.get("promoter"),
            "mobile": vals.get("mobile"),
            "loan_stage": vals.get("next_action") if c.conversion_status.value == "CONVERTED" else None,
            "converted": c.conversion_status.value == "CONVERTED",
            "owner_name": c.owner.full_name if c.owner else None,
        },
        "due_at": fu.due_at.isoformat(),
        "purpose": fu.purpose,
        "status": fu.status.value,
        "outcome": fu.outcome,
        "completed_at": fu.completed_at.isoformat() if fu.completed_at else None,
        "when": _when(fu, now),
    }


def _get(db, staff, fu_id: uuid.UUID, own: bool = True) -> FollowUp:
    fu = db.get(FollowUp, fu_id)
    if fu is None:
        raise HTTPException(status_code=404, detail="Not found")
    # 404 if it is not theirs to see; for a change (own=True) it must also be their own customer: else 403
    (get_own_customer if own else get_visible_customer)(db, staff, fu.customer_id)
    return fu


@router.get("")
def list_follow_ups(
    staff: CurrentStaff,
    db: DbSession,
    status: str = Query(default="pending", pattern="^(pending|done)$"),
    customer_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,  # Admin: one SM's follow-ups
    mine: bool = False,  # Admin: only their own
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    now = datetime.now(UTC)
    base = scope_customers(select(Customer.id), staff, mine)
    stmt = select(FollowUp).where(FollowUp.customer_id.in_(base))
    if customer_id is not None:
        stmt = stmt.where(FollowUp.customer_id == customer_id)
    if staff_id is not None and staff.role != StaffRole.SM:
        stmt = stmt.where(FollowUp.staff_id == staff_id)
    want = FollowUpStatus.PENDING if status == "pending" else FollowUpStatus.DONE
    order = FollowUp.due_at.asc() if want == FollowUpStatus.PENDING else FollowUp.completed_at.desc().nulls_last()
    rows = db.scalars(
        stmt.where(FollowUp.status == want).options(joinedload(FollowUp.customer).joinedload(Customer.owner)).order_by(order).limit(limit)
    ).unique().all()
    if want == FollowUpStatus.PENDING:
        rows = sorted(rows, key=_day_key)
    place = _place(db, {fu.customer_id for fu in rows})
    items = [_out(fu, now, place) for fu in rows]

    # counts for the tab badge: always about pending ones, whatever list was asked for
    pend = db.scalars(
        select(FollowUp).where(FollowUp.customer_id.in_(base), FollowUp.status == FollowUpStatus.PENDING)
        .options(joinedload(FollowUp.customer))
    ).unique().all()
    counts = {"overdue": 0, "today": 0, "upcoming": 0}
    for fu in pend:
        counts[_when(fu, now)] += 1
    return {"items": items, "counts": counts}


@router.post("", status_code=201)
def create_follow_up(body: NewFollowUp, staff: FieldStaff, db: DbSession) -> dict:
    customer = get_own_customer(db, staff, body.customer_id)
    fu = FollowUp(customer_id=customer.id, staff_id=customer.owner_staff_id, due_at=body.due_at, purpose=(body.purpose or "").strip() or None)
    db.add(fu)
    svc.mirror(db, customer)
    audit(db, staff, "FOLLOW_UP_CREATED", customer, {"due_at": body.due_at.isoformat()})
    db.commit()
    db.refresh(fu)
    return _out(fu, datetime.now(UTC))


@router.patch("/{fu_id}")
def update_follow_up(fu_id: uuid.UUID, body: FollowUpPatch, staff: FieldStaff, db: DbSession) -> dict:
    fu = _get(db, staff, fu_id)
    if fu.status != FollowUpStatus.PENDING:
        raise HTTPException(status_code=409, detail="This follow-up is already done.")
    if body.due_at is not None:
        if svc.local(body.due_at).date() != svc.local(fu.due_at).date():
            fu.sort_order = None  # a different day: back to time order there
        fu.due_at = body.due_at
    if body.is_priority is not None:
        fu.is_priority = body.is_priority
    if body.purpose is not None:
        fu.purpose = body.purpose.strip() or None
    svc.mirror(db, fu.customer)
    audit(db, staff, "FOLLOW_UP_CHANGED", fu.customer)
    db.commit()
    db.refresh(fu)
    return _out(fu, datetime.now(UTC))


@router.post("/reorder")
def reorder(body: ReorderIn, staff: FieldStaff, db: DbSession) -> dict:
    """Save the SM's own order for a list of (one day's) pending follow-ups."""
    if len(set(body.ids)) != len(body.ids):
        raise HTTPException(status_code=422, detail="Each visit can be listed once.")
    for position, fu_id in enumerate(body.ids, start=1):
        fu = _get(db, staff, fu_id)
        if fu.status != FollowUpStatus.PENDING:
            raise HTTPException(status_code=409, detail="Only visits still to do can be reordered.")
        fu.sort_order = position
    db.commit()
    return {"ok": True}


@router.post("/{fu_id}/complete")
def complete_follow_up(fu_id: uuid.UUID, body: CompleteIn, staff: FieldStaff, db: DbSession) -> dict:
    fu = _get(db, staff, fu_id)
    if fu.status != FollowUpStatus.PENDING:
        raise HTTPException(status_code=409, detail="This follow-up is already done.")
    svc.complete(db, fu, body.outcome)
    if body.next is not None:
        db.add(
            FollowUp(
                customer_id=fu.customer_id, staff_id=fu.staff_id, due_at=body.next.due_at,
                purpose=(body.next.purpose or fu.purpose), status=FollowUpStatus.PENDING,
            )
        )
    svc.mirror(db, fu.customer)
    audit(db, staff, "FOLLOW_UP_DONE", fu.customer, {"scheduled_next": body.next is not None})
    db.commit()
    db.refresh(fu)
    return _out(fu, datetime.now(UTC))
