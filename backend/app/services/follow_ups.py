"""Follow-ups: planned contacts with a customer (see FollowUp in models.py).

Rules in one place:
  * A meeting that sets (or clears) the Next Action Date replaces the customer's pending follow-ups.
  * The earliest pending follow-up is mirrored into the customer's current values (next_action,
    next_action_date) so the home-screen tiles, search and the Zoho Lead keep working unchanged.
  * Completing the last pending follow-up clears the Next Action Date, so nothing shows as overdue by mistake.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Customer, FollowUp, FollowUpStatus, Meeting, Staff
from app.services.customers import apply_values

DEFAULT_TIME = time(10, 0)  # used when a follow-up has a date but no time


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().business_timezone)


def to_due_at(day: str, hhmm: str | None) -> datetime:
    """A date (YYYY-MM-DD) and an optional HH:MM, read as business-timezone local time."""
    t = time.fromisoformat(hhmm) if hhmm else DEFAULT_TIME
    return datetime.combine(date.fromisoformat(day), t, tzinfo=tz())


def local(dt: datetime) -> datetime:
    return dt.astimezone(tz())


def pending_for(db: Session, customer_id) -> list[FollowUp]:
    return list(
        db.scalars(
            select(FollowUp)
            .where(FollowUp.customer_id == customer_id, FollowUp.status == FollowUpStatus.PENDING)
            .order_by(FollowUp.due_at)
        )
    )


def mirror(db: Session, customer: Customer) -> None:
    """Copy the earliest pending follow-up into the customer's current values."""
    db.flush()
    nxt = next(iter(pending_for(db, customer.id)), None)
    cleaned: dict[str, Any] = (
        {"next_action_date": local(nxt.due_at).date().isoformat(), "next_action": nxt.purpose or customer.current_values.get("next_action")}
        if nxt
        else {"next_action_date": None}
    )
    cleaned = {k: v for k, v in cleaned.items() if not (k == "next_action" and v is None)}
    apply_values(customer, cleaned)


def complete(db: Session, fu: FollowUp, outcome: str | None, when: datetime | None = None) -> None:
    fu.status = FollowUpStatus.DONE
    fu.outcome = (outcome or "").strip() or None
    fu.completed_at = when or datetime.now(UTC)


def plan_after_meeting(db: Session, staff: Staff, customer: Customer, meeting: Meeting, cleaned: dict[str, Any]) -> None:
    """Called when a meeting is saved. Only acts if the meeting set or cleared the Next Action Date."""
    if "next_action_date" not in cleaned:
        return
    for old in pending_for(db, customer.id):
        complete(db, old, f"Replaced in meeting #{meeting.sequence_no}", meeting.ended_at)
    day = cleaned.get("next_action_date")
    action = customer.current_values.get("next_action")
    closed = customer.current_values.get("status") in ("Reject", "Cancelled")
    if day and action != "Dropped" and not closed:
        db.add(
            FollowUp(
                customer_id=customer.id,
                staff_id=customer.owner_staff_id,
                meeting_id=meeting.id,
                due_at=to_due_at(day, customer.current_values.get("follow_up_time")),
                purpose=action,
                status=FollowUpStatus.PENDING,
            )
        )
    db.flush()
