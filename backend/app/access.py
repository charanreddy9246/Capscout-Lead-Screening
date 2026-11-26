"""Role-based data access. Every customer query goes through here.

  SM           sees only the customers they own.
  ADMIN        sees every customer (all SMs).
  SUPER_ADMIN  sees everything an Admin sees, and also manages the Admins.

Two separate rules: the ROLE decides what you may SEE; OWNERSHIP decides what you may CHANGE. Everyone,
whatever the role, can only change customers they own. An Admin can also ask for "mine" to see just their own.

The rules live on the server, so a changed phone app cannot get around them.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Customer, Staff, StaffRole


def scope_customers(stmt: Select, staff: Staff, mine: bool = False) -> Select:
    if staff.role in (StaffRole.ADMIN, StaffRole.SUPER_ADMIN) and not mine:
        return stmt
    return stmt.where(Customer.owner_staff_id == staff.id)


def get_visible_customer(db: Session, staff: Staff, customer_id: uuid.UUID) -> Customer:
    """Return the customer or 404. Never reveals that another staff member's record exists."""
    customer = db.scalar(scope_customers(select(Customer).where(Customer.id == customer_id), staff))
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return customer


def get_own_customer(db: Session, staff: Staff, customer_id: uuid.UUID) -> Customer:
    """For every change: the customer must be visible AND owned by this person (403 if only visible)."""
    customer = get_visible_customer(db, staff, customer_id)
    if customer.owner_staff_id != staff.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the person who owns this customer can change it.")
    return customer

