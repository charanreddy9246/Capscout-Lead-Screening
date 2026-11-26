"""Deals: read-only, from Zoho, only for the SM's own converted leads (a FAKE Zoho is used)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.main import create_app
from app.models import ConversionStatus, Customer, StaffRole
from app.routers.deals import get_zoho
from app.zoho import deals as deals_mod
from app.zoho.client import ZohoUnavailable
from tests.test_follow_ups import _customer


class DealsFake:
    """Zoho as it really behaves: a converted lead is left out of a plain query and only found with
    Converted__s = true; the deal is created at the same second as the conversion."""

    def __init__(self):
        self.leads: dict[str, dict] = {}  # lead id -> {"company", "at"} (only the converted ones)
        self.deals: dict[str, dict] = {}  # deal id -> fields (incl. Created_Time, Account_Name)
        self.calls: list[str] = []
        self.down = False

    def convert(self, lead, company, deal, at="2026-11-25T12:53:01+05:30", account=None, **fields):
        self.leads[lead] = {"Company": company, "Converted_Date_Time": at}
        self.deals[deal] = {"Deal_Name": company, "Created_Time": at, "Account_Name": {"name": account or company}, **fields}

    async def call(self, tool, arguments):
        self.calls.append(tool)
        if self.down:
            raise ZohoUnavailable("network down")
        q = arguments["body"]["select_query"]
        if "from Leads" in q:
            assert "Converted__s = true" in q, "a plain query would miss converted leads"
            ids = [p.strip("' ") for p in q.split("in (")[1].rstrip(") ").split(",")]
            return {"data": {"data": [{"id": i, **self.leads[i]} for i in ids if i in self.leads]}}
        if "Created_Time between" in q:
            at = q.split("between '")[1].split("'")[0]
            return {"data": {"data": [{"id": i, **d} for i, d in self.deals.items() if d["Created_Time"] == at]}}
        ids = [p.strip("' ") for p in q.split("in (")[1].rstrip(") ").split(",")]
        return {"data": {"data": [{"id": i, **self.deals[i]} for i in ids if i in self.deals]}}


@pytest.fixture(autouse=True)
def _fresh_cache():
    deals_mod.clear_cache()


@pytest.fixture
def zoho(client):
    fake = DealsFake()

    async def _fake():
        yield fake

    client.app.dependency_overrides[get_zoho] = _fake
    yield fake
    client.app.dependency_overrides.pop(get_zoho, None)


def _make_lead(client, db, headers, lead_id, mobile, name):
    cid = _customer(client, headers) if False else client.post(
        "/api/customers", json={"values": {"promoter": name, "business_name": name, "mobile": mobile}}, headers=headers
    ).json()["id"]
    c = db.get(Customer, cid)
    c.conversion_status = ConversionStatus.CONVERTED
    c.zoho_lead_id = lead_id
    db.commit()
    return cid


def test_a_converted_lead_shows_its_deal_and_the_deal_id_is_remembered(client, make_staff, db, zoho):
    _, sm = make_staff("SM1")
    cid = _make_lead(client, db, sm, "L1", "9876501001", "Acme")
    _make_lead(client, db, sm, "L2", "9876501002", "Not Yet")  # never converted in Zoho
    zoho.convert("L1", "Acme", "D1", Amount=500000, Stage="Negotiation/Review", Owner={"name": "Ops Team"})
    zoho.deals["D1"]["Deal_Name"] = "Acme loan"  # operations renamed the deal: the match does not depend on its name

    items = client.get("/api/deals", headers=sm).json()["items"]
    assert [(i["customer_id"], i["deal"]["name"], i["deal"]["stage"], i["deal"]["owner"]) for i in items] == [(cid, "Acme loan", "Negotiation/Review", "Ops Team")]
    assert db.scalar(select(Customer.zoho_deal_id).where(Customer.id == cid)) == "D1"  # remembered

    # operations move it in Zoho: the next read (after the short cache) shows the new stage, nothing else needed
    deals_mod.clear_cache()
    zoho.deals["D1"]["Stage"] = "Closed Won"
    assert client.get("/api/deals", headers=sm).json()["items"][0]["deal"]["stage"] == "Closed Won"
    # the second time the conversion question is not asked again for a lead we already know
    n = len([c for c in zoho.calls])
    client.get("/api/deals", headers=sm)
    assert not any("Leads" in str(c) for c in zoho.calls[n:])  # a lead we already know is not asked about again


def test_each_sm_only_sees_their_own_deals_and_admins_see_all(client, make_staff, db, zoho):
    _, a = make_staff("SM1")
    _, b = make_staff("SM2")
    _, admin = make_staff("AD1", role=StaffRole.ADMIN)
    _, sup = make_staff("SU1", role=StaffRole.SUPER_ADMIN)
    _make_lead(client, db, a, "LA", "9876501011", "A Co")
    _make_lead(client, db, b, "LB", "9876501012", "B Co")
    zoho.convert("LA", "A Co", "DA", at="2026-11-25T10:00:01+05:30", Stage="Qualification")
    zoho.convert("LB", "B Co", "DB", at="2026-11-25T10:05:09+05:30", Stage="Qualification")
    zoho.deals["DA"]["Deal_Name"], zoho.deals["DB"]["Deal_Name"] = "DA deal", "DB deal"
    names = lambda who: sorted(i["deal"]["name"] for i in client.get("/api/deals", headers=who).json()["items"])  # noqa: E731
    assert names(a) == ["DA deal"] and names(b) == ["DB deal"]
    assert names(admin) == ["DA deal", "DB deal"] and names(sup) == ["DA deal", "DB deal"]


def test_deals_are_read_only_and_a_lead_without_a_deal_is_left_out(client, make_staff, db, zoho):
    _, sm = make_staff("SM1")
    _make_lead(client, db, sm, "L1", "9876501021", "Plain")
    assert client.get("/api/deals", headers=sm).json()["items"] == []
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/deals", headers=sm).status_code in (404, 405)


def test_zoho_being_down_gives_a_clear_message_not_a_crash(client, make_staff, db, zoho):
    _, sm = make_staff("SM1")
    _make_lead(client, db, sm, "L1", "9876501031", "Acme")
    zoho.down = True
    r = client.get("/api/deals", headers=sm)
    assert r.status_code == 503 and "Zoho" in r.json()["detail"]


def test_without_zoho_set_up_the_list_is_simply_empty(client, make_staff):
    _, sm = make_staff("SM1")
    assert client.get("/api/deals", headers=sm).json() == {"items": [], "zoho": False}


def test_a_lead_is_not_matched_to_someone_elses_deal_made_at_another_time(client, make_staff, db, zoho):
    _, sm = make_staff("SM1")
    _make_lead(client, db, sm, "L1", "9876501041", "Acme")
    zoho.leads["L1"] = {"Company": "Acme", "Converted_Date_Time": "2026-11-25T12:53:01+05:30"}
    zoho.deals["X"] = {"Deal_Name": "Other", "Created_Time": "2026-11-25T09:00:00+05:30", "Account_Name": {"name": "Other"}}
    assert client.get("/api/deals", headers=sm).json()["items"] == []  # converted, but no deal to show: nothing is guessed
