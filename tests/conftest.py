from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smfd.data import GameData  # noqa: E402


def make_game(prices: dict, dividends: dict | None = None, splits: dict | None = None,
              groups: dict | None = None, stake: float = 10.0) -> GameData:
    """Build a GameData from plain dicts: prices = {ticker: {date_str: price}}."""
    frames = {
        t: {pd.Timestamp(d): v for d, v in series.items()}
        for t, series in prices.items()
    }
    df = pd.DataFrame(frames).sort_index().ffill().bfill()
    tickers = list(prices.keys())
    groups = groups or {t: "ANTY" for t in tickers}
    return GameData(
        stake=stake,
        players=[{"etf": groups[t], "name": t, "ticker": t} for t in tickers],
        tickers=tickers,
        name_map={t: t for t in tickers},
        group_map=groups,
        prices=df,
        raw_prices=df,
        dividends={t: (dividends or {}).get(t, []) for t in tickers},
        splits={t: (splits or {}).get(t, []) for t in tickers},
        as_of=datetime.datetime(2026, 6, 9, 21, 0, tzinfo=datetime.timezone.utc),
        fetch_errors=[],
        stale=False,
        legacy_format=False,
    )


@pytest.fixture
def fixture_roster() -> GameData:
    """Small deterministic roster: a riser, a faller, a dividend payer, a flat pick."""
    dates = ["2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12"]
    prices = {
        "UP": dict(zip(dates, [100.0, 102.0, 104.0, 106.0, 110.0])),
        "DOWN": dict(zip(dates, [50.0, 48.0, 46.0, 45.0, 40.0])),
        "DIVY": dict(zip(dates, [20.0, 20.0, 21.0, 21.0, 22.0])),
        "FLAT": dict(zip(dates, [10.0, 10.0, 10.0, 10.0, 10.0])),
    }
    dividends = {"DIVY": [(datetime.date(2026, 3, 10), 0.50)]}
    groups = {"UP": "ANTY", "DOWN": "UNCL", "DIVY": "KIDZ", "FLAT": "ANTY"}
    return make_game(prices, dividends=dividends, groups=groups)
