"""Starter wording for the message an SM sends a customer, chosen by the customer's Next Action.

The text is only a draft: the SM reads and edits it before sending. These are plain starter
sentences for the client to approve or reword (they must not promise approval or quote figures).
"""

from __future__ import annotations

from datetime import datetime

from app.models import Customer, Staff
from app.services.follow_ups import local

COMPANY = "CapScout"

# {name} {sm} {company} {visit} are filled in. {visit} is empty when no visit is planned.
TEMPLATES: dict[str, str] = {
    # A lead's stage (its Next Action)
    "Document collection": "Hi {name}, as discussed, please share the pending documents (for example bank statements and KYC) so we can move your application forward.{visit} Thank you, {sm}, {company}",
    "Identify bank": "Hi {name}, we are matching your requirement with suitable lenders and will update you soon.{visit} Regards, {sm}, {company}",
    "Disbursement": "Hi {name}, thank you for choosing {company}. We are glad we could help with your loan. Regards, {sm}",
    # Older values, kept so existing customers still get a sensible draft
    "New": "Hi {name}, thank you for meeting with us. I'm {sm} from {company}. I'll be in touch shortly about your loan requirement.{visit}",
    "Qualified": "Hi {name}, thank you for your time. Based on our discussion, we will now shortlist suitable loan options for you.{visit}",
    "Documents Pending": "Hi {name}, as discussed, please share the pending documents (for example bank statements and KYC) so we can move your application forward.{visit} Thank you, {sm}, {company}",
    "Lender Matching": "Hi {name}, we are matching your requirement with suitable lenders and will update you soon.{visit} Regards, {sm}, {company}",
    "Login": "Hi {name}, your application is being submitted to the lender. We will keep you posted on the progress.{visit} Regards, {sm}, {company}",
    "Sanction": "Hi {name}, your application is under review for sanction. We will update you as soon as we have news.{visit} Regards, {sm}, {company}",
    "Disbursed": "Hi {name}, thank you for choosing {company}. We are glad we could help with your loan. Regards, {sm}",
    "Dropped": "Hi {name}, thank you for your time. If your requirement changes, please contact me anytime. Regards, {sm}, {company}",
}
DEFAULT = "Hi {name}, this is {sm} from {company}, following up on our meeting.{visit}"


def _first_name(vals: dict) -> str:
    who = (vals.get("promoter") or "").strip() or (vals.get("business_name") or "").strip() or "there"
    return who.split()[0] if vals.get("promoter") else who


def draft(customer: Customer, staff: Staff, next_visit: datetime | None) -> str:
    vals = customer.current_values or {}
    visit = ""
    if next_visit is not None:
        d = local(next_visit)
        visit = f" Our next visit is on {d:%a, %d %b} at {d:%I:%M %p}.".replace(" 0", " ")
    text = TEMPLATES.get(vals.get("next_action") or "", DEFAULT)
    return text.format(name=_first_name(vals), sm=staff.full_name, company=COMPANY, visit=visit)
