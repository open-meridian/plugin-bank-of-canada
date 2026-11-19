"""The plugin's own conversion of the Bank of Canada's recorded answers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder

from bank_of_canada.series import zero_percent, zero_tenor

from conftest import CURVES, FX, HELD, INSTANCE, feed, resolving, want


def checked(tmp: Path, *left_out: str) -> Recorder:
    plugin = resolving(Recorder(INSTANCE), *left_out)
    asyncio.run(feed(tmp, plugin).check())
    return plugin


def rates_of(plugin: Recorder, subject: str) -> list[ops.Rate]:
    return [
        r
        for b in plugin.on("RecordRates")
        for r in b.rates
        if r.meta.subjects[0].entity_id == subject
    ]


def test_corra_a_fixing_with_its_percentiles_and_volume(tmp_path: Path) -> None:
    corra = rates_of(checked(tmp_path), HELD["CORRA"])
    day = next(r for r in corra if r.meta.business_date == "2026-11-17")
    assert day.kind == ops.RATE_KIND_FIXING and str(as_decimal(day.value.value)) == "2.5500"
    assert day.convention.day_count == ops.DAY_COUNT_ACT_365_FIXED
    assert {p.percentile: str(as_decimal(p.value)) for p in day.percentiles} == {
        25: "2.5500",
        75: "2.5900",
    }
    assert str(as_decimal(day.volume.amount)) == "82194964725" and day.volume.currency_code == "CAD"
    assert not day.meta.source_times and day.meta.raw.key.startswith("responses/")


def test_the_index_and_the_policy_rate(tmp_path: Path) -> None:
    plugin = checked(tmp_path)
    index = next(
        r
        for r in rates_of(plugin, HELD["CORRA compounded index"])
        if r.meta.business_date == "2026-11-17"
    )
    assert index.kind == ops.RATE_KIND_INDEX_LEVEL and index.value.index_base == "2020-06-12=100"
    assert str(as_decimal(index.value.value)) == "117.68209047"
    target = rates_of(plugin, HELD["Target for the overnight rate"])
    assert target and all(r.kind == ops.RATE_KIND_FIXING for r in target)


def test_benchmark_yields_on_the_curve_by_tenor(tmp_path: Path) -> None:
    bonds = rates_of(checked(tmp_path), HELD["Benchmark bond yields"])
    day = {(r.tenor.count, r.tenor.unit): r for r in bonds if r.meta.business_date == "2026-11-17"}
    assert sorted(c for c, _ in day) == [2, 3, 5, 7, 10]
    ten = day[(10, ops.TENOR_UNIT_YEAR)]
    assert ten.kind == ops.RATE_KIND_BENCHMARK_YIELD and str(as_decimal(ten.value.value)) == "3.81"
    assert ten.convention.compounding == ops.COMPOUNDING_COMPOUNDED
    assert ten.convention.periods_per_year == 2


def test_the_zero_curve_in_per_cent_at_120_tenors(tmp_path: Path) -> None:
    zero = rates_of(checked(tmp_path), HELD["Zero-coupon yield curve"])
    day = [r for r in zero if r.meta.business_date == "2026-10-28"]
    assert len(day) == 120 and all(r.kind == ops.RATE_KIND_ZERO for r in day)
    first = next(r for r in day if (r.tenor.count, r.tenor.unit) == (3, ops.TENOR_UNIT_MONTH))
    assert str(as_decimal(first.value.value)) == "2.53829000"
    assert first.convention.compounding == ops.COMPOUNDING_CONTINUOUS
    assert first.meta.source.dataset == CURVES
    assert zero_tenor("ZC125YR") == "15M" and zero_tenor("ZC3000YR") == "30Y"
    assert str(zero_percent("0.0251821000")) == "2.51821000"


def test_each_rate_the_price_of_a_currency_in_canadian_dollars(tmp_path: Path) -> None:
    plugin = checked(tmp_path)
    prices = [p for b in plugin.on("RecordPrices") for p in b.prices]
    dollar = next(p for p in prices if p.meta.row_key == "USDCAD:2026-11-18")
    assert dollar.meta.subjects[0].entity_id == "LCL-USD"
    assert str(as_decimal(dollar.price.amount)) == "1.4326" and dollar.price.currency_code == "CAD"
    assert dollar.kind == ops.PRICE_KIND_CLOSE and dollar.meta.source.dataset == FX


def test_a_record_not_held_is_reported_missing_and_waits(tmp_path: Path) -> None:
    plugin = checked(tmp_path, "Zero-coupon yield curve")
    missed = {i.value for p in plugin.on("ReportMissingInstrument") for i in p.identifiers}
    assert missed == {"Zero-coupon yield curve"}
    assert not rates_of(plugin, HELD["Zero-coupon yield curve"])


def test_a_past_day_wanted_and_a_subject_declined(tmp_path: Path) -> None:
    plugin = resolving(Recorder(INSTANCE))
    work = feed(tmp_path, plugin)
    asyncio.run(work.check())
    for asked in (
        want("w-1", [HELD["CORRA"]], day="2026-10-01"),
        want("w-2", ["INS-ELSE"], day="2026-10-01"),
        want("w-3", [HELD["CORRA"]], day="2026-10-04"),
    ):
        plugin.answer("ObservationsWanted", lambda _, held=asked: held.message)  # type: ignore[misc]
        asyncio.run(plugin.hear(work))
    against = [b for b in plugin.on("RecordRates") if b.want_id == "w-1"]
    assert against and {r.meta.business_date for r in against[0].rates} == {"2026-10-01"}
    reasons = [ops.UnansweredReason.Name(d.reason) for d in plugin.on("DeclineWant")]
    assert reasons == ["UNANSWERED_REASON_NOT_COVERED", "UNANSWERED_REASON_SOURCE_SILENT"]


def test_nothing_recorded_twice_in_a_process(tmp_path: Path) -> None:
    plugin = resolving(Recorder(INSTANCE))
    work = feed(tmp_path, plugin)
    asyncio.run(work.check())
    before = (len(plugin.on("RecordRates")), len(plugin.on("RecordPrices")))
    asyncio.run(work.check())
    assert (len(plugin.on("RecordRates")), len(plugin.on("RecordPrices"))) == before
