"""Risk & Income: volatility, drawdown, and where each return actually came from."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def risk_table(total_returns: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Per-pick risk/income stats, in leaderboard order.

    Columns: annualized_vol_pct, max_drawdown_pct, price_return_pct,
    dividend_return_pct, total_return_pct, dividend_share_pct (portion of the
    gain that came from dividends, 0 when the pick is at a loss).
    """
    if total_returns.empty or scores.empty:
        return pd.DataFrame()
    # Daily % changes of the value series. total_returns is cumulative % on
    # stake; convert to a value index to get true daily returns.
    value_index = 1 + total_returns / 100
    daily = value_index.pct_change().iloc[1:]

    rows = {}
    for t in scores.index:
        vol = float(daily[t].std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100) if len(daily) > 1 else 0.0
        running_max = value_index[t].cummax()
        drawdown = (value_index[t] / running_max - 1) * 100
        total = scores.loc[t, "total_return_pct"]
        div = scores.loc[t, "dividend_return_pct"]
        rows[t] = {
            "annualized_vol_pct": vol,
            "max_drawdown_pct": float(drawdown.min()),
            "price_return_pct": float(scores.loc[t, "price_return_pct"]),
            "dividend_return_pct": float(div),
            "total_return_pct": float(total),
            "dividend_share_pct": float(div / total * 100) if total > 0 else 0.0,
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    return df.sort_values("total_return_pct", ascending=False)


def group_risk(risk: pd.DataFrame, group_map: dict) -> pd.DataFrame:
    """Average vol/drawdown/returns per group, sorted by avg total return."""
    if risk.empty:
        return pd.DataFrame()
    out = risk.copy()
    out["group"] = [group_map.get(t, "") for t in out.index]
    agg = out.groupby("group")[
        ["annualized_vol_pct", "max_drawdown_pct", "price_return_pct",
         "dividend_return_pct", "total_return_pct"]
    ].mean()
    return agg.sort_values("total_return_pct", ascending=False)
