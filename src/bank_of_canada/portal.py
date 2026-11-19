"""The Bank of Canada's website, where Valet and the zero-coupon curves are
served, and its stand-in.

Four kinds of request are made, and nothing else, each for a range of days:

- CORRA, its percentiles and volume, its compounded index and the target
  for the overnight rate -- `/valet/observations/AVG.INTWO,...,V39079/json`;
- the benchmark bond yields -- `/valet/observations/group/bond_yields_benchmark/json`;
- the daily exchange rates -- `/valet/observations/group/FX_RATES_DAILY/json`;
- the zero-coupon curves -- `/stats/results/csv?lookupPage=lookup_yield_curve.php&...`,
  the address the curves page's form asks;

each Valet request with `start_date` and `end_date`, the curves' with
`dFrom` and `dTo`. A range with no value is answered with no observation.

Read from the Bank itself: no key, no account; its terms are its website's
(docs/terms.md), which ask that its request limits not be circumvented, and
state none as figures. The plugin asks one request at a time, at most one
every two seconds, says who it is in its User-Agent, and checks the current
ranges every hour. Valet states no Last-Modified, so an answer whose values
read as the last one recorded records nothing (feed.py).

`SyntheticPortal` answers from the real responses committed under
responses/ (responses/index.json), recorded on 2026-11-19: Valet's three
from 3 August to 19 November 2026, and the zero-coupon curves from 3 August
to 28 October 2026 (the Bank publishes them with a two-week lag). A request
is answered with the recorded values in its range, and each current range
ends on its recording's last day whatever the clock says, so the plugin's
tests and its e2e run on it, offline, the same on any day.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from typing import Any, Protocol

from .series import RATE_SERIES

BASE = "https://www.bankofcanada.ca"
RATES, BONDS, FX, ZERO = "rates", "bonds", "fx", "zero"
SOURCES = (RATES, BONDS, FX, ZERO)
#: Each source's address, before its range.
PATHS = {
    RATES: "/valet/observations/" + ",".join(RATE_SERIES) + "/json",
    BONDS: "/valet/observations/group/bond_yields_benchmark/json",
    FX: "/valet/observations/group/FX_RATES_DAILY/json",
    ZERO: "/stats/results/csv?lookupPage=lookup_yield_curve.php&startRange=1986-01-01&searchRange=",
}
USER_AGENT = "meridian-bank-of-canada (+https://github.com/open-meridian/plugin-bank-of-canada)"
SPACING = 2.0
TIMEOUT = 60.0
MOST_BYTES = 16 * 1024 * 1024
#: How far each current range reaches back: ten days of the daily series;
#: forty-five of the curves, published weekly with a two-week lag.
CURRENT_DAYS = {RATES: 10, BONDS: 10, FX: 10, ZERO: 45}


def path_for(source: str, start: date, end: date) -> str:
    """The address of `source`'s values from `start` to `end`."""
    if source == ZERO:
        return f"{PATHS[ZERO]}&dFrom={start.isoformat()}&dTo={end.isoformat()}"
    return f"{PATHS[source]}?start_date={start.isoformat()}&end_date={end.isoformat()}"


def source_of(path: str) -> str:
    return next((s for s, at in PATHS.items() if path.startswith(at.split("?")[0])), "")


class PortalUnreachable(Exception):  # noqa: N818 - what the Bank's website was
    """The website could not be asked: no answer, or not in time."""


@dataclass(frozen=True)
class Fetched:
    """One answer, as received."""

    path: str
    status: int
    body: bytes
    fetched_at: datetime
    date: str = ""

    @property
    def url(self) -> str:
        return BASE + self.path

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Portal(Protocol):
    mode: str

    def current(self, today: date, source: str) -> tuple[date, date]: ...

    async def get(self, path: str) -> Fetched: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LivePortal:
    """The Bank's website itself."""

    mode = "live"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    def current(self, today: date, source: str) -> tuple[date, date]:
        return today - timedelta(days=CURRENT_DAYS[source]), today

    async def get(self, path: str) -> Fetched:
        async with self._lock:
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await asyncio.to_thread(self._get, path)
            finally:
                self._last = time.monotonic()

    def _get(self, path: str) -> Fetched:
        request = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 - the Bank's https address
                body = answer.read(MOST_BYTES + 1)
                status = answer.status
                said = answer.headers
        except urllib.error.HTTPError as refused:
            body = refused.read(MOST_BYTES + 1) if refused.fp else b""
            status, said = refused.code, refused.headers
        except (urllib.error.URLError, TimeoutError, OSError) as failed:
            reason = getattr(failed, "reason", failed)
            raise PortalUnreachable(f"{BASE}{path[:80]}: {type(reason).__name__}") from failed
        if len(body) > MOST_BYTES:
            raise PortalUnreachable(f"{BASE}{path[:80]}: answered more than {MOST_BYTES} bytes")
        return Fetched(path, status, body, self._now(), date=said.get("Date", "") if said else "")


@dataclass(frozen=True)
class Recording:
    """One recorded answer, its Date and last day."""

    text: str
    said: str
    last_day: date


class SyntheticPortal:
    """The responses committed under responses/: each range answered with
    the recorded values in it, under its recording's Date."""

    mode = "synthetic"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        held = resources.files(__package__).joinpath("responses")
        index = json.loads(held.joinpath("index.json").read_text(encoding="utf-8"))
        self.recordings = {
            source: Recording(
                gzip.decompress(held.joinpath(index[source]["file"]).read_bytes()).decode(),
                str(index[source]["date"]),
                date.fromisoformat(index[source]["last_day"]),
            )
            for source in SOURCES
        }
        self.asked: list[str] = []

    def current(self, today: date, source: str) -> tuple[date, date]:
        last = self.recordings[source].last_day
        return last - timedelta(days=CURRENT_DAYS[source]), last

    async def get(self, path: str) -> Fetched:
        self.asked.append(path)
        source = source_of(path)
        recording = self.recordings.get(source)
        if recording is None:
            return Fetched(path, 404, b'{"message": "not found"}', self._now())
        query = dict(p.partition("=")[::2] for p in path.partition("?")[2].split("&"))
        try:
            start = date.fromisoformat(query.get("start_date") or query.get("dFrom", ""))
            end = date.fromisoformat(query.get("end_date") or query.get("dTo", ""))
        except ValueError:
            return Fetched(path, 400, b'{"message": "bad date"}', self._now())
        body = _within(recording.text, source, start, end)
        return Fetched(path, 200, body.encode(), self._now(), recording.said)


def _within(text: str, source: str, start: date, end: date) -> str:
    def inside(day: str) -> bool:
        try:
            return start <= date.fromisoformat(day.strip()) <= end
        except ValueError:
            return False

    if source == ZERO:
        rows = list(csv.reader(io.StringIO(text)))
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerows([rows[0], *(r for r in rows[1:] if r and inside(r[0]))])
        return out.getvalue()
    answer: dict[str, Any] = json.loads(text)
    answer["observations"] = [o for o in answer["observations"] if inside(str(o.get("d", "")))]
    return json.dumps(answer)


def portal(synthetic: bool, now: Callable[[], datetime] = utc_now) -> Portal:
    return SyntheticPortal(now) if synthetic else LivePortal(now)
