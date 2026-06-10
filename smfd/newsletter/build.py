"""Assemble the newsletter snapshot from the compute layer.

The snapshot reads the SAME computed numbers as the dashboard, so the email can
never contradict the site. Standings are always all-time (that's the game);
movers and the narrative cover the selected period.
"""

from __future__ import annotations

import datetime
import json
import random

from smfd.compute import groups, race
from smfd.config import GAME_START, GROUP_NAMES, NEWSLETTER_LOG_PATH
from smfd.data import GameData

PERIODS = {
    "month": "Last month",
    "since_last": "Since the last newsletter",
    "all": "All-time",
}


# --- Newsletter log (enables "since last newsletter" + month-over-month) ---

def load_log() -> list:
    try:
        with open(NEWSLETTER_LOG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def last_newsletter_date() -> datetime.date | None:
    log = load_log()
    if not log:
        return None
    try:
        return datetime.date.fromisoformat(log[-1]["date"])
    except (KeyError, ValueError):
        return None


def record_newsletter(period_label: str) -> None:
    log = load_log()
    log.append({"date": datetime.date.today().isoformat(), "period_label": period_label})
    try:
        NEWSLETTER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NEWSLETTER_LOG_PATH, "w") as f:
            json.dump(log, f, indent=2)
    except OSError:
        pass


# --- Snapshot ---

def _months_elapsed(as_of: datetime.date) -> int:
    return max((as_of.year - GAME_START.year) * 12 + as_of.month - GAME_START.month, 1)


def _shift_month_back(d: datetime.date) -> datetime.date:
    year, month = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    try:
        return d.replace(year=year, month=month)
    except ValueError:  # e.g. Mar 31 -> Feb 28
        return d.replace(year=year, month=month, day=1)


def _period_window(period: str, as_of: datetime.date) -> tuple:
    if period == "all":
        return GAME_START, f"All-time · {GAME_START.strftime('%b %d')} – {as_of.strftime('%b %d, %Y')}"
    if period == "since_last":
        last = last_newsletter_date()
        if last and last < as_of:
            return last, (f"Since the last newsletter · {last.strftime('%b %d')} – "
                          f"{as_of.strftime('%b %d, %Y')}")
        period = "month"  # no log yet — fall through
    start = max(_shift_month_back(as_of), GAME_START)
    label = (f"Month {_months_elapsed(as_of)} · {start.strftime('%b %d')} – "
             f"{as_of.strftime('%b %d, %Y')}")
    return start, label


def _pick_row(scores, ticker: str) -> dict:
    return {
        "ticker": ticker,
        "name": scores.loc[ticker, "name"],
        "etf": scores.loc[ticker, "group"],
        "total_return_pct": float(scores.loc[ticker, "total_return_pct"]),
    }


def _roast_line(laggard: dict, rng: random.Random) -> str:
    t = laggard["ticker"]
    pct = laggard["total_return_pct"]
    lines = [
        f"{t} holders, {pct:+.1f}% isn't a return, it's a cry for help. \U0001f480",
        f"Moment of silence for {t} at {pct:+.1f}%. The diaper bag is holding up better. \U0001f480",
        f"{t} at {pct:+.1f}%. Somewhere a piggy bank is outperforming you. \U0001f437",
        f"{t}: {pct:+.1f}%. Alessi has a better savings rate, and she has no income. \U0001f476",
    ]
    return rng.choice(lines)


def _headline(leader: dict, group_standings: list, movers: list) -> str:
    top_group = group_standings[0] if group_standings else None
    if top_group and top_group["change_vs_last"].startswith("+"):
        return (f"{GROUP_NAMES.get(top_group['etf'], top_group['etf'])} retook the group lead, "
                f"powered by {leader['name']}'s {leader['total_return_pct']:+.1f}%.")
    if (movers and movers[0]["period_change_pct"] > 5
            and movers[0]["ticker"] != leader["ticker"]):
        return (f"{movers[0]['ticker']} went on a {movers[0]['period_change_pct']:+.1f} pp tear, "
                f"while {leader['ticker']} still rules the leaderboard at "
                f"{leader['total_return_pct']:+.1f}%.")
    if top_group:
        return (f"{GROUP_NAMES.get(top_group['etf'], top_group['etf'])} holds the group crown and "
                f"{leader['ticker']} leads the field at {leader['total_return_pct']:+.1f}%.")
    return f"{leader['ticker']} leads at {leader['total_return_pct']:+.1f}%."


