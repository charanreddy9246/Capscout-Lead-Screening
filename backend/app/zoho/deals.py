"""Deals: read-only, straight from Zoho.

Operations update deals in Zoho; the app only shows them. The link is the lead: we already store each
lead's Zoho Lead ID and its SM. For an SM's converted leads we ask Zoho whether the lead became a deal
(and which one), remember that Deal ID on our customer, and read the deal's current details live.
Nothing about a deal except its ID is copied into our database.

Only a read tool is used (executeCOQLQuery).

How a converted lead is matched to its deal: a plain Zoho query leaves converted leads out, so we ask for
them explicitly (Converted__s = true). Zoho creates the deal in the same second it converts the lead, so
the deal is the one created at the lead's Converted_Date_Time, with the lead's company as its account.
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer
from app.zoho.client import Zoho, records_from

CACHE_SECONDS = 60
CHUNK = 50  # ids per COQL query

# lead id -> when we last saw that it was NOT converted; deal id -> (when, details)
_not_converted: dict[str, float] = {}
_details: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_cache() -> None:
    _not_converted.clear()
    _details.clear()


def _quoted(ids: list[str]) -> str:
    return ", ".join("'" + i.replace("'", "") + "'" for i in ids)


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


def _same(a: Any, b: Any) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower() and bool(str(a or "").strip())


def pick_deal(candidates: list[dict[str, Any]], company: str | None) -> str | None:
    """The deal made by the conversion: the one whose account (or name) is the lead's company.

    If the name was changed during conversion but only one deal was made at that second, that one is it.
    """
    for d in candidates:
        account = d.get("Account_Name")
        if _same(account.get("name") if isinstance(account, dict) else None, company) or _same(d.get("Deal_Name"), company):
            return str(d["id"])
    return str(candidates[0]["id"]) if len(candidates) == 1 else None


def _shape(rec: dict[str, Any]) -> dict[str, Any]:
    owner = rec.get("Owner")
    return {
        "id": str(rec["id"]),
        "name": rec.get("Deal_Name"),
        "amount": rec.get("Amount"),
        "stage": rec.get("Stage"),
        "closing_date": rec.get("Closing_Date"),
        "next_step": rec.get("Next_Step"),
        "owner": owner.get("name") if isinstance(owner, dict) else None,
        "modified_at": rec.get("Modified_Time"),
    }


async def _coql(zoho: Zoho, query: str) -> list[dict[str, Any]]:
    return records_from(await zoho.call("executeCOQLQuery", {"body": {"select_query": query}}))


async def deals_for(db: Session, zoho: Zoho, customers: list[Customer]) -> dict[Any, dict[str, Any]]:
    """{customer id: deal} for the customers that have become a deal."""
    now = time.monotonic()
    by_lead = {c.zoho_lead_id: c for c in customers if c.zoho_lead_id}

    # 1. which leads have become deals? (one query for all the ones we do not know yet)
    unknown = [
        lead for lead, c in by_lead.items()
        if not c.zoho_deal_id and now - _not_converted.get(lead, -CACHE_SECONDS) >= CACHE_SECONDS
    ]
    found_converted: dict[str, dict[str, Any]] = {}
    for i in range(0, len(unknown), CHUNK):
        chunk = unknown[i : i + CHUNK]
        rows = await _coql(
            zoho,
            "select id, Company, Converted_Date_Time from Leads "
            f"where Converted__s = true and id in ({_quoted(chunk)})",
        )
        found_converted.update({str(r["id"]): r for r in rows})
        for lead in chunk:
            if lead not in found_converted:
                _not_converted[lead] = now
    for lead, row in found_converted.items():
        at = str(row.get("Converted_Date_Time") or "")
        if not _ISO.match(at):
            continue
        deals = await _coql(
            zoho,
            f"select id, Deal_Name, Account_Name from Deals where Created_Time between '{at}' and '{at}'",
        )
        deal_id = pick_deal(deals, row.get("Company"))
        if not deal_id:
            continue  # converted without a deal, or we cannot tell which one it is: show nothing rather than guess
        taken = db.scalar(select(Customer.id).where(Customer.zoho_deal_id == deal_id, Customer.id != by_lead[lead].id))
        if taken is None:
            by_lead[lead].zoho_deal_id = deal_id
    db.commit()

    # 2. the current details of each known deal
    wanted = {c.zoho_deal_id: c for c in by_lead.values() if c.zoho_deal_id}
    stale = [d for d in wanted if d not in _details or now - _details[d][0] >= CACHE_SECONDS]
    for i in range(0, len(stale), CHUNK):
        chunk = stale[i : i + CHUNK]
        rows = await _coql(
            zoho,
            "select id, Deal_Name, Amount, Stage, Closing_Date, Next_Step, Owner, Modified_Time "
            f"from Deals where id in ({_quoted(chunk)})",
        )
        for r in rows:
            _details[str(r["id"])] = (now, _shape(r))
    return {c.id: _details[d][1] for d, c in wanted.items() if d in _details}
