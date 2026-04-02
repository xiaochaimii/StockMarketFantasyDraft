import html as html_mod
import json
import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo
import requests
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import yfinance as yf
import numpy as np
import plotly.graph_objects as go


@st.cache_data(ttl=86400)
def fetch_all_us_stocks():
    url = "https://api.nasdaq.com/api/screener/stocks"
    params = {"tableType": "traded", "limit": 10000, "offset": 0}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = data["data"]["table"]["rows"]
        stocks = []
        for row in rows:
            symbol = row.get("symbol", "").strip()
            name = row.get("name", "").strip()
            if symbol and name:
                stocks.append({"symbol": symbol, "name": name})
        # Clean up verbose suffixes from NASDAQ names
        suffixes = [" Common Stock", " Common Shares", " Ordinary Shares",
                    " American Depositary Shares", " American Depositary Share",
                    ", Inc.", " Inc.", ", Inc", " Inc",
                    " Corporation", " Corp.", " Corp",
                    ", Ltd.", " Ltd.", ", Ltd", " Ltd",
                    " Holdings", " Holding",
                    " Class A", " Class B", " Class C"]
        for s in stocks:
            name = s["name"]
            for suffix in suffixes:
                if name.endswith(suffix):
                    name = name[:-len(suffix)].strip()
            # Also remove trailing comma
            s["name"] = name.rstrip(",").strip()
        stocks.sort(key=lambda s: s["symbol"])
        return stocks
    except Exception as e:
        st.warning(f"Could not load stock list: {e}")
        return []


def is_market_open():
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


REFRESH_INTERVAL = timedelta(seconds=3600) if is_market_open() else None


def format_signed_currency(value):
    return f"${value:.2f}" if value >= 0 else f"(${abs(value):.2f})"


def format_signed_percent(value):
    return f"{value:.2f}%" if value >= 0 else f"({abs(value):.2f}%)"


def interpolate_hex_color(start_hex, end_hex, fraction):
    start_hex = start_hex.lstrip("#")
    end_hex = end_hex.lstrip("#")
    start_rgb = tuple(int(start_hex[i:i + 2], 16) for i in (0, 2, 4))
    end_rgb = tuple(int(end_hex[i:i + 2], 16) for i in (0, 2, 4))
    blended = tuple(
        round(start + (end - start) * fraction)
        for start, end in zip(start_rgb, end_rgb)
    )
    return "#" + "".join(f"{value:02x}" for value in blended)

