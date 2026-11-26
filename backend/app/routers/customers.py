from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.access import get_own_customer, get_visible_customer, scope_customers
from app.auth import CurrentStaff, DbSession, FieldStaff
from app.fields.catalog import load_catalog, progress_keys_for
from app.config import get_settings
from app.models import ConversionStatus, Customer, FieldDefinition, Meeting, StaffRole, SyncStatus
from app.services.conversion import request_conversion
from app.zoho import leadform
from app.services.customers import (
    DuplicateOtherStaff,
    DuplicateOwn,
    InvalidValues,
    OnDuplicate,
    audit,
    create_prospect,
    summary,
)

router = APIRouter(prefix="/customers", tags=["customers"])

OTHER_STAFF_MESSAGE = "This customer is already assigned to another staff member."
SEARCH_KEYS = ("business_name", "promoter", "mobile")


class Tab(str, enum.Enum):
    NOT_CONVERTED = "not_converted"
    CONVERTED = "converted"


TAB_STATUSES = {
    # Converting/failed conversions stay in Not Converted until Zoho confirms the Lead.
    Tab.NOT_CONVERTED: [
        ConversionStatus.NOT_CONVERTED,
        ConversionStatus.CONVERTING,
        ConversionStatus.CONVERSION_FAILED,
    ],
    Tab.CONVERTED: [ConversionStatus.CONVERTED],
}


class View(str, enum.Enum):
    """The tiles on the home screen: prospects AND leads together."""

    FOLLOWUPS = "followups"
    OVERDUE = "overdue"


def _is_open(stmt):
    """Not closed: Lead Status Reject or Cancelled (or an old Next Action of Dropped) is not counted as open."""
    action = Customer.current_values["next_action"].astext
    status_ = Customer.current_values["status"].astext
    return stmt.where(or_(action.is_(None), action != "Dropped"), or_(status_.is_(None), status_.notin_(("Reject", "Cancelled"))))


def _view_filter(stmt, view: View, today: str):
    stmt = _is_open(stmt)
    due = Customer.current_values["next_action_date"].astext  # ISO dates compare correctly as text
    if view == View.FOLLOWUPS:
        stmt = stmt.where(due == today)
    elif view == View.OVERDUE:
        stmt = stmt.where(due.is_not(None), due < today)
    return stmt


class CreateProspect(BaseModel):
    values: dict[str, Any]
    on_duplicate: OnDuplicate = OnDuplicate.ASK
    overwrite_customer_id: uuid.UUID | None = None


def _progress(c: Customer) -> dict[str, int]:
    total = len(progress_keys_for(c.current_values))
    return {"filled": c.fields_filled_count, "total": total, "percent": round(c.fields_filled_count * 100 / total)}


def _card(c: Customer) -> dict[str, Any]:
    vals = c.current_values or {}
    return {
        "id": str(c.id),
        "lead_ref": c.lead_ref,
        "owner_name": c.owner.full_name if c.owner else None,  # so an Admin sees whose customer it is
        "business_name": vals.get("business_name"),
        "promoter": vals.get("promoter"),
        "mobile": vals.get("mobile"),
        # What the prototype's lead card shows.
        "location": vals.get("location"),
        "loan_required": vals.get("loan_required"),
        "purpose": vals.get("purpose"),
        "opportunity_grade": vals.get("opportunity_grade"),
        "status": vals.get("status"),
        "loan_stage": vals.get("next_action") if c.conversion_status == ConversionStatus.CONVERTED else None,  # a lead's Next Action is its stage
        "next_action": vals.get("next_action"),
        "next_action_date": vals.get("next_action_date"),
        "conversion_status": c.conversion_status.value,
        "zoho_lead_id": c.zoho_lead_id,
        "progress": _progress(c),
        "meeting_count": c.meeting_count,
        "last_meeting_at": c.last_meeting_at.isoformat() if c.last_meeting_at else None,
    }


def _detail(c: Customer) -> dict[str, Any]:
    cat = load_catalog()
    vals = c.current_values or {}
    applicable = progress_keys_for(vals)
    sections = []
    for s in cat.sections:
        keys = [f.key for f in cat.fields if f.section == s["key"] and f.key in applicable]
        sections.append(
            {"key": s["key"], "label": s["label"], "filled": sum(k in vals for k in keys), "total": len(keys)}
        )
    return {
        **_card(c),
        "owner": {"id": str(c.owner_staff_id), "full_name": c.owner.full_name},
        "converted_at": c.converted_at.isoformat() if c.converted_at else None,
        # Zoho Lead sync (used once conversion has been requested).
        "lead_sync_status": c.zoho_sync_status.value,
        "lead_sync_error": c.zoho_last_error,
        "lead_sync_attempts": c.zoho_attempts,
        "sections": sections,
        "values": vals,
    }


