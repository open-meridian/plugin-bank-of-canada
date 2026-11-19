"""What this version declares beside its role, `data` (W8.1, W4.1; the
catalogue from contract v18), built from code and used twice: `__main__`
registers with it, and `meridian plugin upload` reads it from the built image
(pyproject.toml's `[tool.meridian] declaration`).

**The catalogue: three datasets** (the product owner, items 128, 129 and 140,
2026-11-19: Tier 1, one plugin for the Bank's two feeds; their keys
proposed, the product owner's to approve), each pushed as the Bank publishes
it and any past day pulled when the lake wants it:

- **`boc_rates`**: CORRA, a fixing with its percentiles and volume; the CORRA
  Compounded Index; the target for the overnight rate -- rates, daily;
- **`boc_curves`**: the Government of Canada's two curves -- the benchmark
  bond yields, `benchmark_yield` at each tenor on the benchmark curve's
  record (ruling 130), daily; and the zero-coupon curve, `zero` rates at 120
  tenors, published weekly with a two-week lag -- rates;
- **`boc_fx`**: the daily average exchange rates, each the price of a
  currency's cash instrument in Canadian dollars -- prices, daily.

Each: `vendor` the Bank of Canada, no aggregator; `modes` `push` and
`pull`; its day Toronto's (the Bank's business day), ending at midnight; no
calendar (the platform holds none for the Canadian dollar yet); no venue;
`history` 0, as each series states; its terms and pricing (contract 30,
ruling 1032) the Bank's, in plain words, and no licence declared -- a
deployment's licence, set on the Data sources page, is the one enforced;
a gap asked again (`gap_recovery` `backfill`, W10.14).

**Storage:** the answers (raw.py), archivable, ten years by default.
"""

from __future__ import annotations

from meridian import DatasetDeclaration
from meridian.declaration import RecordKind

from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

BOC_RATES, BOC_CURVES, BOC_FX = "boc_rates", "boc_curves", "boc_fx"
KEYS = (BOC_RATES, BOC_CURVES, BOC_FX)
VENDOR = "Bank of Canada"
RATE = "meridian.v1.Rate"
PRICE = "meridian.v1.Price"
CADENCE = 86_400
DAY_TIME_ZONE = "America/Toronto"
DAY_END_MINUTE = 0

#: The Bank's terms, in plain words (contract 30, ruling 1032), from its
#: terms page (https://www.bankofcanada.ca/terms/), read by the research on
#: 2026-11-18.
BOC_TERMS = (
    "The Bank of Canada's website and its Valet API: free, no key or account. The Bank allows "
    "its content to be used, copied and distributed with credit to the Bank and a note of any "
    "changes, implying no endorsement; a paid service that includes it must tell its buyers "
    "that it is free on the Bank's website. Third parties' content is excluded unless marked, "
    "and the Bank's request limits may not be circumvented."
)
TERMS = {
    BOC_RATES: BOC_TERMS + " CORRA is administered by the Bank of Canada.",
    BOC_CURVES: BOC_TERMS
    + (
        " Each benchmark yield is a Government of Canada benchmark bond's. The zero-coupon "
        "curves are the Bank's estimates from Government of Canada bond and "
        "treasury bill prices, published weekly with a two-week lag; their forward rates and "
        "model parameters are not carried."
    ),
    BOC_FX: BOC_TERMS
    + (
        " The exchange rates are daily averages, published for information: the Bank states "
        "they are not meant as a benchmark for executing foreign exchange trades."
    ),
}


def _dataset(key: str, data_type: str, cadence: int) -> DatasetDeclaration:
    return DatasetDeclaration(
        key=key,
        vendor=VENDOR,
        data_types=[data_type],
        modes=["push", "pull"],
        cadence=cadence,
        history=0,
        terms_and_pricing=TERMS[key],
        gap_recovery="backfill",
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
    )


RATES_DATASET = DatasetDeclaration(
    key=BOC_RATES,
    vendor=VENDOR,
    data_types=[RATE, "meridian.v1.Rate.volume", "meridian.v1.Rate.percentiles"],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=0,
    terms_and_pricing=TERMS[BOC_RATES],
    gap_recovery="backfill",
    day_time_zone=DAY_TIME_ZONE,
    day_end_minute=DAY_END_MINUTE,
)
CATALOGUE = [
    RATES_DATASET,
    _dataset(BOC_CURVES, RATE, CADENCE),
    _dataset(BOC_FX, PRICE, CADENCE),
]

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)
