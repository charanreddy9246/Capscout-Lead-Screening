"""Generate app/fields/fields_v1.json from the client's Excel tracker.

The Excel file is the source of truth for field labels and dropdown options.
This script adds only what the Excel cannot express: a stable key, an input
type, and the mobile section each field belongs to. It fails loudly if the
Excel headers ever stop matching that mapping, so nothing is silently renamed.

Usage (from backend/):  uv run python scripts/extract_fields.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.cell_range import CellRange

ROOT = Path(__file__).resolve().parents[2]
EXCEL_PATH = ROOT / "Capitabel_MSME_Lead_Screening_Tracker.xlsx"
OUT_PATH = Path(__file__).resolve().parents[1] / "app" / "fields" / "fields_v1.json"

# Mobile steps, in display order, as in the client's UI prototype
# (MSME_Lead_Screening_Prototype.html): Lead, Business, Money, Property, Assess, Decide.
SECTIONS = [
    ("lead", "Lead & source"),
    ("business", "Company & contact"),
    ("money", "Loan & financials"),
    ("property", "Documents & property"),
    ("assess", "Credit & screening"),
    ("decide", "Recommendation & next action"),
]

# exact Excel label -> (key, field_type, section, unit, system_source)
# field_type "system" = filled by the app, excluded from progress (41 of 44 count).
# Within a section, fields display in the order listed here.
FIELD_MAP: dict[str, tuple[str, str, str, str | None, str | None]] = {
    "Lead ID": ("lead_id", "system", "lead", None, "application_ref"),
    "Date": ("date", "system", "lead", None, "meeting_date"),
    "SM Name": ("sm_name", "system", "lead", None, "staff_name"),
    "Source Type": ("source_type", "single_select", "lead", None, None),
    "Source Name": ("source_name", "text", "lead", None, None),
    "Source Contact": ("source_contact", "text", "lead", None, None),
    "Business Name": ("business_name", "text", "lead", None, None),
    "Promoter": ("promoter", "text", "lead", None, None),
    "Mobile": ("mobile", "phone", "lead", None, None),
    "Location": ("location", "text", "lead", None, None),
    "Constitution": ("constitution", "single_select", "business", None, None),
    "Industry": ("industry", "text", "business", None, None),
    "Vintage (Years)": ("vintage_years", "number", "business", "Years", None),
    "Loan Required (₹L)": ("loan_required", "number", "business", "₹L", None),
    "Purpose": ("purpose", "single_select", "business", None, None),
    "Urgency": ("urgency", "single_select", "business", None, None),
    "Secured/Unsecured": ("secured_unsecured", "single_select", "business", None, None),
    "Annual Turnover (₹L)": ("annual_turnover", "number", "money", "₹L", None),
    "Monthly Banking (₹L)": ("monthly_banking", "number", "money", "₹L", None),
    "Monthly Surplus (₹L)": ("monthly_surplus", "number", "money", "₹L", None),
    "Existing Debt (₹L)": ("existing_debt", "number", "money", "₹L", None),
    "Monthly EMI (₹L)": ("monthly_emi", "number", "money", "₹L", None),
    "GST Available": ("gst_available", "single_select", "money", None, None),
    "ITR/Financials": ("itr_financials", "single_select", "money", None, None),
    "Bank Statements": ("bank_statements", "single_select", "money", None, None),
    "Documents Readiness": ("documents_readiness", "single_select", "assess", None, None),
    "Property Available": ("property_available", "single_select", "property", None, None),
    "Property Value (₹L)": ("property_value", "number", "property", "₹L", None),
    "Existing Mortgage": ("existing_mortgage", "single_select", "property", None, None),
    "Overdue": ("overdue", "single_select", "property", None, None),
    "Bounces": ("bounces", "single_select", "property", None, None),
    "Settlement/Write-off": ("settlement_write_off", "single_select", "property", None, None),
    # No dropdown in the Excel; kept as free text per client decision.
    "Litigation/Dispute": ("litigation_dispute", "text", "property", None, None),
    "Business Quality": ("business_quality", "single_select", "assess", None, None),
    "Banking Quality": ("banking_quality", "single_select", "assess", None, None),
    "Credit Risk": ("credit_risk", "single_select", "assess", None, None),
    "Opportunity Grade": ("opportunity_grade", "single_select", "assess", None, None),
    "Likely Product": ("likely_product", "single_select", "assess", None, None),
    "Potential Lender": ("potential_lender", "text", "assess", None, None),
    "SM Recommendation": ("sm_recommendation", "single_select", "decide", None, None),
    # No dropdown in the Excel; kept as free text per client decision.
    "Status": ("status", "text", "decide", None, None),
    "Next Action": ("next_action", "single_select", "decide", None, None),
    "Next Action Date": ("next_action_date", "date", "decide", None, None),
    "Reason/Comments": ("reason_comments", "long_text", "decide", None, None),
}


# --- the client's own changes to the Excel list ---------------------------------------------------
# Applied on top of the Excel so re-running this script never undoes them. Keys never change
# (stored values and Zoho mappings keep working); labels, options, new fields and the LAYOUT below do.
# Decided 2026-10-08 and reworked page by page on 2026-10-27.
RELABEL = {
    "sm_name": "Lead Owner",
    "source_type": "Lead Source",
    "source_name": "Referred By",
    "promoter": "Lead Name",
    "mobile": "Lead Contact",
    "location": "GPS Location",
    "business_name": "Company Name",
    "constitution": "Legal Form",
    "industry": "Company Industry",
    "loan_required": "Requested Loan Amount (₹)",
    "secured_unsecured": "Collateral",
    # Amounts are typed in full rupees (with commas), not in lakhs.
    "annual_turnover": "Annual Turnover (₹)",
    "monthly_banking": "Monthly Banking (₹)",
    "monthly_surplus": "Monthly Surplus (₹)",
    "existing_debt": "Existing Debt (₹)",
    "monthly_emi": "Monthly EMI (₹)",
    "gst_available": "Company GST",
    "property_value": "Property Value (₹)",
    "next_action_date": "Next Visit Date",
    "status": "Lead Status",
}
# Typed as a 10-digit mobile number (the Excel had it as plain text).
PHONE_FIELDS = ["source_contact"]
RUPEE_FIELDS = [
    "loan_required", "annual_turnover", "monthly_banking", "monthly_surplus",
    "existing_debt", "monthly_emi", "property_value",
]
# Dropdown lists sent by the client (2026-10-28). A field listed here becomes a dropdown with exactly
# these options (Sector and Lead Status used to be typed). These lists have no "Other" option.
SET_OPTIONS: dict[str, list[str]] = {
    "source_type": [  # shown as "Lead Source"
        "Associations", "Channel Partnership", "Cold Call", "Customer Referral",
        "Employee Referral", "External Referral", "Field Activity", "Partner",
    ],
    "constitution": [  # shown as "Legal Form"
        "General Partnership", "Limited Liability Partnership", "One Person Company",
        "Private Limited Company", "Section 8 Company", "Sole Proprietorship",
    ],
    "sector": [
        "Auto Components", "Automobile & Commercial Vehicles", "Chemicals & Pharmaceuticals",
        "Civil Contractor & Construction", "Electronics & Electrical", "Engineering & Fabrication",
        "FMCG", "Food Processing & Agro", "Healthcare", "Hospitality", "Leather & Footwear",
    ],
    "purpose": [
        "Business Loan", "Commercial Loan - Commercial Land / Property", "Home Loan - Balance + Top Up",
        "Home Loan - Balance Transfer", "Home Loan - Construction", "Home Loan - Extension/ Improvement",
        "Home Loan - New Purchase", "Home Loan - Plot", "Home Loan - Top Up", "Loan Against Property",
        "Other Loan", "Personal Loan", "Vehicle Loan", "Working Capital", "Expansion", "Capex",
    ],
    "status": ["Hot", "Warm", "Cold", "Reject", "New", "Cancelled"],  # shown as "Lead Status"
    "litigation_dispute": ["Yes", "No", "Unknown"],  # was typed
    # Next Action is asked in meetings with a converted Lead only: it is the stage of the loan file, in order.
    "next_action": ["Document collection", "Identify bank", "Login", "Sanction", "Disbursement"],
}
# Asked only for leads, so it cannot count towards a prospect's progress.
NOT_COUNTED = ["next_action"]

# What each page shows, in order. A field that is in the Excel but not listed here is NOT asked.
LAYOUT: dict[str, list[str]] = {
    "lead": [
        "lead_id", "date", "sm_name", "assigned_to", "customer_type", "customer_type_other", "source_type",
        "source_name", "source_contact", "promoter", "mobile", "location",
    ],
    "business": [
        "business_name", "poc_name", "poc_mobile", "poc_designation", "poc_email",
        "constitution", "vintage_years", "industry", "sector",
    ],
    "money": [
        "loan_required", "purpose", "urgency", "secured_unsecured",
        "annual_turnover", "monthly_banking", "monthly_surplus", "existing_debt", "monthly_emi",
    ],
    "property": [
        "gst_available", "itr_financials", "bank_statements", "documents_readiness",
        "property_available", "property_value", "existing_mortgage",
    ],
    "assess": [
        "overdue", "bounces", "settlement_write_off", "litigation_dispute",
        "business_quality", "banking_quality", "credit_risk", "opportunity_grade",
    ],
    "decide": [
        "potential_lender", "sm_recommendation", "next_action", "next_action_date",
        "follow_up_time", "status", "reason_comments",
    ],
}


def _field(key: str, label: str, ftype: str, section: str, options=None, counts: bool = True) -> dict:
    return {
        "key": key, "label": label, "field_type": ftype, "options": options, "unit": None,
        "section": section, "counts_toward_progress": counts, "system_source": None,
    }


def _text_other(of: str, label: str, section: str) -> dict:
    """The "type it here" box shown when the dropdown `of` is set to "Other" (not counted in progress)."""
    return _field(f"{of}_other", f"{label} (Other)", "text", section, counts=False)


# Fixed positions for the new fields (they must stay the same forever: the database keeps them unique).
NEW_POSITIONS = {
    "constitution_other": 45,
    "source_type_other": 46,
    "purpose_other": 47,
    "customer_type": 52,
    "customer_type_other": 59,
    "assigned_to": 60,
    "poc_name": 53,
    "poc_mobile": 54,
    "poc_designation": 55,
    "poc_email": 56,
    "sector": 57,
    "next_visit_date": 58,
    "follow_up_time": 62,
}

# Fields that are not in the Excel at all.
NEW_FIELDS = [
    # Filled in by the app with the signed-in sales manager's name, like Lead Owner. Never typed.
    {
        "key": "assigned_to", "label": "Assigned To", "field_type": "system", "options": None, "unit": None,
        "section": "lead", "counts_toward_progress": False, "system_source": "staff_name",
    },
    _field("customer_type", "Type of Customer", "single_select", "lead", options=["Individual", "Company", "Other"]),
    _text_other("customer_type", "Type of Customer", "lead"),
    _field("poc_name", "POC Name", "text", "business"),
    _field("poc_mobile", "POC Contact Mobile", "phone", "business"),
    _field("poc_designation", "POC Designation", "text", "business"),
    _field("poc_email", "POC Email ID", "text", "business"),
    _field("sector", "Sector", "text", "business"),
    _field("next_visit_date", "Next Visit Date", "date", "decide"),  # no longer asked: Follow-ups replace it
    # The time of the follow-up that "Next Action Date" sets (HH:MM). Not counted in progress.
    _field("follow_up_time", "Next Visit Time", "text", "decide", counts=False),
]


def apply_client_changes(fields: list[dict]) -> list[dict]:
    for f in fields:
        if f["key"] in RELABEL:
            f["label"] = RELABEL[f["key"]]
        if f["key"] in NOT_COUNTED:
            f["counts_toward_progress"] = False
        if f["key"] in RUPEE_FIELDS:
            f["unit"] = "₹"
        if f["key"] in PHONE_FIELDS:
            f["field_type"] = "phone"
        if f["key"] in SET_OPTIONS:
            assert len(SET_OPTIONS[f["key"]]) == len(set(SET_OPTIONS[f["key"]])), f"duplicate option in {f['key']}"
            f["field_type"] = "single_select"
            f["options"] = SET_OPTIONS[f["key"]]
    for new in NEW_FIELDS:
        fields.append({"excel_column": "new", "position": NEW_POSITIONS[new["key"]], **new})
    for f in fields:  # also the new fields (Sector is one)
        if f["key"] in SET_OPTIONS:
            f["field_type"] = "single_select"
            f["options"] = SET_OPTIONS[f["key"]]
    by_key = {f["key"]: f for f in fields}
    listed = [k for keys in LAYOUT.values() for k in keys]
    assert len(listed) == len(set(listed)), "a field is listed on two pages"
    missing = [k for k in listed if k not in by_key]
    assert not missing, f"LAYOUT lists unknown fields: {missing}"
    # The pages, in order; anything not listed is dropped. Order inside a page follows LAYOUT.
    out: list[dict] = []
    for section, keys in LAYOUT.items():
        for order, key in enumerate(keys, start=1):
            f = by_key[key]
            f["section"] = section
            f["display_order"] = order
            out.append(f)
    return out


def dropdowns_by_column(ws) -> dict[str, list[str]]:
    """Map column letter -> list options from the sheet's data validations."""
    result: dict[str, list[str]] = {}
    for dv in ws.data_validations.dataValidation:
        if dv.type != "list" or not dv.formula1:
            continue
        options = [o.strip() for o in dv.formula1.strip('"').split(",")]
        for rng in str(dv.sqref).split():
            cr = CellRange(rng)
            for col in range(cr.min_col, cr.max_col + 1):
                result[get_column_letter(col)] = options
    return result


