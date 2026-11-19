"""The Bank of Canada's rates, curves and exchange rates into the lake: the
current ranges recorded as the Bank publishes them, and any day recorded
when the lake wants it (W10.4, W10.7), through the SDK's rates helpers
(`meridian.roles.data.rates`) and its `Wants`.

**Push.** At start and every hour, each source's current range -- ten days
of CORRA, the policy rate, the benchmark yields and the exchange rates,
forty-five days of the zero-coupon curves -- is read. An answer whose values
read as the last one this process recorded records nothing; any other is
recorded whole, in the lake's batches, and the lake answers each value it
holds unchanged. A value the Bank revises within the range is the same row
key's next version.

**Rows** (series.py says each): CORRA a `fixing` with its percentiles and
volume; its compounded index an `index_level`; the policy rate a `fixing`;
each benchmark yield a `benchmark_yield` at its tenor on the benchmark
curve's record; each zero-curve point a `zero` at its tenor; each exchange
rate a `close` `Price` of the currency's cash instrument in Canadian dollars.
A value the Bank states nothing for is no row, never a zero. Each is read
from the Bank's text as a `Decimal`, never a float.

**Published time.** The Bank states none on a value, and Valet no
Last-Modified: no row states one, rather than a wrong one.

**Subjects.** Each record by its code at `boc` (series.py), each currency by
its ISO 4217 code, resolved once per process; one the deployment does not
hold is reported missing, and its values wait. The plugin mints nothing.

**Wants.** A want of one of the three datasets, for subjects the plugin
records -- a business date, a range of at most a year, or the latest -- is
read from the Bank and recorded against the want; a day the Bank states
nothing for, or one not come yet, is declined `source_silent`; any other
subject, or another kind of data, `not_covered`.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import meridian
from meridian.operations import Money, ObservationMeta, Price, SubjectRef
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import rates

from .declared import BOC_CURVES, BOC_FX, BOC_RATES, DAY_TIME_ZONE, KEYS, PRICE, RATE
from .portal import (
    BONDS,
    FX,
    RATES,
    SOURCES,
    ZERO,
    Fetched,
    Portal,
    PortalUnreachable,
    path_for,
    utc_now,
)
from .raw import RawStore
from .series import (
    BENCHMARK_RECORD,
    BENCHMARKS,
    BOND,
    CONTINUOUS,
    CORRA,
    CORRA_INDEX_BASE,
    MONEY_MARKET_365,
    PERCENTILES,
    RATE_KINDS,
    SOURCE,
    VOLUME,
    ZERO_RECORD,
    Record,
    fx_code,
    zero_percent,
    zero_tenor,
)
from .valet import NotRead, Observations, parse_curves, parse_valet

log = logging.getLogger("bank_of_canada")

TORONTO = ZoneInfo(DAY_TIME_ZONE)
#: Each source's dataset, and back.
DATASETS = {RATES: BOC_RATES, BONDS: BOC_CURVES, ZERO: BOC_CURVES, FX: BOC_FX}
SOURCES_OF = {BOC_RATES: (RATES,), BOC_CURVES: (BONDS, ZERO), BOC_FX: (FX,)}
#: The most days one want is answered for: a year.
MOST_DAYS = 366


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def day_bounds(day: date) -> tuple[int, int]:
    start = datetime.combine(day, time(0, 0), TORONTO)
    return _ns(start), _ns(datetime.combine(day + timedelta(days=1), time(0, 0), TORONTO))


@dataclass(frozen=True)
class Outcome:
    recorded: int = 0
    restated: int = 0
    unchanged: int = 0
    unresolved: tuple[str, ...] = ()


@dataclass
class Held:
    """A record or a currency as the plugin last saw it: the deployment's
    instrument, or why there is none, and the latest day recorded."""

    code: str
    name: str = ""
    instrument_id: str = ""
    miss: str = ""
    latest_day: date | None = None


@dataclass
class SourceStatus:
    """What the plugin last did with one source, for its pages."""

    source: str
    checked_at: datetime | None = None
    read_at: datetime | None = None
    error: str = ""
    first_day: date | None = None
    latest_day: date | None = None
    fetches: int = 0
    unread: dict[str, int] = field(default_factory=dict)


@dataclass
class Status:
    """What the plugin last did, for its pages; lost on a restart."""

    mode: str = "live"
    started_at: datetime | None = None
    sources: dict[str, SourceStatus] = field(
        default_factory=lambda: {s: SourceStatus(s) for s in SOURCES}
    )
    records: dict[str, Held] = field(default_factory=dict)
    currencies: dict[str, Held] = field(default_factory=dict)

    @property
    def checked_at(self) -> datetime | None:
        stamps = [s.checked_at for s in self.sources.values() if s.checked_at]
        return max(stamps) if stamps else None

    @property
    def error(self) -> str:
        return next((s.error for s in self.sources.values() if s.error), "")

    @property
    def fetches(self) -> int:
        return sum(s.fetches for s in self.sources.values())

    @property
    def read(self) -> bool:
        return any(s.read_at for s in self.sources.values())


class Feed(data.Role):
    """The plugin's data role class, its acts made on itself -- registered
    with `meridian.run`, or bound to the suite's recorder in its tests."""

    def __init__(
        self, portal: Portal, raw: RawStore, now: Callable[[], datetime] = utc_now
    ) -> None:
        self.portal = portal
        self.raw = raw
        self.now = now
        self.wants = data.Wants(self, KEYS, clock_ns=lambda: _ns(self.now()))
        self.rates = rates.Feed(
            self, SOURCE, wants=self.wants, day_zone=DAY_TIME_ZONE, clock_ns=lambda: _ns(self.now())
        )
        self.status = Status(mode=portal.mode, started_at=now())
        self._recorded: dict[str, str] = {}

    def today(self) -> date:
        return self.now().astimezone(TORONTO).date()

    def use(self, portal: Portal) -> None:
        """Read from `portal` from now on: sample data turned on or off."""
        if portal.mode != self.portal.mode:
            self.portal = portal
            self.status.mode = portal.mode
            self._recorded.clear()

    # ── Reading ─────────────────────────────────────────────────────────

    async def read(self, source: str, start: date, end: date) -> tuple[Observations, str]:
        """`source`'s values from `start` to `end`, and the answer's key in
        storage. PortalUnreachable or NotRead otherwise."""
        held = self.status.sources[source]
        fetched: Fetched = await self.portal.get(path_for(source, start, end))
        held.fetches += 1
        key = self.raw.keep(fetched)
        if fetched.status != 200:
            raise PortalUnreachable(f"{fetched.url[:120]} answered {fetched.status}")
        parse = parse_curves if source == ZERO else parse_valet
        read = parse(fetched.text, source)
        for line in read.unread:
            held.unread[line] = held.unread.get(line, 0) + 1
        if source == FX:
            for series, described in read.described.items():
                code = fx_code(series)
                if code:
                    self.status.currencies.setdefault(code, Held(code, described.description))
        return read, key

    # ── Resolving ───────────────────────────────────────────────────────

    async def record_of(self, record: Record) -> str:
        """A record's instrument, by its code at `boc`; empty, reported
        missing, where the deployment holds none."""
        held = self.status.records.setdefault(record.code, Held(record.code, record.description))
        if held.instrument_id:
            return held.instrument_id
        found = await self.rates.subject(
            record.identifier,
            description=record.description,
            instrument_type=record.instrument_type,
        )
        held.instrument_id, held.miss = found, "" if found else "not held: reported missing"
        return found

    async def currency(self, code: str) -> str:
        """A currency's cash instrument by ISO 4217, resolved now where not
        yet; empty, reported missing with why, where none resolves."""
        held = self.status.currencies.setdefault(code, Held(code))
        if held.instrument_id:
            return held.instrument_id
        identifier = ops.Identifier(scheme="iso4217", value=code)
        found = await self.resolve_identifier(
            identifiers=[identifier],
            as_of_ns=_ns(self.now()),
            stated_asset_class="cash",
            stated_currency=code,
            stated_description=f"{code} cash",
        )
        if found.found and found.instrument_id:
            held.instrument_id, held.miss = found.instrument_id, ""
            return str(found.instrument_id)
        if held.miss:
            return ""
        reason = found.miss_reason or ops.MISS_REASON_NOT_FOUND
        held.miss = ops.MissReason.Name(reason).removeprefix("MISS_REASON_").lower()
        await self.report_missing_instrument(
            source=SOURCE,
            asset_class="cash",
            identifiers=[identifier],
            reason=reason,
            as_of_ns=_ns(self.now()),
            observed_at_ns=_ns(self.now()),
        )
        return ""

    # ── Recording ───────────────────────────────────────────────────────

    def _first(self, name: str, day: date, key: str) -> str:
        return self.raw.noted(name, day, key)[0].key

    def _note(self, held: Held, day: date) -> None:
        if held.latest_day is None or day > held.latest_day:
            held.latest_day = day

    async def _rate_rows(self, read: Observations, key: str, days: set[date] | None) -> list[Any]:
        rows: list[Any] = []
        for day in read.days:
            if days is not None and day not in days:
                continue
            stated = read.on(day)
            for series, (record, kind) in RATE_KINDS.items():
                seen = stated.get(series)
                if seen is None:
                    continue
                subject = await self.record_of(record)
                if not subject:
                    continue
                extra: dict[str, Any] = {}
                said = seen.text
                if series == CORRA:
                    percentiles = {p: stated[s].text for p, s in PERCENTILES.items() if s in stated}
                    if percentiles:
                        extra["percentiles"] = percentiles
                    if VOLUME in stated:
                        extra["volume"] = Money(stated[VOLUME].value, "CAD")
                    said += "|" + "|".join(f"{p}:{v}" for p, v in sorted(percentiles.items()))
                    said += "|" + (stated[VOLUME].text if VOLUME in stated else "")
                value = (
                    rates.index_level(seen.text, CORRA_INDEX_BASE)
                    if kind == "index_level"
                    else rates.percent(seen.text)
                )
                rows.append(
                    self.rates.rate(
                        subject,
                        BOC_RATES,
                        kind,
                        value,
                        business_date=day,
                        convention=MONEY_MARKET_365,
                        series=series,
                        raw_key=self._first(f"{series}:{day}={said}", day, key),
                        **extra,
                    )
                )
                self._note(self.status.records[record.code], day)
        return rows

    async def _curve_rows(
        self, read: Observations, key: str, days: set[date] | None, source: str
    ) -> list[Any]:
        record = BENCHMARK_RECORD if source == BONDS else ZERO_RECORD
        rows: list[Any] = []
        for seen in read.observations:
            if days is not None and seen.day not in days:
                continue
            if source == BONDS and seen.series not in BENCHMARKS:
                continue
            subject = await self.record_of(record)
            if not subject:
                break
            if source == BONDS:
                kind, tenor, value, convention, dataset = (
                    "benchmark_yield", BENCHMARKS[seen.series], rates.percent(seen.text),
                    BOND, BOC_CURVES,
                )  # fmt: skip
            else:
                kind, tenor, value, convention, dataset = (
                    "zero", zero_tenor(seen.series), rates.percent(zero_percent(seen.text)),
                    CONTINUOUS, BOC_CURVES,
                )  # fmt: skip
            rows.append(
                self.rates.rate(
                    subject,
                    dataset,
                    kind,
                    value,
                    business_date=seen.day,
                    convention=convention,
                    tenor=tenor,
                    series=record.code,
                    raw_key=self._first(f"{seen.series}:{seen.day}={seen.text}", seen.day, key),
                )
            )
            self._note(self.status.records[record.code], seen.day)
        return rows

    async def _prices(
        self, read: Observations, key: str, days: set[date] | None, subjects: set[str] | None
    ) -> tuple[list[Any], list[str]]:
        prices: list[Any] = []
        unresolved: dict[str, None] = {}
        dataset = self.wants.dataset(BOC_FX)
        for seen in read.observations:
            code = fx_code(seen.series)
            if not code or (days is not None and seen.day not in days):
                continue
            subject = await self.currency(code)
            if not subject:
                unresolved[code] = None
                continue
            if subjects is not None and subject not in subjects:
                continue
            start, end = day_bounds(seen.day)
            first = self._first(f"{code}:{seen.day}={seen.text}", seen.day, key)
            prices.append(
                Price(
                    meta=ObservationMeta(
                        row_key=f"{code}CAD:{seen.day.isoformat()}",
                        subjects=[SubjectRef(entity_id=subject)],
                        source=ops.Source(dataset=dataset),
                        valid_from_ns=start,
                        valid_until_ns=end,
                        business_date=seen.day.isoformat(),
                        raw=self.plugin.raw_record(first[:256]) if first else None,
                    ),
                    kind="close",
                    price=Money(seen.value, "CAD"),
                    basis="per_unit",
                )
            )
            self._note(self.status.currencies[code], seen.day)
        return prices, list(unresolved)

    async def record(
        self,
        read: Observations,
        key: str,
        *,
        want_id: str = "",
        days: Iterable[date] | None = None,
        subjects: set[str] | None = None,
    ) -> tuple[Outcome, set[str]]:
        """Record `read` -- on `days` and for `subjects` where given --
        against `want_id` where given. What the lake answered, and the
        subjects a row was sent for."""
        source = read.source
        dataset = DATASETS[source]
        wanted = set(days) if days is not None else None
        unresolved: list[str] = []
        rows: list[Any]
        if source == FX:
            rows, unresolved = await self._prices(read, key, wanted, subjects)
        elif source == RATES:
            rows = await self._rate_rows(read, key, wanted)
        else:
            rows = await self._curve_rows(read, key, wanted, source)
        if subjects is not None and source != FX:
            rows = [r for r in rows if r.meta.subjects[0].entity_id in subjects]
        if source != FX:
            unresolved = [h.code for h in self.status.records.values() if h.miss]
        self.raw.save_firsts()
        counts = self.wants.sent_to(dataset)
        before = (counts.recorded, counts.restated, counts.unchanged)
        if source == FX:
            await self.wants.record("prices", rows, dataset, want_id)
        else:
            await self.rates.record(dataset, rows, want_id)
        sent = {r.meta.subjects[0].entity_id for r in rows}
        outcome = Outcome(
            counts.recorded - before[0],
            counts.restated - before[1],
            counts.unchanged - before[2],
            tuple(unresolved),
        )
        return outcome, sent

    async def check(self) -> dict[str, Outcome]:
        """Read each source's current range; record it where this process
        has not recorded it as it reads now."""
        done: dict[str, Outcome] = {}
        for source in SOURCES:
            held = self.status.sources[source]
            held.checked_at = self.now()
            start, end = self.portal.current(self.today(), source)
            try:
                read, key = await self.read(source, start, end)
            except (PortalUnreachable, NotRead) as failed:
                held.error = str(failed)
                log.warning("%s was not read: %s", source, failed)
                continue
            held.error = ""
            held.read_at = self.now()
            if read.days:
                held.first_day, held.latest_day = read.days[0], read.days[-1]
            digest = digest_of(read)
            if digest == self._recorded.get(source):
                continue
            outcome, _ = await self.record(read, key)
            done[source] = outcome
            if not outcome.unresolved:
                self._recorded[source] = digest
            log.info(
                "%s of %s to %s: %d recorded, %d restated, %d unchanged%s",
                source,
                held.first_day,
                held.latest_day,
                outcome.recorded,
                outcome.restated,
                outcome.unchanged,
                f"; not held: {', '.join(outcome.unresolved)}" if outcome.unresolved else "",
            )
        return done

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_observations_wanted(
        self, heard: meridian.Heard[ops.ObservationsWantedEvent]
    ) -> None:
        await self.wants.hear(heard, self.answer)

    async def on_want_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        self.wants.withdraw(heard.message.want_id)
        log.info("standing want %s withdrawn", heard.message.want_id)

    def _days(self, source: str, want: ops.ObservationsWantedEvent) -> list[date]:
        if want.business_date:
            return [date.fromisoformat(want.business_date)]
        if want.valid_from_ns or want.valid_until_ns:
            start = datetime.fromtimestamp(want.valid_from_ns / 1e9, TORONTO).date()
            until = want.valid_until_ns - 1 if want.valid_until_ns else _ns(self.now())
            end = datetime.fromtimestamp(until / 1e9, TORONTO).date()
            return [start + timedelta(days=n) for n in range((end - start).days + 1)][-MOST_DAYS:]
        latest = self.status.sources[source].latest_day
        return [latest] if latest else []

    def _held(self, source: str) -> set[str]:
        if source == FX:
            return {h.instrument_id for h in self.status.currencies.values() if h.instrument_id}
        codes = {
            RATES: [r.code for r, _ in RATE_KINDS.values()],
            BONDS: [BENCHMARK_RECORD.code],
            ZERO: [ZERO_RECORD.code],
        }[source]
        return {
            h.instrument_id
            for c, h in self.status.records.items()
            if c in codes and h.instrument_id
        }

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered from the Bank: its values recorded against it,
        and each subject declined, with why."""
        sources = SOURCES_OF.get(key, ())
        serves = PRICE if key == BOC_FX else RATE
        if not sources or want.data_type not in ("", serves):
            return {s: "not_covered" for s in subjects}
        if key == BOC_FX and kinds and ops.PRICE_KIND_CLOSE not in kinds:
            return {s: "not_covered" for s in subjects}
        held = {source: self._held(source) for source in sources}
        declined = {s: "not_covered" for s in subjects if not any(s in h for h in held.values())}
        for source in sources:
            asked = [s for s in subjects if s in held[source]]
            if not asked:
                continue
            if want.standing:
                self.wants.stand(want, asked, kinds)
            days = [d for d in self._days(source, want) if d <= self.today()]
            sent: set[str] = set()
            if days:
                try:
                    read, raw_key = await self.read(source, min(days), max(days))
                    _, sent = await self.record(
                        read, raw_key, want_id=want.want_id, days=days, subjects=set(asked)
                    )
                except (PortalUnreachable, NotRead) as failed:
                    log.warning("want %s: %s was not read: %s", want.want_id, source, failed)
            for subject in asked:
                if subject not in sent:
                    declined[subject] = "source_silent"
        return declined


def digest_of(read: Observations) -> str:
    """What an answer states, as a short digest: its values alone."""
    stated = repr([(o.series, o.day, o.text) for o in read.observations]).encode()
    return hashlib.sha256(stated).hexdigest()[:16]
