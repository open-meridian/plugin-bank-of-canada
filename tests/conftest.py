"""Shared stand-ins: the Bank of Canada's recorded answers, a fixed clock,
the deployment holding some of the Bank's records and every currency, and
the lake's wants as the sidecar delivers them."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.suites import Recorder

from bank_of_canada.feed import Feed
from bank_of_canada.portal import SyntheticPortal
from bank_of_canada.raw import RawStore

#: After the recording: 22:00 UTC on Wednesday 18 November 2026.
AT = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
INSTANCE = "bank-of-canada"
RATES = f"{INSTANCE}:boc_rates"
CURVES = f"{INSTANCE}:boc_curves"
FX = f"{INSTANCE}:boc_fx"
#: The records the tests' deployment holds, by their code at `boc`.
HELD = {
    "CORRA": "INS-CORRA",
    "CORRA compounded index": "INS-CORRAINDEX",
    "Target for the overnight rate": "INS-TARGET",
    "Benchmark bond yields": "INS-BENCHMARK",
    "Zero-coupon yield curve": "INS-ZERO",
}


def resolving(plugin: Recorder, *left_out: str, ambiguous: str = "", missing: str = "") -> Recorder:
    """`plugin` resolving `HELD`'s records but `left_out`, and each ISO code to
    `LCL-<code>` (`ambiguous` to two records, `missing` to none)."""

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        named = params.identifiers[0]
        if named.scheme == "iso4217":
            if named.value == ambiguous:
                return ops.ResolveIdentifierResult(
                    found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS
                )
            if named.value == missing:
                return ops.ResolveIdentifierResult(
                    found=False, miss_reason=ops.MISS_REASON_NOT_FOUND
                )
            return ops.ResolveIdentifierResult(found=True, instrument_id=f"LCL-{named.value}")
        found = HELD.get(named.value, "") if named.source == "boc" else ""
        if not found or named.value in left_out:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)
        return ops.ResolveIdentifierResult(found=True, instrument_id=found)

    plugin.answer("ResolveIdentifier", resolved)
    return plugin


def feed(
    tmp: Path, plugin: Recorder | None = None, *, portal: Any = None, at: datetime = AT
) -> Feed:
    held = plugin if plugin is not None else resolving(Recorder(INSTANCE))
    return held.bind(Feed(portal or SyntheticPortal(lambda: at), RawStore(tmp), now=lambda: at))


def want(
    want_id: str,
    subjects: list[str],
    *,
    day: str = "",
    standing: bool = False,
    dataset: str = RATES,
    data_type: str = "meridian.v1.Rate",
    kinds: tuple[Any, ...] = (),
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=dataset,
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            kinds=list(kinds),
            business_date=day,
            standing=standing,
        ),
    )
