#!/usr/bin/env python3
"""Fetch stock data and save to data/stock_data.json (v2 format).

Reads tickers from players.json, fetches raw prices, splits, dated dividends,
technical signals, earnings, and news via yfinance, then writes a single JSON
file consumed by the app.

v2 format notes (vs legacy):
- ``prices`` are RAW closes (auto_adjust=False) — what the ticker actually traded at.
- ``prices_split_adjusted`` is the raw series back-adjusted to today's share basis
  (prices before a split divided by the cumulative ratio of all later splits).
  All return math downstream uses this series. Never write a dividend-adjusted
  series here — dividends are counted separately as cash and would double-count.
- ``dividends`` are dated per-share cash amounts: {ticker: [{date, amount}]}.
- ``splits`` are {ticker: [{date, ratio}]}; ratio > 1 forward, < 1 reverse.
- ``as_of`` (ISO, America/New_York) + ``fetch_errors`` list. On per-ticker
  failure the previous run's values are kept and the ticker is logged.

Usage:
    python fetch_data.py
"""

from __future__ import annotations

import datetime
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GAME_START = datetime.date(2026, 3, 6)
TIMEZONE = ZoneInfo("America/New_York")
BATCH_SIZE = 20
BATCH_DELAY = 2          # seconds between yf.download batches
MAX_RETRIES = 3
BACKOFF_DELAYS = [2, 8, 32]  # exponential backoff between attempts
THREAD_WORKERS = 10

ROOT = Path(__file__).resolve().parent
PLAYERS_PATH = ROOT / "players.json"
OUTPUT_DIR = ROOT / "data"
OUTPUT_PATH = OUTPUT_DIR / "stock_data.json"

FETCH_ERRORS: list[str] = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_tickers() -> list[dict]:
    with open(PLAYERS_PATH) as f:
        return json.load(f)["players"]


