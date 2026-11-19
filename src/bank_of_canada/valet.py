"""The Bank of Canada's answers, read as the Bank wrote them.

**Valet** (`https://www.bankofcanada.ca/valet`) answers an observations
request as JSON: `seriesDetail`, each series' label, description and unit;
and `observations`, one object a day, `d` the date and each series stated
that day as `{"v": "<value>"}`. A series the Bank states nothing for on a day
is absent from that day's object: no value, never a zero.

**The zero-coupon yield curves** are served as CSV (`/stats/results/csv`,
the curves page's form): a header line, `Date` then `ZC025YR` to
`ZC3000YR`, a column for each quarter-year of maturity from 0.25 to 30
years, then one line a day, each yield a decimal (`0.0251821000` is
2.51821%); `na` where the Bank states none.

A value is kept as the text the Bank wrote, and read as a `Decimal` from it,
never a float; a value that does not read is kept as not read, and never
recorded.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MISSING = {"", "na", "NA", "n/a"}


class NotRead(Exception):  # noqa: N818 - what the answer was not
    """An answer that is not what was asked for."""


@dataclass(frozen=True)
class Observation:
    """One value as the Bank stated it: its series, day and text."""

    series: str
    day: date
    text: str

    @property
    def value(self) -> Decimal:
        return Decimal(self.text)


@dataclass(frozen=True)
class Described:
    """A series as the Bank describes it."""

    label: str = ""
    description: str = ""
    unit: str = ""


@dataclass
class Observations:
    """An answer read: its values in order, each series' description, and
    the values that did not read."""

    source: str
    observations: list[Observation] = field(default_factory=list)
    described: dict[str, Described] = field(default_factory=dict)
    unread: list[str] = field(default_factory=list)

    @property
    def days(self) -> list[date]:
        return sorted({o.day for o in self.observations})

    def on(self, day: date) -> dict[str, Observation]:
        return {o.series: o for o in self.observations if o.day == day}


def _number(text: str) -> bool:
    try:
        return Decimal(text).is_finite()
    except InvalidOperation:
        return False


def parse_valet(text: str, source: str) -> Observations:
    """A Valet observations answer, read; NotRead where it is not one."""
    read = Observations(source)
    try:
        answer: Any = json.loads(text)
    except ValueError as failed:
        raise NotRead(f"the answer is not JSON: {text[:80]!r}") from failed
    if not isinstance(answer, dict) or not isinstance(answer.get("observations"), list):
        raise NotRead(f"the answer holds no observations: {text[:80]!r}")
    for name, detail in (answer.get("seriesDetail") or {}).items():
        if isinstance(detail, dict):
            unit = detail.get("metadata", {}) if isinstance(detail.get("metadata"), dict) else {}
            read.described[str(name)] = Described(
                str(detail.get("label", "")).strip(),
                str(detail.get("description", "")).strip(),
                str(unit.get("unit", "") or detail.get("unit", "")).strip(),
            )
    for held in answer["observations"]:
        if not isinstance(held, dict):
            continue
        try:
            day = date.fromisoformat(str(held.get("d", "")))
        except ValueError:
            read.unread.append(f"{source}: a day {str(held.get('d'))[:20]!r}")
            continue
        for name, stated in held.items():
            if name == "d" or not isinstance(stated, dict):
                continue
            text = str(stated.get("v", "")).strip()
            if text in MISSING:
                continue
            if not _number(text):
                read.unread.append(f"{name} {day}: {text[:40]!r}")
                continue
            read.observations.append(Observation(str(name), day, text))
    read.observations.sort(key=lambda o: (o.series, o.day))
    return read


def parse_curves(text: str, source: str) -> Observations:
    """The zero-coupon curves' CSV, read; NotRead where it is not one."""
    read = Observations(source)
    if not text.strip():
        return read
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rows[0]]
    if not header or header[0] != "Date" or not all(h.startswith("ZC") for h in header[1:] if h):
        raise NotRead(f"the answer is not the curves' CSV: {text[:80]!r}")
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        try:
            day = date.fromisoformat(row[0].strip())
        except ValueError:
            read.unread.append(f"{source}: a day {row[0][:20]!r}")
            continue
        for name, stated in zip(header[1:], row[1:], strict=False):
            text = stated.strip()
            if not name or text in MISSING:
                continue
            if not _number(text):
                read.unread.append(f"{name} {day}: {text[:40]!r}")
                continue
            read.observations.append(Observation(name, day, text))
    read.observations.sort(key=lambda o: (o.series, o.day))
    return read