@router.get("")
def list_customers(
    staff: CurrentStaff,
    db: DbSession,
    tab: Tab = Tab.NOT_CONVERTED,
    view: View | None = None,
    staff_id: uuid.UUID | None = None,  # an Admin looking at one SM's customers
    mine: bool = False,  # an Admin: only the customers they own
    today: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if view is not None:  # a home-screen tile: prospects and leads together
        stmt = _view_filter(scope_customers(select(Customer), staff, mine), view, today or date.today().isoformat())
    else:
        stmt = scope_customers(select(Customer).where(Customer.conversion_status.in_(TAB_STATUSES[tab])), staff, mine)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(*(Customer.current_values[k].astext.ilike(pattern) for k in SEARCH_KEYS)))
    if staff_id is not None and staff.role != StaffRole.SM:
        stmt = stmt.where(Customer.owner_staff_id == staff_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.options(selectinload(Customer.owner))
        .order_by(Customer.last_meeting_at.desc().nulls_last(), Customer.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"total": total, "items": [_card(c) for c in rows]}


@router.get("/-/summary")
def summary_counts(
    staff: CurrentStaff,
    db: DbSession,
    mine: bool = False,
    today: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    """Header numbers for the home screen: tab counts and Zoho sync state."""
    by_status = dict(
        db.execute(
            scope_customers(select(Customer.conversion_status, func.count()).select_from(Customer), staff, mine).group_by(
                Customer.conversion_status
            )
        ).all()
    )
    sync = dict(
        db.execute(
            scope_customers(
                select(Meeting.zoho_sync_status, func.count()).select_from(Meeting).join(Customer), staff, mine
            ).group_by(Meeting.zoho_sync_status)
        ).all()
    )
    day = today or date.today().isoformat()

    def count(view: View) -> int:
        return db.scalar(select(func.count()).select_from(_view_filter(scope_customers(select(Customer), staff, mine), view, day).subquery())) or 0

    return {
        "follow_ups_today": count(View.FOLLOWUPS),
        "overdue": count(View.OVERDUE),
        "not_converted": sum(by_status.get(s, 0) for s in TAB_STATUSES[Tab.NOT_CONVERTED]),
        "converted": by_status.get(ConversionStatus.CONVERTED, 0),
        "sync_pending": sync.get(SyncStatus.PENDING, 0) + sync.get(SyncStatus.SYNCING, 0),
        "sync_failed": sync.get(SyncStatus.FAILED, 0),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(body: CreateProspect, staff: FieldStaff, db: DbSession):
    try:
        customer, created = create_prospect(db, staff, body.values, body.on_duplicate, body.overwrite_customer_id)
    except InvalidValues as e:
        db.rollback()
        raise HTTPException(status_code=422, detail={"code": "INVALID_VALUES", "errors": e.errors}) from None
    except DuplicateOtherStaff:
        raise HTTPException(
            status_code=409, detail={"code": "ASSIGNED_TO_OTHER_STAFF", "message": OTHER_STAFF_MESSAGE}
        ) from None
    except DuplicateOwn as e:
        db.rollback()
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "DUPLICATE_OWN",
                    "message": "A customer with this mobile number already exists.",
                    "choices": ["overwrite", "create_new", "cancel"],
                    "matches": [
                        {
                            "id": str(m.id),
                            "lead_ref": m.lead_ref,
                            "conversion_status": m.conversion_status.value,
                            "last_meeting_at": m.last_meeting_at.isoformat() if m.last_meeting_at else None,
                            **summary(m),
                        }
                        for m in e.matches
                    ],
                }
            },
        )
    if created:
        return _detail(customer)
    return JSONResponse(status_code=200, content=_detail(customer))


@router.get("/{customer_id}")
def get_customer(customer_id: uuid.UUID, staff: CurrentStaff, db: DbSession, quiet: bool = False) -> dict:
    customer = get_visible_customer(db, staff, customer_id)
    if not quiet:  # automatic status refreshes (quiet=true) are not "views" worth auditing
        audit(db, staff, "CUSTOMER_VIEWED", customer)
        db.commit()
    return _detail(customer)


class ConvertIn(BaseModel):
    # The Zoho Lead form as confirmed on the phone: {zoho_api_name: value}.
    # Omitted when retrying a failed conversion (the earlier values are kept).
    lead_values: dict[str, Any] | None = None


async def _zoho_form_fields():
    cfg = get_settings()
    if not cfg.zoho_mcp_url:
        raise HTTPException(status_code=503, detail="The Lead form is not available yet. Please tell your admin.")
    try:
        return await leadform.load_lead_fields(cfg)
    except Exception as e:  # noqa: BLE001 - tell the app plainly instead of a server error
        raise HTTPException(status_code=503, detail=f"Could not load the Lead form: {e}"[:300]) from None


def _db_mapping(db) -> dict[str, str]:
    rows = db.execute(
        select(FieldDefinition.key, FieldDefinition.zoho_api_name).where(FieldDefinition.zoho_api_name.is_not(None))
    ).all()
    return {k: v for k, v in rows if v}


@router.get("/{customer_id}/convert-form")
async def convert_form(customer_id: uuid.UUID, staff: FieldStaff, db: DbSession) -> dict:
    """The "Convert to Lead" form: Zoho's own Lead fields, pre-filled from what the app collected."""
    customer = get_own_customer(db, staff, customer_id)
    fields = await _zoho_form_fields()
    return {
        "customer": {"id": str(customer.id), "lead_ref": customer.lead_ref, "name": (customer.current_values or {}).get("business_name") or (customer.current_values or {}).get("promoter")},
        "fields": leadform.build_form(fields, customer, _db_mapping(db)),
    }


@router.post("/{customer_id}/convert")
async def convert_to_lead(customer_id: uuid.UUID, staff: FieldStaff, db: DbSession, body: ConvertIn | None = None):
    """Explicit "Convert to Lead" action (after the user confirms the form on the phone).

    Sets the customer to CONVERTING; the Zoho Lead is created by the sync
    worker with the confirmed values, which then sets CONVERTED. Safe to repeat.
    """
    customer = get_own_customer(db, staff, customer_id)
    clean = None
    if body is not None and body.lead_values is not None:
        fields = await _zoho_form_fields()
        clean, errors = leadform.validate(fields, body.lead_values)
        if errors:
            raise HTTPException(status_code=422, detail={"code": "INVALID_VALUES", "errors": errors})
    request_conversion(db, staff, customer, clean)
    db.refresh(customer)
    return _detail(customer)
