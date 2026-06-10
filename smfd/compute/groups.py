"""Group Battle: Uncle vs Auntie vs Kid head-to-head."""

from __future__ import annotations

import pandas as pd

from smfd.config import GROUPS


def group_return_series(total_returns: pd.DataFrame, group_map: dict) -> pd.DataFrame:
    """Daily average total return per group — the 3-line battle chart."""
    cols = {}
    for g in GROUPS:
        members = [t for t in total_returns.columns if group_map.get(t) == g]
        if members:
            cols[g] = total_returns[members].mean(axis=1)
    return pd.DataFrame(cols)


def group_standings(total_returns: pd.DataFrame, scores: pd.DataFrame,
                    group_map: dict, compare_days: int = 5) -> list:
    """Current group standings with rank change vs *compare_days* trading days ago.

    Returns a list (rank order) of dicts: etf, avg_return_pct, rank,
    change_vs_last (+n/-n/=), members, winners, best/worst ticker + return.
    """
    series = group_return_series(total_returns, group_map)
    if series.empty:
        return []
    today = series.iloc[-1].sort_values(ascending=False)
    prev_idx = max(len(series) - 1 - compare_days, 0)
    prev = series.iloc[prev_idx].sort_values(ascending=False)
    prev_ranks = {g: i for i, g in enumerate(prev.index, start=1)}

    standings = []
    for rank, (g, avg) in enumerate(today.items(), start=1):
        members = [t for t in scores.index if group_map.get(t) == g]
        member_scores = scores.loc[members]
        diff = prev_ranks.get(g, rank) - rank
        change = "=" if diff == 0 else f"{diff:+d}"
        best = member_scores["total_return_pct"].idxmax() if members else ""
        worst = member_scores["total_return_pct"].idxmin() if members else ""
        standings.append({
            "etf": g,
            "avg_return_pct": float(avg),
            "rank": rank,
            "change_vs_last": change,
            "members": len(members),
            "winners": int((member_scores["total_return_pct"] >= 0).sum()) if members else 0,
            "total_value": float(member_scores["total_value"].sum()) if members else 0.0,
            "invested": float((member_scores["total_value"] - member_scores["profit"]).sum()) if members else 0.0,
            "best_ticker": best,
            "best_return_pct": float(member_scores.loc[best, "total_return_pct"]) if best else 0.0,
            "worst_ticker": worst,
            "worst_return_pct": float(member_scores.loc[worst, "total_return_pct"]) if worst else 0.0,
        })
    return standings


def group_spread(standings: list) -> float:
    """Gap in avg return %% between the leading and trailing group."""
    if len(standings) < 2:
        return 0.0
    return standings[0]["avg_return_pct"] - standings[-1]["avg_return_pct"]


def lead_changes(total_returns: pd.DataFrame, group_map: dict) -> list:
    """Days on which the leading group changed: [{date, etf, prev_etf}]."""
    series = group_return_series(total_returns, group_map)
    if series.empty:
        return []
    leaders = series.idxmax(axis=1)
    changes = []
    prev = None
    for date, g in leaders.items():
        if g != prev and prev is not None:
            changes.append({"date": date, "etf": g, "prev_etf": prev})
        prev = g
    return changes
