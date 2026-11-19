"""The data suite (meridian.suites), each case the Bank of Canada's series
present mapped to the plugin's own conversion of the Bank's recorded
answers, the whole suite passing.

Presented: the exchange rates' price cases (each a close of the currency's
cash instrument in Canadian dollars, exact, a correction the same row's next
version, a currency resolving to two records, a want recorded against and a
subject declined); CORRA's `a-rate-fixing` (with its percentiles and
volume), `a-same-day-revision` and `an-index-level` (the CORRA Compounded
Index); the zero-coupon curve's `a-tenor-not-published`; the wants and
licences cases.

Not presented, each with why: every case about a kind of data the Bank never
publishes here (bars, trades, quotes, venues, crypto, outcomes, chains,
filings, holdings, dividends, ratings, pools, derived series); the calendar
cases (no calendar declared); `two-conventions-one-tenor` (no bill),
`a-curve-point-from-another-source`, `a-curve-for-a-date` (it asks for par
yields; the Bank's curves here are zero rates and benchmark yields);
`a-daily-close` and `reports-its-feed-delay` (the Bank states no published
time); `records-a-datasets-liveness`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import ANSWERED_BY_SDK, Recorder, run, suite

from bank_of_canada.portal import Fetched, SyntheticPortal

from conftest import AT, CURVES, FX, HELD, INSTANCE, RATES, feed, resolving, want

NEVER = {
    "bars": "the Bank states one rate a day: no open, high, low or volume",
    "a crypto asset's price": "the Bank rates currencies: no token",
    "prices on a venue": "the Bank's rates are its own, no venue's",
    "a security's price": "the Bank rates currencies: no security another source named",
    "trades": "the Bank states one rate a day: no trades",
    "quotes": "the Bank states one rate a day: no quotes",
    "settlement dates": "records each value as published; never computes a settlement date",
    "outcomes": "the Bank publishes no event contract, so no outcome",
    "disputed outcomes": "the Bank publishes no event contract, so no outcome disputed",
    "streams": "it polls the Bank hourly; it streams nothing",
    "option chains": "the Bank publishes no option chain",
    "filings": "the Bank publishes rates: no company's filings",
    "holdings": "the Bank publishes rates: no holdings report",
    "corporate actions": "the Bank publishes rates: no declared dividend",
    "ratings": "the Bank publishes rates: no rating",
    "derived series": "the Bank's values are recorded as published: no series derived from them",
    "factors": "the Bank publishes rates: no pool, so no pool's factor",
    "calendars": "its datasets declare no calendar: the platform holds none for the dollar yet",
    "publication times": "the Bank states no published time for a value",
}
NOT_PRESENTED = {
    **{c.name: NEVER[c.about] for c in suite("data").cases if c.about in NEVER},
    "two-conventions-one-tenor": "the Bank publishes no bill here: one convention a point",
    "a-curve-point-from-another-source": "the Bank publishes no curve point another source does",
    "queries-the-lake-within-bounds": "it records no trades",
    "a-daily-close": "the Bank states no published time for a rate",
    "a-curve-for-a-date": "the Bank publishes zero rates and benchmark yields here: no par yield",
}


class Changed(SyntheticPortal):
    """The Bank, read twice: as recorded, then with CORRA of 17 November
    revised and the dollar's rate of 17 November corrected."""

    def __init__(self) -> None:
        super().__init__(lambda: AT)
        self.reads: dict[str, int] = {}

    async def get(self, path: str) -> Fetched:
        got = await super().get(path)
        source = "rates" if "AVG.INTWO" in path else "fx" if "FX_RATES" in path else ""
        self.reads[source] = self.reads.get(source, 0) + 1
        if not source or self.reads[source] == 1:
            return got
        answer = json.loads(got.text)
        for day in answer["observations"]:
            if day["d"] == "2026-11-17":
                series = "AVG.INTWO" if source == "rates" else "FXUSDCAD"
                day[series] = {"v": "2.5600" if source == "rates" else "1.5000"}
        return Fetched(path, 200, json.dumps(answer).encode(), got.fetched_at, got.date)


class Gap(SyntheticPortal):
    """The Bank, the zero curve's 10-year point of 28 October left 'na'."""

    async def get(self, path: str) -> Fetched:
        got = await super().get(path)
        if "lookup_yield_curve" not in path:
            return got
        lines = got.text.splitlines()
        header = [h.strip() for h in lines[0].split(",")]
        at = header.index("ZC1000YR")
        out = [lines[0]]
        for line in lines[1:]:
            cells = line.split(",")
            if cells[0].strip() == "2026-10-28":
                cells[at] = "na"
            out.append(",".join(cells))
        return Fetched(path, 200, ("\n".join(out) + "\n").encode(), got.fetched_at, got.date)


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    async def read(recorder: Recorder) -> None:
        resolving(recorder)
        await feed(tmp, recorder).check()

    async def changed(recorder: Recorder) -> None:
        resolving(recorder)
        work = feed(tmp, recorder, portal=Changed())
        await work.check()
        await work.check()

    async def two_records(recorder: Recorder) -> None:
        resolving(recorder, ambiguous="GBP")
        await feed(tmp, recorder).check()

    async def gap(recorder: Recorder) -> None:
        resolving(recorder)
        await feed(tmp, recorder, portal=Gap(lambda: AT)).check()
        sent = [r for b in recorder.on("RecordRates") for r in b.rates]
        on_28th = {
            (r.tenor.count, r.tenor.unit)
            for r in sent
            if r.meta.business_date == "2026-10-28" and r.kind == ops.RATE_KIND_ZERO
        }
        assert on_28th and (10, ops.TENOR_UNIT_YEAR) not in on_28th

    def wanted(message: Any) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            resolving(recorder)
            work = feed(tmp, recorder)
            await work.check()
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.hear(work)

        return produce

    async def licences(recorder: Recorder) -> None:
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=FX)]),
        )
        work = feed(tmp, recorder)
        await work.wants.read_licences()
        assert work.wants.licensed == {FX}

    async def withdrawn(recorder: Recorder) -> None:
        resolving(recorder)
        work = feed(tmp, recorder)
        recorder.answer(
            "WantWithdrawn", lambda _: ops.WantWithdrawnEvent(want_id="w-s", dataset=RATES)
        )
        await recorder.hear(work)

    close = (ops.PRICE_KIND_CLOSE,)
    return {
        "the-forming-day-restated": changed,
        "an-exact-price": read,
        "an-fx-rate": read,
        "an-asset-that-does-not-resolve": two_records,
        "a-want-recorded-against": wanted(
            want(
                "w-1",
                ["LCL-USD"],
                day="2026-10-01",
                dataset=FX,
                data_type="meridian.v1.Price",
                kinds=close,
            ).message
        ),  # fmt: skip
        "a-subject-declined": wanted(
            want(
                "w-2",
                ["LCL-CAD"],
                day="2026-10-01",
                dataset=FX,
                data_type="meridian.v1.Price",
                kinds=close,
            ).message
        ),  # fmt: skip
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
        "a-rate-fixing": read,
        "a-same-day-revision": changed,
        "an-index-level": read,
        "a-tenor-not-published": gap,
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id=INSTANCE)
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    assert len(report.passed_cases) == 12 + len(ANSWERED_BY_SDK)
    assert HELD and CURVES
