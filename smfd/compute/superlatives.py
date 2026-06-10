"""Fun stats: superlatives and achievement badges. Pure functions on the
daily total-return table (price + dividends-to-date)."""

from __future__ import annotations

from collections import Counter

import pandas as pd


def compute_superlatives(total_returns: pd.DataFrame, throne: dict,
                         name_map: dict, group_map: dict) -> dict:
    results = {}
    daily = total_returns
    tickers = list(daily.columns)
    daily_changes = daily.diff()

    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        best_idx = changes.stack().idxmax()
        worst_idx = changes.stack().idxmin()
        results["best_day"] = {
            "ticker": best_idx[1], "name": name_map.get(best_idx[1], best_idx[1]),
            "date": best_idx[0], "change": float(changes.loc[best_idx[0], best_idx[1]]),
        }
        results["worst_day"] = {
            "ticker": worst_idx[1], "name": name_map.get(worst_idx[1], worst_idx[1]),
            "date": worst_idx[0], "change": float(changes.loc[worst_idx[0], worst_idx[1]]),
        }

    # Comeback Kid: dipped negative, recovered the most off the low
    best_ticker, best_recovery = "", 0.0
    for t in tickers:
        low = daily[t].min()
        if low >= 0:
            continue
        recovery = daily[t].iloc[-1] - low
        if recovery > best_recovery:
            best_recovery, best_ticker = recovery, t
    if not best_ticker:  # nobody went negative: biggest bounce off any low
        best_ticker = min(tickers, key=lambda t: daily[t].min())
        best_recovery = daily[best_ticker].iloc[-1] - daily[best_ticker].min()
    results["comeback"] = {
        "ticker": best_ticker, "name": name_map.get(best_ticker, best_ticker),
        "recovery": float(best_recovery),
        "low": float(daily[best_ticker].min()),
        "final": float(daily[best_ticker].iloc[-1]),
    }

    # Longest reign: most total days on either throne
    reign_counts = Counter()
    for key in ("mvp_history", "bench_history"):
        history = throne[key]
        for i, entry in enumerate(history):
            if i > 0:
                days = abs((history[i - 1]["date"] - entry["date"]).days)
                reign_counts[entry["ticker"]] += days
            elif len(history) == 1:
                reign_counts[entry["ticker"]] += 1
    if reign_counts:
        ticker, days = reign_counts.most_common(1)[0]
        results["longest_reign"] = {"ticker": ticker, "name": name_map.get(ticker, ticker), "days": days}
    else:
        results["longest_reign"] = {"ticker": "", "name": "", "days": 0}

    # Rivalry: pair that swapped a throne the most
    swap_pairs = Counter()
    for history in (throne["mvp_history"], throne["bench_history"]):
        for entry in history:
            if entry.get("prev_ticker"):
                swap_pairs[tuple(sorted([entry["ticker"], entry["prev_ticker"]]))] += 1
    if swap_pairs:
        pair, count = swap_pairs.most_common(1)[0]
        results["rivalry"] = {
            "ticker1": pair[0], "name1": name_map.get(pair[0], pair[0]),
            "ticker2": pair[1], "name2": name_map.get(pair[1], pair[1]),
            "swaps": count,
        }
    else:
        results["rivalry"] = {"ticker1": "", "ticker2": "", "name1": "", "name2": "", "swaps": 0}

    # Group war: longest streak of daily best-average-move
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        winners = []
        for date in changes.index:
            sums, counts = {}, {}
            for t in tickers:
                g = group_map.get(t, "")
                if g:
                    sums[g] = sums.get(g, 0) + changes.loc[date, t]
                    counts[g] = counts.get(g, 0) + 1
            if sums:
                winners.append(max(sums, key=lambda g: sums[g] / counts[g]))
        best_g, best_streak, cur = "", 0, 1
        for i in range(1, len(winners)):
            if winners[i] == winners[i - 1]:
                cur += 1
            else:
                if cur > best_streak:
                    best_streak, best_g = cur, winners[i - 1]
                cur = 1
        if cur > best_streak and winners:
            best_streak, best_g = cur, winners[-1]
        results["etf_war"] = {"etf": best_g, "streak": best_streak}
    else:
        results["etf_war"] = {"etf": "", "streak": 0}

    # Sleeper / Fallen Angel / Middle Child
    total = len(tickers)
    if len(daily) > 1:
        first_ranks = daily.iloc[1].rank(ascending=False)
        final_ranks = daily.iloc[-1].rank(ascending=False)
        final = daily.iloc[-1]
        bottom_half = [t for t in tickers if first_ranks[t] > total / 2]
        if bottom_half:
            sleeper = max(bottom_half, key=lambda t: final[t])
            results["sleeper"] = {
                "ticker": sleeper, "name": name_map.get(sleeper, sleeper),
                "start_rank": int(first_ranks[sleeper]), "end_rank": int(final_ranks[sleeper]),
            }
        else:
            results["sleeper"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}
        top_half = [t for t in tickers if first_ranks[t] <= total / 2]
        if top_half:
            fallen = max(top_half, key=lambda t: final_ranks[t] - first_ranks[t])
            results["fallen"] = {
                "ticker": fallen, "name": name_map.get(fallen, fallen),
                "start_rank": int(first_ranks[fallen]), "end_rank": int(final_ranks[fallen]),
            }
        else:
            results["fallen"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}
    else:
        results["sleeper"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}
        results["fallen"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}

    final = daily.iloc[-1]
    middle = min(tickers, key=lambda t: abs(final[t]))
    results["middle"] = {
        "ticker": middle, "name": name_map.get(middle, middle),
        "return": float(final[middle]),
        "rank": int(final.rank(ascending=False)[middle]), "total": total,
    }

    # Power rankings: biggest 5-day movers
    if len(daily) >= 6:
        weekly = daily.iloc[-1] - daily.iloc[-6]
        climber, faller = weekly.idxmax(), weekly.idxmin()
        results["power"] = {
            "climber": climber, "climber_name": name_map.get(climber, climber),
            "climber_change": float(weekly[climber]),
            "faller": faller, "faller_name": name_map.get(faller, faller),
            "faller_change": float(weekly[faller]),
        }
    else:
        results["power"] = {"climber": "", "climber_name": "", "climber_change": 0,
                            "faller": "", "faller_name": "", "faller_change": 0}

    return results


