"""The Bank of Canada's series this version carries, what each one is, and
the record it is recorded against: the plugin's series map.

**Rates** (`boc_rates`, Valet). CORRA (`AVG.INTWO`), a daily `fixing` with
its 25th and 75th percentiles (`CORRA_RATE_AT_PERCENTILE_25`, `_75`) and its
total volume in Canadian dollars (`CORRA_TOTAL_VOLUME`); the CORRA
Compounded Index (`CORRA.COMPOUNDED.INDEX`), an `index_level` based 12 June
2020 = 100, as the Bank states it; and the target for the overnight rate,
the policy rate (`V39079`), a `fixing`. Each is in per cent, actual/365,
simple: the Canadian money market's convention, which the Bank states on
none of these series -- the plugin's statement, said on the Datasets page.

**Benchmark bond yields** (`boc_curves`, Valet's `bond_yields_benchmark`).
The Government of Canada's 2, 3, 5, 7 and 10-year benchmark bonds' yields,
each a `benchmark_yield` (ruling 130) at its tenor on one `rate_curve`
record, semi-annual bond-equivalent (the Government of Canada's bond
convention; the Bank states only "Percent"). The long-term benchmark and the
Real Return Bonds' yield are **not carried**: the Bank states no tenor for
the long-term benchmark, and a real yield is another curve's.

**Zero-coupon curve** (`boc_curves` too, the curves page's CSV). The Bank's
zero-coupon Government of Canada curve, one `rate_curve` record, its 120
points from 3 months to 30 years each a `zero` rate at its tenor (a quarter
year as 3, 6 or 9 months, a whole year as years), the Bank's decimal made
per cent exactly (`0.0251821000` is 2.51821000%), continuously compounded,
as the Bank's methodology states its zero rates (-ln d(t) / t). Its forward
rates and model parameters are not recorded (ruling 131).

**FX** (`boc_fx`, Valet's `FX_RATES_DAILY`): each currency's daily average
rate, "Canadian dollars per <currency>", a `Price` of the currency's cash
instrument in Canadian dollars, never inverted.

Each record is asked of the deployment by the Bank's code for it as a
`symbol` at the source `boc`, a name **proposed** with this version for the
platform's seed; the platform seeds none yet, so until a deployment holds a
record its values wait, reported missing, never minted. Each currency is
resolved by its ISO 4217 code, as plugin-ecb resolves its.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from meridian.operations import RateConvention
from meridian.roles.data import rates

SOURCE = "boc"
INTEREST_RATE, INDEX, RATE_CURVE = "interest_rate", "index", "rate_curve"

#: The Canadian money market's convention, and the Government of Canada's
#: bond convention: semi-annual, bond-equivalent.
MONEY_MARKET_365 = RateConvention(day_count="act_365_fixed", compounding="simple")
BOND = rates.BOND_EQUIVALENT
CONTINUOUS = rates.CONTINUOUS
CORRA_INDEX_BASE = "2020-06-12=100"

#: The Valet series read with CORRA, and the percentile each states.
CORRA = "AVG.INTWO"
CORRA_INDEX = "CORRA.COMPOUNDED.INDEX"
TARGET = "V39079"
VOLUME = "CORRA_TOTAL_VOLUME"
PERCENTILES = {25: "CORRA_RATE_AT_PERCENTILE_25", 75: "CORRA_RATE_AT_PERCENTILE_75"}
RATE_SERIES = (CORRA, CORRA_INDEX, TARGET, VOLUME, *PERCENTILES.values())


@dataclass(frozen=True)
class Record:
    """A referential record, by the code proposed for it at `boc`."""

    code: str
    instrument_type: str
    description: str

    @property
    def identifier(self) -> tuple[str, str, str]:
        return ("symbol", self.code, SOURCE)


CORRA_RECORD = Record("CORRA", INTEREST_RATE, "Canadian Overnight Repo Rate Average (CORRA)")
CORRA_INDEX_RECORD = Record("CORRA compounded index", INDEX, "CORRA Compounded Index")
TARGET_RECORD = Record(
    "Target for the overnight rate", INTEREST_RATE, "Bank of Canada target for the overnight rate"
)
BENCHMARK_RECORD = Record(
    "Benchmark bond yields", RATE_CURVE, "Government of Canada benchmark bond yields"
)
ZERO_RECORD = Record(
    "Zero-coupon yield curve", RATE_CURVE, "Government of Canada zero-coupon yield curve"
)
RECORDS = (CORRA_RECORD, CORRA_INDEX_RECORD, TARGET_RECORD, BENCHMARK_RECORD, ZERO_RECORD)

#: Each rate series: its record and kind.
RATE_KINDS = {
    CORRA: (CORRA_RECORD, "fixing"),
    CORRA_INDEX: (CORRA_INDEX_RECORD, "index_level"),
    TARGET: (TARGET_RECORD, "fixing"),
}
#: The benchmark bonds carried, by Valet series, and each one's tenor.
BENCHMARKS = {
    "BD.CDN.2YR.DQ.YLD": "2Y",
    "BD.CDN.3YR.DQ.YLD": "3Y",
    "BD.CDN.5YR.DQ.YLD": "5Y",
    "BD.CDN.7YR.DQ.YLD": "7Y",
    "BD.CDN.10YR.DQ.YLD": "10Y",
}
#: The benchmark group's series not carried, and why.
NOT_CARRIED = {
    "BD.CDN.LONG.DQ.YLD": "the Bank states no tenor for its long-term benchmark",
    "BD.CDN.RRB.DQ.YLD": "a real yield, another curve's",
}


def zero_tenor(column: str) -> str:
    """A curve column's tenor: `ZC025YR` 3M, `ZC100YR` 1Y, `ZC125YR` 15M."""
    years = Decimal(column.removeprefix("ZC").removesuffix("YR")) / 100
    months = int(years * 12)
    return f"{months // 12}Y" if months % 12 == 0 else f"{months}M"


def zero_percent(text: str) -> Decimal:
    """A curve's decimal as per cent, exactly: `0.0251821000` is `2.51821000`."""
    return Decimal(text).scaleb(2)


def fx_code(series: str) -> str:
    """A rate's currency: `FXUSDCAD` is USD; empty for another series."""
    if series.startswith("FX") and series.endswith("CAD") and len(series) == 8:
        return series[2:5]
    return ""
