"""US stock market calendar: holidays, trading days, session-aware staleness."""

from __future__ import annotations

import calendar
import datetime

from dateutil.easter import easter

from smfd.config import TIMEZONE, STALE_GRACE_HOURS

MARKET_CLOSE_TIME = datetime.time(16, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    first = datetime.date(year, month, 1)
    diff = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=diff + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> datetime.date:
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    diff = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=diff)


def _observed(d: datetime.date) -> datetime.date | None:
    """Weekend holidays shift: Sunday -> Monday, Saturday -> Friday."""
    if d.weekday() == 6:
        return d + datetime.timedelta(days=1)
    if d.weekday() == 5:
        return d - datetime.timedelta(days=1)
    return d


def us_market_holidays(year: int) -> dict:
    """Return {date: name} of US stock market holidays for the given year."""
    holidays = {}
    nyd = datetime.date(year, 1, 1)
    if nyd.weekday() == 6:
        holidays[datetime.date(year, 1, 2)] = "New Year's Day"
    elif nyd.weekday() != 5:  # Saturday New Year's is not observed
        holidays[nyd] = "New Year's Day"
    holidays[_nth_weekday(year, 1, 0, 3)] = "MLK Day"
    holidays[_nth_weekday(year, 2, 0, 3)] = "Presidents' Day"
    holidays[easter(year) - datetime.timedelta(days=2)] = "Good Friday"
    holidays[_last_weekday(year, 5, 0)] = "Memorial Day"
    holidays[_observed(datetime.date(year, 6, 19))] = "Juneteenth"
    holidays[_observed(datetime.date(year, 7, 4))] = "Independence Day"
    holidays[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    holidays[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving"
    holidays[_observed(datetime.date(year, 12, 25))] = "Christmas"
    return holidays


def is_trading_day(d: datetime.date) -> bool:
    return d.weekday() < 5 and d not in us_market_holidays(d.year)


def previous_trading_day(d: datetime.date) -> datetime.date:
    d -= datetime.timedelta(days=1)
    while not is_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d


def next_market_holiday(today: datetime.date) -> tuple:
    """Return (date, name) of the next market holiday strictly after today."""
    names = {}
    names.update(us_market_holidays(today.year))
    names.update(us_market_holidays(today.year + 1))
    upcoming = sorted((d, n) for d, n in names.items() if d > today)
    return upcoming[0] if upcoming else (None, "")


def last_completed_close(now: datetime.datetime) -> datetime.datetime:
    """The most recent trading-session close at or before *now* (ET-aware)."""
    now = now.astimezone(TIMEZONE)
    d = now.date()
    if not is_trading_day(d) or now.time() < MARKET_CLOSE_TIME:
        d = previous_trading_day(d)
    while not is_trading_day(d):
        d = previous_trading_day(d)
    return datetime.datetime.combine(d, MARKET_CLOSE_TIME, tzinfo=TIMEZONE)


def is_stale(as_of: datetime.datetime, now: datetime.datetime | None = None) -> bool:
    """Data is stale when some completed session's close is comfortably past
    (STALE_GRACE_HOURS) and the data still predates it.

    Weekends and the gap between a close and that evening's fetch never
    false-alarm, but a missed nightly fetch is flagged by the following evening.
    """
    if as_of is None:
        return True
    now = (now or datetime.datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=TIMEZONE)
    # Walk back through completed closes the data predates; the earliest missed
    # close is the one that has had the longest to be corrected.
    close = last_completed_close(now)
    earliest_missed = None
    for _ in range(10):  # >10 missed sessions is unambiguously stale
        if as_of >= close:
            break
        earliest_missed = close
        close = datetime.datetime.combine(
            previous_trading_day(close.date()), MARKET_CLOSE_TIME, tzinfo=TIMEZONE)
    else:
        return True
    if earliest_missed is None:
        return False
    return now - earliest_missed > datetime.timedelta(hours=STALE_GRACE_HOURS)