def _narrative(snapshot: dict, n_picks: int, rng: random.Random) -> str:
    leader = snapshot["leader"]
    laggard = snapshot["laggard"]
    days = snapshot["days_remaining"]
    movers = snapshot["top_movers"]
    mover_bit = ""
    if movers:
        m = movers[0]
        mover_bit = (f" Biggest mover this period: {m['ticker']} at "
                     f"{m['period_change_pct']:+.1f} pp — somebody's been eating their vegetables.")
    closers = [
        f"With {days} days left, there's plenty of runway for chaos. Keep those picks warm!",
        f"{days} days to the finish line — anything can happen, and in this draft it usually does!",
        f"Just {days} days until Alessi renders final judgment. No pressure, {laggard['ticker']}.",
    ]
    return (
        f"{leader['name']} ({leader['ticker']}) is sitting on the throne at "
        f"{leader['total_return_pct']:+.1f}%, while {laggard['name']} ({laggard['ticker']}) is "
        f"redecorating the basement at {laggard['total_return_pct']:+.1f}%.{mover_bit} "
        f"All {n_picks} picks are still in it — {rng.choice(closers)}"
    )


def build_snapshot(data: GameData, computed: dict, period: str = "month") -> dict:
    scores = computed["scores"]
    total_returns = computed["total_returns"]
    as_of = total_returns.index[-1].date()

    window_start, period_label = _period_window(period, as_of)

    # Period movers: change in total return (pp) across the window
    in_window = total_returns.loc[total_returns.index >= str(window_start)]
    if len(in_window) >= 2:
        period_change = (in_window.iloc[-1] - in_window.iloc[0]).sort_values(ascending=False)
    else:
        period_change = total_returns.iloc[-1].sort_values(ascending=False)
    top_movers = [{"ticker": t, "period_change_pct": float(v)}
                  for t, v in period_change.head(3).items()]
    bottom_movers = [{"ticker": t, "period_change_pct": float(v)}
                     for t, v in period_change.tail(3).sort_values().items()]

    # Group standings with rank change measured across the period window
    compare_days = max(len(in_window) - 1, 1)
    standings = groups.group_standings(total_returns, scores, data.group_map,
                                       compare_days=compare_days)
    group_rows = [{"etf": s["etf"], "avg_return_pct": s["avg_return_pct"],
                   "rank": s["rank"], "change_vs_last": s["change_vs_last"]}
                  for s in standings]

    leader = _pick_row(scores, scores.index[0])
    laggard = _pick_row(scores, scores.index[-1])

    rng = random.Random(as_of.isoformat())  # deterministic per day: preview == download
    snapshot = {
        "period_label": period_label,
        "period": period,
        "as_of": as_of.isoformat(),
        "days_remaining": race.days_remaining(as_of),
        "leader": leader,
        "laggard": laggard,
        "group_standings": group_rows,
        "standings_top": [_pick_row(scores, t) for t in scores.head(5).index],
        "standings_bottom": [_pick_row(scores, t) for t in scores.tail(5).index],
        "top_movers": top_movers,
        "bottom_movers": bottom_movers,
        "total_value": float(scores["total_value"].sum()),
        "total_invested": float(data.stake * len(scores)),
        "total_dividends": float(scores["dividend_income"].sum()),
        "n_picks": len(scores),
    }
    snapshot["headline_stat"] = _headline(leader, group_rows, top_movers)
    snapshot["roast"] = _roast_line(laggard, rng)
    snapshot["narrative"] = _narrative(snapshot, len(scores), rng)
    return snapshot
