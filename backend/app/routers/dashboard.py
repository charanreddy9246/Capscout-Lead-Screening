"""The analytics dashboard: ONE endpoint, and the server decides whose numbers come back.

  SM           always their own numbers (a "staff_id" they send is ignored).
  ADMIN        the whole team, or any one SM when "staff_id" is given.
  SUPER_ADMIN  the same as ADMIN.

Everything is counted from what the app already records (meetings, customers); nothing new is collected.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select

from app.auth import DbSession, require_roles
from app.config import get_settings
from app.fields.catalog import load_catalog
from app.models import ConversionStatus, Customer, GpsStatus, Meeting, Staff, StaffRole, SyncStatus
from app.routers.customers import View, _is_open, _view_filter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Every role has a dashboard: SMs their own, Admins the team, or any one person (an SM, or themselves).
DashboardUser = Annotated[Staff, Depends(require_roles(StaffRole.SM, StaffRole.ADMIN, StaffRole.SUPER_ADMIN))]

PERIODS = {"today": 1, "week": 7, "month": 30}  # the last N days, today included


def _window(today: date, key: str) -> tuple[datetime, datetime]:
    """[start, end) of the period, from midnight to midnight in the company's time zone."""
    tz = ZoneInfo(get_settings().business_timezone)
    start = datetime.combine(today - timedelta(days=PERIODS[key] - 1), time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def _counts_by_staff(db, stmt_col, stmt_from, *conditions) -> dict[uuid.UUID, int]:
    rows = db.execute(select(stmt_col, func.count()).select_from(stmt_from).where(*conditions).group_by(stmt_col)).all()
    return {k: v for k, v in rows}


@router.get("")
def dashboard(
    staff: DashboardUser,
    db: DbSession,
    period: str = Query(default="week", pattern="^(today|week|month)$"),
    staff_id: uuid.UUID | None = None,
    today: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    day = date.fromisoformat(today) if today else datetime.now(ZoneInfo(get_settings().business_timezone)).date()
    start, end = _window(day, period)

    # --- whose numbers? decided here, never by the phone ---
    person: Staff | None = None
    if staff.role == StaffRole.SM:
        person = staff
    elif staff_id is not None:
        person = db.get(Staff, staff_id)
        if person is None or (person.role != StaffRole.SM and person.id != staff.id):
            raise HTTPException(status_code=404, detail="Not found")
    scope = "me" if staff.role == StaffRole.SM else ("person" if person else "team")

    def mine(*conds, col=Customer.owner_staff_id):
        return [*conds, col == person.id] if person else list(conds)

    iso_today = day.isoformat()
    open_customers = _is_open(select(func.count()).select_from(Customer).where(*mine()))
    totals = {
        "meetings": db.scalar(
            select(func.count()).select_from(Meeting).where(*mine(Meeting.started_at >= start, Meeting.started_at < end, col=Meeting.staff_id))
        ),
        "new_prospects": db.scalar(
            select(func.count()).select_from(Customer).where(*mine(Customer.created_at >= start, Customer.created_at < end))
        ),
        "leads_converted": db.scalar(
            select(func.count()).select_from(Customer).where(
                *mine(Customer.converted_at >= start, Customer.converted_at < end, Customer.conversion_status == ConversionStatus.CONVERTED)
            )
        ),
        "follow_ups_today": db.scalar(
            select(func.count()).select_from(_view_filter(select(Customer).where(*mine()), View.FOLLOWUPS, iso_today).subquery())
        ),
        "overdue": db.scalar(
            select(func.count()).select_from(_view_filter(select(Customer).where(*mine()), View.OVERDUE, iso_today).subquery())
        ),
        "no_gps": db.scalar(
            select(func.count()).select_from(Meeting).where(
                *mine(Meeting.started_at >= start, Meeting.started_at < end, Meeting.gps_status == GpsStatus.UNAVAILABLE, col=Meeting.staff_id)
            )
        ),
        "sync_failed": db.scalar(
            select(func.count()).select_from(Meeting).where(*mine(Meeting.zoho_sync_status == SyncStatus.FAILED, col=Meeting.staff_id))
        ),
        "open_customers": db.scalar(open_customers),
    }

    # Open prospects by Lead Status (counted here: the set is small and this avoids a GROUP BY on JSON).
    stages = db.scalars(
        _is_open(select(Customer.current_values["status"].astext).where(Customer.conversion_status != ConversionStatus.CONVERTED, *mine()))
    ).all()
    pipeline_rows = Counter(label or "Not set" for label in stages).most_common()

    # Converted Leads by stage = their Next Action, in journey order (the stages come from the field catalogue).
    stage_names = next(f for f in load_catalog().fields if f.key == "next_action").options or ()
    lead_stage_values = Counter(
        db.scalars(
            select(Customer.current_values["next_action"].astext).where(
                Customer.conversion_status == ConversionStatus.CONVERTED, *mine()
            )
        ).all()
    )
    lead_stages = [{"label": s, "count": lead_stage_values.get(s, 0)} for s in stage_names]
    lead_stages.append({"label": "Not set", "count": sum(n for k, n in lead_stage_values.items() if k not in stage_names)})

    out = {
        "scope": scope,
        "person": {"id": str(person.id), "full_name": person.full_name} if person else None,
        "period": {"key": period, "from": start.isoformat(), "to": end.isoformat(), "days": PERIODS[period]},
        "totals": totals,
        "pipeline": [{"label": label, "count": n} for label, n in pipeline_rows],
        "lead_stages": lead_stages,
    }

    if scope == "team":  # one row per active SM, zeros included
        in_window = and_(Meeting.started_at >= start, Meeting.started_at < end)
        meetings = _counts_by_staff(db, Meeting.staff_id, Meeting, in_window)
        no_gps = _counts_by_staff(db, Meeting.staff_id, Meeting, in_window, Meeting.gps_status == GpsStatus.UNAVAILABLE)
        prospects = _counts_by_staff(db, Customer.owner_staff_id, Customer, Customer.created_at >= start, Customer.created_at < end)
        converted = _counts_by_staff(
            db, Customer.owner_staff_id, Customer,
            Customer.converted_at >= start, Customer.converted_at < end, Customer.conversion_status == ConversionStatus.CONVERTED,
        )
        overdue_rows = db.execute(
            _view_filter(select(Customer.owner_staff_id, func.count()).select_from(Customer), View.OVERDUE, iso_today).group_by(
                Customer.owner_staff_id
            )
        ).all()
        overdue = {k: v for k, v in overdue_rows}
        last = dict(db.execute(select(Meeting.staff_id, func.max(Meeting.started_at)).group_by(Meeting.staff_id)).all())
        sms = db.scalars(select(Staff).where(Staff.role == StaffRole.SM, Staff.is_active.is_(True)).order_by(Staff.full_name)).all()
        out["members"] = [
            {
                "id": str(s.id),
                "full_name": s.full_name,
                "meetings": meetings.get(s.id, 0),
                "new_prospects": prospects.get(s.id, 0),
                "leads_converted": converted.get(s.id, 0),
                "overdue": overdue.get(s.id, 0),
                "no_gps": no_gps.get(s.id, 0),
                "last_meeting_at": last[s.id].isoformat() if last.get(s.id) else None,
            }
            for s in sms
        ]
    return out
