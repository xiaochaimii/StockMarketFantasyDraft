"""Race to the Finish: distance-to-lead, days remaining, just-for-fun projections."""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd

from smfd.config import GAME_END

PROJECTION_WINDOW = 30   # trailing trading days for the linear extrapolation
CATCH_UP_SIGMA = 2.0     # generous: catchable within 2 sigma of remaining drift


def days_remaining(today: datetime.date | None = None) -> int:
    today = today or datetime.date.today()
    return max((GAME_END - today).days, 0)


def trading_days_remaining(today: datetime.date | None = None) -> int:
    """Rough trading-day count to the finish (weekdays; holidays are noise here)."""
    today = today or datetime.date.today()
    return max(int(np.busday_count(today, GAME_END)), 0)


def race_table(total_returns: pd.DataFrame, scores: pd.DataFrame,
               today: datetime.date | None = None) -> pd.DataFrame:
    """Per-pick race stats, in leaderboard order.

    Columns: total_return_pct, gap_to_leader (pp), gap_to_safety (pp above last
    place), trend_per_day (trailing-30d slope), projected_final_pct
    (just-for-fun linear extrapolation), can_catch_leader.
    """
    if total_returns.empty or scores.empty:
        return pd.DataFrame()
    current = scores["total_return_pct"]
    leader_ret = current.max()
    last_ret = current.min()
    remaining = trading_days_remaining(today)

    window = total_returns.iloc[-min(PROJECTION_WINDOW, len(total_returns)):]
    x = np.arange(len(window))
    daily_changes = total_returns.diff().iloc[1:]

    rows = {}
    for t in scores.index:
        series = window[t].values
        slope = float(np.polyfit(x, series, 1)[0]) if len(series) >= 2 else 0.0
        vol = float(daily_changes[t].std()) if len(daily_changes) > 1 else 0.0
        gap = float(leader_ret - current[t])
        # Generous "alive" test: drift to close the gap within CATCH_UP_SIGMA
        # of what daily volatility could plausibly add up to over the remaining days
        reachable = CATCH_UP_SIGMA * vol * np.sqrt(max(remaining, 1))
        rows[t] = {
            "total_return_pct": float(current[t]),
            "gap_to_leader": gap,
            "gap_to_safety": float(current[t] - last_ret),
            "trend_per_day": slope,
            "projected_final_pct": float(current[t] + slope * remaining),
            "can_catch_leader": bool(gap <= reachable),
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    return df.sort_values("total_return_pct", ascending=False)


def milestones(today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    from smfd.config import GAME_START
    total = (GAME_END - GAME_START).days
    elapsed = (today - GAME_START).days
    return {
        "days_remaining": days_remaining(today),
        "trading_days_remaining": trading_days_remaining(today),
        "days_elapsed": max(elapsed, 0),
        "pct_complete": min(max(elapsed / total * 100, 0), 100) if total else 0,
        "end_date": GAME_END,
    }