# --- Config ---
st.set_page_config(page_title="Stock Market Fantasy Draft", layout="wide", initial_sidebar_state="collapsed")

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet" />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
<style>
:root {
    --bg: #eef3ea;
    --panel: rgba(248, 251, 246, 0.8);
    --panel-strong: rgba(251, 253, 250, 0.96);
    --border: rgba(18, 51, 36, 0.12);
    --text: #102018;
    --muted: #5d6f65;
    --accent: #0e5f3a;
    --accent-2: #d7a83a;
    --negative: #8f2d1b;
    --shadow: 0 18px 44px rgba(16, 42, 32, 0.12);
}
html, body, [class*="css"]  {
    font-family: 'Space Grotesk', sans-serif !important;
}
/* Fix Safari mobile whitespace/overflow */
html, body {
    overflow-x: hidden !important;
    -webkit-overflow-scrolling: touch;
}
@media (max-width: 768px) {
    [data-testid="stSidebar"] {
        display: none !important;
    }
}
* {
    font-family: 'Space Grotesk', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji' !important;
}
span[class*="material"], [data-testid*="collapse"] span, [data-testid*="Collapse"] span, [data-testid*="expand"] span, [data-testid*="Expand"] span, [kind="icon"] span, .stIcon span, [data-testid="stBaseButton-headerNoPadding"] span { font-family: 'Material Symbols Rounded' !important; }
table td, table th, code, .mono { font-family: 'IBM Plex Mono', monospace !important; }
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(215, 168, 58, 0.24), transparent 24%),
        radial-gradient(circle at top right, rgba(14, 95, 58, 0.16), transparent 20%),
        linear-gradient(180deg, #f8fbf6 0%, var(--bg) 100%);
    color: var(--text);
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d2f20 0%, #081f16 100%);
}
[data-testid="stSidebar"] * {
    color: #f7efe4 !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] {
    background: #ffffff !important;
    border-radius: 14px;
}
[data-testid="stSidebar"] [data-baseweb="select"] {
    background: #ffffff !important;
    border-radius: 14px;
}
[data-testid="stSidebar"] .stDateInput {
    background: transparent;
    border-radius: 0;
}
[data-testid="stSidebar"] .stDateInput [data-baseweb="input"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(247, 239, 228, 0.4) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0.2rem 0 !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] textarea {
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
    background-color: #ffffff !important;
}
[data-testid="stSidebar"] .stDateInput [data-baseweb="input"] input {
    background-color: transparent !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
[data-testid="stSidebar"] textarea::placeholder {
    color: rgba(16, 32, 24, 0.7) !important;
    -webkit-text-fill-color: rgba(16, 32, 24, 0.7) !important;
}
[data-testid="stSidebar"] [data-baseweb="input"] div,
[data-testid="stSidebar"] [data-testid="InputInstructions"],
[data-testid="stSidebar"] [data-testid="InputInstructions"] * {
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
}
[data-testid="stSidebar"] .stDateInput input {
    color: #f7efe4 !important;
    -webkit-text-fill-color: #f7efe4 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
    background-color: #ffffff !important;
}
[data-testid="stSidebar"] button {
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.16);
}
[data-testid="stHeader"] {
    background: transparent;
}
.block-container {
    padding-top: 2.5rem;
    padding-bottom: 3rem;
}
.hero-card,
.section-card {
    background: var(--panel);
    backdrop-filter: blur(16px);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
}
.hero-card {
    padding: 1.4rem 1.75rem;
    border-radius: 28px;
    margin-bottom: 0.75rem;
    position: relative;
    overflow: hidden;
}
.hero-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}
.hero-card::after {
    content: "";
    position: absolute;
    inset: auto -10% -40% auto;
    width: 18rem;
    height: 18rem;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(215, 168, 58, 0.2) 0%, transparent 65%);
}
.hero-kicker {
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-size: 0.76rem;
    color: var(--accent-2);
    font-weight: 700;
}
.hero-title {
    font-size: clamp(2rem, 4vw, 3.5rem);
    line-height: 0.95;
    margin: 0.4rem 0 0.8rem;
    font-weight: 700;
}
.hero-subtitle {
    color: var(--muted);
    max-width: 58rem;
    font-size: 1rem;
    margin-bottom: 0;
}
.section-card {
    border-radius: 24px;
    padding: 0.85rem 1.1rem 1rem;
    margin-top: 0.6rem;
}
.metric-card {
    background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(242, 248, 241, 0.96) 100%);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 1rem 1.1rem;
    box-shadow: 0 12px 24px rgba(82, 58, 32, 0.08);
    position: relative;
    height: 100%;
    min-height: 175px;
}
/* Force equal-height columns */
[data-testid="stHorizontalBlock"] {
    align-items: stretch !important;
}
[data-testid="stColumn"] {
    display: flex !important;
}
[data-testid="stColumn"] > div {
    height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stColumn"] > div > div {
    flex: 1 !important;
}
[data-testid="stColumn"] > div > div > div {
    height: 100% !important;
}
.metric-card::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 6px;
    border-radius: 20px 0 0 20px;
}
.metric-card.mvp::before {
    background: linear-gradient(180deg, #19a05f 0%, #0e5f3a 100%);
}
.metric-card.bench::before {
    background: linear-gradient(180deg, #d14a34 0%, #8b1e1e 100%);
}
.metric-label {
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.72rem;
    font-weight: 700;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    margin-top: 0.15rem;
}
.metric-detail {
    color: var(--muted);
    font-size: 0.86rem;
    margin-top: 0.2rem;
}
.positive { color: var(--accent); }
.negative { color: var(--negative); }
.section-heading {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.section-copy {
    color: var(--muted);
    margin-bottom: 0;
}
h1, h2, h3 {
    color: var(--text);
    letter-spacing: -0.03em;
}
div[data-testid="stMetric"] {
    background: var(--panel-strong);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 0.9rem 1rem;
    box-shadow: 0 12px 24px rgba(82, 58, 32, 0.08);
}
div[data-testid="stPlotlyChart"] {
    background: var(--panel-strong);
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 0.35rem;
    box-shadow: var(--shadow);
    overflow: hidden;
}
table.leaderboard {
    width: 100% !important;
    border-collapse: separate !important;
    border-spacing: 0;
    overflow: hidden;
    border-radius: 18px;
    background: var(--panel-strong);
}
table.leaderboard td, table.leaderboard th {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(18, 51, 36, 0.08);
}
table.leaderboard th {
    background: linear-gradient(90deg, #0d2f20 0%, #13492f 100%);
    color: #f4f0e3;
    position: sticky;
    top: 0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.75rem;
}
table.leaderboard tr:nth-child(even) td {
    background: rgba(16, 95, 58, 0.04);
}
table.leaderboard tr td:first-child {
    font-weight: 700;
    color: var(--accent);
}
[data-testid="InputInstructions"] {
    display: none !important;
}
div[data-testid="stTextInput"] [data-baseweb="input"],
div[data-testid="stTextInput"] [data-baseweb="input"] * {
    background-color: #ffffff !important;
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
}
div[data-testid="stTextInput"] [data-baseweb="input"] {
    border-radius: 14px !important;
    border: 1px solid rgba(16, 32, 24, 0.2) !important;
}
.stDateInput input {
    border-radius: 14px !important;
    background-color: #ffffff !important;
    border: 1px solid rgba(16, 32, 24, 0.2) !important;
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] {
    border-radius: 14px !important;
    background-color: #ffffff !important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] * {
    background-color: #ffffff !important;
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
}
/* Input labels in main area */
div[data-testid="stTextInput"] label,
div[data-testid="stSelectbox"] label {
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
    font-weight: 500;
}
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button {
    border-radius: 999px;
    border: 0;
    background: linear-gradient(90deg, var(--accent) 0%, #0f8773 100%);
    color: #fff !important;
    -webkit-text-fill-color: #fff !important;
    font-weight: 700;
    padding-inline: 1rem;
}
hr {
    border-color: rgba(76, 55, 34, 0.12);
}
.hero-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.7rem;
    margin-top: 1rem;
}
.hero-pill {
    border: 1px solid rgba(18, 51, 36, 0.12);
    background: rgba(255, 255, 255, 0.72);
    border-radius: 999px;
    padding: 0.4rem 0.8rem;
    font-size: 0.82rem;
    color: var(--muted);
}
@media (max-width: 768px) {
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1.5rem;
    }
    .hero-card {
        padding: 1rem 1rem;
        border-radius: 18px;
    }
    .hero-title {
        font-size: 1.5rem;
    }
    .hero-subtitle {
        font-size: 0.85rem;
        max-width: 100%;
    }
    .section-card {
        border-radius: 16px;
        padding: 0.75rem 0.9rem;
    }
    .section-heading {
        font-size: 1rem;
    }
    .metric-card {
        padding: 0.75rem 0.9rem;
        border-radius: 16px;
    }
    .metric-value {
        font-size: 1.3rem;
    }
    .metric-label {
        font-size: 0.65rem;
    }
    .metric-detail {
        font-size: 0.75rem;
    }
    table.leaderboard td, table.leaderboard th {
        padding: 8px 8px;
        font-size: 0.7rem;
        white-space: nowrap;
    }
    table.leaderboard th {
        font-size: 0.65rem;
    }
    div[data-testid="stPlotlyChart"] {
        border-radius: 16px;
    }
    .hero-pill {
        font-size: 0.72rem;
        padding: 0.3rem 0.6rem;
    }
}
.throne-scroll {
    max-height: 320px;
    overflow-y: auto;
    padding-right: 0.25rem;
}
.throne-entry {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.45rem 0;
    border-bottom: 1px solid rgba(18, 51, 36, 0.08);
}
.throne-entry:last-child {
    border-bottom: none;
}
.throne-date {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.72rem;
    color: var(--muted);
    white-space: nowrap;
}
.throne-ticker {
    font-weight: 700;
    font-size: 0.85rem;
}
.throne-detail {
    font-size: 0.78rem;
    color: var(--muted);
}
@media (max-width: 768px) {
    .throne-entry {
        flex-wrap: wrap;
        gap: 0.3rem;
    }
    .throne-scroll {
        max-height: 240px;
    }
}
.etf-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0;
}
.etf-label {
    font-size: 0.82rem;
    font-weight: 700;
    min-width: 6.5rem;
    white-space: nowrap;
}
.etf-bar-bg {
    flex: 1;
    background: rgba(18, 51, 36, 0.06);
    border-radius: 6px;
    height: 1.5rem;
    overflow: hidden;
    position: relative;
    display: flex;
}
.etf-bar-bg::after {
    content: '';
    position: absolute;
    left: 50%;
    top: 2px;
    bottom: 2px;
    width: 1px;
    background: rgba(128, 128, 128, 0.35);
    z-index: 1;
}
.etf-bar-half {
    width: 50%;
    height: 100%;
    display: flex;
    overflow: hidden;
}
.etf-bar-half.left {
    justify-content: flex-end;
}
.etf-bar-half.right {
    justify-content: flex-start;
}
.etf-bar {
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    font-size: 0.72rem;
    font-weight: 700;
    color: #fff;
    min-width: 3rem;
    transition: width 0.4s ease;
}
.etf-bar.neg {
    justify-content: flex-start;
    padding-left: 0.4rem;
    border-radius: 6px 0 0 6px;
}
.etf-bar.pos {
    justify-content: flex-end;
    padding-right: 0.4rem;
    border-radius: 0 6px 6px 0;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Default: dark arrow for light background (collapsed sidebar) */
[data-testid="stIconMaterial"] {
    color: #102018 !important;
}
/* Light arrow when inside the dark sidebar */
section[data-testid="stSidebar"] [data-testid="stIconMaterial"] {
    color: #f8fbf6 !important;
}
.stTabs [data-baseweb="tab-list"] button,
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"],
.stTabs [data-baseweb="tab-list"] button p {
    color: #102018 !important;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

with open("players.json") as f:
    config = json.load(f)

INVESTMENT = config["investment_amount"]
PLAYERS = config["players"]
TICKERS = [p["ticker"] for p in PLAYERS]
NAME_MAP = {p["ticker"]: p["name"] for p in PLAYERS}
ETF_MAP = {p["ticker"]: p.get("etf", "") for p in PLAYERS}

# --- Sidebar ---
st.sidebar.title("Trading Windows")

default_start = datetime.date(2026, 3, 6)
default_end = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date()

start_date = st.sidebar.date_input("Start Date", value=default_start, format="MM/DD/YYYY")
end_date = st.sidebar.date_input("End Date", value=default_end, format="MM/DD/YYYY")

st.sidebar.title("Search Stocks")
search_options = [""] + [f"{p['ticker']} — {p['name']}" for p in sorted(PLAYERS, key=lambda x: x['ticker'].upper())]
roster_selection = st.sidebar.selectbox("Search stocks", search_options, format_func=lambda x: "Select a stock" if x == "" else x, label_visibility="collapsed", key="stock_search")
roster_search = roster_selection.split(" — ")[0] if roster_selection else ""
if roster_search:
    st.sidebar.button("Reset Search", on_click=lambda: st.session_state.update({"stock_search": ""}))

# --- Main ---

@st.cache_data(ttl=3600)
def fetch_returns(tickers, start, end):
    """Download adjusted prices and compute daily cumulative % return."""
    data = yf.download(
        tickers,
        start=start,
        end=end + datetime.timedelta(days=1),
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if data.empty:
        return None, None, None

    close = data["Close"]

    # If single ticker, yf.download returns a Series — wrap it
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])

    # Forward-fill then back-fill gaps (holidays / missing data)
    close = close.ffill().bfill()

    # Compute cumulative % return from the first available price
    start_prices = close.iloc[0]
    end_prices = close.iloc[-1]
    pct_return = (close / start_prices - 1) * 100

    return pct_return, start_prices, end_prices


@st.cache_data(ttl=3600)
def fetch_dividends(tickers, start, end):
    """Fetch total dividends per share for each ticker in the date range."""
    divs = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            d = t.dividends
            if d is not None and not d.empty:
                # Filter to date range
                d.index = d.index.tz_localize(None)
                mask = (d.index >= pd.Timestamp(start)) & (d.index <= pd.Timestamp(end))
                divs[ticker] = d[mask].sum()
            else:
                divs[ticker] = 0.0
        except Exception:
            divs[ticker] = 0.0
    return divs


def compute_throne_history(returns, valid_tickers, name_map):
    """Compute MVP/Benchwarmer streak counts and transition history."""
    daily_returns = returns[valid_tickers]
    if len(daily_returns) > 1:
        daily_returns = daily_returns.iloc[1:]
    mvp_series = daily_returns.idxmax(axis=1)
    bench_series = daily_returns.idxmin(axis=1)

    def _streak_and_history(series):
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
                ret = daily_returns.loc[date, holder]
                history.append({
                    "date": date,
                    "ticker": holder,
                    "name": name_map.get(holder, holder),
                    "prev_ticker": prev_holder,
                    "return_pct": ret,
                })
                prev_holder = holder
        history.reverse()
        return streak, history

    def _longest_streak(series):
        """Find the longest consecutive streak ever for any holder."""
        holders = series.tolist()
        dates = series.index.tolist()
        if not holders:
            return {"ticker": "", "streak": 0, "start": None, "end": None}
        best_ticker = holders[0]
        best_streak = 1
        best_start = 0
        best_end = 0
        cur_streak = 1
        cur_start = 0
        for i in range(1, len(holders)):
            if holders[i] == holders[i - 1]:
                cur_streak += 1
            else:
                if cur_streak > best_streak:
                    best_streak = cur_streak
                    best_ticker = holders[i - 1]
                    best_start = cur_start
                    best_end = i - 1
                cur_streak = 1
                cur_start = i
        if cur_streak > best_streak:
            best_streak = cur_streak
            best_ticker = holders[-1]
            best_start = cur_start
            best_end = len(holders) - 1
        return {"ticker": best_ticker, "streak": best_streak, "start": dates[best_start], "end": dates[best_end]}

    mvp_streak, mvp_history = _streak_and_history(mvp_series)
    bench_streak, bench_history = _streak_and_history(bench_series)
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
    }



def compute_superlatives(returns, valid_tickers, name_map, etf_map, throne):
    """Compute fun superlative stats."""
    results = {}
    daily = returns[valid_tickers]
    daily_changes = daily.diff()

    # --- Best Single Day / Worst Single Day ---
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        best_day_idx = changes.stack().idxmax()
        worst_day_idx = changes.stack().idxmin()
        results["best_day"] = {
            "ticker": best_day_idx[1],
            "name": name_map.get(best_day_idx[1], best_day_idx[1]),
            "date": best_day_idx[0],
            "change": changes.loc[best_day_idx[0], best_day_idx[1]],
        }
        results["worst_day"] = {
            "ticker": worst_day_idx[1],
            "name": name_map.get(worst_day_idx[1], worst_day_idx[1]),
            "date": worst_day_idx[0],
            "change": changes.loc[worst_day_idx[0], worst_day_idx[1]],
        }

    # --- Comeback Kid: went negative the most, then recovered the most ---
    best_comeback_ticker = ""
    best_comeback_val = 0
    for ticker in valid_tickers:
        series = daily[ticker]
        min_val = series.min()
        if min_val >= 0:
            continue  # never went negative, not a comeback
        final_val = series.iloc[-1]
        recovery = final_val - min_val
        if recovery > best_comeback_val:
            best_comeback_val = recovery
            best_comeback_ticker = ticker
    if best_comeback_ticker:
        results["comeback"] = {
            "ticker": best_comeback_ticker,
            "name": name_map.get(best_comeback_ticker, best_comeback_ticker),
            "recovery": best_comeback_val,
            "low": daily[best_comeback_ticker].min(),
            "final": daily[best_comeback_ticker].iloc[-1],
        }
    else:
        # fallback: no stock went negative, pick biggest recovery from lowest point
        best_comeback_ticker = min(valid_tickers, key=lambda t: daily[t].min())
        results["comeback"] = {
            "ticker": best_comeback_ticker,
            "name": name_map.get(best_comeback_ticker, best_comeback_ticker),
            "recovery": daily[best_comeback_ticker].iloc[-1] - daily[best_comeback_ticker].min(),
            "low": daily[best_comeback_ticker].min(),
            "final": daily[best_comeback_ticker].iloc[-1],
        }

    # --- Throne Stats ---
    from collections import Counter


    # Longest Reign: stock with the most total days on any throne
    reign_counts = Counter()
    for series_name in ["mvp_history", "bench_history"]:
        history = throne[series_name]
        for i, entry in enumerate(history):
            if i > 0:
                # history is reversed (newest first), so previous entry's date is the end
                days = abs((history[i-1]["date"] - entry["date"]).days)
                reign_counts[entry["ticker"]] += days
            elif i == 0 and len(history) == 1:
                reign_counts[entry["ticker"]] += 1
    if reign_counts:
        reign_ticker, reign_days = reign_counts.most_common(1)[0]
        results["longest_reign"] = {
            "ticker": reign_ticker,
            "name": name_map.get(reign_ticker, reign_ticker),
            "days": reign_days,
        }
    else:
        results["longest_reign"] = {"ticker": "", "name": "", "days": 0}


    # --- Rivalry: pair that swapped MVP/Benchwarmer most ---
    swap_pairs = Counter()
    for history in [throne["mvp_history"], throne["bench_history"]]:
        for entry in history:
            if entry.get("prev_ticker"):
                pair = tuple(sorted([entry["ticker"], entry["prev_ticker"]]))
                swap_pairs[pair] += 1
    if swap_pairs:
        rival_pair, rival_count = swap_pairs.most_common(1)[0]
        results["rivalry"] = {
            "ticker1": rival_pair[0], "name1": name_map.get(rival_pair[0], rival_pair[0]),
            "ticker2": rival_pair[1], "name2": name_map.get(rival_pair[1], rival_pair[1]),
            "swaps": rival_count,
        }
    else:
        results["rivalry"] = {"ticker1": "", "ticker2": "", "name1": "", "name2": "", "swaps": 0}

    # --- ETF War: ETF with longest streak of having the daily best average ---
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        etf_daily_winner = []
        for date in changes.index:
            etf_day_avg = {}
            etf_day_count = {}
            for ticker in valid_tickers:
                etf = etf_map.get(ticker, "")
                if etf:
                    etf_day_avg[etf] = etf_day_avg.get(etf, 0) + changes.loc[date, ticker]
                    etf_day_count[etf] = etf_day_count.get(etf, 0) + 1
            if etf_day_avg:
                for e in etf_day_avg:
                    etf_day_avg[e] /= etf_day_count[e]
                winner = max(etf_day_avg, key=etf_day_avg.get)
                etf_daily_winner.append(winner)
        # Find longest streak
        best_etf = ""
        best_etf_streak = 0
        cur_streak = 1
        for i in range(1, len(etf_daily_winner)):
            if etf_daily_winner[i] == etf_daily_winner[i - 1]:
                cur_streak += 1
            else:
                if cur_streak > best_etf_streak:
                    best_etf_streak = cur_streak
                    best_etf = etf_daily_winner[i - 1]
                cur_streak = 1
        if cur_streak > best_etf_streak:
            best_etf_streak = cur_streak
            best_etf = etf_daily_winner[-1] if etf_daily_winner else ""
        results["etf_war"] = {"etf": best_etf, "streak": best_etf_streak}
    else:
        results["etf_war"] = {"etf": "", "streak": 0}

    # --- Sleeper Pick: started bottom half, climbed highest ---
    if len(daily) > 1:
        first_day_ranks = daily.iloc[1].rank(ascending=False)
        total = len(valid_tickers)
        bottom_half = [t for t in valid_tickers if first_day_ranks[t] > total / 2]
        final = daily.iloc[-1]
        final_ranks = daily.iloc[-1].rank(ascending=False)
        if bottom_half:
            sleeper = max(bottom_half, key=lambda t: final[t])
            results["sleeper"] = {
                "ticker": sleeper,
                "name": name_map.get(sleeper, sleeper),
                "start_rank": int(first_day_ranks[sleeper]),
                "end_rank": int(final_ranks[sleeper]),
            }
        else:
            results["sleeper"] = {"ticker": "", "name": "", "start_rank": 0, "final_return": 0}
    else:
        results["sleeper"] = {"ticker": "", "name": "", "start_rank": 0, "final_return": 0}

    # --- Fallen Angel: started top half, dropped the most ranks ---
    if len(daily) > 1:
        first_day_ranks = daily.iloc[1].rank(ascending=False)
        final_ranks = daily.iloc[-1].rank(ascending=False)
        top_half = [t for t in valid_tickers if first_day_ranks[t] <= total / 2]
        if top_half:
            fallen = max(top_half, key=lambda t: final_ranks[t] - first_day_ranks[t])
            results["fallen"] = {
                "ticker": fallen,
                "name": name_map.get(fallen, fallen),
                "start_rank": int(first_day_ranks[fallen]),
                "end_rank": int(final_ranks[fallen]),
            }
        else:
            results["fallen"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}
    else:
        results["fallen"] = {"ticker": "", "name": "", "start_rank": 0, "end_rank": 0}

    # --- Middle Child: closest to 0% return ---
    final = daily.iloc[-1]
    middle = min(valid_tickers, key=lambda t: abs(final[t]))
    middle_rank = int(final.rank(ascending=False)[middle])
    results["middle"] = {
        "ticker": middle,
        "name": name_map.get(middle, middle),
        "return": final[middle],
        "rank": middle_rank,
        "total": len(valid_tickers),
    }

    # --- Power Rankings: biggest climbers/fallers in last 5 trading days ---
    if len(daily) >= 6:
        recent_start = daily.iloc[-6]
        recent_end = daily.iloc[-1]
        weekly_change = recent_end - recent_start
        top_climber = weekly_change[valid_tickers].idxmax()
        top_faller = weekly_change[valid_tickers].idxmin()
        results["power"] = {
            "climber": top_climber,
            "climber_name": name_map.get(top_climber, top_climber),
            "climber_change": weekly_change[top_climber],
            "faller": top_faller,
            "faller_name": name_map.get(top_faller, top_faller),
            "faller_change": weekly_change[top_faller],
        }
    else:
        results["power"] = {
            "climber": "", "climber_name": "", "climber_change": 0,
            "faller": "", "faller_name": "", "faller_change": 0,
        }

    return results


tab_dashboard, tab_admin = st.tabs(["Dashboard", "Admin"])

with tab_dashboard:
    st.markdown("""
    <section class="hero-card">
      <div class="hero-top-row">
        <h1 class="hero-title">Stock Market Draft Standings</h1>
      </div>
      <div class="hero-meta">
        <span class="hero-pill">Window: """ + start_date.strftime("%b %d, %Y") + """ to """ + end_date.strftime("%b %d, %Y") + """</span>
        <span class="hero-pill">Entry stake: $""" + f"{INVESTMENT:.0f}" + """ per stock</span>
        <span class="hero-pill">Stocks tracked: """ + str(len(TICKERS)) + """</span>
      </div>
    </section>
    """, unsafe_allow_html=True)

    @st.fragment(run_every=REFRESH_INTERVAL)
    def live_dashboard():
        if start_date >= end_date:
            st.error("Start date must be before end date.")
            st.stop()

        try:
            returns, start_prices, end_prices = fetch_returns(TICKERS, start_date, end_date)
        except Exception as e:
            st.error(f"Failed to fetch stock data: {e}")
            st.stop()

        if returns is None or returns.empty:
            st.warning("No data returned for the selected date range.")
            st.stop()

        # Identify valid vs invalid tickers
        valid_tickers = [t for t in TICKERS if t in returns.columns and returns[t].notna().any()]

        # Fetch dividends for valid tickers
        try:
            dividends = fetch_dividends(valid_tickers, start_date, end_date)
        except Exception:
            dividends = {t: 0.0 for t in valid_tickers}
        invalid_tickers = [t for t in TICKERS if t not in valid_tickers]

        for t in invalid_tickers:
            st.warning(f"No data for ticker **{t}** ({NAME_MAP[t]}) — excluded from results.")

        if not valid_tickers:
            st.error("No valid ticker data to display.")
            st.stop()

        # --- Rank tickers by final return ---
        final_returns = returns[valid_tickers].iloc[-1].sort_values(ascending=False)
        top10_tickers = final_returns.head(10).index.tolist()
        bottom10_tickers = final_returns.tail(10).index.tolist()

        # --- ETF Winner ---
        ETF_EMOJI = {"UNCL": "👨‍🦳", "ANTY": "👩🏻", "KIDZ": "👶🏻"}
        etf_sums = {}
        etf_counts = {}
        for ticker in valid_tickers:
            etf = ETF_MAP.get(ticker, "")
            if etf:
                etf_sums[etf] = etf_sums.get(etf, 0) + final_returns[ticker]
                etf_counts[etf] = etf_counts.get(etf, 0) + 1
        etf_avgs = {etf: etf_sums[etf] / etf_counts[etf] for etf in etf_sums}
        etf_ranked = sorted(etf_avgs.items(), key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        best_ticker = final_returns.index[0]
        worst_ticker = final_returns.index[-1]
        throne = compute_throne_history(returns, valid_tickers, NAME_MAP)
        superlatives = compute_superlatives(returns, valid_tickers, NAME_MAP, ETF_MAP, throne)

        # --- Live status indicator ---
        now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
        live_timestamp = now_et.strftime("%I:%M:%S %p ET")
        if is_market_open():
            countdown_iframe = (
                '<iframe srcdoc="'
                '<body style=&quot;margin:0;padding:0;overflow:hidden;background:transparent;&quot;>'
                '<span id=&quot;c&quot; style=&quot;font-family:Space Grotesk,-apple-system,BlinkMacSystemFont,sans-serif;'
                'font-size:14px;color:#aaa;&quot;>(refreshes in 60m 00s)</span>'
                '<script>var e=document.getElementById(&quot;c&quot;),s=3600;'
                'setInterval(function(){s--;if(s&lt;=0){e.textContent=&quot;(refreshing…)&quot;;}else{'
                'var m=Math.floor(s/60),sec=s%60;e.textContent=&quot;(refreshes in &quot;+m+&quot;m &quot;+(sec&lt;10?&quot;0&quot;:&quot;&quot;)+sec+&quot;s)&quot;;}},1000);'
                '</script></body>'
                '" style="border:none;width:175px;height:18px;vertical-align:text-bottom;display:inline-block;'
                'overflow:hidden;background:transparent;" scrolling="no"></iframe>'
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.3rem;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#19a05f;'
                f'box-shadow:0 0 6px #19a05f;"></span>'
                f'<span style="font-size:14px;color:#888;line-height:18px;">'
                f'<strong style="color:#19a05f;">LIVE</strong> &middot; {live_timestamp}'
                f' {countdown_iframe}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.3rem;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--muted);"></span>'
                f'<span style="font-size:0.78rem;color:var(--muted);">'
                f'Closed &middot; {live_timestamp}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        metric_cols = st.columns(4)
        metric_cols[0].markdown(
            f"""
            <div class="metric-card mvp">
              <div class="metric-label">👑 MVP</div>
              <div class="metric-value positive">{ETF_EMOJI.get(ETF_MAP.get(best_ticker, ''), '')} {html_mod.escape(best_ticker)}</div>
              <div class="metric-detail">{html_mod.escape(NAME_MAP[best_ticker])} <span class="positive">{final_returns[best_ticker]:+.2f}%</span></div>
              <div class="metric-detail">🔥 {throne['mvp_streak']} day streak</div>
              <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Highest total return</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        metric_cols[1].markdown(
            f"""
            <div class="metric-card bench">
              <div class="metric-label">💩 Benchwarmer</div>
              <div class="metric-value negative">{ETF_EMOJI.get(ETF_MAP.get(worst_ticker, ''), '')} {html_mod.escape(worst_ticker)}</div>
              <div class="metric-detail">{html_mod.escape(NAME_MAP[worst_ticker])} <span class="negative">({abs(final_returns[worst_ticker]):.2f}%)</span></div>
              <div class="metric-detail">📉 {throne['bench_streak']} day streak</div>
              <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Lowest total return</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- ETF Standing with progress bars ---
        max_etf_val = max(abs(v) for v in etf_avgs.values()) if etf_avgs else 1
        etf_bar_html = ""
        for i, (etf, avg_ret) in enumerate(etf_ranked):
            medal = medals[i] if i < len(medals) else ""
            emoji = ETF_EMOJI.get(etf, "")
            bar_pct = max(int(abs(avg_ret) / max_etf_val * 100), 12)
            bar_color = "var(--accent)" if avg_ret >= 0 else "var(--negative)"
            if avg_ret >= 0:
                left_half = '<div class="etf-bar-half left"></div>'
                right_half = (
                    f'<div class="etf-bar-half right">'
                    f'<div class="etf-bar pos" style="width:{bar_pct}%;background:{bar_color};">{avg_ret:+.2f}%</div>'
                    f'</div>'
                )
            else:
                left_half = (
                    f'<div class="etf-bar-half left">'
                    f'<div class="etf-bar neg" style="width:{bar_pct}%;background:{bar_color};">{avg_ret:+.2f}%</div>'
                    f'</div>'
                )
                right_half = '<div class="etf-bar-half right"></div>'
            etf_bar_html += (
                f'<div class="etf-row">'
                f'<span class="etf-label">{medal} {emoji} {html_mod.escape(etf)}</span>'
                f'<div class="etf-bar-bg">{left_half}{right_half}</div>'
                f'</div>'
            )
        metric_cols[2].markdown(
            f"""
            <div class="metric-card" style="height:100%;">
              <div class="metric-label">ETF Standing</div>
              <div style="margin-top:0.4rem;">{etf_bar_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sw = throne["streak_winner"]
        if sw["ticker"]:
            sw_ticker = sw["ticker"]
            is_mvp = sw["type"] == "mvp"
            sw_emoji = "🔥" if is_mvp else "📉"
            sw_class = "positive" if is_mvp else "negative"
            sw_label = "MVP" if is_mvp else "Benchwarmer"
            sw_start = sw["start"].strftime("%b %d") if hasattr(sw["start"], "strftime") else str(sw["start"])
            sw_end = sw["end"].strftime("%b %d") if hasattr(sw["end"], "strftime") else str(sw["end"])
            metric_cols[3].markdown(
                f"""
                <div class="metric-card" style="height:100%;">
                  <div class="metric-label">Streak Winner</div>
                  <div class="metric-value {sw_class}">{ETF_EMOJI.get(ETF_MAP.get(sw_ticker, ''), '')} {html_mod.escape(sw_ticker)}</div>
                  <div class="metric-detail">{html_mod.escape(NAME_MAP.get(sw_ticker, sw_ticker))}</div>
                  <div class="metric-detail">{sw_emoji} {sw['streak']} day {sw_label} streak</div>
                  <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">{sw_start} – {sw_end}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # --- Superlatives Section ---
        st.markdown("#### 🏆 Bragging Rights")
        sup = superlatives

        sup_row1 = st.columns(3)

        # Comeback Kid
        cb = sup["comeback"]
        if cb["ticker"]:
            sup_row1[0].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">🔄 Comeback Kid</div>
                  <div class="metric-value positive">{html_mod.escape(cb['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(cb['name'])}</div>
                  <div class="metric-detail">Low: <span class="negative">{cb['low']:+.2f}%</span> → Now: <span class="positive">{cb['final']:+.2f}%</span></div>
                  <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Recovery: +{cb['recovery']:.2f}pp</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Best Single Day
        bd = sup.get("best_day")
        if bd:
            bd_date = bd["date"].strftime("%b %d") if hasattr(bd["date"], "strftime") else str(bd["date"])
            sup_row1[1].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">🚀 Best Single Day</div>
                  <div class="metric-value positive">{html_mod.escape(bd['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(bd['name'])}</div>
                  <div class="metric-detail"><span class="positive">{bd['change']:+.2f}%</span> on {bd_date}</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Worst Single Day
        wd = sup.get("worst_day")
        if wd:
            wd_date = wd["date"].strftime("%b %d") if hasattr(wd["date"], "strftime") else str(wd["date"])
            sup_row1[2].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">💥 Worst Single Day</div>
                  <div class="metric-value negative">{html_mod.escape(wd['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(wd['name'])}</div>
                  <div class="metric-detail"><span class="negative">{wd['change']:+.2f}%</span> on {wd_date}</div>
                </div>""",
                unsafe_allow_html=True,
            )

        sup_row2 = st.columns(3)

        # Longest Reign
        lr = sup["longest_reign"]
        if lr["ticker"]:
            sup_row2[0].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">👑 Longest Reign</div>
                  <div class="metric-value">{html_mod.escape(lr['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(lr['name'])}</div>
                  <div class="metric-detail">{lr['days']} total days on the throne</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Rivalry
        rv = sup["rivalry"]
        if rv["ticker1"]:
            sup_row2[1].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">⚔️ Rivalry</div>
                  <div class="metric-value">{html_mod.escape(rv['ticker1'])} vs {html_mod.escape(rv['ticker2'])}</div>
                  <div class="metric-detail">{html_mod.escape(rv['name1'])} vs {html_mod.escape(rv['name2'])}</div>
                  <div class="metric-detail">Swapped {rv['swaps']}x on the throne</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # ETF War
        ew = sup["etf_war"]
        if ew["etf"]:
            etf_emoji = ETF_EMOJI.get(ew["etf"], "")
            sup_row2[2].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">⚡ ETF War</div>
                  <div class="metric-value">{etf_emoji} {html_mod.escape(ew['etf'])}</div>
                  <div class="metric-detail">Longest daily win streak</div>
                  <div class="metric-detail">🔥 {ew['streak']} consecutive days</div>
                </div>""",
                unsafe_allow_html=True,
            )

        sup_row3 = st.columns(3)

        # Sleeper Pick
        sp = sup["sleeper"]
        if sp["ticker"]:
            sup_row3[0].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">😴 Sleeper Pick</div>
                  <div class="metric-value positive">{html_mod.escape(sp['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(sp['name'])}</div>
                  <div class="metric-detail">Rank #{sp['start_rank']} → #{sp['end_rank']}</div>
                  <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Started bottom half, climbed highest</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Fallen Angel
        fa = sup["fallen"]
        if fa["ticker"]:
            sup_row3[1].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">😇 Fallen Angel</div>
                  <div class="metric-value negative">{html_mod.escape(fa['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(fa['name'])}</div>
                  <div class="metric-detail">Rank #{fa['start_rank']} → #{fa['end_rank']}</div>
                  <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Started top half, dropped the most</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Middle Child
        mc = sup["middle"]
        if mc["ticker"]:
            ret_class = "positive" if mc["return"] >= 0 else "negative"
            sup_row3[2].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">🫥 Middle Child</div>
                  <div class="metric-value">{html_mod.escape(mc['ticker'])}</div>
                  <div class="metric-detail">{html_mod.escape(mc['name'])}</div>
                  <div class="metric-detail">Return: <span class="{ret_class}">{mc['return']:+.2f}%</span></div>
                  <div class="metric-detail" style="font-size:0.75rem;opacity:0.7;">Closest to 0%</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Power Rankings
        pw = sup["power"]
        if pw["climber"]:
            st.markdown("#### 🔥 Hot or Not (Last 5 Trading Days)")
            pw_cols = st.columns(2)
            pw_cols[0].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">📈 Biggest Climber</div>
                  <div class="metric-value positive">{html_mod.escape(pw['climber'])}</div>
                  <div class="metric-detail">{html_mod.escape(pw['climber_name'])}</div>
                  <div class="metric-detail"><span class="positive">{pw['climber_change']:+.2f}%</span> in 5 days</div>
                </div>""",
                unsafe_allow_html=True,
            )
            pw_cols[1].markdown(
                f"""<div class="metric-card" style="height:100%;">
                  <div class="metric-label">📉 Biggest Faller</div>
                  <div class="metric-value negative">{html_mod.escape(pw['faller'])}</div>
                  <div class="metric-detail">{html_mod.escape(pw['faller_name'])}</div>
                  <div class="metric-detail"><span class="negative">{pw['faller_change']:+.2f}%</span> in 5 days</div>
                </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # --- ggbump-style sigmoid helper ---
        def sigmoid_between(x_from, x_to, y_from, y_to, n=100, smooth=8):
            t = np.linspace(-smooth, smooth, n)
            s = np.exp(t) / (np.exp(t) + 1)
            x_out = x_from + (x_to - x_from) * ((t + smooth) / (2 * smooth))
            y_out = y_from + (y_to - y_from) * s
            return x_out, y_out

        def build_bump_traces(ranks_df, returns_df, tickers, colors, label_rank_fn=None):
            traces = []
            dates_num = np.arange(len(ranks_df))
            dates = ranks_df.index

            # Build y-axis tick labels using ticker symbols (compact for mobile)
            tick_labels = {}
            for i, ticker in enumerate(tickers):
                rank_vals = ranks_df[ticker].values
                final_bump_rank = int(rank_vals[-1])
                final_rank = label_rank_fn(final_bump_rank) if label_rank_fn else final_bump_rank
                final_ret = float(final_returns[ticker])
                color = colors[i % len(colors)]
                tick_labels[final_bump_rank] = f"<span style='color:{color}'><b>#{final_rank}</b> {ticker} {final_ret:+.2f}%</span>"

            for i, ticker in enumerate(tickers):
                rank_vals = ranks_df[ticker].values
                ret_vals = returns_df[ticker].values
                color = colors[i % len(colors)]

                # Sigmoid curve segments
                all_x, all_y = [], []
                for j in range(len(rank_vals) - 1):
                    sx, sy = sigmoid_between(dates_num[j], dates_num[j + 1],
                                             rank_vals[j], rank_vals[j + 1])
                    all_x.extend(sx)
                    all_y.extend(sy)

                # Map numeric x back to dates
                date_x = []
                d0, d1 = dates[0], dates[-1]
                total_secs = (d1 - d0).total_seconds() if hasattr(d1 - d0, 'total_seconds') else float(dates_num[-1])
                for xv in all_x:
                    frac = xv / dates_num[-1] if dates_num[-1] != 0 else 0
                    date_x.append(d0 + pd.Timedelta(seconds=frac * total_secs))

                traces.append(go.Scatter(
                    x=date_x, y=all_y, mode="lines",
                    line=dict(width=3, color=color),
                    hoverinfo="skip", showlegend=False,
                ))
                traces.append(go.Scatter(
                    x=list(dates), y=list(rank_vals), mode="markers",
                    name=NAME_MAP[ticker],
                    marker=dict(size=8, color=color, line=dict(width=1.5, color="white")),
                    customdata=[round(float(v), 2) for v in ret_vals],
                    hovertemplate="#%{y:.0f} %{fullData.name} %{customdata:.2f}%<extra></extra>",
                    showlegend=False,
                ))

            tick_vals = sorted(tick_labels.keys())
            tick_texts = [tick_labels[v] for v in tick_vals]
            return traces, tick_vals, tick_texts

        CHART_COLORS = [
            "#1f77b4", "#e45756", "#2ca02c", "#ff7f0e", "#9467bd",
            "#17becf", "#d62728", "#8c564b", "#e377c2", "#7f7f7f",
        ]

        bump_layout = dict(
            xaxis_title="", yaxis_title="",
            yaxis=dict(autorange="reversed", range=[0.5, 10.5],
                       gridcolor="rgba(31, 26, 23, 0.06)", side="right",
                       tickfont=dict(size=11)),
            hovermode="x",
            hoverlabel=dict(bgcolor="white", font_color="#102018", font_size=13, bordercolor="#ccc"),
            height=420, showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fbfdf9",
            font=dict(family="Space Grotesk, sans-serif", color="#102018"),
            title_font=dict(size=18, color="#102018"),
            margin=dict(t=50, r=10, b=40, l=10),
        )

        # --- Bump Chart: Top 10 In the Money ---
        top10_returns = returns[top10_tickers]
        top10_ranks = top10_returns.rank(axis=1, ascending=False)
        # Assign initial ranks (day 1 = all 0%) based on final ordering to avoid random ties
        top10_ranks.iloc[0] = range(1, len(top10_tickers) + 1)
        top10_returns_trimmed = top10_returns

        top_traces, top_tv, top_tt = build_bump_traces(
            top10_ranks, top10_returns_trimmed, top10_tickers, CHART_COLORS,
        )
        fig_top = go.Figure(data=top_traces)
        fig_top.update_layout(title="Top 10 Stocks In the Money", **bump_layout)
        fig_top.update_xaxes(showgrid=False, fixedrange=True, tickfont=dict(color="#102018"))
        fig_top.update_yaxes(zeroline=False, fixedrange=True, automargin=True,
                             tickmode="array", tickvals=top_tv, ticktext=top_tt)

        chart_config = {"displayModeBar": False, "scrollZoom": False}
        st.plotly_chart(fig_top, use_container_width=True, config=chart_config)

        # --- Bump Chart: Bottom 10 Out of the Money ---
        bottom10_returns = returns[bottom10_tickers]
        bottom10_ranks = bottom10_returns.rank(axis=1, ascending=False)
        bottom10_ranks.iloc[0] = range(1, len(bottom10_tickers) + 1)
        bottom10_returns_trimmed = bottom10_returns

        total = len(final_returns)
        bottom_traces, bot_tv, bot_tt = build_bump_traces(
            bottom10_ranks, bottom10_returns_trimmed, bottom10_tickers,
            CHART_COLORS, label_rank_fn=lambda r: total - 10 + r,
        )
        fig_bottom = go.Figure(data=bottom_traces)
        fig_bottom.update_layout(title="Bottom 10 Stocks Out of the Money", **bump_layout)
        fig_bottom.update_xaxes(showgrid=False, fixedrange=True, tickfont=dict(color="#102018"))
        fig_bottom.update_yaxes(zeroline=False, fixedrange=True, automargin=True,
                                tickmode="array", tickvals=bot_tv, ticktext=bot_tt)

        st.plotly_chart(fig_bottom, use_container_width=True, config=chart_config)

        # --- Throne History (below charts) ---
        def _render_throne_entries(history):
            entries = []
            for entry in history:
                date_str = entry["date"].strftime("%b %d")
                ticker_esc = html_mod.escape(entry["ticker"])
                name_esc = html_mod.escape(entry["name"])
                ret = entry["return_pct"]
                ret_str = f"{ret:+.2f}%"
                ret_cls = "positive" if ret >= 0 else "negative"
                displaced = ""
                if entry["prev_ticker"]:
                    displaced = f' · displaced {html_mod.escape(entry["prev_ticker"])}'
                entries.append(
                    f'<div class="throne-entry">'
                    f'<span class="throne-date">{date_str}</span>'
                    f'<span class="throne-ticker">{ticker_esc}</span>'
                    f'<span class="throne-detail">{name_esc} · <span class="{ret_cls}">{ret_str}</span>{displaced}</span>'
                    f'</div>'
                )
            return "".join(entries)

        throne_cols = st.columns(2)
        throne_cols[0].markdown(
            f"""
            <div class="metric-card mvp">
              <div class="section-heading">👑 MVP Throne</div>
              <div class="throne-scroll">{_render_throne_entries(throne['mvp_history'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        throne_cols[1].markdown(
            f"""
            <div class="metric-card bench">
              <div class="section-heading">🪑 Benchwarmer Throne</div>
              <div class="throne-scroll">{_render_throne_entries(throne['bench_history'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- Leaderboard ---
        st.markdown("""
        <section class="section-card">
          <div class="section-heading">Leaderboard</div>
          <p class="section-copy"><strong>Price Return (%)</strong> is the percentage change in share price over the period, excluding dividends.</p>
          <p class="section-copy"><strong>Total Return (%)</strong> is the percentage return including both share price change and dividend payouts.</p>
        </section>
        """, unsafe_allow_html=True)

        start_date_label = returns.index[0].strftime("%m/%d/%Y")
        end_date_label = returns.index[-1].strftime("%m/%d/%Y")

        # Compute rank changes vs yesterday's standing
        if len(returns) >= 2:
            prev_returns = returns[valid_tickers].iloc[-2].sort_values(ascending=False)
            prev_ranks = {ticker: rank for rank, ticker in enumerate(prev_returns.index, start=1)}
        else:
            prev_ranks = {}

        rows = []
        for rank, (ticker, ret) in enumerate(final_returns.items(), start=1):
            # Shares bought with investment
            share_price = start_prices[ticker]
            shares = INVESTMENT / share_price
            # Dividend income for those shares
            div_per_share = dividends.get(ticker, 0.0)
            div_income = shares * div_per_share
            # Market value = shares × current price
            market_value = shares * end_prices[ticker]
            # Final value = market value + dividends
            final_value = market_value + div_income
            total_return = (final_value / INVESTMENT - 1) * 100
            profit = final_value - INVESTMENT
            total_players = len(final_returns)
            if rank == 1:
                display_ticker = f"👑 {ticker}"
            elif rank == total_players:
                display_ticker = f"💩 {ticker}"
            else:
                display_ticker = ticker
            prev_rank = prev_ranks.get(ticker, rank)
            rank_diff = prev_rank - rank  # positive = moved up, negative = moved down
            if rank_diff > 0:
                arrow = '<span style="color:#19a05f;font-size:12px;">▲</span>'
            elif rank_diff < 0:
                arrow = '<span style="color:#d14a34;font-size:12px;">▼</span>'
            else:
                arrow = '<span style="color:#102018;font-size:12px;display:inline-block;transform:rotate(90deg);">▲</span>'
            rows.append({
                "Rank": f'<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap;">{arrow} {rank}</span>',
                "ETF": ETF_MAP.get(ticker, ""),
                "Stock": NAME_MAP[ticker],
                "Ticker": display_ticker,
                f"Start Price ({start_date_label})": f"${share_price:.2f}",
                f"End Price ({end_date_label})": f"${end_prices[ticker]:.2f}",
                "Stake": f"${INVESTMENT:.2f}",
                f"Units ({start_date_label})": f"{shares:.4f}",
                "Profit/(Loss)": format_signed_currency(profit),
                "Market Value": format_signed_currency(market_value),
                "Dividends": format_signed_currency(div_income),
                "Price Return (%)": format_signed_percent(ret),
                "Total Return (%)": format_signed_percent(total_return),
            })

        df = pd.DataFrame(rows)
        total_rows = max(len(df) - 1, 1)

        # Find the first row with negative total return
        first_negative_idx = next((i for i, r in enumerate(rows) if r["Total Return (%)"].startswith("(")), None)

        # Build set of matching row indices for search highlight
        search_matches = set()
        if roster_search:
            for i, r in enumerate(rows):
                ticker_raw = r["Ticker"].replace("👑 ", "").replace("💩 ", "")
                if roster_search.upper() in ticker_raw.upper() or roster_search.upper() in r["Stock"].upper():
                    search_matches.add(i)


        def leaderboard_row_style(row):
            fraction = row.name / total_rows
            color = interpolate_hex_color("#19a05f", "#d14a34", fraction)
            styles = [f"color: {color};"] * len(row)
            if row.name == first_negative_idx:
                styles = [s + " border-top: 3px solid #102018;" for s in styles]
            if row.name in search_matches:
                styles = [s + " background-color: rgba(215, 168, 58, 0.3);" for s in styles]
            return styles


        styled_df = (
            df.style
            .hide(axis="index")
            .set_table_attributes('class="leaderboard"')
            .apply(leaderboard_row_style, axis=1)
        )
        st.markdown(f'<div style="overflow-x: auto;">{styled_df.to_html(escape=False)}</div>', unsafe_allow_html=True)

        # --- Subscribe ---
        st.markdown("---")

    live_dashboard()

with tab_admin:
    if not st.session_state.admin_authenticated:
        st.markdown("")
        col_login = st.columns([1, 2, 1])[1]
        with col_login:
            st.markdown("#### Admin Login")
            with st.form("login_form"):
                userid_input = st.text_input("User ID", label_visibility="collapsed", placeholder="Enter user ID")
                password_input = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter admin password")
                submitted = st.form_submit_button("Login", use_container_width=True)
                if submitted:
                    if userid_input == st.secrets.get("ADMIN_USERNAME", "") and password_input == st.secrets.get("ADMIN_PASSWORD", ""):
                        st.session_state.admin_authenticated = True
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
    else:
        st.markdown("")
        col_mgmt = st.columns([1, 2, 1])[1]
        with col_mgmt:
            st.markdown("#### Select an ETF")
            new_etf = st.selectbox("ETF", ["", "ANTY", "UNCL", "KIDZ"], format_func=lambda x: "Select an ETF" if x == "" else x, label_visibility="collapsed", key="new_etf")
            st.markdown("#### Add Ticker")
            all_stocks = fetch_all_us_stocks()
            claimed_tickers = {p["ticker"]: p.get("etf", "") for p in config["players"]}

            search_query = st.text_input("Search for a stock", placeholder="Type a ticker or company name...", label_visibility="collapsed", key="admin_stock_search")
            components.html("""
            <script>
            const doc = window.parent.document;
            const input = doc.querySelector('input[aria-label="Search for a stock"]');
            if (input && !input.dataset.keyupBound) {
                input.dataset.keyupBound = 'true';
                let timeout = null;
                input.addEventListener('input', function() {
                    clearTimeout(timeout);
                    timeout = setTimeout(() => {
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.blur();
                        input.focus();
                    }, 300);
                });
            }
            </script>
            """, height=0)

            if search_query and len(search_query.strip()) >= 2:
                query = search_query.strip().upper()
                filtered = []
                for s in all_stocks:
                    sym = s["symbol"]
                    name_upper = s["name"].upper()
                    if query in sym or query in name_upper:
                        claimed = sym in claimed_tickers
                        if sym == query:
                            priority = 0
                        elif sym.startswith(query):
                            priority = 1
                        elif name_upper.startswith(query):
                            priority = 2
                        else:
                            priority = 3
                        filtered.append((priority, s, claimed))
                filtered.sort(key=lambda x: (x[0], x[1]["symbol"]))
                filtered = filtered[:20]

                if filtered:
                    # Separate available and claimed
                    available = [(p, s, c) for p, s, c in filtered if not c]
                    claimed_list = [(p, s, c) for p, s, c in filtered if c]

                    # Fetch prices: current for available, entry for claimed
                    all_syms = [s["symbol"] for _, s, _ in filtered]
                    fetched_prices = {}
                    if all_syms:
                        try:
                            # Current prices
                            cur_data = yf.download(all_syms, period="1d", progress=False)
                            if not cur_data.empty:
                                adj = cur_data["Adj Close"] if "Adj Close" in cur_data.columns else cur_data["Close"]
                                if isinstance(adj, pd.Series):
                                    fetched_prices[all_syms[0]] = {"current": adj.iloc[-1]}
                                else:
                                    for t in all_syms:
                                        if t in adj.columns and not adj[t].dropna().empty:
                                            fetched_prices[t] = {"current": adj[t].dropna().iloc[-1]}
                        except Exception:
                            pass

                    # Entry prices for claimed
                    claimed_syms = [s["symbol"] for _, s, _ in claimed_list]
                    if claimed_syms:
                        try:
                            entry_data = yf.download(claimed_syms, start=start_date, end=start_date + timedelta(days=7), progress=False)
                            if not entry_data.empty:
                                adj = entry_data["Adj Close"] if "Adj Close" in entry_data.columns else entry_data["Close"]
                                if isinstance(adj, pd.Series):
                                    fetched_prices.setdefault(claimed_syms[0], {})["entry"] = adj.iloc[0]
                                else:
                                    for t in claimed_syms:
                                        if t in adj.columns and not adj[t].dropna().empty:
                                            fetched_prices.setdefault(t, {})["entry"] = adj[t].dropna().iloc[0]
                        except Exception:
                            pass

                    ETF_EMOJI_ADMIN = {"UNCL": "👨‍🦳", "ANTY": "👩🏻", "KIDZ": "👶🏻"}

                    # Show claimed stocks first
                    if claimed_list:
                        for _, s, _ in claimed_list:
                            sym = s["symbol"]
                            name = s["name"]
                            etf_label = claimed_tickers[sym]
                            etf_emoji = ETF_EMOJI_ADMIN.get(etf_label, "")
                            prices = fetched_prices.get(sym, {})
                            entry_price = prices.get("entry")
                            cur_price = prices.get("current")
                            details = ""
                            if entry_price:
                                shares = INVESTMENT / entry_price
                                parts = [f"Entry: ${entry_price:.2f}", f"${INVESTMENT:.0f} invested", f"{shares:.4f} shares"]
                                if cur_price:
                                    mkt_val = shares * cur_price
                                    pnl = mkt_val - INVESTMENT
                                    pnl_color = "#19a05f" if pnl >= 0 else "#d14a34"
                                    parts.append(f'P/L: <span style="color:{pnl_color}">${pnl:+.2f}</span>')
                                details = f'<div style="font-size:0.8rem;color:#666;margin-top:0.3rem;">{" &middot; ".join(parts)}</div>'
                            st.markdown(
                                f'<div style="background:rgba(209,74,52,0.06);border:1px solid rgba(209,74,52,0.2);border-radius:12px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;">'
                                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                                f'<span><strong>{html_mod.escape(sym)}</strong> — {html_mod.escape(name)}</span>'
                                f'<span style="background:#d14a34;color:#fff;font-size:0.7rem;padding:2px 8px;border-radius:10px;font-weight:600;">Claimed {etf_emoji} {html_mod.escape(etf_label)}</span>'
                                f'</div>'
                                f'{details}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                    # Show available stocks below
                    if available:
                        if claimed_list:
                            st.markdown('<div style="border-top:1px solid var(--border);margin:0.5rem 0;"></div>', unsafe_allow_html=True)
                        for _, s, _ in available:
                            sym = s["symbol"]
                            name = s["name"]
                            prices = fetched_prices.get(sym, {})
                            cur_price = prices.get("current")
                            price_line = f'<div style="font-size:0.8rem;color:#666;margin-top:0.3rem;">Current: ${cur_price:.2f}</div>' if cur_price else ""
                            st.markdown(
                                f'<div style="background:rgba(242,248,241,0.7);border:1px solid var(--border);border-radius:12px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;">'
                                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                                f'<span><strong>{html_mod.escape(sym)}</strong> — {html_mod.escape(name)}</span>'
                                f'<span style="background:#19a05f;color:#fff;font-size:0.7rem;padding:2px 8px;border-radius:10px;font-weight:600;">Available</span>'
                                f'</div>'
                                f'{price_line}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if new_etf:
                                if st.button("Add", key=f"add_{sym}", use_container_width=True):
                                    config["players"].append({"etf": new_etf, "name": name, "ticker": sym})
                                    with open("players.json", "w") as f:
                                        json.dump(config, f, indent=2)
                                    st.rerun()
                            else:
                                st.button("Add", key=f"add_{sym}", disabled=True, help="Select an ETF first", use_container_width=True)
                else:
                    st.info("No stocks found matching your search.")

            st.markdown("#### Remove Ticker")
            remove_options = [p["ticker"] for p in config["players"]]
            remove_ticker = st.selectbox(
                "Select ticker to remove",
                [""] + remove_options,
                format_func=lambda x: "Select a ticker" if x == "" else x,
                label_visibility="collapsed",
                key="remove_ticker",
            )
            col_remove, col_reset = st.columns(2)
            with col_remove:
                if st.button("Remove Ticker", use_container_width=True) and remove_ticker:
                    config["players"] = [p for p in config["players"] if p["ticker"] != remove_ticker]
                    with open("players.json", "w") as f:
                        json.dump(config, f, indent=2)
                    st.success(f"Removed {remove_ticker}!")
                    st.rerun()
            with col_reset:
                st.button("Reset", use_container_width=True, on_click=lambda: st.session_state.update({"remove_ticker": ""}))

            st.markdown("")
            if st.button("Logout", use_container_width=True):
                st.session_state.admin_authenticated = False
                st.rerun()