def load_previous_output() -> dict:
    """Previous run's JSON — fallback so a flaky ticker keeps its last good data."""
    try:
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _retry(fn, label=""):
    """Call *fn* with exponential-backoff retries. Raises after the last attempt."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[min(attempt - 1, len(BACKOFF_DELAYS) - 1)]
                print(f"  [retry {attempt}/{MAX_RETRIES} in {delay}s] {label}: {exc}")
                time.sleep(delay)
            else:
                print(f"  [FAILED] {label}: {exc}")
                raise


# ---------------------------------------------------------------------------
# 1. Daily raw close prices
# ---------------------------------------------------------------------------


def fetch_prices(tickers: list[str], start: datetime.date, end: datetime.date) -> dict:
    """Download daily RAW closes in batches -> {ticker: {date_str: price}}."""
    all_close = pd.DataFrame()
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        label = f"price batch {i // BATCH_SIZE + 1}"
        print(f"  Downloading {label} ({len(batch)} tickers)...")

        def _download(batch=batch):
            return yf.download(
                batch,
                start=start,
                end=end + datetime.timedelta(days=1),
                auto_adjust=False,  # raw closes; split adjustment is done explicitly below
                progress=False,
                threads=True,
            )

        try:
            data = _retry(_download, label=label)
        except Exception as exc:
            FETCH_ERRORS.append(f"{label}: {exc}")
            continue

        if data.empty:
            FETCH_ERRORS.append(f"{label}: empty response")
            continue

        close = data["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame(name=batch[0])
        all_close = pd.concat([all_close, close], axis=1)

        if i + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_DELAY)

    all_close = all_close.ffill().bfill()

    prices: dict[str, dict[str, float]] = {}
    for ticker in tickers:
        if ticker in all_close.columns and not all_close[ticker].isna().all():
            series = all_close[ticker].dropna()
            prices[ticker] = {
                d.strftime("%Y-%m-%d"): round(float(v), 4) for d, v in series.items()
            }
    return prices


# ---------------------------------------------------------------------------
# 2. Splits + dated dividends (correctness-critical)
# ---------------------------------------------------------------------------


def fetch_actions(tickers: list[str], start: datetime.date, end: datetime.date) -> tuple[dict, dict]:
    """Fetch split and dividend action streams per ticker (threaded).

    Splits are fetched over the full history (a split before game start still
    matters if yfinance's raw series spans it — it doesn't for our window, but
    the window filter keeps this honest); dividends only within the window.
    """

    def _fetch_one(ticker: str):
        splits_out, divs_out = [], []
        try:
            t = yf.Ticker(ticker)
            s = t.splits
            if s is not None and not s.empty:
                s.index = s.index.tz_localize(None)
                for d, ratio in s.items():
                    dd = d.date()
                    if start <= dd <= end and ratio:
                        splits_out.append({"date": dd.isoformat(), "ratio": float(ratio)})
            d = t.dividends
            if d is not None and not d.empty:
                d.index = d.index.tz_localize(None)
                mask = (d.index >= pd.Timestamp(start)) & (d.index <= pd.Timestamp(end))
                for ex_date, amount in d[mask].items():
                    if amount:
                        divs_out.append({"date": ex_date.date().isoformat(),
                                         "amount": round(float(amount), 6)})
            return ticker, splits_out, divs_out, None
        except Exception as exc:
            return ticker, [], [], str(exc)

    print(f"  Fetching splits + dividends for {len(tickers)} tickers...")
    splits, dividends = {}, {}
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, s_out, d_out, err = future.result()
            splits[ticker] = s_out
            dividends[ticker] = d_out
            if err:
                FETCH_ERRORS.append(f"actions {ticker}: {err}")
    return splits, dividends


def _cliff_present(series: dict, split_date: str, ratio: float) -> bool:
    """Does the price series still contain the raw split-day cliff?

    Yahoo restates price history to the post-split basis, so the downloaded
    Close is normally ALREADY split-adjusted (verified: PPLT's 10:1 on
    2026-05-18 shows no cliff). We only back-adjust if the cliff is actually
    there — adjusting an already-adjusted series would manufacture a phantom
    return. Test: multiplying the split-day jump by the ratio should bring it
    closer to 1.0 if (and only if) the cliff exists.
    """
    import math
    dates = sorted(series)
    after = next((d for d in dates if d >= split_date), None)
    before = next((d for d in reversed(dates) if d < split_date), None)
    if after is None or before is None or not series[before]:
        return False
    jump = series[after] / series[before]
    if jump <= 0:
        return False
    return abs(math.log(jump * ratio)) < abs(math.log(jump))


def split_adjust_prices(prices: dict, splits: dict) -> dict:
    """Ensure closes are on today's share basis.

    For each split still visible as a cliff in the series, prices before the
    split date are divided by the ratio (a 4:1 split divides earlier prices
    by 4; a 1:10 reverse split, ratio 0.1, multiplies them by 10). Splits that
    Yahoo has already restated away are left untouched.
    """
    adjusted: dict[str, dict[str, float]] = {}
    for ticker, series in prices.items():
        ticker_splits = [
            (s["date"], s["ratio"]) for s in splits.get(ticker, [])
            if s["ratio"] and _cliff_present(series, s["date"], s["ratio"])
        ]
        if not ticker_splits:
            adjusted[ticker] = dict(series)
            continue
        out = {}
        for date_str, price in series.items():
            factor = 1.0
            for split_date, ratio in ticker_splits:
                if date_str < split_date:
                    factor *= ratio
            out[date_str] = round(price / factor, 6)
        adjusted[ticker] = out
    return adjusted


# ---------------------------------------------------------------------------
# 3. Technical signals (on split+dividend adjusted closes — standard practice)
# ---------------------------------------------------------------------------


def compute_signals(tickers: list[str], start: datetime.date, end: datetime.date) -> dict:
    extended_start = start - datetime.timedelta(days=45)

    print("  Downloading extended price history for signals...")
    try:
        data = _retry(
            lambda: yf.download(
                tickers,
                start=extended_start,
                end=end + datetime.timedelta(days=1),
                auto_adjust=True,
                progress=False,
                threads=True,
            ),
            label="signal price download",
        )
    except Exception as exc:
        FETCH_ERRORS.append(f"signals: {exc}")
        return {}
    if data.empty:
        return {}

    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    close = close.ffill().bfill()

    signals: dict = {}
    for ticker in tickers:
        if ticker not in close.columns or close[ticker].isna().all():
            continue
        prices = close[ticker].dropna()
        if len(prices) < 20:
            signals[ticker] = {"rsi": None, "signal": "HOLD", "score": 0,
                               "sma_cross": None, "price_vs_sma": None,
                               "signal_date": None, "prev_signal": None}
            continue

        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        current_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

        sma10 = prices.rolling(window=10).mean()
        sma20 = prices.rolling(window=20).mean()
        sma_cross = bool(sma10.iloc[-1] > sma20.iloc[-1])
        price_vs_sma = bool(prices.iloc[-1] > sma20.iloc[-1])

        def _score(r, cross, above):
            s = 0
            if r < 30:
                s += 1
            elif r > 70:
                s -= 1
            s += 1 if cross else -1
            s += 1 if above else -1
            return s

        def _label(s):
            return "BUY" if s >= 2 else ("SELL" if s <= -2 else "HOLD")

        score = _score(current_rsi, sma_cross, price_vs_sma)
        signal = _label(score)

        daily_signals = []
        for i in range(len(prices)):
            if pd.isna(rsi.iloc[i]) or pd.isna(sma20.iloc[i]) or pd.isna(sma10.iloc[i]):
                daily_signals.append(None)
                continue
            daily_signals.append(_label(_score(
                float(rsi.iloc[i]),
                sma10.iloc[i] > sma20.iloc[i],
                prices.iloc[i] > sma20.iloc[i],
            )))

        prev_signal, change_date = None, None
        for j in range(len(daily_signals) - 1, 0, -1):
            if daily_signals[j] is None or daily_signals[j - 1] is None:
                continue
            if daily_signals[j] != daily_signals[j - 1]:
                prev_signal = daily_signals[j - 1]
                change_date = prices.index[j].strftime("%m/%d")
                break

        signals[ticker] = {
            "rsi": round(current_rsi, 1),
            "signal": signal,
            "score": score,
            "sma_cross": sma_cross,
            "price_vs_sma": price_vs_sma,
            "signal_date": change_date,
            "prev_signal": prev_signal,
        }
    return signals


# ---------------------------------------------------------------------------
# 4. Earnings
# ---------------------------------------------------------------------------


def fetch_earnings(tickers: list[str]) -> dict:
    def _fetch_one(ticker: str):
        result = {"next_date": "", "eps_est": None, "eps_actual": None,
                  "last_earnings_date": "", "last_eps_reported": None,
                  "last_eps_estimate": None}
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            cal_dict = None
            if cal is not None:
                if isinstance(cal, dict):
                    cal_dict = cal
                elif hasattr(cal, "T"):
                    try:
                        cal_dict = cal.T.iloc[0].to_dict() if len(cal.columns) > 0 else None
                    except Exception:
                        pass
            if cal_dict:
                ed_list = cal_dict.get("Earnings Date", [])
                if not isinstance(ed_list, list):
                    ed_list = [ed_list] if ed_list else []
                if ed_list:
                    try:
                        result["next_date"] = ed_list[0].strftime("%b %d")
                    except Exception:
                        result["next_date"] = str(ed_list[0])[:6] if ed_list[0] else ""
                eps_avg = cal_dict.get("Earnings Average")
                if eps_avg:
                    result["eps_est"] = round(eps_avg, 2)

            try:
                eh = t.earnings_history
                if eh is not None and len(eh) > 0:
                    latest = eh.iloc[-1]
                    result["last_earnings_date"] = eh.index[-1].strftime("%b %y")
                    for src, dst in (("epsActual", "last_eps_reported"),
                                     ("epsEstimate", "last_eps_estimate")):
                        v = latest.get(src)
                        if v is not None and str(v) != "nan":
                            result[dst] = round(float(v), 2)
                    if result["next_date"]:
                        try:
                            ed = datetime.datetime.strptime(
                                f"{result['next_date']} {datetime.date.today().year}",
                                "%b %d %Y").date()
                            if ed <= datetime.date.today() and result["last_eps_reported"] is not None:
                                result["eps_actual"] = result["last_eps_reported"]
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as exc:
            FETCH_ERRORS.append(f"earnings {ticker}: {exc}")
        return ticker, result

    print(f"  Fetching earnings for {len(tickers)} tickers...")
    results = {}
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, data = future.result()
            results[ticker] = data
    return results


# ---------------------------------------------------------------------------
# 5. News
# ---------------------------------------------------------------------------


def fetch_news(tickers: list[str]) -> dict:
    def _fetch_one(ticker: str):
        items = []
        try:
            t = yf.Ticker(ticker)
            news = t.news
            if news:
                for raw in news[:3]:
                    content = raw.get("content", raw)
                    title = content.get("title", "") or raw.get("title", "")
                    publisher = (
                        content.get("provider", {}).get("displayName", "")
                        if isinstance(content.get("provider"), dict)
                        else raw.get("publisher", "")
                    )
                    link = (
                        content.get("canonicalUrl", {}).get("url", "")
                        if isinstance(content.get("canonicalUrl"), dict)
                        else raw.get("link", "")
                    )
                    pub_time = raw.get("providerPublishTime", content.get("pubDate", ""))
                    if title:
                        items.append({"title": title, "publisher": publisher,
                                      "link": link, "providerPublishTime": pub_time})
        except Exception:
            pass  # news is cosmetic; never fail the run for it
        return ticker, items

    print(f"  Fetching news for {len(tickers)} tickers...")
    results = {}
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, items = future.result()
            results[ticker] = items
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    now_et = datetime.datetime.now(TIMEZONE)
    start = GAME_START
    end = now_et.date()

    print(f"Stock data fetch — {start} to {end}")
    print("=" * 50)

    players = load_tickers()
    tickers = [p["ticker"] for p in players]
    previous = load_previous_output()
    print(f"Loaded {len(tickers)} tickers from players.json\n")

    print("[1/5] Fetching daily raw prices...")
    prices = fetch_prices(tickers, start, end)
    print(f"  Got prices for {len(prices)} tickers\n")

    print("[2/5] Fetching splits + dividends...")
    splits, dividends = fetch_actions(tickers, start, end)
    print("  Done\n")

    # Per-ticker failure: keep the previous run's values rather than dropping out
    for ticker in tickers:
        if ticker not in prices:
            prev_prices = previous.get("prices", {}).get(ticker)
            if prev_prices:
                prices[ticker] = prev_prices
                splits[ticker] = previous.get("splits", {}).get(ticker, splits.get(ticker, []))
                prev_divs = previous.get("dividends", {}).get(ticker)
                if isinstance(prev_divs, list):  # only reuse v2-format dividends
                    dividends[ticker] = prev_divs
                FETCH_ERRORS.append(f"{ticker}: no fresh prices — kept previous values")
            else:
                FETCH_ERRORS.append(f"{ticker}: no prices and no previous values")

    prices_split_adjusted = split_adjust_prices(prices, splits)

    start_prices: dict[str, float] = {}
    end_prices: dict[str, float] = {}
    for ticker, series in prices.items():
        sorted_dates = sorted(series.keys())
        if sorted_dates:
            start_prices[ticker] = series[sorted_dates[0]]
            end_prices[ticker] = series[sorted_dates[-1]]

    print("[3/5] Computing technical signals...")
    signals = compute_signals(tickers, start, end)
    print(f"  Computed signals for {len(signals)} tickers\n")

    print("[4/5] Fetching earnings data...")
    earnings = fetch_earnings(tickers)
    print("  Done\n")

    print("[5/5] Fetching news headlines...")
    news = fetch_news(tickers)
    print("  Done\n")

    output = {
        "format": 2,
        "as_of": now_et.isoformat(),
        "last_updated": now_et.isoformat(),  # legacy key, kept for compatibility
        "fetch_errors": FETCH_ERRORS,
        "prices": prices,
        "prices_split_adjusted": prices_split_adjusted,
        "splits": splits,
        "dividends": dividends,
        "start_prices": start_prices,
        "end_prices": end_prices,
        "signals": signals,
        "earnings": earnings,
        "news": news,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print("=" * 50)
    print(f"Saved to {OUTPUT_PATH}")
    print(f"as_of: {now_et.isoformat()}")
    if FETCH_ERRORS:
        print(f"fetch_errors ({len(FETCH_ERRORS)}):")
        for e in FETCH_ERRORS:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
