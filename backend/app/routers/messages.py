"""Messages to a customer: a draft from the Next Action, then a log of what the SM sent.

The app never sends anything itself: the SM edits the draft and sends it from their own WhatsApp,
SMS app or by copying it. The send is recorded here. Admins and the Super Admin can read the log.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.access import get_own_customer, get_visible_customer
from app.auth import CurrentStaff, DbSession, FieldStaff
from app.models import CustomerMessage
from app.services import follow_ups as fu
from app.services import message_templates
from app.services.customers import audit

router = APIRouter(prefix="/customers/{customer_id}/messages", tags=["messages"])

CHANNELS = ("WHATSAPP", "SMS", "COPY")


class SentIn(BaseModel):
    channel: str = Field(pattern="^(WHATSAPP|SMS|COPY)$")
    body: str = Field(min_length=1, max_length=1000)


def _out(m: CustomerMessage) -> dict:
    return {
        "id": str(m.id),
        "channel": m.channel,
        "body": m.body,
        "sent_at": m.created_at.isoformat(),
        "by": m.staff.full_name if m.staff else None,
    }


@router.get("")
def history(customer_id: uuid.UUID, staff: CurrentStaff, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    customer = get_visible_customer(db, staff, customer_id)
    rows = db.scalars(
        select(CustomerMessage).where(CustomerMessage.customer_id == customer.id)
        .options(joinedload(CustomerMessage.staff)).order_by(CustomerMessage.created_at.desc()).limit(limit)
    ).all()
    return {"items": [_out(m) for m in rows]}


@router.get("/draft")
def draft(customer_id: uuid.UUID, staff: FieldStaff, db: DbSession) -> dict:
    customer = get_own_customer(db, staff, customer_id)
    nxt = next(iter(fu.pending_for(db, customer.id)), None)
    return {
        "text": message_templates.draft(customer, staff, nxt.due_at if nxt else None),
        "mobile": customer.current_values.get("mobile"),
        "next_action": customer.current_values.get("next_action"),
    }


@router.post("", status_code=201)
def sent(customer_id: uuid.UUID, body: SentIn, staff: FieldStaff, db: DbSession) -> dict:
    customer = get_own_customer(db, staff, customer_id)
    m = CustomerMessage(customer_id=customer.id, staff_id=staff.id, channel=body.channel, body=body.body.strip())
    db.add(m)
    audit(db, staff, "MESSAGE_SENT", customer, {"channel": body.channel})
    db.commit()
    db.refresh(m)
    return _out(m)