def main() -> int:
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["Lead Screening"]
    headers = [c.value for c in ws[1] if c.value is not None]
    if len(headers) != 44:
        print(f"Expected 44 headers, found {len(headers)}", file=sys.stderr)
        return 1
    if set(headers) != set(FIELD_MAP):
        print("Excel headers no longer match FIELD_MAP:", file=sys.stderr)
        print("  only in Excel:", sorted(set(headers) - set(FIELD_MAP)), file=sys.stderr)
        print("  only in map:  ", sorted(set(FIELD_MAP) - set(headers)), file=sys.stderr)
        return 1

    dropdowns = dropdowns_by_column(ws)
    section_order = {key: i for i, (key, _) in enumerate(SECTIONS, start=1)}
    # Order inside a step follows FIELD_MAP (the prototype's screen order).
    display_counter: dict[str, int] = {}
    display_order: dict[str, int] = {}
    for label, (_, _, section, _, _) in FIELD_MAP.items():
        display_counter[section] = display_counter.get(section, 0) + 1
        display_order[label] = display_counter[section]
    fields = []
    for position, label in enumerate(headers, start=1):
        key, ftype, section, unit, system_source = FIELD_MAP[label]
        col = get_column_letter(position)
        assert column_index_from_string(col) == position
        options = dropdowns.get(col)
        if ftype == "single_select" and not options:
            print(f"{label} mapped as single_select but has no dropdown", file=sys.stderr)
            return 1
        if options and ftype != "single_select":
            print(f"{label} has a dropdown but is mapped as {ftype}", file=sys.stderr)
            return 1
        fields.append(
            {
                "key": key,
                "label": label,
                "excel_column": col,
                "position": position,
                "field_type": ftype,
                "options": options,
                "unit": unit,
                "section": section,
                "display_order": display_order[label],
                "counts_toward_progress": ftype != "system",
                "system_source": system_source,
            }
        )

    fields = apply_client_changes(fields)
    out = {
        "version": 1,
        "source": EXCEL_PATH.name,
        "sections": [
            {"key": k, "label": lbl, "display_order": section_order[k]} for k, lbl in SECTIONS
        ],
        "fields": fields,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    progress = sum(f["counts_toward_progress"] for f in fields)
    print(f"Wrote {len(fields)} fields ({progress} count toward progress) to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
