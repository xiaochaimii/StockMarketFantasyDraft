"""Daily roasts — teasing, never mean. These are friends.

Roasts regenerate once per trading day (after the 4 PM close) and persist in
roasts_cache.json with a 30-day template-dedup history so jokes don't repeat.
Ticker markup is the caller's job; templates here take pre-colored ticker HTML.
"""

from __future__ import annotations

import datetime
import json
import random
import re

import pandas as pd

from smfd import market_calendar
from smfd.config import ROASTS_CACHE_PATH, TIMEZONE


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def generate_roasts(final_returns: pd.Series, total_returns: pd.DataFrame,
                    throne: dict, ticker_html: dict, used_history: dict | None = None,
                    rng: random.Random | None = None) -> list:
    rng = rng or random.Random()
    sorted_rets = final_returns.sort_values(ascending=False)
    total = len(sorted_rets)
    candidates = []

    for t, ret in sorted_rets.items():
        tc = ticker_html.get(t, f"<b>{t}</b>")
        if ret > 15:
            candidates += [
                f"\U0001f451 {tc} is up {ret:+.2f}% and won't shut up about it. We get it, you're winning.",
                f"\U0001f451 {tc} at {ret:+.2f}%? Enjoy it while it lasts. The market humbles everyone.",
                f"\U0001f451 {tc} sitting pretty at {ret:+.2f}%. Main character energy.",
                f"\U0001f451 Someone check on {tc}'s ego. {ret:+.2f}% and counting. Insufferable.",
            ]
        elif ret > 5:
            candidates += [
                f"\U0001f7e2 {tc} quietly sitting at {ret:+.2f}%. Not flashy, but getting the job done.",
                f"\U0001f7e2 {tc} at {ret:+.2f}%. Slow and steady. Boring but profitable.",
            ]
        elif -2 < ret < 2:
            candidates += [
                f"\U0001fae5 {tc} returned {ret:+.2f}%. Absolute NPC energy. Doing nothing and hoping nobody notices.",
                f"\U0001fae5 {tc} at {ret:+.2f}%. The human equivalent of 'I'm just here so I don't get fined.'",
                f"\U0001fae5 {tc} with {ret:+.2f}%. Flatline energy. Even the chart fell asleep.",
            ]
        elif ret < -15:
            candidates += [
                f"\U0001f4a9 {tc} at {ret:+.2f}%. If this were a group project, you'd be the one who didn't show up.",
                f"\U0001f4a9 Moment of silence for {tc} at {ret:+.2f}%. You didn't have to go this hard… in the wrong direction.",
                f"\U0001f4a9 {tc} at {ret:+.2f}%. Certified bag holder. No, not designer bags.",
            ]
        elif ret < -5:
            candidates += [
                f"\U0001f534 {tc} down {ret:+.2f}%. Not great, not terrible. Actually, it's terrible.",
                f"\U0001f534 {tc} returning {ret:+.2f}%. Underperforming a savings account. Impressive.",
            ]

    if len(total_returns) > 2:
        worst_days = total_returns.diff().dropna().min()
        volatile = worst_days[worst_days < -3].index.tolist()
        rng.shuffle(volatile)
        for t in volatile[:3]:
            tc = ticker_html.get(t, f"<b>{t}</b>")
            drop = worst_days[t]
            candidates += [
                f"\U0001f3a2 {tc} nosedived {drop:+.2f}% in one day. That's bungee jumping without the cord.",
                f"\U0001f3a2 {tc} dropped {drop:+.2f}% in a single day. Somewhere a stop-loss is crying.",
            ]

    bottom_half = sorted_rets.tail(total // 2)
    if len(bottom_half) >= 3:
        sampled = bottom_half.sample(3, random_state=rng.randint(0, 99999))
        names = ", ".join(ticker_html.get(t, f"<b>{t}</b>") for t in sampled.index)
        combined = sampled.sum()
        candidates += [
            f"\U0001f6bd {names} combining for {combined:+.2f}%. The Avengers of underperformance.",
            f"\U0001f6bd {names} returning {combined:+.2f}% together. Three picks, one shared L.",
        ]

    mvp_changes = len([e for e in throne["mvp_history"] if e.get("prev_ticker")])
    if mvp_changes >= 4:
        candidates += [
            f"\U0001f3b0 The MVP throne changed hands {mvp_changes} times. More drama than a reality TV show.",
        ]
    elif mvp_changes <= 1 and len(sorted_rets):
        mvp = sorted_rets.index[0]
        candidates += [
            f"\U0001f3b0 <b>{mvp}</b> has owned the throne the whole time. Everyone else? Participation trophies.",
        ]

    red = int((final_returns <= 0).sum())
    if red > total * 0.6:
        candidates += [
            f"\U0001f534 {red} out of {total} in the red. This isn't a portfolio, it's a crime scene.",
        ]
    elif red < total * 0.3:
        candidates += [
            f"\U0001f7e2 Only {red} out of {total} in the red. Don't get comfortable — the market is just loading the next prank.",
        ]

    # Skip anything used in the last 30 days
    recently_used = set()
    for snippets in (used_history or {}).values():
        recently_used.update(snippets)
    fresh = [r for r in candidates if _strip_html(r)[:80] not in recently_used]
    pool = fresh if fresh else candidates

    def _template(text: str) -> str:
        t = _strip_html(text)
        for ticker in sorted_rets.index:
            t = t.replace(ticker, "")
        return re.sub(r"[+-]?\d+\.?\d*%?", "", t).strip()

    rng.shuffle(pool)
    roasts, used_tickers, used_templates = [], set(), set()
    for r in pool:
        tmpl = _template(r)
        if tmpl in used_templates:
            continue
        text = _strip_html(r)
        found = next((t for t in sorted_rets.index if t in text), None)
        if found and found in used_tickers:
            continue
        roasts.append(r)
        used_templates.add(tmpl)
        if found:
            used_tickers.add(found)
        if len(roasts) >= 8:
            break
    for r in pool:  # backfill to at least 7
        if len(roasts) >= 7:
            break
        if r not in roasts:
            roasts.append(r)
    return roasts


def current_roast_day(now: datetime.datetime | None = None) -> str:
    """The trading day today's roasts are about (rolls over at 4 PM ET)."""
    now = (now or datetime.datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    day = now.date()
    if not (market_calendar.is_trading_day(day) and now.hour >= 16):
        day = market_calendar.previous_trading_day(day)
    return day.isoformat()


def load_cache() -> dict:
    try:
        with open(ROASTS_CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": "", "roasts": [], "used": {}}


def daily_roasts(final_returns: pd.Series, total_returns: pd.DataFrame,
                 throne: dict, ticker_html: dict) -> tuple[str, list]:
    """Cached-per-trading-day roasts. Returns (roast_day_iso, roasts)."""
    day = current_roast_day()
    cache = load_cache()
    if cache.get("date") == day and cache.get("roasts"):
        return day, cache["roasts"]

    used = cache.get("used", {})
    roasts = generate_roasts(final_returns, total_returns, throne, ticker_html, used)
    used[day] = [_strip_html(r)[:80] for r in roasts]
    for old in sorted(used)[:-30]:
        del used[old]
    try:
        with open(ROASTS_CACHE_PATH, "w") as f:
            json.dump({"date": day, "roasts": roasts, "used": used}, f, indent=2)
    except OSError:
        pass  # read-only deploys: roasts regenerate per session instead
    return day, roasts
