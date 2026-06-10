"""Playful momentum 'predictions' + accuracy tracking. Not financial advice —
the disclaimer is part of the feature."""

from __future__ import annotations

import datetime
import json

import pandas as pd

from smfd.config import GROUP_EMOJI, PREDICTION_HISTORY_PATH


def generate_predictions(total_returns: pd.DataFrame, scores: pd.DataFrame,
                         name_map: dict, group_map: dict) -> list:
    """System predictions from 5-day momentum, volatility, and trend."""
    predictions = []
    daily = total_returns
    if len(daily) < 6:
        return predictions
    daily_changes = daily.diff()
    final_returns = scores["total_return_pct"]

    recent = daily.iloc[-6:]
    momentum = recent.iloc[-1] - recent.iloc[0]
    lookback = min(10, len(daily_changes) - 1)
    volatility = daily_changes.iloc[-lookback:].std()
    positive_days = (daily_changes.iloc[-5:] > 0).sum()

    def _emoji(t):
        return GROUP_EMOJI.get(group_map.get(t, ""), "")

    scores_map = {}
    for t in daily.columns:
        mom = momentum[t] / max(abs(momentum).max(), 0.01)
        trend = positive_days[t] / 5.0
        ret = final_returns.get(t, 0) / max(abs(final_returns).max(), 0.01)
        scores_map[t] = mom * 0.5 + trend * 0.3 + ret * 0.2

    mvp = max(scores_map, key=scores_map.get)
    predictions.append({
        "icon": "\U0001f451", "title": "Predicted MVP", "ticker": mvp,
        "name": name_map.get(mvp, mvp),
        "detail": f"Strong momentum ({momentum[mvp]:+.2f}%) + {int(positive_days[mvp])}/5 green days",
        "confidence": min(95, max(40, int(scores_map[mvp] * 100))),
        "emoji": _emoji(mvp),
    })

    breakout = {t: volatility[t] * momentum[t] for t in daily.columns
                if volatility[t] > volatility.median() and momentum[t] > 0}
    if breakout:
        b = max(breakout, key=breakout.get)
        predictions.append({
            "icon": "\U0001f4a5", "title": "Breakout Watch", "ticker": b,
            "name": name_map.get(b, b),
            "detail": f"High volatility (±{volatility[b]:.2f}%) with upward momentum",
            "confidence": min(70, max(30, int(breakout[b] * 10))),
            "emoji": _emoji(b),
        })

    danger = {t: abs(momentum[t]) * (1 + volatility[t]) for t in daily.columns if momentum[t] < 0}
    if danger:
        d = max(danger, key=danger.get)
        predictions.append({
            "icon": "⚠️", "title": "Danger Zone", "ticker": d,
            "name": name_map.get(d, d),
            "detail": f"Dropping {momentum[d]:+.2f}% over 5 days with high volatility",
            "confidence": min(75, max(35, int(danger[d] * 5))),
            "emoji": _emoji(d),
        })

    bench = {t: abs(momentum[t]) * (1 + (5 - positive_days[t]) / 5)
             for t in daily.columns if momentum[t] < 0}
    if bench:
        b = max(bench, key=bench.get)
        predictions.append({
            "icon": "\U0001f4a9", "title": "Predicted Benchwarmer", "ticker": b,
            "name": name_map.get(b, b),
            "detail": f"Dropping {momentum[b]:+.2f}% with {int(positive_days[b])}/5 green days",
            "confidence": min(90, max(35, int(bench[b] * 8))),
            "emoji": _emoji(b),
        })

    group_mom, group_n = {}, {}
    for t in daily.columns:
        g = group_map.get(t, "")
        if g:
            group_mom[g] = group_mom.get(g, 0) + momentum[t]
            group_n[g] = group_n.get(g, 0) + 1
    if group_mom:
        avg = {g: group_mom[g] / group_n[g] for g in group_mom}
        hot = max(avg, key=avg.get)
        predictions.append({
            "icon": "\U0001f4c8", "title": "Head of Household", "ticker": hot,
            "name": f"{GROUP_EMOJI.get(hot, '')} {hot} Division",
            "detail": f"Avg 5-day momentum: {avg[hot]:+.2f}% across {group_n[hot]} picks",
            "confidence": min(65, max(30, int(abs(avg[hot]) * 10))),
            "emoji": GROUP_EMOJI.get(hot, ""),
        })

    current_mvp = final_returns.idxmax()
    challengers = {t: s for t, s in scores_map.items() if t != current_mvp and s > 0}
    if challengers:
        c = max(challengers, key=challengers.get)
        predictions.append({
            "icon": "\U0001f93a", "title": "Throne Challenger", "ticker": c,
            "name": name_map.get(c, c),
            "detail": f"Most likely to dethrone {current_mvp} next week",
            "confidence": min(60, max(25, int(challengers[c] * 80))),
            "emoji": _emoji(c),
        })

    bottom_half = final_returns.sort_values().head(len(final_returns) // 2).index
    sleepers = {t: momentum[t] for t in bottom_half if momentum.get(t, 0) > 0}
    if sleepers:
        s = max(sleepers, key=sleepers.get)
        predictions.append({
            "icon": "\U0001f634", "title": "Sleeper Alert", "ticker": s,
            "name": name_map.get(s, s),
            "detail": f"Bottom half but gaining {sleepers[s]:+.2f}% momentum",
            "confidence": min(50, max(20, int(sleepers[s] * 10))),
            "emoji": _emoji(s),
        })

    vol_bomb = volatility[list(daily.columns)].idxmax()
    predictions.append({
        "icon": "\U0001f4a3", "title": "Volatility Bomb", "ticker": vol_bomb,
        "name": name_map.get(vol_bomb, vol_bomb),
        "detail": f"Avg daily swing of ±{volatility[vol_bomb]:.2f}% — expect fireworks",
        "confidence": min(70, max(30, int(volatility[vol_bomb] * 12))),
        "emoji": _emoji(vol_bomb),
    })

    predictions.sort(key=lambda p: p.get("confidence", 0), reverse=True)
    return predictions


# --- History (machine-appended, once per day) ---

def load_history() -> dict:
    try:
        with open(PREDICTION_HISTORY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"past": []}


def record_predictions(predictions: list, history: dict) -> None:
    today = datetime.date.today().isoformat()
    if any(p.get("recorded_date") == today for p in history.get("past", [])):
        return
    for pred in predictions:
        history.setdefault("past", []).append({
            "recorded_date": today,
            "title": pred["title"],
            "ticker": pred["ticker"],
            "confidence": pred.get("confidence", 50),
            "detail": pred["detail"],
        })
    try:
        with open(PREDICTION_HISTORY_PATH, "w") as f:
            json.dump(history, f, indent=2, default=str)
    except OSError:
        pass  # read-only deploys: accuracy tracking just pauses


def check_past_predictions(history: dict, current_returns: pd.Series) -> list:
    """Score predictions at least 5 days old against today's standings."""
    today = datetime.date.today()
    results = []
    for pred in history.get("past", []):
        try:
            pred_date = datetime.date.fromisoformat(pred["recorded_date"])
        except (ValueError, KeyError):
            continue
        if (today - pred_date).days < 5:
            continue
        ticker = pred["ticker"]
        if ticker not in current_returns.index:
            continue
        ret = current_returns[ticker]
        title = pred["title"]
        if title == "Predicted MVP":
            correct = ticker == current_returns.idxmax()
            actual = f"Actual MVP: {current_returns.idxmax()} ({current_returns.max():+.2f}%)"
        elif title == "Breakout Watch":
            correct = ret > current_returns.median()
            actual = f"Return: {ret:+.2f}%"
        elif title == "Danger Zone":
            correct = ret < current_returns.median()
            actual = f"Return: {ret:+.2f}%"
        elif title == "Predicted Benchwarmer":
            correct = ticker == current_returns.idxmin()
            actual = f"Actual Bench: {current_returns.idxmin()} ({current_returns.min():+.2f}%)"
        else:
            continue
        results.append({"date": pred["recorded_date"], "title": title, "ticker": ticker,
                        "confidence": pred.get("confidence", 50), "correct": correct,
                        "actual": actual})
    return results
