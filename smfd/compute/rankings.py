"""Leaderboard ordering, rank changes, and MVP/Benchwarmer throne history."""

from __future__ import annotations

import pandas as pd


def rank_changes(total_returns: pd.DataFrame) -> dict:
    """Rank delta vs the previous trading day: ticker -> prev_rank - current_rank.

    Positive = climbed, negative = fell, 0 = held (or no history).
    """
    if len(total_returns) < 2:
        return {t: 0 for t in total_returns.columns}
    today = total_returns.iloc[-1].sort_values(ascending=False)
    yesterday = total_returns.iloc[-2].sort_values(ascending=False)
    cur = {t: i for i, t in enumerate(today.index, start=1)}
    prev = {t: i for i, t in enumerate(yesterday.index, start=1)}
    return {t: prev.get(t, cur[t]) - cur[t] for t in cur}


def _streak_and_history(series: pd.Series, returns_by_day: pd.DataFrame, name_map: dict):
    dates = series.index.tolist()
    holders = series.tolist()
    if not dates:
        return 0, []
    current = holders[-1]
    streak = 1
    for i in range(len(holders) - 2, -1, -1):
        if holders[i] == current:
            streak += 1
        else:
            break
    history = []
    prev_holder = None
    for date, holder in zip(dates, holders):
        if holder != prev_holder:
            history.append({
                "date": date,
                "ticker": holder,
                "name": name_map.get(holder, holder),
                "prev_ticker": prev_holder,
                "return_pct": float(returns_by_day.loc[date, holder]),
            })
            prev_holder = holder
    history.reverse()  # newest first
    return streak, history


def _longest_streak(series: pd.Series) -> dict:
    holders = series.tolist()
    dates = series.index.tolist()
    if not holders:
        return {"ticker": "", "streak": 0, "start": None, "end": None}
    best = {"ticker": holders[0], "streak": 1, "start": dates[0], "end": dates[0]}
    cur_streak, cur_start = 1, 0
    for i in range(1, len(holders)):
        if holders[i] == holders[i - 1]:
            cur_streak += 1
        else:
            cur_streak, cur_start = 1, i
        if cur_streak > best["streak"]:
            best = {"ticker": holders[i], "streak": cur_streak,
                    "start": dates[cur_start], "end": dates[i]}
    return best


def compute_throne_history(total_returns: pd.DataFrame, name_map: dict) -> dict:
    """MVP/Benchwarmer streaks and transition history from the daily total-return table."""
    daily = total_returns.copy()
    if len(daily) > 1:
        daily = daily.iloc[1:]  # day 0 is all zeros — not a meaningful throne day
    daily.index = pd.to_datetime(daily.index)
    daily = daily.groupby(daily.index.date).last()
    daily.index = pd.to_datetime(daily.index)

    mvp_series = daily.idxmax(axis=1)
    bench_series = daily.idxmin(axis=1)

    mvp_streak, mvp_history = _streak_and_history(mvp_series, daily, name_map)
    bench_streak, bench_history = _streak_and_history(bench_series, daily, name_map)
    mvp_longest = _longest_streak(mvp_series)
    bench_longest = _longest_streak(bench_series)
    if mvp_longest["streak"] >= bench_longest["streak"]:
        streak_winner = {**mvp_longest, "type": "mvp"}
    else:
        streak_winner = {**bench_longest, "type": "bench"}
    return {
        "mvp_streak": mvp_streak,
        "bench_streak": bench_streak,
        "mvp_history": mvp_history,
        "bench_history": bench_history,
        "streak_winner": streak_winner,
        "mvp_longest": mvp_longest,
        "bench_longest": bench_longest,
    }
