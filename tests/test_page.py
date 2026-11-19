"""The two pages under Manage, and their read tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.suites import Recorder
from meridian.testing import PageClient

from bank_of_canada import page as page_module
from bank_of_canada.page import CONNECTION, DATASETS_PAGE, figures, hold, pages

from conftest import HELD, INSTANCE, feed, resolving


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    work = feed(tmp_path, resolving(Recorder(INSTANCE), "Zero-coupon yield curve"))
    asyncio.run(work.check())
    hold(work)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        (CONNECTION, "admin"): 200,
        (CONNECTION, "write"): 403,
        (CONNECTION, "read"): 403,
        (DATASETS_PAGE, "admin"): 200,
        (DATASETS_PAGE, "write"): 403,
        (DATASETS_PAGE, "read"): 403,
    }
    client.assert_no_account_data("1.4326", "117.68209047", "2.5500")


def test_connection_and_its_sources(client: PageClient) -> None:
    text = client.get(CONNECTION, "admin").text
    assert "No key needed" in text and "Does not stream" in text and "1 record not held" in text
    sources = client.get(CONNECTION, "admin", tab="sources").text
    assert sources.count("<tr data-source=") == 4
    assert "Wed 18 Nov 2026" in sources and "Wed 28 Oct 2026" in sources


def test_datasets_and_records(client: PageClient) -> None:
    text = client.get(DATASETS_PAGE, "admin").text
    assert all(f"bank-of-canada:{k}" in text for k in ("boc_rates", "boc_curves", "boc_fx"))
    records = client.get(DATASETS_PAGE, "admin", tab="records").text
    assert 'data-code="CORRA"' in records and 'data-code="USD"' in records
    assert 'data-code="BD.CDN.LONG.DQ.YLD"' in records and "Source: Bank of Canada" in records
    searched = client.get(DATASETS_PAGE, "admin", q="CORRA").text
    assert searched.count("<tr data-code=") == 2


def test_the_tools_answer_what_the_pages_show(client: PageClient) -> None:
    data = client.call_tool("read_connection").data
    assert data["mode"] == "Sample data" and [s["dataset"] for s in data["sources"]] == [
        "bank-of-canada:boc_rates", "bank-of-canada:boc_curves",
        "bank-of-canada:boc_fx", "bank-of-canada:boc_curves",
    ]  # fmt: skip
    read = client.call_tool("read_datasets").data
    held = {r["code"]: r for r in read["records"]}
    assert held["CORRA"]["instrument_id"] == HELD["CORRA"]
    assert held["Zero-coupon yield curve"]["miss"] == "not held: reported missing"
    assert held["USD"]["instrument_id"] == "LCL-USD"
    assert held["BD.CDN.LONG.DQ.YLD"]["miss"] == "not carried"


def test_before_the_first_check_and_not_reached(tmp_path: Path) -> None:
    page_module._held.clear()
    assert "Checking the Bank" in PageClient(pages).get(CONNECTION, "admin").text
    work = feed(tmp_path)
    work.status.sources["rates"].error = "https://www.bankofcanada.ca/valet: URLError"
    hold(work)
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert 'state="error"' in text and "Not answering" in text


def test_the_figures_are_the_data_roles(client: PageClient) -> None:
    work = page_module._held["feed"]
    said = figures(work.status, work)
    assert [f.label for f in said][:3] == ["Connection", "Entitled at the vendor", "Stream"]
