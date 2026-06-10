"""Canonical scoring — this defines who wins.

For each pick, on the **split-adjusted** price series:

    units              = stake / start_price            (constant in adjusted space)
    price_value        = units * current_price
    dividend_income    = units * sum(per-share dividends at each ex-date in window)
    total_value        = price_value + dividend_income
    total_return_pct   = (total_value / stake - 1) * 100

Dividends are separate cash — never use a dividend-adjusted price series here,
that would count them twice. Pure functions, no Streamlit.
"""

from __future__ import annotations

import datetime

import pandas as pd

from smfd.data import GameData


def _window(prices: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    out = prices
    if start is not None:
        out = out.loc[out.index >= pd.Timestamp(start)]
    if end is not None:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out


def _dividends_in(dividends: list, start: datetime.date, end: datetime.date) -> list:
    return [(d, amt) for d, amt in dividends if start <= d <= end]


def cumulative_dividend_cash(index: pd.DatetimeIndex, dividends: list, units: float) -> pd.Series:
    """Dividend cash received up to and including each date in *index*."""
    cash = pd.Series(0.0, index=index)
    for ex_date, amount in dividends:
        cash.loc[index >= pd.Timestamp(ex_date)] += units * amount
    return cash


def compute_scores(data: GameData, start=None, end=None) -> pd.DataFrame:
    """Per-pick scoring table, sorted by total_return_pct descending.

    Columns: group, name, start_price, end_price, units, price_value,
    dividend_income, total_value, profit, price_return_pct,
    dividend_return_pct, total_return_pct.
    """
    prices = _window(data.prices, start, end)
    rows = {}
    if prices.empty:
        return pd.DataFrame(rows)
    start_d = prices.index[0].date()
    end_d = prices.index[-1].date()
    for t in data.valid_tickers:
        series = prices[t].dropna()
        if series.empty:
            continue
        start_price = float(series.iloc[0])
        end_price = float(series.iloc[-1])
        if not start_price:
            continue
        units = data.stake / start_price
        divs = _dividends_in(data.dividends.get(t, []), start_d, end_d)
        dividend_income = units * sum(amt for _, amt in divs)
        price_value = units * end_price
        total_value = price_value + dividend_income
        rows[t] = {
            "group": data.group_map.get(t, ""),
            "name": data.name_map.get(t, t),
            "start_price": start_price,
            "end_price": end_price,
            "units": units,
            "price_value": price_value,
            "dividend_income": dividend_income,
            "total_value": total_value,
            "profit": total_value - data.stake,
            "price_return_pct": (end_price / start_price - 1) * 100,
            "dividend_return_pct": (dividend_income / data.stake) * 100,
            "total_return_pct": (total_value / data.stake - 1) * 100,
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    if df.empty:
        return df
    return df.sort_values("total_return_pct", ascending=False)


def total_return_series(data: GameData, start=None, end=None) -> pd.DataFrame:
    """Cumulative total return %% per pick per day (price + dividend cash to date)."""
    prices = _window(data.prices, start, end)
    if prices.empty:
        return pd.DataFrame()
    start_d = prices.index[0].date()
    end_d = prices.index[-1].date()
    out = {}
    for t in data.valid_tickers:
        series = prices[t]
        start_price = float(series.iloc[0])
        if not start_price:
            continue
        units = data.stake / start_price
        divs = _dividends_in(data.dividends.get(t, []), start_d, end_d)
        cash = cumulative_dividend_cash(prices.index, divs, units)
        value = units * series + cash
        out[t] = (value / data.stake - 1) * 100
    return pd.DataFrame(out)


def price_return_series(data: GameData, start=None, end=None) -> pd.DataFrame:
    """Cumulative price-only return %% per pick per day (no dividends)."""
    prices = _window(data.prices, start, end)
    if prices.empty:
        return pd.DataFrame()
    cols = [t for t in data.valid_tickers if t in prices.columns]
    sub = prices[cols]
    return (sub / sub.iloc[0] - 1) * 100
