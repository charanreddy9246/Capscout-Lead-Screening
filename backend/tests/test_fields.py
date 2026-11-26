from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import func, select

from app.fields.catalog import FieldValueError, clean_value, load_catalog, normalize_mobile, progress_keys_for
from app.models import FieldDefinition

EXCEL = Path(__file__).resolve().parents[2] / "Capitabel_MSME_Lead_Screening_Tracker.xlsx"


PAGES = {
    "lead": ["lead_id", "date", "sm_name", "assigned_to", "customer_type", "customer_type_other", "source_type", "source_name",
             "source_contact", "promoter", "mobile", "location"],
    "business": ["business_name", "poc_name", "poc_mobile", "poc_designation", "poc_email", "constitution",
                 "vintage_years", "industry", "sector"],
    "money": ["loan_required", "purpose", "urgency", "secured_unsecured", "annual_turnover",
              "monthly_banking", "monthly_surplus", "existing_debt", "monthly_emi"],
    "property": ["gst_available", "itr_financials", "bank_statements", "documents_readiness",
                 "property_available", "property_value", "existing_mortgage"],
    "assess": ["overdue", "bounces", "settlement_write_off", "litigation_dispute", "business_quality",
               "banking_quality", "credit_risk", "opportunity_grade"],
    "decide": ["potential_lender", "sm_recommendation", "next_action", "next_action_date", "follow_up_time",
               "status", "reason_comments"],
}


def test_each_page_shows_exactly_the_fields_the_client_listed_in_order():
    cat = load_catalog()
    for section, keys in PAGES.items():
        on_page = [f.key for f in sorted(cat.fields, key=lambda f: f.display_order) if f.section == section]
        assert on_page == keys, section
    assert len(cat.fields) == 52
    assert cat.progress_total == 45
    for dropped in ("likely_product", "property_type", "property_documents", "likely_product_other"):
        assert dropped not in cat.by_key  # not asked any more


def test_catalog_labels_and_options_after_the_clients_changes():
    by = load_catalog().by_key
    labels = {k: by[k].label for k in ("promoter", "mobile", "business_name", "constitution", "secured_unsecured",
                                         "annual_turnover", "next_action_date", "status", "gst_available")}
    assert labels == {
        "promoter": "Lead Name", "mobile": "Lead Contact", "business_name": "Company Name",
        "constitution": "Legal Form", "secured_unsecured": "Collateral", "annual_turnover": "Annual Turnover (₹)",
        "next_action_date": "Next Visit Date", "status": "Lead Status", "gst_available": "Company GST",
    }
    assert by["constitution"].options == (
        "General Partnership", "Limited Liability Partnership", "One Person Company",
        "Private Limited Company", "Section 8 Company", "Sole Proprietorship",
    )
    assert by["source_type"].options[0] == "Associations" and len(by["source_type"].options) == 8
    assert by["status"].options == ("Hot", "Warm", "Cold", "Reject", "New", "Cancelled")
    assert by["sector"].field_type == "single_select" and len(by["sector"].options) == 11
    assert len(by["purpose"].options) == 16 and by["purpose"].options[0] == "Business Loan"
    assert "Other Loan" in by["purpose"].options
    assert by["poc_mobile"].field_type == "phone" and by["next_action_date"].field_type == "date"
    assert by["customer_type"].options == ("Individual", "Company", "Other")
    assert by["loan_required"].unit == "₹" and by["property_value"].unit == "₹"


def test_every_excel_field_still_exists_unless_the_client_dropped_it():
    ws = openpyxl.load_workbook(EXCEL)["Lead Screening"]
    headers = [c.value for c in ws[1] if c.value is not None]
    assert len(headers) == 44  # the Excel itself is unchanged
    cat = load_catalog()
    assert len(cat.fields) >= 40


def test_every_dropdown_with_other_has_a_box_to_type_it():
    cat = load_catalog()
    for f in cat.fields:
        if f.options and "Other" in f.options:
            box = cat.by_key[f"{f.key}_other"]
            assert box.field_type == "text" and not box.counts_toward_progress and box.section == f.section


def test_progress_total_depends_on_the_answers_that_hide_fields():
    assert {"source_name", "source_contact"} <= progress_keys_for({"source_type": "DSA"})
    assert len(progress_keys_for({})) == 45
    direct = progress_keys_for({"source_type": "Direct"})
    assert not {"source_name", "source_contact"} & direct and len(direct) == 43
    no_property = progress_keys_for({"property_available": "No"})
    assert not {"property_value", "existing_mortgage"} & no_property and len(no_property) == 43
    unsecured = progress_keys_for({"secured_unsecured": "Unsecured"})
    assert not {"property_available", "property_value", "existing_mortgage"} & unsecured and len(unsecured) == 42
    assert len(progress_keys_for({"secured_unsecured": "Open to both"})) == 45
    assert len(progress_keys_for({"source_type": "Direct", "secured_unsecured": "Unsecured"})) == 40


def test_every_field_is_in_a_section():
    cat = load_catalog()
    section_keys = {s["key"] for s in cat.sections}
    assert {f.section for f in cat.fields} <= section_keys


def test_catalog_seeded_into_database(db):
    assert db.scalar(select(func.count()).select_from(FieldDefinition)) == 52
    grade = db.get(FieldDefinition, "opportunity_grade")
    assert grade.options == ["A – Priority", "B – Develop", "C – Selective", "D – Reject"]


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("source_type", "Cold Call", "Cold Call"),
        ("sector", "FMCG", "FMCG"),
        ("loan_required", "25.50", "25.5"),
        ("loan_required", 40, "40"),
        ("next_action_date", "2026-10-15", "2026-10-15"),
        ("mobile", "+91 98765 43210", "9876543210"),
        ("status", "Hot", "Hot"),
        ("litigation_dispute", "No", "No"),
        ("promoter", "", None),
    ],
)
def test_clean_value_accepts(key, value, expected):
    assert clean_value(key, value) == expected


@pytest.mark.parametrize(
    "key,value",
    [
        ("source_type", "Walk-in"),  # not one of the options
        ("status", "Follow up next week"),  # Lead Status is a dropdown now
        ("loan_required", "-5"),
        ("loan_required", "lots"),
        ("next_action_date", "15/10/2026"),
        ("mobile", "12345"),
        ("lead_id", "X"),  # system field
        ("made_up_field", "x"),
    ],
)
def test_clean_value_rejects(key, value):
    with pytest.raises(FieldValueError):
        clean_value(key, value)


def test_normalize_mobile():
    assert normalize_mobile("09876543210") == "9876543210"
    assert normalize_mobile("919876543210") == "9876543210"
    assert normalize_mobile("98765") is None
