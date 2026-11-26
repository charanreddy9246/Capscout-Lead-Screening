"""Prospect -> Lead conversion.

Lifecycle (business rule from the brief):

    NOT_CONVERTED --Convert to Lead (confirmed)--> CONVERTING
    CONVERTING --Zoho Lead created, ID stored--> CONVERTED   (moves to Converted Leads)
    CONVERTING --Zoho error--> CONVERSION_FAILED --Retry--> CONVERTING

Nothing about the customer is copied or recreated: the same customer row and
all its meetings simply change status. The Zoho call itself is made by the
sync worker (Phase 5), which reports back through `lead_created` /
`lead_creation_failed`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fields.catalog import load_catalog
from app.models import ConversionStatus, Customer, FollowUp, FollowUpStatus, Staff, SyncStatus
from app.services.customers import apply_values, audit


class AlreadyLinkedElsewhere(Exception):
    """The Zoho Lead ID is already stored on a different customer."""


def request_conversion(
    db: Session, staff: Staff, customer: Customer, lead_values: dict | None = None
) -> bool:
    """Start (or retry) conversion. Returns False if nothing needed doing.

    `lead_values` is the Zoho Lead form as confirmed by the staff member; it is stored and
    sent to Zoho as is. A retry without values keeps the ones stored earlier.

    Repeated taps / retried requests are harmless: a customer that is already
    converting or converted is returned unchanged.
    """
    db.execute(select(Customer.id).where(Customer.id == customer.id).with_for_update())
    db.refresh(customer)
    if customer.conversion_status in (ConversionStatus.CONVERTING, ConversionStatus.CONVERTED):
        db.rollback()
        return False

    retry = customer.conversion_status == ConversionStatus.CONVERSION_FAILED
    if lead_values is not None:
        customer.zoho_lead_payload = lead_values
    customer.conversion_status = ConversionStatus.CONVERTING
    customer.converted_by_staff_id = staff.id
    customer.zoho_sync_status = SyncStatus.PENDING
    customer.zoho_next_attempt_at = datetime.now(UTC)
    customer.zoho_last_error = None
    if retry:
        customer.zoho_attempts = 0
    audit(db, staff, "LEAD_CONVERSION_RETRIED" if retry else "LEAD_CONVERSION_REQUESTED", customer)
    db.commit()
    return True


FIRST_STAGE = "Document collection"


def _start_the_loan_journey(db: Session, customer: Customer) -> None:
    """A new lead starts at the first stage. A leftover prospect value is not a stage, so it is replaced."""
    stages = next(f for f in load_catalog().fields if f.key == "next_action").options or ()
    if (customer.current_values or {}).get("next_action") in stages:
        return
    apply_values(customer, {"next_action": FIRST_STAGE})
    for fu in db.scalars(select(FollowUp).where(FollowUp.customer_id == customer.id, FollowUp.status == FollowUpStatus.PENDING)):
        if fu.purpose not in stages:
            fu.purpose = FIRST_STAGE


def lead_created(db: Session, customer: Customer, zoho_lead_id: str) -> None:
    """Called once Zoho has created the Lead. Moves the customer to Converted Leads."""
    clash = db.scalar(select(Customer.id).where(Customer.zoho_lead_id == zoho_lead_id, Customer.id != customer.id))
    if clash:
        raise AlreadyLinkedElsewhere(zoho_lead_id)
    customer.zoho_lead_id = zoho_lead_id
    customer.conversion_status = ConversionStatus.CONVERTED
    customer.converted_at = datetime.now(UTC)
    _start_the_loan_journey(db, customer)
    customer.zoho_sync_status = SyncStatus.SYNCED
    customer.zoho_last_error = None
    customer.zoho_next_attempt_at = None
    db.commit()


def lead_creation_failed(
    db: Session, customer: Customer, error: str, final: bool, retry_at: datetime | None = None
) -> None:
    """Record a failed Zoho attempt. `final` = give up retrying automatically."""
    customer.zoho_attempts += 1
    customer.zoho_last_error = error[:2000]
    customer.zoho_sync_status = SyncStatus.FAILED
    if final:
        customer.conversion_status = ConversionStatus.CONVERSION_FAILED
        customer.zoho_next_attempt_at = None
    else:
        customer.zoho_next_attempt_at = retry_at
    db.commit()
