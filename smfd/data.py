"""Load game data: roster + nightly stock JSON. No Streamlit calls here.

Supports two on-disk formats for data/stock_data.json:

- **v2** (written by the current fetch_data.py): adds ``as_of``, ``fetch_errors``,
  per-ticker ``splits`` and dated ``dividends``, and ``prices_split_adjusted``.
  Return math uses the split-adjusted series + dividends as separate cash.
- **legacy** (pre-redesign): ``last_updated``, auto-adjusted ``prices`` (split AND
  dividend adjusted) and a single summed dividend float per ticker. We reproduce
  the legacy app's numbers in this mode (including its dividend double-count) so
  the dashboard keeps working until the nightly action writes a v2 file. The
  parity tests rely on this mode matching the old app exactly.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field

import pandas as pd

from smfd import market_calendar
from smfd.config import PLAYERS_PATH, STOCK_DATA_PATH, TIMEZONE


@dataclass
class GameData:
    stake: float
    players: list  # [{etf, name, ticker}]
    tickers: list
    name_map: dict
    group_map: dict  # ticker -> ANTY/UNCL/KIDZ
    prices: pd.DataFrame          # split-adjusted close, rows=dates, cols=tickers
    raw_prices: pd.DataFrame      # as-traded close (legacy mode: same as prices)
    dividends: dict               # ticker -> [(date, per-share amount, split-adjusted)]
    splits: dict                  # ticker -> [(date, ratio)]
    as_of: datetime.datetime | None
    fetch_errors: list
    stale: bool
    legacy_format: bool
    signals: dict = field(default_factory=dict)
    earnings: dict = field(default_factory=dict)
    news: dict = field(default_factory=dict)

    @property
    def valid_tickers(self) -> list:
        return [t for t in self.tickers if t in self.prices.columns and self.prices[t].notna().any()]


def _parse_as_of(raw: dict) -> datetime.datetime | None:
    stamp = raw.get("as_of") or raw.get("last_updated")
    if not stamp:
        return None
    try:
        dt = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE)
    return dt.astimezone(TIMEZONE)


def _prices_frame(price_data: dict, tickers: list) -> pd.DataFrame:
    frames = {
        t: {pd.Timestamp(d): v for d, v in price_data[t].items()}
        for t in tickers
        if t in price_data
    }
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index().ffill().bfill()


def split_adjust_dividends(dividends: list, splits: list) -> list:
    """Convert as-paid per-share dividends to today's share basis.

    A dividend paid before a split was paid on pre-split shares; in today's
    (post-split) basis the per-share amount shrinks by every later split ratio.

    NOTE: not applied to fetch_data.py v2 output — Yahoo restates dividend
    history to the current share basis the same way it restates prices, so
    those amounts are already correct. Use this only for a source that
    provides true as-paid amounts.
    """
    out = []
    for div_date, amount in dividends:
        factor = 1.0
        for split_date, ratio in splits:
            if ratio and split_date > div_date:
                factor *= ratio
        out.append((div_date, amount / factor))
    return out


def load_game_data(players_path=PLAYERS_PATH, stock_data_path=STOCK_DATA_PATH,
                   now: datetime.datetime | None = None) -> GameData:
    with open(players_path) as f:
        config = json.load(f)
    players = config["players"]
    tickers = [p["ticker"] for p in players]

    try:
        with open(stock_data_path) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    legacy = "prices_split_adjusted" not in raw
    as_of = _parse_as_of(raw)

    raw_prices = _prices_frame(raw.get("prices", {}), tickers)
    if legacy:
        # Legacy auto-adjusted series doubles as the "split-adjusted" series.
        prices = raw_prices
    else:
        prices = _prices_frame(raw.get("prices_split_adjusted", {}), tickers)

    splits: dict = {}
    dividends: dict = {}
    if legacy:
        # One summed float per ticker. Model it as a single payment on the first
        # date so cumulative total return matches the legacy app, which applied
        # the full dividend to every day retroactively.
        first_date = prices.index[0].date() if len(prices) else None
        for t in tickers:
            amt = raw.get("dividends", {}).get(t, 0.0) or 0.0
            splits[t] = []
            dividends[t] = [(first_date, float(amt))] if amt and first_date else []
    else:
        for t in tickers:
            splits[t] = [
                (datetime.date.fromisoformat(s["date"]), float(s["ratio"]))
                for s in raw.get("splits", {}).get(t, [])
            ]
            # v2 dividends come from Yahoo already restated to today's share
            # basis (same convention as its price history) — use as-is.
            dividends[t] = [
                (datetime.date.fromisoformat(d["date"]), float(d["amount"]))
                for d in raw.get("dividends", {}).get(t, [])
            ]

    return GameData(
        stake=float(config.get("investment_amount", 10.0)),
        players=players,
        tickers=tickers,
        name_map={p["ticker"]: p["name"] for p in players},
        group_map={p["ticker"]: p.get("etf", "") for p in players},
        prices=prices,
        raw_prices=raw_prices,
        dividends=dividends,
        splits=splits,
        as_of=as_of,
        fetch_errors=list(raw.get("fetch_errors", [])),
        stale=market_calendar.is_stale(as_of, now=now),
        legacy_format=legacy,
        signals=raw.get("signals", {}),
        earnings=raw.get("earnings", {}),
        news=raw.get("news", {}),
    )