def compute_achievements(total_returns: pd.DataFrame, throne: dict, scores: pd.DataFrame) -> list:
    """Achievement badges: list of {icon, name, desc, holder, unlocked}."""
    badges = []
    daily = total_returns
    daily_changes = daily.diff()
    final_returns = scores["total_return_pct"]

    if len(daily) > 1:
        mvp_counts = Counter(daily.iloc[1:].idxmax(axis=1))
        if mvp_counts:
            top, count = mvp_counts.most_common(1)[0]
            badges.append({"icon": "\U0001f48e", "name": "Diamond Hands",
                           "desc": "Most days as MVP", "holder": f"{top} ({count}d)",
                           "unlocked": count >= 5})
        bench_counts = Counter(daily.iloc[1:].idxmin(axis=1))
        if bench_counts:
            worst, count = bench_counts.most_common(1)[0]
            badges.append({"icon": "\U0001f40c", "name": "Bottom Feeder",
                           "desc": "Most days as benchwarmer", "holder": f"{worst} ({count}d)",
                           "unlocked": count >= 5})

    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        vol = changes.std()
        badges.append({"icon": "\U0001f3a2", "name": "Rollercoaster",
                       "desc": "Most volatile stock",
                       "holder": f"{vol.idxmax()} (±{vol.max():.2f}%/day)", "unlocked": True})
        badges.append({"icon": "\U0001f9d8", "name": "Steady Eddie",
                       "desc": "Least volatile stock",
                       "holder": f"{vol.idxmin()} (±{vol.min():.2f}%/day)", "unlocked": True})
        best_idx = changes.stack().idxmax()
        best_val = float(changes.loc[best_idx[0], best_idx[1]])
        badges.append({"icon": "\U0001f315", "name": "Moonshot",
                       "desc": "Biggest single-day gain",
                       "holder": f"{best_idx[1]} (+{best_val:.2f}%)", "unlocked": best_val > 3})
        worst_idx = changes.stack().idxmin()
        worst_val = float(changes.loc[worst_idx[0], worst_idx[1]])
        badges.append({"icon": "\U0001f4a5", "name": "Crash Landing",
                       "desc": "Biggest single-day loss",
                       "holder": f"{worst_idx[1]} ({worst_val:+.2f}%)", "unlocked": worst_val < -3})

    if "dividend_income" in scores.columns and len(scores):
        div_king = scores["dividend_income"].idxmax()
        badges.append({"icon": "\U0001f4b0", "name": "Dividend King",
                       "desc": "Most dividend income",
                       "holder": f"{div_king} (${scores.loc[div_king, 'dividend_income']:.2f})",
                       "unlocked": scores.loc[div_king, "dividend_income"] > 0})

    throne_takes = Counter(e["ticker"] for e in throne["mvp_history"])
    if throne_takes:
        term, count = throne_takes.most_common(1)[0]
        badges.append({"icon": "\U0001f916", "name": "The Terminator",
                       "desc": "Took MVP throne most times",
                       "holder": f"{term} ({count}x)", "unlocked": count >= 2})

    sw = throne.get("streak_winner", {})
    if sw.get("ticker") and sw.get("type") == "mvp":
        badges.append({"icon": "⚔️", "name": "Iron Throne",
                       "desc": "Longest MVP streak ever",
                       "holder": f"{sw['ticker']} ({sw['streak']}d)", "unlocked": sw["streak"] >= 5})

    sorted_rets = final_returns.sort_values(ascending=False)
    if len(sorted_rets) >= 2:
        gaps = sorted_rets.diff(-1).abs()
        i = gaps.iloc[:-1].idxmin()
        pos = sorted_rets.index.get_loc(i)
        pair = (sorted_rets.index[pos], sorted_rets.index[pos + 1])
        min_gap = float(gaps[i])
        badges.append({"icon": "\U0001f4f8", "name": "Photo Finish",
                       "desc": "Closest return gap",
                       "holder": f"{pair[0]} vs {pair[1]} ({min_gap:.2f}%)",
                       "unlocked": min_gap < 1.0})

    if len(daily) > 1:
        first_ranks = daily.iloc[1].rank(ascending=False)
        final_ranks = daily.iloc[-1].rank(ascending=False)
        total = len(daily.columns)
        horses = [t for t in daily.columns
                  if first_ranks[t] > total * 0.75 and final_ranks[t] <= total * 0.25]
        if horses:
            best = max(horses, key=lambda t: final_returns.get(t, 0))
            badges.append({"icon": "\U0001f40e", "name": "Dark Horse",
                           "desc": "Bottom 25% → Top 25%",
                           "holder": f"{best} (#{int(first_ranks[best])}→#{int(final_ranks[best])})",
                           "unlocked": True})
        else:
            badges.append({"icon": "\U0001f40e", "name": "Dark Horse",
                           "desc": "Bottom 25% → Top 25%", "holder": "No one yet",
                           "unlocked": False})
    return badges
