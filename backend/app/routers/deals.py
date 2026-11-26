"""Deals: what the leads became in Zoho. Read-only: the operations team changes deals in Zoho, never here.

An SM sees only deals that came from their own leads; Admins and the Super Admin see all of them.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.access import scope_customers
from app.auth import CurrentStaff, DbSession
from app.config import Settings, get_settings
from app.models import ConversionStatus, Customer, StaffRole
from app.zoho.client import McpZoho, Zoho, ZohoError
from app.zoho.deals import deals_for

router = APIRouter(prefix="/deals", tags=["deals"])

UNREACHABLE = "Could not reach Zoho to load the deals. Try again in a moment."


async def get_zoho(cfg: Settings = Depends(get_settings)) -> AsyncIterator[Zoho | None]:
    """A Zoho connection for this request (None when Zoho is not set up). Tests replace this."""
    if not cfg.zoho_mcp_url or not cfg.zoho_sync_enabled:
        yield None
        return
    z = McpZoho(cfg.zoho_mcp_url, cfg.zoho_call_timeout_seconds)
    try:
        await z.__aenter__()
    except ZohoError:
        raise HTTPException(status_code=503, detail=UNREACHABLE) from None
    try:
        yield z
    finally:
        await z.__aexit__(None, None, None)


@router.get("")
async def list_deals(
    staff: CurrentStaff,
    db: DbSession,
    zoho: Zoho | None = Depends(get_zoho),
    customer_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,  # Admin: one SM's deals
    mine: bool = False,  # Admin: only their own
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    if zoho is None:
        return {"items": [], "zoho": False}
    stmt = scope_customers(
        select(Customer).where(Customer.conversion_status == ConversionStatus.CONVERTED, Customer.zoho_lead_id.is_not(None)),
        staff,
        mine,
    ).options(selectinload(Customer.owner))
    if customer_id is not None:
        stmt = stmt.where(Customer.id == customer_id)
    if staff_id is not None and staff.role != StaffRole.SM:
        stmt = stmt.where(Customer.owner_staff_id == staff_id)
    customers = list(db.scalars(stmt.order_by(Customer.converted_at.desc().nulls_last()).limit(limit)).all())
    try:
        found = await deals_for(db, zoho, customers)
    except ZohoError:
        db.rollback()
        raise HTTPException(status_code=503, detail=UNREACHABLE) from None
    items = []
    for c in customers:
        deal = found.get(c.id)
        if deal is None:
            continue
        vals = c.current_values or {}
        items.append(
            {
                "customer_id": str(c.id),
                "business_name": vals.get("business_name"),
                "promoter": vals.get("promoter"),
                "mobile": vals.get("mobile"),
                "sm_name": c.owner.full_name if c.owner else None,
                "deal": deal,
            }
        )
    return {"items": items, "zoho": True}
