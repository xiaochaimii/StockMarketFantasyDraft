import html as html_mod
import json
import datetime
import random
import hashlib
import os
from datetime import timedelta
from zoneinfo import ZoneInfo
from collections import Counter
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


def _us_market_holidays(year):
    """Return a set of US stock market holiday dates for the given year."""
    from dateutil.easter import easter
    holidays = set()
    # New Year's Day
    nyd = datetime.date(year, 1, 1)
    if nyd.weekday() == 6:  # Sunday -> observed Monday
        holidays.add(datetime.date(year, 1, 2))
    elif nyd.weekday() == 5:  # Saturday -> not observed (prior Friday is prev year)
        pass
    else:
        holidays.add(nyd)
    # MLK Day: 3rd Monday of January
    holidays.add(_nth_weekday(year, 1, 0, 3))
    # Presidents' Day: 3rd Monday of February
    holidays.add(_nth_weekday(year, 2, 0, 3))
    # Good Friday
    holidays.add(easter(year) - datetime.timedelta(days=2))
    # Memorial Day: last Monday of May
    holidays.add(_last_weekday(year, 5, 0))
    # Juneteenth
    jt = datetime.date(year, 6, 19)
    if jt.weekday() == 6:
        holidays.add(datetime.date(year, 6, 20))
    elif jt.weekday() == 5:
        holidays.add(datetime.date(year, 6, 18))
    else:
        holidays.add(jt)
    # Independence Day
    jul4 = datetime.date(year, 7, 4)
    if jul4.weekday() == 6:
        holidays.add(datetime.date(year, 7, 5))
    elif jul4.weekday() == 5:
        holidays.add(datetime.date(year, 7, 3))
    else:
        holidays.add(jul4)
    # Labor Day: 1st Monday of September
    holidays.add(_nth_weekday(year, 9, 0, 1))
    # Thanksgiving: 4th Thursday of November
    holidays.add(_nth_weekday(year, 11, 3, 4))
    # Christmas
    xmas = datetime.date(year, 12, 25)
    if xmas.weekday() == 6:
        holidays.add(datetime.date(year, 12, 26))
    elif xmas.weekday() == 5:
        holidays.add(datetime.date(year, 12, 24))
    else:
        holidays.add(xmas)
    return holidays


def _nth_weekday(year, month, weekday, n):
    """Return the nth occurrence of weekday (0=Mon) in the given month."""
    first = datetime.date(year, month, 1)
    diff = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=diff + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    """Return the last occurrence of weekday (0=Mon) in the given month."""
    import calendar
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    diff = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=diff)


def is_market_open():
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    if now_et.date() in _us_market_holidays(now_et.year):
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


REFRESH_INTERVAL = timedelta(seconds=3600) if is_market_open() else None


def format_signed_currency(value):
    if value >= 0:
        return f'<span style="color:#19a05f;">${value:.2f}</span>'
    return f'<span style="color:#d14a34;">(${abs(value):.2f})</span>'


def format_signed_percent(value):
    if value >= 0:
        return f'<span style="color:#19a05f;">{value:.2f}%</span>'
    return f'<span style="color:#d14a34;">({abs(value):.2f}%)</span>'


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
/* Fix Safari mobile whitespace/overflow */
html, body {
    -webkit-overflow-scrolling: touch;
}
@media (max-width: 768px) {
    [data-testid="stSidebar"][aria-expanded="false"] {
        display: none !important;
    }
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100vw !important;
        overflow-x: clip !important;
    }
    [data-testid="stAppViewContainer"] {
        max-width: 100vw !important;
        overflow-x: clip !important;
    }
    [data-testid="stAppViewContainer"] > section > div {
        max-width: 100vw !important;
    }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    .hero-card {
        padding: 1rem !important;
    }
    .hero-title {
        font-size: 1.3rem !important;
    }
    .section-card {
        padding: 0.8rem !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    iframe {
        max-width: 100% !important;
    }
}
/* Mobile landscape: short viewport height + wide screen */
@media (max-height: 500px) and (orientation: landscape) {
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="stHeader"] {
        display: none !important;
    }
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }
    .hero-card {
        padding: 0.8rem 1rem !important;
        border-radius: 16px;
        margin-bottom: 0.4rem !important;
    }
    .hero-title {
        font-size: 1.2rem !important;
        margin: 0.2rem 0 0.3rem !important;
    }
    .hero-meta {
        gap: 0.3rem !important;
        margin-top: 0.3rem !important;
    }
    .hero-pill {
        font-size: 0.65rem !important;
        padding: 0.2rem 0.5rem !important;
    }
    .metric-card {
        padding: 0.5rem 0.7rem !important;
        min-height: auto !important;
    }
    .section-card {
        border-radius: 14px;
        padding: 0.6rem 0.8rem;
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
    z-index: 999 !important;
}
[data-testid="stDecoration"] {
    display: none !important;
}
/* Force the main menu popover above all content with solid background */
div[data-testid="stMainMenuPopover"] {
    z-index: 99999 !important;
    background: #ffffff !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important;
}
div[data-testid="stMainMenuPopover"] ul {
    background: #ffffff !important;
}
div[data-testid="stMainMenuPopover"] li {
    color: #102018 !important;
    background: #ffffff !important;
}
div[data-testid="stMainMenuPopover"] li:hover {
    background: #f0f0f0 !important;
}
/* Prevent plotly charts from creating competing stacking contexts */
#js-plotly-tester {
    z-index: auto !important;
}
svg.main-svg {
    z-index: auto !important;
}
.block-container {
    padding-top: 0rem;
    padding-bottom: 3rem;
}
[data-testid="stAppViewBlockContainer"] > div:first-child {
    margin-top: 0 !important;
    padding-top: 0 !important;
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
    border-radius: 24px;
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
.metric-card.meh::before {
    background: linear-gradient(180deg, #d7a83a 0%, #b8922e 100%);
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
.leaderboard-scroll {
    display: block !important;
    overflow-x: scroll !important;
    overflow-y: visible !important;
    -webkit-overflow-scrolling: touch;
    width: 100% !important;
    max-width: calc(100vw - 4rem) !important;
    border: 1px solid var(--border);
    border-radius: 18px;
}
/* Force all Streamlit parents of leaderboard to allow overflow */
div:has(> .leaderboard-scroll),
div:has(> div > .leaderboard-scroll),
div:has(> div > div > .leaderboard-scroll) {
    overflow: visible !important;
}
table.leaderboard {
    width: 100% !important;
    min-width: 1400px;
    border-collapse: separate !important;
    border-spacing: 0;
    border-radius: 18px;
    background: var(--panel-strong);
}
table.leaderboard td, table.leaderboard th {
    padding: 10px 8px;
    text-align: left;
    border-bottom: 1px solid rgba(18, 51, 36, 0.08);
    white-space: nowrap;
}
table.leaderboard th {
    white-space: normal !important;
}
table.leaderboard th {
    background: linear-gradient(90deg, #0d2f20 0%, #13492f 100%);
    color: #f4f0e3;
    position: sticky;
    top: 0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.7rem;
    white-space: normal;
    min-width: 60px;
    padding: 10px 8px;
    line-height: 1.3;
}
table.leaderboard tr:nth-child(even) td {
    background: rgba(16, 95, 58, 0.04);
}
table.leaderboard tr td:first-child {
    font-weight: 700;
    color: var(--accent);
}
table.leaderboard tbody tr:hover td {
    background: rgba(14, 95, 58, 0.08);
    transition: background 0.15s ease;
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
        padding: 1.2rem 1.2rem !important;
        border-radius: 20px;
        margin-bottom: 0.6rem !important;
    }
    .hero-title {
        font-size: 1.45rem !important;
        margin: 0.3rem 0 0.5rem !important;
    }
    .hero-meta {
        gap: 0.4rem !important;
        margin-top: 0.4rem !important;
    }
    .hero-pill {
        font-size: 0.7rem !important;
        padding: 0.25rem 0.55rem !important;
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
    /* Metric cards mobile */
    .metric-card {
        padding: 0.6rem 0.75rem !important;
        min-height: auto !important;
        border-radius: 16px;
    }
    .metric-value {
        font-size: 1.15rem !important;
    }
    .metric-label {
        font-size: 0.65rem;
    }
    .metric-detail {
        font-size: 0.72rem;
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
    /* Global mobile overflow fix */
    .block-container, .block-container > div {
        max-width: 100vw !important;
    }
    /* Market Pulse mobile */
    .recap-card {
        padding: 0.8rem 0.8rem !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    .recap-card > div:first-child {
        flex-direction: column !important;
        gap: 0.5rem !important;
    }
    .recap-card span[style*="font-size:2.4rem"] {
        font-size: 1.8rem !important;
    }
    .recap-card div[style*="font-size:1.2rem"] {
        font-size: 1rem !important;
    }
    /* Signal table mobile - scrollable */
    .signal-table {
        display: block !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
        font-size: 0.65rem !important;
    }
    .signal-table td, .signal-table th {
        padding: 0.25rem 0.35rem !important;
        font-size: 0.62rem !important;
        white-space: nowrap !important;
    }
    /* Bragging rights table mobile - scrollable */
    table:not(.leaderboard):not(.signal-table) {
        display: block !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
    }
    table td, table th {
        font-size: 0.7rem;
    }
    /* Prediction cards mobile */
    .pred-card {
        padding: 0.4rem 0.5rem !important;
        min-height: auto !important;
    }
    .pred-ticker {
        font-size: 0.85rem !important;
    }
    .pred-icon {
        font-size: 1rem !important;
        margin-bottom: 0.1rem !important;
    }
    .pred-title {
        font-size: 0.6rem !important;
    }
    .pred-name, .pred-detail {
        font-size: 0.65rem !important;
    }
    .pred-confidence {
        font-size: 0.58rem !important;
        padding: 0.05rem 0.35rem !important;
    }
    /* Multi-award bar mobile */
    .sup-multi-bar {
        flex-wrap: wrap !important;
        font-size: 0.7rem !important;
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
        max-height: none;
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

/* Make component iframes transparent so extra space is invisible */
iframe {
    background: transparent !important;
    color-scheme: normal;
}
.stHtml iframe,
[data-testid="stHtml"] iframe {
    background: transparent !important;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* --- Trash Talk Ticker --- */
.trash-talk-ticker {
    background: linear-gradient(90deg, #0d2f20, #13492f);
    border-radius: 16px;
    padding: 0.6rem 0;
    margin-bottom: 0.75rem;
    overflow: clip;
    overflow-clip-margin: content-box;
}
@keyframes ticker-scroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-50%); }
}
.ticker-track {
    display: flex;
    gap: 2.5rem;
    animation: ticker-scroll 500s linear infinite;
    white-space: nowrap;
    width: max-content;
}
.ticker-item {
    color: #f4f0e3;
    font-size: 0.82rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
}

/* --- Bragging Rights Badge Grid --- */
.sup-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}
@media (max-width: 1200px) {
    .sup-grid { grid-template-columns: repeat(5, 1fr); }
}
@media (max-width: 768px) {
    .sup-grid { grid-template-columns: repeat(3, 1fr); }
}
.sup-badge {
    background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(242,248,241,0.96) 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 0.65rem 0.5rem 0.55rem;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 120px;
    justify-content: flex-start;
}
.sup-badge:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(16, 42, 32, 0.12);
}
.sup-badge-icon {
    font-size: 1.8rem;
    line-height: 1;
    margin-bottom: 0.2rem;
}
.sup-badge-name {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--text);
    line-height: 1.2;
}
.sup-badge-holder {
    font-size: 0.68rem;
    color: var(--muted);
    margin-top: 0.1rem;
    line-height: 1.2;
}
.sup-badge-desc {
    font-size: 0.6rem;
    color: var(--muted);
    opacity: 0.65;
    margin-top: 0.1rem;
    line-height: 1.2;
}
.sup-multi-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    padding: 0.5rem 0.8rem;
    background: rgba(215,168,58,0.08);
    border: 1px solid rgba(215,168,58,0.2);
    border-radius: 12px;
    font-size: 0.78rem;
    margin-bottom: 0.5rem;
    align-items: center;
}
.sup-multi-bar .multi-label {
    font-weight: 700;
    color: #b45309;
}
.sup-multi-stock {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    background: rgba(255,255,255,0.6);
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
    font-size: 0.72rem;
}
.sup-multi-stock b {
    color: var(--text);
}

/* --- Achievements / Badges --- */
.badge-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
    gap: 0.6rem;
}
.badge-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(242,248,241,0.96));
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 0.75rem 0.8rem;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
    position: relative;
    overflow: hidden;
}
.badge-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(16, 42, 32, 0.15);
}
.badge-card.locked {
    opacity: 0.4;
    filter: grayscale(1);
}
.badge-icon {
    font-size: 2rem;
    margin-bottom: 0.2rem;
}
.badge-name {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--text);
}
.badge-holder {
    font-size: 0.7rem;
    color: var(--muted);
    margin-top: 0.15rem;
}

/* --- Weekly Recap --- */
.recap-card {
    background: linear-gradient(135deg, #0d2f20 0%, #1a5c3a 50%, #0d2f20 100%);
    border-radius: 24px;
    padding: 1.4rem 1.5rem;
    color: #f4f0e3;
    position: relative;
    overflow: hidden;
}
.recap-card::after {
    content: '';
    position: absolute;
    top: -30%;
    right: -10%;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(215,168,58,0.25), transparent 65%);
}
.recap-title {
    font-size: 1.1rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
    color: var(--accent-2);
}
.recap-line {
    font-size: 0.88rem;
    padding: 0.25rem 0;
    opacity: 0.92;
}

/* --- Trivia --- */
.trivia-card {
    background: linear-gradient(135deg, rgba(215,168,58,0.08), rgba(215,168,58,0.02));
    border: 1px solid rgba(215,168,58,0.25);
    border-radius: 16px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.75rem;
}
.trivia-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent-2);
    margin-bottom: 0.25rem;
}
.trivia-text {
    font-size: 0.88rem;
    color: var(--text);
    line-height: 1.4;
}

/* --- Emoji Reactions --- */
/* Roast reaction buttons - handled inside components.html */

/* --- Predictions --- */
.pred-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.5rem;
}
@media (max-width: 768px) {
    .pred-grid { grid-template-columns: repeat(2, 1fr); }
}
.pred-card {
    background: linear-gradient(135deg, rgba(14,95,58,0.06), rgba(14,95,58,0.02));
    border: 1px solid rgba(14,95,58,0.2);
    border-radius: 16px;
    padding: 0.8rem 1rem;
    position: relative;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.pred-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(14, 95, 58, 0.12);
}
.pred-card .pred-icon {
    font-size: 1.5rem;
    margin-bottom: 0.2rem;
}
.pred-card .pred-title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
}
.pred-card .pred-ticker {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--text);
}
.pred-card .pred-name {
    font-size: 0.8rem;
    color: var(--muted);
}
.pred-card .pred-detail {
    font-size: 0.78rem;
    color: var(--text);
    margin-top: 0.2rem;
    opacity: 0.85;
}
.pred-confidence {
    display: inline-block;
    background: rgba(14,95,58,0.12);
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--accent);
    margin-top: 0.3rem;
}
/* Shrink vote buttons inside prediction cards */
.pred-vote-row button {
    padding: 0.15rem 0.4rem !important;
    min-height: 0 !important;
    font-size: 0.75rem !important;
    border-radius: 8px !important;
    background: rgba(14,95,58,0.08) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
}
.pred-vote-row button:hover {
    background: rgba(14,95,58,0.18) !important;
}
.pred-vote-row [data-testid="stHorizontalBlock"] {
    gap: 0.3rem !important;
}

/* --- Signals & News --- */
.signal-badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.03em;
}
.signal-buy { background: rgba(25,160,95,0.15); color: #19a05f; }
.signal-sell { background: rgba(209,74,52,0.12); color: #d14a34; }
.signal-hold { background: rgba(18,51,36,0.08); color: var(--muted); }
.signal-table {
    width: 100% !important;
    border-collapse: separate !important;
    border-spacing: 0;
    overflow: hidden;
    border-radius: 18px;
    background: var(--panel-strong);
}
.signal-table th {
    background: linear-gradient(90deg, #0d2f20 0%, #13492f 100%);
    color: #f4f0e3;
    position: sticky;
    top: 0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.75rem;
    padding: 12px 14px;
    text-align: left;
}
.signal-table td {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(18, 51, 36, 0.08);
}
.signal-table tr:nth-child(even) td {
    background: rgba(16, 95, 58, 0.04);
}
.signal-table tr td:first-child {
    font-weight: 700;
    color: var(--accent);
}
.signal-table tbody tr:hover td {
    background: rgba(14, 95, 58, 0.08);
    transition: background 0.15s ease;
}
.news-item {
    padding: 0.5rem 0;
    border-bottom: 1px solid rgba(18,51,36,0.08);
}
.news-item:last-child { border-bottom: none; }
.news-item a {
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.85rem;
}
.news-item a:hover { color: var(--accent); }
.news-item .news-meta {
    font-size: 0.7rem;
    color: var(--muted);
    margin-top: 0.1rem;
}
.rsi-bar {
    display: inline-block;
    width: 50px;
    height: 6px;
    background: rgba(18,51,36,0.1);
    border-radius: 3px;
    position: relative;
    vertical-align: middle;
}
.rsi-bar-fill {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    border-radius: 3px;
}

/* --- Confetti --- */
@keyframes confetti-fall {
    0% { transform: translateY(-100vh) rotate(0deg); opacity: 1; }
    100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
}
.confetti-piece {
    position: fixed;
    top: -10px;
    z-index: 9999;
    pointer-events: none;
    animation: confetti-fall 3s ease-in-out forwards;
}
/* Respect reduced motion preferences */
@media (prefers-reduced-motion: reduce) {
    .trash-talk-ticker .ticker-track {
        animation: none !important;
    }
    .confetti-piece {
        animation: none !important;
        display: none !important;
    }
}
/* Consistent section spacing */
.section-gap {
    margin-top: 1.5rem;
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
_ETF_CLR = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"}
def _etf_colored(ticker, escaped=False):
    """Return ticker wrapped in a colored span based on its ETF."""
    t = ticker if escaped else html_mod.escape(ticker)
    clr = _ETF_CLR.get(ETF_MAP.get(ticker, ""), "")
    if clr:
        return f'<span style="color:{clr};font-weight:700;">{t}</span>'
    return f'<b>{t}</b>'

SECTOR_MAP = {
    "AAPL": "Tech", "AB": "Finance", "ALK": "Transport", "AMD": "Tech", "AMZN": "Tech",
    "ANET": "Tech", "APLD": "Tech", "ARM": "Tech", "ASML": "Tech", "ASTS": "Transport",
    "AVGO": "Tech", "BRK-B": "Finance", "CIFR": "Tech", "COIN": "Finance", "COST": "Consumer",
    "CRWD": "Tech", "DASH": "Consumer", "DIS": "Consumer", "DUOL": "Tech", "ENLT": "Energy",
    "FIG": "Tech", "GD": "Defense", "GLD": "Energy", "GOOG": "Tech", "HD": "Consumer",
    "HNST": "Consumer", "IBM": "Tech", "INTC": "Tech", "ION": "Energy", "IONQ": "Tech",
    "IREN": "Tech", "JNJ": "Healthcare", "LLY": "Healthcare", "LMT": "Defense",
    "LRCX": "Tech", "MAR": "Consumer", "MCD": "Consumer", "MELI": "Consumer",
    "META": "Tech", "MRNA": "Healthcare", "MSFT": "Tech", "MSTR": "Finance",
    "MU": "Tech", "NFLX": "Media", "NOC": "Defense", "NTDOY": "Media", "NVDA": "Tech",
    "NVO": "Healthcare", "ORCL": "Tech", "PANW": "Tech", "PG": "Consumer", "PLTR": "Tech",
    "PPLT": "Energy", "RBLX": "Tech", "RIVN": "Transport", "RTX": "Defense",
    "SLV": "Energy", "SNDK": "Tech", "STX": "Tech", "SVNDY": "Consumer", "TER": "Tech",
    "TGT": "Consumer", "TPL": "Energy", "TSM": "Tech", "TYGO": "Energy",
    "UNH": "Healthcare", "WDAY": "Media", "WDC": "Tech", "WM": "Consumer",
    "WMT": "Consumer", "XOM": "Energy",
}

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
        threads=True,
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


@st.cache_data(ttl=3600)
def compute_signals(tickers, start, end):
    """Compute technical buy/sell signals from price data."""
    # Fetch extra history for indicator warm-up (30 extra calendar days)
    extended_start = start - datetime.timedelta(days=45)
    data = yf.download(tickers, start=extended_start, end=end + datetime.timedelta(days=1),
                       auto_adjust=True, progress=False, threads=True)
    if data.empty:
        return {}

    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    close = close.ffill().bfill()

    signals = {}
    for ticker in tickers:
        if ticker not in close.columns or close[ticker].isna().all():
            continue
        prices = close[ticker].dropna()
        if len(prices) < 20:
            signals[ticker] = {"rsi": None, "signal": "HOLD", "score": 0, "sma_cross": None, "price_vs_sma": None}
            continue

        # RSI (14-day)
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        # SMA crossover (10 vs 20)
        sma10 = prices.rolling(window=10).mean()
        sma20 = prices.rolling(window=20).mean()
        sma_cross = bool(sma10.iloc[-1] > sma20.iloc[-1])

        # Price vs 20-day SMA
        price_vs_sma = bool(prices.iloc[-1] > sma20.iloc[-1])

        # Composite score
        score = 0
        if current_rsi < 30:
            score += 1
        elif current_rsi > 70:
            score -= 1
        if sma_cross:
            score += 1
        else:
            score -= 1
        if price_vs_sma:
            score += 1
        else:
            score -= 1

        if score >= 2:
            signal = "BUY"
        elif score <= -2:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Compute daily signals to detect most recent change
        prev_signal = None
        change_date = None
        if len(prices) >= 20:
            sma10_series = prices.rolling(window=10).mean()
            sma20_series = prices.rolling(window=20).mean()
            daily_signals = []
            for i in range(len(prices)):
                if pd.isna(rsi.iloc[i]) or pd.isna(sma20_series.iloc[i]) or pd.isna(sma10_series.iloc[i]):
                    daily_signals.append(None)
                    continue
                s = 0
                r = float(rsi.iloc[i])
                if r < 30:
                    s += 1
                elif r > 70:
                    s -= 1
                if sma10_series.iloc[i] > sma20_series.iloc[i]:
                    s += 1
                else:
                    s -= 1
                if prices.iloc[i] > sma20_series.iloc[i]:
                    s += 1
                else:
                    s -= 1
                if s >= 2:
                    daily_signals.append("BUY")
                elif s <= -2:
                    daily_signals.append("SELL")
                else:
                    daily_signals.append("HOLD")
            # Walk backwards to find last change
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
            "prev_signal": prev_signal,
            "change_date": change_date,
        }
    return signals


@st.cache_data(ttl=7200)
def fetch_news_batch(tickers_tuple):
    """Fetch latest news for tickers via yfinance using threads."""
    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one(ticker):
        try:
            t = yf.Ticker(ticker)
            news = t.news
            if news:
                item = news[0]
                content = item.get("content", item)
                title = content.get("title", "") or item.get("title", "")
                publisher = content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else item.get("publisher", "")
                link = content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", "")
                if title:
                    return {"ticker": ticker, "title": title, "publisher": publisher, "link": link}
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = pool.map(_fetch_one, tickers_tuple)
    return [r for r in results if r]


@st.cache_data(ttl=86400)
def fetch_earnings(tickers_tuple):
    """Fetch next earnings date and EPS estimates for tickers via yfinance using threads."""
    from concurrent.futures import ThreadPoolExecutor
    import datetime as _dt
    import time as _time

    _empty = {"next_date": "", "eps_est": None, "eps_actual": None, "last_earnings_date": "", "last_eps_reported": None, "last_eps_estimate": None}

    def _fetch_one(ticker):
        for attempt in range(2):
            try:
                t = yf.Ticker(ticker)
                cal = t.calendar
                # Handle DataFrame format from older yfinance versions
                if cal is not None and hasattr(cal, 'to_dict') and not isinstance(cal, dict):
                    try:
                        cal = cal.to_dict()
                    except Exception:
                        cal = {}
                if cal is not None and isinstance(cal, dict) and cal:
                    earnings_dates_list = cal.get("Earnings Date", [])
                    next_date = earnings_dates_list[0].strftime("%b %d") if earnings_dates_list else ""
                    eps_est = cal.get("Earnings Average")
                    info = t.info
                    eps_actual = info.get("trailingEps")
                    # Get most recent quarterly earnings for beat/miss
                    last_earnings_date = ""
                    last_eps_reported = None
                    last_eps_estimate = None
                    try:
                        eh = t.earnings_history
                        if eh is not None and len(eh) > 0:
                            latest = eh.iloc[-1]
                            last_earnings_date = eh.index[-1].strftime("%b %y")
                            v = latest.get("epsActual")
                            if v is not None and str(v) != "nan":
                                last_eps_reported = round(float(v), 2)
                            v = latest.get("epsEstimate")
                            if v is not None and str(v) != "nan":
                                last_eps_estimate = round(float(v), 2)
                    except Exception:
                        pass
                    return ticker, {
                        "next_date": next_date,
                        "eps_est": round(eps_est, 2) if eps_est else None,
                        "eps_actual": round(eps_actual, 2) if eps_actual else None,
                        "last_earnings_date": last_earnings_date,
                        "last_eps_reported": last_eps_reported,
                        "last_eps_estimate": last_eps_estimate,
                    }
                else:
                    # Empty calendar (ETFs, etc.) — no earnings data available
                    return ticker, dict(_empty)
            except Exception as e:
                if attempt == 0:
                    _time.sleep(0.5)
                    continue
                print(f"[fetch_earnings] {ticker} failed after retry: {e}")
        return ticker, dict(_empty)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = pool.map(_fetch_one, tickers_tuple)
    return dict(results)


def compute_throne_history(returns, valid_tickers, name_map, dividends=None, start_prices=None, investment=10.0):
    """Compute MVP/Benchwarmer streak counts and transition history using total return (price + dividends)."""
    # Compute total return for each ticker on each day, matching final_returns formula exactly:
    # total_return = ((investment / start_price * close_price + investment / start_price * dividend) / investment - 1) * 100
    # Which simplifies to: (close/start - 1)*100 + (dividend/start)*100 = price_return + div_return
    # returns already contains (close/start - 1)*100, so just add div_return
    cum_returns = returns[valid_tickers].copy()
    if dividends and start_prices is not None:
        for t in valid_tickers:
            if start_prices[t] and start_prices[t] != 0:
                div_ret = (dividends.get(t, 0.0) / start_prices[t]) * 100
                cum_returns[t] = cum_returns[t] + div_ret
    # Skip first row (day 0 = all zeros + div_ret, not meaningful)
    if len(cum_returns) > 1:
        cum_returns = cum_returns.iloc[1:]

    # Determine #1 (MVP) and last place (benchwarmer) each day by total return
    mvp_series = cum_returns.idxmax(axis=1)
    bench_series = cum_returns.idxmin(axis=1)

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
                ret = cum_returns.loc[date, holder]
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



def compute_superlatives(returns, valid_tickers, name_map, etf_map, throne, dividends=None, start_prices=None):
    """Compute fun superlative stats."""
    results = {}
    daily = returns[valid_tickers].copy()
    # Add dividend return for total-return-based rankings
    if dividends and start_prices is not None:
        for t in valid_tickers:
            div_ret = (dividends.get(t, 0.0) / start_prices[t]) * 100 if start_prices[t] else 0
            daily[t] = daily[t] + div_ret
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


# --- News Ticker Generator ---
def generate_trash_talk(throne, superlatives, final_returns, name_map, etf_map, returns, valid_tickers):
    """Generate news headline ticker for all stocks."""
    lines = []

    # Fetch latest news headlines for top 15 and bottom 15 stocks (not all 71)
    news_candidates = list(final_returns.head(15).index) + list(final_returns.tail(15).index)
    news_candidates = list(dict.fromkeys(news_candidates))  # dedupe
    all_news = fetch_news_batch(tuple(news_candidates))
    # Deduplicate: one headline per ticker (first = most recent)
    seen_tickers = set()
    for article in all_news:
        t = article["ticker"]
        if t not in seen_tickers:
            seen_tickers.add(t)
            lines.append(f"\U0001f4f0 {t}: {article['title']}")

    return lines


# --- Achievements / Badges ---
def compute_achievements(returns, valid_tickers, name_map, dividends, throne, final_returns, start_prices, investment):
    """Compute fun achievement badges."""
    badges = []
    daily = returns[valid_tickers].copy()
    # Add dividend return for total-return-based MVP
    for t in valid_tickers:
        div_ret = (dividends.get(t, 0.0) / start_prices[t]) * 100 if start_prices[t] else 0
        daily[t] = daily[t] + div_ret
    daily_changes = daily.diff()

    # Diamond Hands: held MVP for 10+ days total
    if len(daily) > 1:
        daily_mvp = daily.iloc[1:].idxmax(axis=1)
        mvp_counts = Counter(daily_mvp)
        if mvp_counts:
            top_mvp, top_count = mvp_counts.most_common(1)[0]
            badges.append({
                "icon": "\U0001f48e", "name": "Diamond Hands",
                "desc": f"Most days as MVP",
                "holder": f"{top_mvp} ({top_count}d)",
                "unlocked": top_count >= 5,
            })

    # Rollercoaster: biggest intraday swing range
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        volatility = changes.std()
        wild = volatility.idxmax()
        badges.append({
            "icon": "\U0001f3a2", "name": "Rollercoaster",
            "desc": "Most volatile stock",
            "holder": f"{wild} (\u00b1{volatility[wild]:.2f}%/day)",
            "unlocked": True,
        })

    # Dividend King: highest dividend income
    if dividends:
        div_income = {}
        for t in valid_tickers:
            shares = investment / start_prices[t]
            div_income[t] = shares * dividends.get(t, 0.0)
        best_div = max(div_income, key=div_income.get)
        badges.append({
            "icon": "\U0001f4b0", "name": "Dividend King",
            "desc": "Most dividend income",
            "holder": f"{best_div} (${div_income[best_div]:.2f})",
            "unlocked": div_income[best_div] > 0,
        })

    # Steady Eddie: lowest volatility
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        volatility = changes.std()
        steady = volatility.idxmin()
        badges.append({
            "icon": "\U0001f9d8", "name": "Steady Eddie",
            "desc": "Least volatile stock",
            "holder": f"{steady} (\u00b1{volatility[steady]:.2f}%/day)",
            "unlocked": True,
        })

    # Moonshot: biggest single-day gain
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        best_idx = changes.stack().idxmax()
        best_val = changes.loc[best_idx[0], best_idx[1]]
        badges.append({
            "icon": "\U0001f315", "name": "Moonshot",
            "desc": "Biggest single-day gain",
            "holder": f"{best_idx[1]} (+{best_val:.2f}%)",
            "unlocked": best_val > 3,
        })

    # Crash Landing: biggest single-day loss
    if len(daily_changes) > 1:
        changes = daily_changes.iloc[1:]
        worst_idx = changes.stack().idxmin()
        worst_val = changes.loc[worst_idx[0], worst_idx[1]]
        badges.append({
            "icon": "\U0001f4a5", "name": "Crash Landing",
            "desc": "Biggest single-day loss",
            "holder": f"{worst_idx[1]} ({worst_val:+.2f}%)",
            "unlocked": worst_val < -3,
        })

    # The Terminator: took the throne most times
    throne_takes = Counter()
    for entry in throne["mvp_history"]:
        throne_takes[entry["ticker"]] += 1
    if throne_takes:
        term_ticker, term_count = throne_takes.most_common(1)[0]
        badges.append({
            "icon": "\U0001f916", "name": "The Terminator",
            "desc": "Took MVP throne most times",
            "holder": f"{term_ticker} ({term_count}x)",
            "unlocked": term_count >= 2,
        })

    # Iron Throne: longest continuous MVP streak
    sw = throne.get("streak_winner", {})
    if sw.get("ticker") and sw.get("type") == "mvp":
        badges.append({
            "icon": "\u2694\ufe0f", "name": "Iron Throne",
            "desc": "Longest MVP streak ever",
            "holder": f"{sw['ticker']} ({sw['streak']}d)",
            "unlocked": sw["streak"] >= 5,
        })

    # Bottom Feeder: longest benchwarmer streak
    if len(daily) > 1:
        daily_bench = daily.iloc[1:].idxmin(axis=1)
        bench_counts = Counter(daily_bench)
        if bench_counts:
            worst_bench, worst_count = bench_counts.most_common(1)[0]
            badges.append({
                "icon": "\U0001f40c", "name": "Bottom Feeder",
                "desc": "Most days as benchwarmer",
                "holder": f"{worst_bench} ({worst_count}d)",
                "unlocked": worst_count >= 5,
            })

    # Photo Finish: two stocks closest in final return
    sorted_rets = final_returns.sort_values(ascending=False)
    if len(sorted_rets) >= 2:
        min_gap = float('inf')
        photo_pair = ("", "")
        for i in range(len(sorted_rets) - 1):
            gap = abs(sorted_rets.iloc[i] - sorted_rets.iloc[i + 1])
            if gap < min_gap:
                min_gap = gap
                photo_pair = (sorted_rets.index[i], sorted_rets.index[i + 1])
        badges.append({
            "icon": "\U0001f4f8", "name": "Photo Finish",
            "desc": "Closest return gap",
            "holder": f"{photo_pair[0]} vs {photo_pair[1]} ({min_gap:.2f}%)",
            "unlocked": min_gap < 1.0,
        })

    # Dark Horse: started in bottom 25%, finished in top 25%
    if len(daily) > 1:
        first_ranks = daily.iloc[1].rank(ascending=False)
        final_ranks = daily.iloc[-1].rank(ascending=False)
        total = len(valid_tickers)
        q1 = total * 0.25
        q4 = total * 0.75
        dark_horses = [t for t in valid_tickers if first_ranks[t] > q4 and final_ranks[t] <= q1]
        if dark_horses:
            best_horse = max(dark_horses, key=lambda t: final_returns[t])
            badges.append({
                "icon": "\U0001f40e", "name": "Dark Horse",
                "desc": "Bottom 25% \u2192 Top 25%",
                "holder": f"{best_horse} (#{int(first_ranks[best_horse])}\u2192#{int(final_ranks[best_horse])})",
                "unlocked": True,
            })
        else:
            badges.append({
                "icon": "\U0001f40e", "name": "Dark Horse",
                "desc": "Bottom 25% \u2192 Top 25%",
                "holder": "No one yet",
                "unlocked": False,
            })

    return badges


# --- Stock Trivia ---
STOCK_TRIVIA = {
    "AAPL": [
        "Apple's first logo featured Isaac Newton sitting under a tree.",
        "The original Apple I computer sold for $666.66.",
        "Apple has more cash reserves than most countries' GDP.",
    ],
    "MSFT": [
        "Microsoft's first product was a BASIC interpreter for the Altair 8800.",
        "Bill Gates' SAT score was 1590 out of 1600.",
        "The name 'Microsoft' is a blend of 'microcomputer' and 'software'.",
    ],
    "AMZN": [
        "Amazon was originally going to be called 'Cadabra' (as in abracadabra).",
        "Jeff Bezos' first office desk was made from a door.",
        "Amazon's first book order was 'Fluid Concepts and Creative Analogies'.",
    ],
    "GOOG": [
        "Google's original name was 'BackRub'.",
        "The first Google Doodle was a Burning Man stick figure in 1998.",
        "'Googol' (the number 10^100) inspired the name Google.",
    ],
    "META": [
        "Facebook was originally limited to Harvard students only.",
        "The iconic blue color was chosen because Zuckerberg is red-green colorblind.",
        "Facebook's 'Like' button was almost called the 'Awesome' button.",
    ],
    "NVDA": [
        "NVIDIA's name comes from 'invidia', the Latin word for envy.",
        "The company was founded in a Denny's restaurant in 1993.",
        "NVIDIA's first product, the NV1, could also play Sega Saturn games.",
    ],
    "TSLA": [
        "Tesla's first car, the Roadster, was built on a Lotus Elise chassis.",
        "The Tesla logo is actually a cross-section of an electric motor.",
        "SpaceX launched a Tesla Roadster into space in 2018.",
    ],
    "NFLX": [
        "Netflix was founded because Reed Hastings got a $40 late fee from Blockbuster.",
        "Netflix's first DVD shipped was 'Beetlejuice' in 1998.",
        "The company considered naming itself 'Kibble' at one point.",
    ],
    "DIS": [
        "Walt Disney was fired from a newspaper for 'lacking imagination'.",
        "Mickey Mouse was originally going to be named 'Mortimer Mouse'.",
        "Disney World is roughly the same size as San Francisco.",
    ],
    "COST": [
        "Costco sells more hot dogs than every MLB stadium combined.",
        "The Costco hot dog combo has been $1.50 since 1985.",
        "Costco's Kirkland Signature is one of the largest brands in the world.",
    ],
    "COIN": [
        "Coinbase was the first crypto company to go public on the Nasdaq.",
        "The company was founded in a two-bedroom apartment in San Francisco.",
    ],
    "AMD": [
        "AMD was founded by Jerry Sanders, a former Fairchild Semiconductor exec.",
        "AMD and Intel were both founded within a year of each other (1968-1969).",
    ],
    "INTC": [
        "Intel's first product was a memory chip, not a processor.",
        "The Intel Inside jingle is one of the most recognized sounds in advertising.",
        "Gordon Moore (of Moore's Law) co-founded Intel.",
    ],
    "WMT": [
        "The first Walmart opened in 1962 in Rogers, Arkansas.",
        "Walmart is the world's largest employer with over 2 million workers.",
    ],
    "BRK-B": [
        "Berkshire Hathaway was originally a textile company.",
        "Warren Buffett bought his first stock at age 11.",
        "Berkshire's Class A shares are the most expensive stock in the world.",
    ],
    "RBLX": [
        "Over half of American kids under 16 play Roblox.",
        "Roblox was originally called 'DynaBlocks' when it launched in 2004.",
    ],
    "MCD": [
        "McDonald's serves about 69 million customers daily worldwide.",
        "The Big Mac was invented by a franchisee, not McDonald's corporate.",
    ],
    "PLTR": [
        "Palantir is named after the seeing stones in Lord of the Rings.",
        "The company was co-founded by Peter Thiel and Alex Karp.",
    ],
    "MSTR": [
        "MicroStrategy holds over 200,000 Bitcoin on its balance sheet.",
        "The company rebranded to 'Strategy' but its ticker is still MSTR.",
    ],
}

# Generic trivia for stocks without specific entries
GENERIC_TRIVIA = [
    "The stock market has returned an average of about 10% per year since 1926.",
    "The NYSE was founded under a buttonwood tree on Wall Street in 1792.",
    "The term 'bull market' may come from bulls attacking by thrusting horns upward.",
    "The worst single-day crash in history was Black Monday (Oct 19, 1987) \u2014 down 22.6%.",
    "Over 90% of day traders lose money according to academic studies.",
    "The S&P 500 has had a positive annual return in about 73% of years since 1926.",
    "Warren Buffett's first stock purchase was at age 11 \u2014 he bought Cities Service Preferred.",
    "The word 'stock' comes from the old English word for a tree trunk or block of wood.",
]


def get_daily_trivia(ticker):
    """Get a deterministic-but-daily-rotating trivia for a ticker. Returns None if no specific trivia."""
    facts = STOCK_TRIVIA.get(ticker)
    if not facts:
        return None
    today_str = datetime.date.today().isoformat()
    seed = hashlib.md5(f"{ticker}{today_str}".encode()).hexdigest()
    idx = int(seed, 16) % len(facts)
    return facts[idx]


# --- Emoji Reactions Storage ---
REACTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reactions.json")
REACTION_EMOJIS = ["\U0001f602", "\U0001f480", "\U0001f525"]  # 😂 💀 🔥
REACTIONS_SHEET_URL = "https://script.google.com/macros/s/AKfycbxc39wqHaw6kAEU74SF7sJGuGhG-un9vPDZflX8GcQMl-ZmgMPyY3n1BvI689QnGx2s/exec"


@st.cache_data(ttl=30, show_spinner=False)
def load_reactions():
    """Load reaction counts from Google Sheets."""
    try:
        resp = requests.get(REACTIONS_SHEET_URL, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    # Fallback to local file
    try:
        with open(REACTIONS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_reactions(data):
    with open(REACTIONS_FILE, "w") as f:
        json.dump(data, f)


# --- Prediction History Storage ---
PRED_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prediction_history.json")


def load_pred_history():
    try:
        with open(PRED_HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"votes": {}, "past": []}


def save_pred_history(data):
    with open(PRED_HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def record_predictions(preds, end_date_str, pred_history):
    """Save current predictions so we can check accuracy later."""
    today = datetime.date.today().isoformat()
    # Only record once per day
    existing_dates = [p.get("recorded_date") for p in pred_history.get("past", [])]
    if today in existing_dates:
        return
    for pred in preds:
        pred_history.setdefault("past", []).append({
            "recorded_date": today,
            "end_date": end_date_str,
            "title": pred["title"],
            "ticker": pred["ticker"],
            "confidence": pred.get("confidence", 50),
            "detail": pred["detail"],
            "return_at_prediction": None,  # filled in when we check later
        })
    save_pred_history(pred_history)


def check_past_predictions(pred_history, current_returns):
    """Check past predictions and compute accuracy. Only evaluates predictions older than 5 days."""
    today = datetime.date.today()
    results = []
    for pred in pred_history.get("past", []):
        # Only check predictions that are at least 5 days old
        try:
            pred_date = datetime.date.fromisoformat(pred["recorded_date"])
        except (ValueError, KeyError):
            continue
        if (today - pred_date).days < 5:
            continue

        ticker = pred["ticker"]
        if ticker in current_returns.index:
            current_ret = current_returns[ticker]
            title = pred["title"]
            if title == "Predicted MVP":
                correct = ticker == current_returns.idxmax()
                actual = f"Actual MVP: {current_returns.idxmax()} ({current_returns.max():+.2f}%)"
            elif title == "Breakout Watch":
                correct = current_ret > current_returns.median()
                actual = f"Return: {current_ret:+.2f}%"
            elif title == "Danger Zone":
                correct = current_ret < current_returns.median()
                actual = f"Return: {current_ret:+.2f}%"
            elif title == "Predicted Benchwarmer":
                correct = ticker == current_returns.idxmin()
                actual = f"Actual Bench: {current_returns.idxmin()} ({current_returns.min():+.2f}%)"
            else:
                correct = None
                actual = f"Return: {current_ret:+.2f}%"
            results.append({
                "date": pred["recorded_date"],
                "title": title,
                "ticker": ticker,
                "confidence": pred["confidence"],
                "correct": correct,
                "actual": actual,
            })
    return results


# --- System Predictions ---
def generate_predictions(returns, valid_tickers, name_map, etf_map, final_returns, dividends, start_prices, investment):
    """Generate system predictions for next week based on momentum, trends, and patterns."""
    predictions = []
    daily = returns[valid_tickers]
    daily_changes = daily.diff()
    ETF_EMOJI = {"UNCL": "\U0001f468\u200d\U0001f9b3", "ANTY": "\U0001f469\U0001f3fb", "KIDZ": "\U0001f476\U0001f3fb"}

    if len(daily) < 6:
        return predictions

    # 5-day momentum
    recent = daily.iloc[-6:]
    momentum = recent.iloc[-1] - recent.iloc[0]

    # Volatility (last 10 days or available)
    lookback = min(10, len(daily_changes) - 1)
    recent_changes = daily_changes.iloc[-lookback:]
    volatility = recent_changes.std()

    # Trend consistency: how many of last 5 days were positive moves
    last5_changes = daily_changes.iloc[-5:]
    positive_days = (last5_changes > 0).sum()

    # --- Prediction 1: Most Likely MVP Next Week ---
    # Score = momentum * 0.5 + trend_consistency * 0.3 + current_return * 0.2
    scores = {}
    for t in valid_tickers:
        mom_score = momentum[t] / max(abs(momentum).max(), 0.01)  # normalize
        trend_score = positive_days[t] / 5.0
        ret_score = final_returns[t] / max(abs(final_returns).max(), 0.01)
        scores[t] = mom_score * 0.5 + trend_score * 0.3 + ret_score * 0.2
    mvp_pred = max(scores, key=scores.get)
    etf_emoji = ETF_EMOJI.get(etf_map.get(mvp_pred, ""), "")
    predictions.append({
        "icon": "\U0001f451",
        "title": "Predicted MVP",
        "ticker": mvp_pred,
        "name": name_map.get(mvp_pred, mvp_pred),
        "detail": f"Strong momentum ({momentum[mvp_pred]:+.2f}%) + {int(positive_days[mvp_pred])}/5 green days",
        "confidence": min(95, max(40, int(scores[mvp_pred] * 100))),
        "emoji": etf_emoji,
    })

    # --- Prediction 2: Breakout Candidate (high volatility + recent uptrend) ---
    breakout_scores = {}
    for t in valid_tickers:
        if volatility[t] > volatility.median() and momentum[t] > 0:
            breakout_scores[t] = volatility[t] * momentum[t]
    if breakout_scores:
        breakout = max(breakout_scores, key=breakout_scores.get)
        etf_emoji = ETF_EMOJI.get(etf_map.get(breakout, ""), "")
        predictions.append({
            "icon": "\U0001f4a5",
            "title": "Breakout Watch",
            "ticker": breakout,
            "name": name_map.get(breakout, breakout),
            "detail": f"High volatility (\u00b1{volatility[breakout]:.2f}%) with upward momentum",
            "confidence": min(70, max(30, int(breakout_scores[breakout] * 10))),
            "emoji": etf_emoji,
        })

    # --- Prediction 3: Danger Zone (negative momentum + high volatility) ---
    danger_scores = {}
    for t in valid_tickers:
        if momentum[t] < 0:
            danger_scores[t] = abs(momentum[t]) * (1 + volatility[t])
    if danger_scores:
        danger = max(danger_scores, key=danger_scores.get)
        etf_emoji = ETF_EMOJI.get(etf_map.get(danger, ""), "")
        predictions.append({
            "icon": "\u26a0\ufe0f",
            "title": "Danger Zone",
            "ticker": danger,
            "name": name_map.get(danger, danger),
            "detail": f"Dropping {momentum[danger]:+.2f}% over 5 days with high volatility",
            "confidence": min(75, max(35, int(danger_scores[danger] * 5))),
            "emoji": etf_emoji,
        })

    # --- Prediction 4: Predicted Benchwarmer (worst momentum + negative trend) ---
    bench_scores = {}
    for t in valid_tickers:
        if momentum[t] < 0:
            bench_scores[t] = abs(momentum[t]) * (1 + (5 - positive_days[t]) / 5)
    if bench_scores:
        bench_pred = max(bench_scores, key=bench_scores.get)
        etf_emoji = ETF_EMOJI.get(etf_map.get(bench_pred, ""), "")
        predictions.append({
            "icon": "\U0001f4a9",
            "title": "Predicted Benchwarmer",
            "ticker": bench_pred,
            "name": name_map.get(bench_pred, bench_pred),
            "detail": f"Dropping {momentum[bench_pred]:+.2f}% with {int(positive_days[bench_pred])}/5 green days",
            "confidence": min(90, max(35, int(bench_scores[bench_pred] * 8))),
            "emoji": etf_emoji,
        })

    # --- Prediction 5: ETF to Watch ---
    etf_momentum = {}
    etf_counts = {}
    for t in valid_tickers:
        etf = etf_map.get(t, "")
        if etf:
            etf_momentum[etf] = etf_momentum.get(etf, 0) + momentum[t]
            etf_counts[etf] = etf_counts.get(etf, 0) + 1
    if etf_momentum:
        etf_avg_mom = {e: etf_momentum[e] / etf_counts[e] for e in etf_momentum}
        hot_etf = max(etf_avg_mom, key=etf_avg_mom.get)
        etf_emoji = ETF_EMOJI.get(hot_etf, "")
        predictions.append({
            "icon": "\U0001f4c8",
            "title": "Head of Household",
            "ticker": hot_etf,
            "name": f"{etf_emoji} {hot_etf} Division",
            "detail": f"Avg 5-day momentum: {etf_avg_mom[hot_etf]:+.2f}% across {etf_counts[hot_etf]} stocks",
            "confidence": min(65, max(30, int(abs(etf_avg_mom[hot_etf]) * 10))),
            "emoji": etf_emoji,
        })

    # --- Prediction 6: Next Throne Change ---
    # Stock most likely to dethrone current MVP
    current_mvp = final_returns.idxmax()
    challengers = {t: scores[t] for t in valid_tickers if t != current_mvp and scores.get(t, 0) > 0}
    if challengers:
        challenger = max(challengers, key=challengers.get)
        etf_emoji = ETF_EMOJI.get(etf_map.get(challenger, ""), "")
        predictions.append({
            "icon": "\U0001f93a",
            "title": "Throne Challenger",
            "ticker": challenger,
            "name": name_map.get(challenger, challenger),
            "detail": f"Most likely to dethrone {current_mvp} next week",
            "confidence": min(60, max(25, int(challengers[challenger] * 80))),
            "emoji": etf_emoji,
        })

    # --- Prediction 7: Sleeper of the Week ---
    # Stock in bottom half with strongest upward momentum
    bottom_half = final_returns.tail(len(final_returns) // 2).index
    sleeper_scores = {t: momentum[t] for t in bottom_half if t in momentum.index and momentum[t] > 0}
    if sleeper_scores:
        sleeper = max(sleeper_scores, key=sleeper_scores.get)
        etf_emoji = ETF_EMOJI.get(etf_map.get(sleeper, ""), "")
        predictions.append({
            "icon": "\U0001f634",
            "title": "Sleeper Alert",
            "ticker": sleeper,
            "name": name_map.get(sleeper, sleeper),
            "detail": f"Bottom half but gaining {sleeper_scores[sleeper]:+.2f}% momentum",
            "confidence": min(50, max(20, int(sleeper_scores[sleeper] * 10))),
            "emoji": etf_emoji,
        })

    # --- Prediction 8: Volatility Bomb ---
    if len(recent_changes) > 0:
        vol_scores = recent_changes.std()
        vol_bomb = vol_scores[valid_tickers].idxmax()
        vol_val = vol_scores[vol_bomb]
        etf_emoji = ETF_EMOJI.get(etf_map.get(vol_bomb, ""), "")
        predictions.append({
            "icon": "\U0001f4a3",
            "title": "Volatility Bomb",
            "ticker": vol_bomb,
            "name": name_map.get(vol_bomb, vol_bomb),
            "detail": f"Avg daily swing of \u00b1{vol_val:.2f}% \u2014 expect fireworks",
            "confidence": min(70, max(30, int(vol_val * 12))),
            "emoji": etf_emoji,
        })

    # Sort by confidence descending
    predictions.sort(key=lambda p: p.get("confidence", 0), reverse=True)

    return predictions


tab_dashboard, tab_feud, tab_admin = st.tabs(["Dashboard", "Family Feud", "Admin"])

with tab_dashboard:
    st.markdown("""
    <section class="hero-card">
      <div class="hero-top-row">
        <h1 class="hero-title">🧷 No Diaper Change Standings</h1>
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
        loading_msg = st.empty()
        loading_msg.markdown(
            '<div style="text-align:center;padding:2rem 1rem;color:var(--muted);">'
            '<div style="display:inline-block;width:40px;height:40px;border:4px solid rgba(14,95,58,0.15);'
            'border-top:4px solid var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin-bottom:0.8rem;"></div>'
            '<div style="font-size:1.2rem;font-weight:600;">Loading dashboard...</div>'
            '<div style="font-size:0.8rem;margin-top:0.2rem;">Fetching stock data, news & signals</div>'
            '</div>'
            '<style>@keyframes spin { 0% { transform:rotate(0deg); } 100% { transform:rotate(360deg); } }</style>',
            unsafe_allow_html=True,
        )
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

        loading_msg.empty()

        # Store data for other tabs
        st.session_state["_returns"] = returns
        st.session_state["_valid_tickers"] = valid_tickers
        st.session_state["_start_prices"] = start_prices
        st.session_state["_end_prices"] = end_prices
        st.session_state["_dividends"] = dividends

        # --- Rank tickers by total return (price + dividends) ---
        price_returns = returns[valid_tickers].iloc[-1]
        total_returns_series = pd.Series({
            t: ((INVESTMENT / start_prices[t] * end_prices[t] + INVESTMENT / start_prices[t] * dividends.get(t, 0.0)) / INVESTMENT - 1) * 100
            for t in valid_tickers
        }).sort_values(ascending=False)
        final_returns = total_returns_series
        top10_tickers = final_returns.head(10).index.tolist()
        bottom10_tickers = final_returns.tail(10).index.tolist()

        # Compute rank changes vs yesterday for arrows (total return based)
        if len(returns) >= 2:
            prev_price = returns[valid_tickers].iloc[-2]
            prev_total = pd.Series({
                t: prev_price[t] + (dividends.get(t, 0.0) / start_prices[t]) * 100
                for t in valid_tickers
            }).sort_values(ascending=False)
            prev_ranks = {ticker: rank for rank, ticker in enumerate(prev_total.index, start=1)}
        else:
            prev_ranks = {}

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
        throne = compute_throne_history(returns, valid_tickers, NAME_MAP, dividends, start_prices)
        superlatives = compute_superlatives(returns, valid_tickers, NAME_MAP, ETF_MAP, throne, dividends, start_prices)

        # --- Live status indicator with countdown ---
        now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
        live_timestamp = now_et.strftime("%I:%M:%S %p ET")
        if is_market_open():
            # Countdown to market close (4:00 PM ET)
            market_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            secs_to_close = max(0, int((market_close_et - now_et).total_seconds()))
            countdown_iframe = (
                '<iframe srcdoc="'
                '<body style=&quot;margin:0;padding:0;overflow:hidden;background:transparent;&quot;>'
                '<span id=&quot;c&quot; style=&quot;font-family:Space Grotesk,-apple-system,BlinkMacSystemFont,sans-serif;'
                f'font-size:14px;color:#aaa;&quot;></span>'
                f'<script>var e=document.getElementById(&quot;c&quot;),s={secs_to_close};'
                'setInterval(function(){s--;if(s&lt;=0){e.textContent=&quot;Market closed&quot;;}else{'
                'var h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;'
                'e.textContent=&quot;closes in &quot;+h+&quot;h &quot;+(m&lt;10?&quot;0&quot;:&quot;&quot;)+m+&quot;m &quot;+(sec&lt;10?&quot;0&quot;:&quot;&quot;)+sec+&quot;s&quot;;}},1000);'
                '</script></body>'
                '" style="border:none;width:200px;height:18px;vertical-align:text-bottom;display:inline-block;'
                'overflow:hidden;background:transparent;" scrolling="no"></iframe>'
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#19a05f;'
                f'box-shadow:0 0 6px #19a05f;"></span>'
                f'<span style="font-size:14px;color:#888;line-height:18px;">'
                f'<strong style="color:#19a05f;">LIVE</strong> &middot; {live_timestamp}'
                f' &middot; {countdown_iframe}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        else:
            # Countdown to next market open (9:30 AM ET next trading day)
            next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            if now_et >= next_open:
                next_open += datetime.timedelta(days=1)
            while next_open.weekday() >= 5 or next_open.date() in _us_market_holidays(next_open.year):
                next_open += datetime.timedelta(days=1)
            secs_to_open = max(0, int((next_open - now_et).total_seconds()))
            next_open_label = next_open.strftime("%a %b %d, %I:%M %p ET")
            countdown_iframe = (
                '<iframe srcdoc="'
                '<body style=&quot;margin:0;padding:0;overflow:hidden;background:transparent;&quot;>'
                '<span id=&quot;c&quot; style=&quot;font-family:Space Grotesk,-apple-system,BlinkMacSystemFont,sans-serif;'
                f'font-size:13px;color:#5d6f65;&quot;></span>'
                f'<script>var e=document.getElementById(&quot;c&quot;),s={secs_to_open};'
                'function u(){if(s&lt;=0){e.textContent=&quot;Market opening...&quot;;return;}'
                'var d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60),sec=s%60;'
                'var t=&quot;&quot;;if(d&gt;0)t+=d+&quot;d &quot;;t+=h+&quot;h &quot;+(m&lt;10?&quot;0&quot;:&quot;&quot;)+m+&quot;m &quot;+(sec&lt;10?&quot;0&quot;:&quot;&quot;)+sec+&quot;s&quot;;'
                'e.textContent=t;s--;}'
                'u();setInterval(u,1000);'
                '</script></body>'
                '" style="border:none;width:180px;height:18px;vertical-align:text-bottom;display:inline-block;'
                'overflow:hidden;background:transparent;" scrolling="no"></iframe>'
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--muted);"></span>'
                f'<span style="font-size:0.78rem;color:var(--muted);">'
                f'Market: <strong>CLOSED</strong> &middot; {live_timestamp}'
                f'</span></div>'
                f'<div style="font-size:0.75rem;color:var(--muted);margin:0.15rem 0 0.5rem 0;">'
                f'\U0001f514 Opens {next_open_label} &middot; {countdown_iframe}'
                f'</div>',
                unsafe_allow_html=True,
            )
        # --- Generate Trash Talk & Achievements ---
        trash_talk_lines = generate_trash_talk(throne, superlatives, final_returns, NAME_MAP, ETF_MAP, returns, valid_tickers)
        achievements = compute_achievements(returns, valid_tickers, NAME_MAP, dividends, throne, final_returns, start_prices, INVESTMENT)

        # --- Confetti for new MVP (only on the day of dethroning) ---
        mvp_is_new = False
        if throne["mvp_history"] and len(throne["mvp_history"]) >= 2:
            latest = throne["mvp_history"][0]
            if latest.get("prev_ticker"):
                dethrone_date = pd.Timestamp(latest["date"]).date()
                today = datetime.date.today()
                mvp_is_new = (dethrone_date == today)
        if mvp_is_new:
            confetti_colors = ["#19a05f", "#d7a83a", "#1f77b4", "#e45756", "#9467bd", "#ff7f0e"]
            confetti_html = ""
            for i in range(40):
                left = random.randint(0, 100)
                delay = random.random() * 2
                size = random.randint(6, 12)
                color = confetti_colors[i % len(confetti_colors)]
                shape = random.choice(["square", "circle"])
                radius = "50%" if shape == "circle" else "2px"
                confetti_html += (
                    f'<div class="confetti-piece" style="left:{left}%;animation-delay:{delay:.1f}s;'
                    f'width:{size}px;height:{size}px;background:{color};border-radius:{radius};"></div>'
                )
            st.markdown(confetti_html, unsafe_allow_html=True)

        # --- Trash Talk Ticker ---
        if trash_talk_lines:
            items_html = " ".join(
                f'<span class="ticker-item">{html_mod.escape(line)}</span>'
                for line in trash_talk_lines
            )
            # Duplicate for seamless loop
            st.markdown(
                f'<div class="trash-talk-ticker">'
                f'<div class="ticker-track">{items_html}{items_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # --- Signals & News ---
        meh = superlatives.get("middle", {})
        meh_ticker = meh.get("ticker", "")
        meh_ret = meh.get("return", 0)
        meh_rank = meh.get("rank", 0)

        # --- Portfolio Overview (hero card) ---
        _port_total_invested = INVESTMENT * len(valid_tickers)
        _port_mkt_val = sum(INVESTMENT / start_prices[t] * end_prices[t] for t in valid_tickers)
        _port_divs = sum(INVESTMENT / start_prices[t] * dividends.get(t, 0.0) for t in valid_tickers)
        _port_value = _port_mkt_val + _port_divs
        _port_pl = _port_value - _port_total_invested
        _port_ret = (_port_value / _port_total_invested - 1) * 100 if _port_total_invested else 0
        _port_pl_color = "#19a05f" if _port_pl >= 0 else "#d14a34"
        st.markdown(
            f'<div style="background:linear-gradient(135deg,{"#15803d,#166534" if _port_pl >= 0 else "#b91c1c,#991b1b"});border-radius:16px;padding:1.2rem 1.5rem;color:#fff;margin:0.5rem 0 1rem;position:relative;overflow:hidden;">'
            f'<div style="position:absolute;right:-40px;top:-40px;width:180px;height:180px;border-radius:999px;background:rgba(255,255,255,0.05);"></div>'
            f'<div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;opacity:0.8;">Portfolio Value</div>'
            f'<div style="font-size:2rem;font-weight:900;letter-spacing:-0.03em;margin:0.2rem 0 0.5rem;">${_port_value:,.2f}</div>'
            f'<div style="display:flex;gap:1.5rem;font-size:0.78rem;opacity:0.85;">'
            f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;letter-spacing:0.04em;">P/L</div>{"(" if _port_pl < 0 else ""}${abs(_port_pl):,.2f}{")" if _port_pl < 0 else ""}</div>'
            f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;letter-spacing:0.04em;">P/L %</div>{"(" if _port_ret < 0 else ""}{abs(_port_ret):.2f}%{")" if _port_ret < 0 else ""}</div>'
            f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;letter-spacing:0.04em;">Dividends</div>${_port_divs:,.2f}</div>'
            f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;letter-spacing:0.04em;">Invested</div>${_port_total_invested:,.2f} · {len(valid_tickers)} stocks × ${INVESTMENT:.0f}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:0.8rem 0 0.6rem;">'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Who\'s Hot \U0001f525 Who\'s Not \U0001f4a9 Who\'s Meh \U0001f610</span></div>',
            unsafe_allow_html=True,
        )

        # Helper to build stock card (green/cream theme)
        _ETF_EMOJI_CARD = {"UNCL": "👨‍🦳", "ANTY": "👩🏻", "KIDZ": "👶🏻"}
        def _stock_card(ticker, ret, rank_label, streak_text, streak_icon, border_color, etf_map=ETF_MAP):
            _etf = etf_map.get(ticker, "")
            _etf_em = _ETF_EMOJI_CARD.get(_etf, "")
            _sp = start_prices[ticker]
            _ep = end_prices[ticker]
            _shares = INVESTMENT / _sp
            _div = _shares * dividends.get(ticker, 0.0)
            _mv = _shares * _ep
            _fv = _mv + _div
            _pl = _fv - INVESTMENT
            _ret_color = "#19a05f" if ret >= 0 else "#d14a34"
            _pl_color = "#19a05f" if _pl >= 0 else "#d14a34"
            return (
                f'<div style="background:var(--panel-strong);border:1px solid var(--border);border-left:3px solid {border_color};'
                f'border-radius:14px;padding:1rem 1.1rem;box-shadow:0 4px 12px rgba(82,58,32,0.06);">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div>'
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.25rem;">'
                f'<span style="font-size:0.9rem;">{rank_label}</span>'
                f'<span style="font-size:1.05rem;">{_etf_colored(ticker)}</span>'
                f'<span style="font-size:0.85rem;">{_etf_em}</span>'
                f'</div>'
                f'<div style="font-size:0.75rem;color:var(--muted);">{html_mod.escape(NAME_MAP.get(ticker, ""))} · {SECTOR_MAP.get(ticker, "")}</div>'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:1.3rem;font-weight:800;color:{_ret_color};">{ret:+.2f}%</div>'
                f'<div style="font-size:0.68rem;color:var(--muted);">Total Return</div>'
                f'</div></div>'
                f'<div style="display:flex;gap:1.2rem;margin-top:0.7rem;font-size:0.76rem;">'
                f'<div><span style="color:var(--muted);">Price</span><br><span style="font-weight:600;">${_sp:.2f} → ${_ep:.2f}</span></div>'
                f'<div><span style="color:var(--muted);">P/L</span><br><span style="font-weight:600;color:{_pl_color};">{"+" if _pl >= 0 else ""}${_pl:.2f}</span></div>'
                f'<div><span style="color:var(--muted);">Value</span><br><span style="font-weight:600;">${_fv:.2f}</span></div>'
                f'</div>'
                f'<div style="margin-top:0.5rem;font-size:0.7rem;">'
                f'<span style="color:{_ret_color};">{streak_icon} {streak_text}</span>'
                f'</div></div>'
            )

        metric_cols = st.columns(3)
        metric_cols[0].markdown(
            _stock_card(best_ticker, final_returns[best_ticker], "🔥", f"{throne['mvp_streak']}-day streak", "🔥", "#19a05f"),
            unsafe_allow_html=True,
        )
        metric_cols[1].markdown(
            _stock_card(worst_ticker, final_returns[worst_ticker], "💩", f"{throne['bench_streak']}-day streak", "📉", "#d14a34"),
            unsafe_allow_html=True,
        )
        metric_cols[2].markdown(
            _stock_card(meh_ticker, meh_ret, "😐", "Closest to 0% return", "⚖️", "#a1a1aa"),
            unsafe_allow_html=True,
        )

        # --- ETF Breakdown (replaces ETF Standing) ---
        _etf_emoji_top = {"UNCL": "👨‍🦳", "ANTY": "👩🏻", "KIDZ": "👶🏻"}
        _etf_colors_top = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"}
        _etf_names_top = {"ANTY": "Auntie", "UNCL": "Uncle", "KIDZ": "Kids"}

        _etf_cards_top = ''
        for etf_code in ["ANTY", "UNCL", "KIDZ"]:
            _etf_tickers_t = [t for t in valid_tickers if ETF_MAP.get(t) == etf_code]
            if not _etf_tickers_t:
                continue
            _etf_inv = INVESTMENT * len(_etf_tickers_t)
            _etf_mk = sum(INVESTMENT / start_prices[t] * end_prices[t] for t in _etf_tickers_t)
            _etf_dv = sum(INVESTMENT / start_prices[t] * dividends.get(t, 0.0) for t in _etf_tickers_t)
            _etf_vl = _etf_mk + _etf_dv
            _etf_p = _etf_vl - _etf_inv
            _etf_ar = ((_etf_vl / _etf_inv) - 1) * 100 if _etf_inv else 0
            _etf_w = sum(1 for t in _etf_tickers_t if (INVESTMENT / start_prices[t] * end_prices[t] + INVESTMENT / start_prices[t] * dividends.get(t, 0.0)) >= INVESTMENT)
            _etf_l = len(_etf_tickers_t) - _etf_w
            _etf_wr = int(_etf_w / len(_etf_tickers_t) * 100) if _etf_tickers_t else 0
            _etf_rt = {t: ((INVESTMENT / start_prices[t] * end_prices[t] + INVESTMENT / start_prices[t] * dividends.get(t, 0.0)) / INVESTMENT - 1) * 100 for t in _etf_tickers_t}
            _etf_bt = max(_etf_rt, key=_etf_rt.get)
            _etf_wt = min(_etf_rt, key=_etf_rt.get)
            _ec = _etf_colors_top[etf_code]
            _pc = "#19a05f" if _etf_p >= 0 else "#d14a34"
            _rc = "#19a05f" if _etf_ar >= 0 else "#d14a34"
            _wp = int(_etf_w / len(_etf_tickers_t) * 100) if _etf_tickers_t else 0
            _lp = 100 - _wp

            _etf_cards_top += (
                f'<div style="background:var(--panel-strong);border:1px solid var(--border);border-radius:16px;'
                f'padding:1rem 1.2rem;border-left:3px solid {_ec};">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.7rem;">'
                f'<div><div style="font-size:1.1rem;font-weight:800;">{_etf_emoji_top[etf_code]} <span style="color:{_ec};">{etf_code}</span></div>'
                f'<div style="font-size:0.7rem;color:var(--muted);">{len(_etf_tickers_t)} stocks · Managed by {_etf_names_top[etf_code]}</div></div>'
                f'<div style="text-align:right;"><div style="font-size:1.2rem;font-weight:800;color:{_rc};">{_etf_ar:+.2f}%</div>'
                f'<div style="font-size:0.68rem;color:var(--muted);">Avg Total Return</div></div></div>'
                f'<div style="display:flex;gap:0.5rem;margin-bottom:0.6rem;">'
                f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
                f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);">Portfolio</div>'
                f'<div style="font-size:0.95rem;font-weight:700;color:{_pc};">${_etf_vl:,.2f}</div></div>'
                f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
                f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);">P/L</div>'
                f'<div style="font-size:0.95rem;font-weight:700;color:{_pc};">{"+" if _etf_p >= 0 else ""}${_etf_p:,.2f}</div></div>'
                f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
                f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);">Win Rate</div>'
                f'<div style="font-size:0.95rem;font-weight:700;">{_etf_wr}%</div></div></div>'
                f'<div style="display:flex;border-radius:6px;overflow:hidden;height:24px;">'
                f'<div style="width:{_wp}%;background:rgba(25,160,95,0.12);display:flex;align-items:center;justify-content:center;font-size:0.68rem;font-weight:700;color:#19a05f;">{_etf_w} ↑</div>'
                f'<div style="width:{_lp}%;background:rgba(209,74,52,0.1);display:flex;align-items:center;justify-content:center;font-size:0.68rem;font-weight:700;color:#d14a34;">{_etf_l} ↓</div></div>'
                f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-top:0.5rem;">'
                f'<span>Best: {_etf_colored(_etf_bt)} <b style="color:#19a05f;">{_etf_rt[_etf_bt]:+.2f}%</b></span>'
                f'<span>Worst: {_etf_colored(_etf_wt)} <b style="color:#d14a34;">{_etf_rt[_etf_wt]:+.2f}%</b></span>'
                f'</div></div>'
            )

        st.markdown(
            f'<div style="margin:0.8rem 0 0.5rem;font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;color:var(--accent);display:flex;align-items:center;gap:0.5rem;">'
            f'<span style="font-size:1.3rem;">🤜🤛</span> ETF Head-to-Head</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;margin-bottom:0.8rem;">'
            f'{_etf_cards_top}</div>',
            unsafe_allow_html=True,
        )

        # --- Superlatives Section ---
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">💪</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Bragging Rights</span></div>',
            unsafe_allow_html=True,
        )
        sup = superlatives

        def _find_badge(name):
            for b in achievements:
                if b["name"] == name:
                    return b
            return None

        # Fetch earnings data early for Beat Street badges
        earnings_data = fetch_earnings(tuple(valid_tickers))

        # Build badges as opposite pairs
        badges_data = []  # (icon, name, holder, desc)

        # Pair 1: Diamond Hands vs Bag Holder (with date ranges)
        diamond = _find_badge("Diamond Hands")
        bottom = _find_badge("Bottom Feeder")
        # Build total-return daily data for MVP/bench date lookups
        _daily_tr = returns[valid_tickers].copy()
        for _t in valid_tickers:
            _div_ret = (dividends.get(_t, 0.0) / start_prices[_t]) * 100 if start_prices[_t] else 0
            _daily_tr[_t] = _daily_tr[_t] + _div_ret
        if diamond and diamond["unlocked"]:
            # Find first and last date this stock was MVP
            dh_ticker = diamond["holder"].split(" (")[0]
            if len(returns) > 1:
                daily_mvp = _daily_tr.iloc[1:].idxmax(axis=1)
                dh_dates = daily_mvp[daily_mvp == dh_ticker].index
                if len(dh_dates) > 0:
                    dh_first = dh_dates[0].strftime("%b %d")
                    dh_last = dh_dates[-1].strftime("%b %d")
                    badges_data.append(("\U0001f48e", "Diamond Hands", f'{diamond["holder"]}, {dh_first} \u2013 {dh_last}', "Most days as MVP"))
                else:
                    badges_data.append(("\U0001f48e", "Diamond Hands", diamond["holder"], "Most days as MVP"))
            else:
                badges_data.append(("\U0001f48e", "Diamond Hands", diamond["holder"], "Most days as MVP"))
        if bottom and bottom["unlocked"]:
            bh_ticker = bottom["holder"].split(" (")[0]
            if len(returns) > 1:
                daily_bench = _daily_tr.iloc[1:].idxmin(axis=1)
                bh_dates = daily_bench[daily_bench == bh_ticker].index
                if len(bh_dates) > 0:
                    bh_first = bh_dates[0].strftime("%b %d")
                    bh_last = bh_dates[-1].strftime("%b %d")
                    badges_data.append(("\U0001f9fb", "Bag Holder", f'{bottom["holder"]}, {bh_first} \u2013 {bh_last}', "Most days as benchwarmer"))
                else:
                    badges_data.append(("\U0001f9fb", "Bag Holder", bottom["holder"], "Most days as benchwarmer"))
            else:
                badges_data.append(("\U0001f9fb", "Bag Holder", bottom["holder"], "Most days as benchwarmer"))

        # Pair 2: Moonshot vs Crash Landing
        bd = sup.get("best_day")
        wd = sup.get("worst_day")
        if bd:
            bd_date = bd["date"].strftime("%b %d") if hasattr(bd["date"], "strftime") else str(bd["date"])
            badges_data.append(("\U0001f315", "Moonshot", f'{bd["ticker"]} ({bd["change"]:+.2f}% on {bd_date})', "Biggest single-day gain"))
        if wd:
            wd_date = wd["date"].strftime("%b %d") if hasattr(wd["date"], "strftime") else str(wd["date"])
            badges_data.append(("\U0001f4a5", "Crash Landing", f'{wd["ticker"]} ({wd["change"]:+.2f}% on {wd_date})', "Biggest single-day loss"))

        # Pair 3: Rollercoaster vs Steady Eddie
        coaster = _find_badge("Rollercoaster")
        steady = _find_badge("Steady Eddie")
        if coaster:
            badges_data.append(("\U0001f3a2", "Rollercoaster", coaster["holder"], "Most volatile stock"))
        if steady:
            badges_data.append(("\U0001f9d8", "Steady Eddie", steady["holder"], "Least volatile stock"))

        # Pair 4: Comeback Kid vs Dead Weight
        cb = sup["comeback"]
        if cb["ticker"]:
            badges_data.append(("\U0001f9d7", "Comeback Kid", f'{cb["ticker"]} ({cb["low"]:+.2f}% \u2192 {cb["final"]:+.2f}%)', "Biggest recovery from a low"))
        # Dead Weight: stock that went negative and stayed there (worst current return)
        negative_tickers = [t for t in valid_tickers if final_returns[t] < 0]
        if negative_tickers:
            dead_weight = min(negative_tickers, key=lambda t: final_returns[t])
            dw_low = float(_daily_tr[dead_weight].min())
            badges_data.append(("\U0001faa8", "Dead Weight", f'{dead_weight} ({dw_low:+.2f}% \u2192 {final_returns[dead_weight]:+.2f}%)', "Went down and stayed down"))

        # Pair 5: Dark Horse vs Fallen Angel
        horse = _find_badge("Dark Horse")
        fa = sup["fallen"]
        if horse and horse["unlocked"]:
            badges_data.append(("\U0001f40e", "Dark Horse", horse["holder"], "Bottom half \u2192 climbed highest"))
        if fa["ticker"]:
            badges_data.append(("\U0001f607", "Fallen Angel", f'{fa["ticker"]} (#{fa["start_rank"]}\u2192#{fa["end_rank"]})', "Top half \u2192 dropped the most"))

        # Pair 6: The Terminator vs Middle Child
        term = _find_badge("The Terminator")
        mc = sup["middle"]
        if term:
            badges_data.append(("\U0001f916", "The Terminator", term["holder"], "Took MVP throne most times"))
        if mc["ticker"]:
            badges_data.append(("\U0001fae5", "Middle Child", f'{mc["ticker"]} ({mc["return"]:+.2f}%)', "Closest to 0%"))

        # Pair 7: Rivalry vs ETF War
        rv = sup["rivalry"]
        ew = sup["etf_war"]
        if rv["ticker1"]:
            badges_data.append(("\u2694\ufe0f", "Rivalry", f'{rv["ticker1"]} vs {rv["ticker2"]} ({rv["swaps"]}x)', "Most throne swaps"))
        if ew["etf"]:
            etf_emoji = ETF_EMOJI.get(ew["etf"], "")
            badges_data.append(("\u26a1", "ETF War", f'{etf_emoji} {ew["etf"]} ({ew["streak"]}d)', "Longest daily win streak"))

        # Pair 8: Dividend King vs All Talk
        divking = _find_badge("Dividend King")
        if divking and divking["unlocked"]:
            badges_data.append(("\U0001f4b0", "Dividend King", divking["holder"], "Most dividend income"))
        # All Talk: best return with $0 dividends
        zero_div_tickers = [t for t in valid_tickers if dividends.get(t, 0.0) == 0]
        if zero_div_tickers:
            all_talk = max(zero_div_tickers, key=lambda t: final_returns[t])
            badges_data.append(("\U0001f4ac", "All Talk", f'{all_talk} ({final_returns[all_talk]:+.2f}%, $0 divs)', "Best return, zero dividends"))

        # Pair 9: Beat Street vs Street Loser (EPS surprise)
        _bs_best_b = None
        _bs_worst_b = None
        _bs_best_surp_b = -999
        _bs_worst_surp_b = 999
        for t in valid_tickers:
            _earn = earnings_data.get(t, {})
            _rep = _earn.get("last_eps_reported")
            _est_e = _earn.get("last_eps_estimate")
            if _rep is not None and _est_e is not None and _est_e != 0:
                _surp = ((_rep - _est_e) / abs(_est_e)) * 100
                if _surp > _bs_best_surp_b:
                    _bs_best_surp_b = _surp
                    _bs_best_b = (t, _rep, _est_e, _surp)
                if _surp < _bs_worst_surp_b:
                    _bs_worst_surp_b = _surp
                    _bs_worst_b = (t, _rep, _est_e, _surp)
        if _bs_best_b and _bs_best_surp_b > 0:
            badges_data.append(("🐂", "Beat Street", f'{_bs_best_b[0]} (${_bs_best_b[1]:.2f} vs est ${_bs_best_b[2]:.2f}, +{_bs_best_surp_b:.1f}%)', "Biggest EPS beat"))
        if _bs_worst_b and _bs_worst_surp_b < 0:
            badges_data.append(("🐻", "Street Loser", f'{_bs_worst_b[0]} (${_bs_worst_b[1]:.2f} vs est ${_bs_worst_b[2]:.2f}, {_bs_worst_surp_b:.1f}%)', "Biggest EPS miss"))

        # Multi-Award bar: find stocks that appear in multiple badges
        ticker_badges = {}
        for icon, name, holder, desc in badges_data:
            # Extract tickers from holder string
            tickers_in_badge = []
            base = holder.split(" (")[0] if holder else ""
            if " vs " in base:
                # Rivalry-style: "ARM vs SNDK"
                for part in base.split(" vs "):
                    part = part.strip()
                    if part and part not in ("Most", "Biggest", "Took", "Bottom", "Top", "Closest", "Went", "Best", "Longest"):
                        tickers_in_badge.append(part)
            else:
                t = base.split(" ")[0] if base else ""
                if t and t not in ("Most", "Biggest", "Took", "Bottom", "Top", "Closest", "Went", "Best", "Longest"):
                    tickers_in_badge.append(t)
            for t in tickers_in_badge:
                ticker_badges.setdefault(t, []).append((icon, name))
        multi_badge_tickers = {t: badges for t, badges in ticker_badges.items() if len(badges) > 1}

        # ETF award count
        _etf_award_counts = {"ANTY": 0, "UNCL": 0, "KIDZ": 0}
        for icon, name, holder, desc in badges_data:
            base = holder.split(" (")[0] if holder else ""
            tickers_in = []
            if " vs " in base:
                tickers_in = [p.strip() for p in base.split(" vs ")]
            else:
                t = base.split(" ")[0] if base else ""
                if t:
                    tickers_in = [t]
            for t in tickers_in:
                etf = ETF_MAP.get(t, "")
                if etf in _etf_award_counts:
                    _etf_award_counts[etf] += 1
        _etf_emoji_aw = {"ANTY": "\U0001f469\U0001f3fb", "UNCL": "\U0001f468\u200d\U0001f9b3", "KIDZ": "\U0001f476\U0001f3fb"}
        _etf_bar_parts = []
        for code in ["ANTY", "UNCL", "KIDZ"]:
            c = _etf_award_counts[code]
            clr = _ETF_CLR[code]
            _etf_bar_parts.append(
                f'<span style="display:inline-flex;align-items:center;gap:0.3rem;">'
                f'{_etf_emoji_aw[code]} <span style="color:{clr};font-weight:700;">{code}</span> '
                f'<span style="font-weight:600;">{c}</span></span>'
            )

        _combined_html = '<div class="sup-multi-bar" style="flex-direction:column;align-items:flex-start;gap:0.4rem;">'
        if multi_badge_tickers:
            _combined_html += '<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">'
            _combined_html += '<span class="multi-label">🎯 Multi-Award:</span>'
            for t, badge_list in sorted(multi_badge_tickers.items(), key=lambda x: -len(x[1])):
                badge_icons = "".join(f'{i}' for i, _ in badge_list)
                _combined_html += f'<span class="sup-multi-stock">{_etf_colored(t)} {badge_icons}</span>'
            _combined_html += '</div>'
        _combined_html += (
            f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">'
            f'<span class="multi-label">🎗️ Awards by ETF:</span>'
            f'{"".join(_etf_bar_parts)}'
            f'</div></div>'
        )
        st.markdown(_combined_html, unsafe_allow_html=True)

        # Render as a two-column paired table
        pairs = []
        for i in range(0, len(badges_data), 2):
            left = badges_data[i]
            right = badges_data[i + 1] if i + 1 < len(badges_data) else None
            pairs.append((left, right))

        _BADGE_TONES = {
            "Diamond Hands": "green", "Moonshot": "green", "Dark Horse": "green",
            "Comeback Kid": "green", "Steady Eddie": "green", "The Terminator": "green",
            "Dividend King": "green", "Beat Street": "green",
            "Bag Holder": "red", "Crash Landing": "red", "Dead Weight": "red",
            "Fallen Angel": "red", "All Talk": "red", "Street Loser": "red",
            "Rollercoaster": "amber", "Middle Child": "amber", "Rivalry": "amber",
            "ETF War": "amber",
        }
        _TONE_STYLES = {
            "green": ("rgba(25,160,95,0.12)", "rgba(25,160,95,0.05)", "rgba(25,160,95,0.10)"),
            "red":   ("rgba(209,74,52,0.12)", "rgba(209,74,52,0.05)", "rgba(209,74,52,0.10)"),
            "amber": ("rgba(215,168,58,0.15)", "rgba(215,168,58,0.06)", "rgba(215,168,58,0.12)"),
        }

        def _color_holder_tickers(holder):
            """Escape holder string and color any known tickers by ETF, and ETF codes themselves."""
            escaped = html_mod.escape(holder)
            for t in sorted(ETF_MAP.keys(), key=len, reverse=True):
                clr = _ETF_CLR.get(ETF_MAP.get(t, ""), "")
                if clr and t in escaped:
                    escaped = escaped.replace(t, f'<span style="color:{clr};font-weight:700;">{t}</span>')
            for etf_code, clr in _ETF_CLR.items():
                if etf_code in escaped and f';">{etf_code}</span>' not in escaped:
                    escaped = escaped.replace(etf_code, f'<span style="color:{clr};font-weight:700;">{etf_code}</span>')
            return escaped

        def _badge_cell(icon, name, holder, desc):
            tone = _BADGE_TONES.get(name, "green")
            bg_from, bg_to, shadow_color = _TONE_STYLES[tone]
            holder_html = _color_holder_tickers(holder)
            return (
                f'<td style="padding:0.85rem 1.2rem;vertical-align:middle;transition:background 0.15s;" '
                f'onmouseover="this.style.background=\'rgba(14,95,58,0.06)\'" '
                f'onmouseout="this.style.background=\'transparent\'">'
                f'<div style="display:flex;align-items:center;gap:0.9rem;">'
                f'<div style="width:42px;height:42px;border-radius:12px;'
                f'background:linear-gradient(135deg,{bg_from},{bg_to});'
                f'display:flex;align-items:center;justify-content:center;flex-shrink:0;'
                f'box-shadow:0 2px 6px {shadow_color};">'
                f'<span style="font-size:1.5rem;line-height:1;">{icon}</span></div>'
                f'<div>'
                f'<div style="font-weight:800;font-size:0.82rem;color:#102018;letter-spacing:0.02em;">{html_mod.escape(name)}</div>'
                f'<div style="font-size:0.78rem;color:#2d4a3a;margin-top:0.1rem;">{holder_html}</div>'
                f'<div style="font-size:0.62rem;color:#5d6f65;opacity:0.8;margin-top:0.1rem;">{html_mod.escape(desc)}</div>'
                f'</div></div></td>'
            )

        table_html = (
            '<table style="width:100%;border-collapse:separate;border-spacing:0;'
            'border-radius:18px;overflow:hidden;'
            'background:linear-gradient(180deg,rgba(251,253,250,0.98) 0%,rgba(237,245,238,0.95) 100%);'
            'border:1px solid rgba(18,51,36,0.12);box-shadow:0 8px 32px rgba(14,95,58,0.06);">'
        )
        for pi, (left, right) in enumerate(pairs):
            is_last = pi == len(pairs) - 1
            table_html += '<tr>'
            table_html += _badge_cell(*left)
            if right:
                table_html += f'<td style="width:1px;padding:0;"><div style="width:1px;height:100%;background:rgba(18,51,36,0.08);"></div></td>'
                table_html += _badge_cell(*right)
            table_html += '</tr>'
            if not is_last:
                table_html += f'<tr><td colspan="3" style="padding:0;"><div style="height:1px;background:rgba(18,51,36,0.06);"></div></td></tr>'
        table_html += '</table>'
        st.markdown(f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">{table_html}</div>', unsafe_allow_html=True)

        # --- Market Pulse ---
        stock_signals = compute_signals(valid_tickers, start_date, end_date)

        # Compute signal counts for the bar
        buy_count = sum(1 for s in stock_signals.values() if s["signal"] == "BUY") if stock_signals else 0
        sell_count = sum(1 for s in stock_signals.values() if s["signal"] == "SELL") if stock_signals else 0
        hold_count = sum(1 for s in stock_signals.values() if s["signal"] == "HOLD") if stock_signals else 0
        total_signals = buy_count + sell_count + hold_count
        buy_pct = int(buy_count / total_signals * 100) if total_signals else 0
        sell_pct = int(sell_count / total_signals * 100) if total_signals else 0
        hold_pct = 100 - buy_pct - sell_pct

        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">\U0001f4ca</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Market Pulse</span></div>',
            unsafe_allow_html=True,
        )
        green_count = int((final_returns > 0).sum())
        red_count = int((final_returns <= 0).sum())
        total_stocks = len(final_returns)
        green_pct = int(green_count / total_stocks * 100) if total_stocks else 0
        avg_return = final_returns.mean()

        # Mood
        if green_pct >= 70:
            mood_emoji, mood_text = "\U0001f929", "Rally Mode"
        elif green_pct >= 55:
            mood_emoji, mood_text = "\U0001f60e", "Feeling Good"
        elif green_pct >= 45:
            mood_emoji, mood_text = "\U0001f610", "Mixed Signals"
        elif green_pct >= 30:
            mood_emoji, mood_text = "\U0001f62c", "Getting Rough"
        else:
            mood_emoji, mood_text = "\U0001f4a9", "Total Carnage"

        trading_days = len(returns) - 1 if len(returns) > 1 else 0

        signal_bar_html = ""
        if stock_signals:
            signal_bar_html = (
                f'<div style="display:flex;border-radius:10px;overflow:hidden;height:34px;margin-top:0.6rem;">'
                f'<div style="width:{buy_pct}%;background:#19a05f;display:flex;align-items:center;justify-content:center;'
                f'font-size:clamp(0.6rem,2vw,0.75rem);font-weight:700;color:#fff;padding:0 0.3rem;">{buy_count} BUY</div>'
                f'<div style="width:{hold_pct}%;background:#d7a83a;display:flex;align-items:center;justify-content:center;'
                f'font-size:clamp(0.6rem,2vw,0.75rem);font-weight:700;color:#fff;padding:0 0.3rem;">{hold_count} HOLD</div>'
                f'<div style="width:{sell_pct}%;background:#d14a34;display:flex;align-items:center;justify-content:center;'
                f'font-size:clamp(0.6rem,2vw,0.75rem);font-weight:700;color:#fff;padding:0 0.3rem;">{sell_count} SELL</div>'
                f'</div>'
            )

        st.markdown(
            f'<div class="recap-card" style="padding:1.2rem 1.4rem;text-align:center;">'
            f'<div style="font-size:2.8rem;line-height:1;margin-bottom:0.3rem;">{mood_emoji}</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:#f4f0e3;margin-bottom:0.15rem;">{mood_text}</div>'
            f'<div style="font-size:0.78rem;opacity:0.65;margin-bottom:0.05rem;">'
            f'{start_date.strftime("%b %d")} \u2013 {end_date.strftime("%b %d, %Y")}</div>'
            f'<div style="font-size:0.78rem;opacity:0.65;margin-bottom:0.8rem;">'
            f'{trading_days} trading days &middot; Avg total return: {avg_return:+.2f}%</div>'
            f'<div style="display:flex;border-radius:10px;overflow:hidden;height:34px;">'
            f'<div style="width:{green_pct}%;background:#19a05f;display:flex;align-items:center;justify-content:center;'
            f'font-size:clamp(0.6rem,2vw,0.75rem);font-weight:700;color:#fff;padding:0 0.4rem;">'
            f'{green_count} up ({green_pct}%)</div>'
            f'<div style="width:{100-green_pct}%;background:#d14a34;display:flex;align-items:center;justify-content:center;'
            f'font-size:clamp(0.6rem,2vw,0.75rem);font-weight:700;color:#fff;padding:0 0.4rem;">'
            f'{red_count} down ({100-green_pct}%)</div>'
            f'</div>'
            f'{signal_bar_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # earnings_data already fetched above for bragging rights

        # --- Shots Fired ---
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">\U0001f4a5</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Shots Fired</span>'
            '<span style="font-size:0.75rem;color:gray;font-weight:400;letter-spacing:normal;text-transform:none;'
            'margin-left:0.5rem;">reactions have a 200s cooldown</span></div>',
            unsafe_allow_html=True,
        )

        def _generate_roasts(final_rets, name_map, throne, superlatives, returns_df, valid_tickers):
            roasts = []
            sorted_rets = final_rets.sort_values(ascending=False)
            total = len(sorted_rets)
            mvp = sorted_rets.index[0]
            mvp_ret = sorted_rets.iloc[0]
            bench = sorted_rets.index[-1]
            bench_ret = sorted_rets.iloc[-1]

            mvp_roasts = [
                f"{_etf_colored(mvp)} is up {mvp_ret:+.2f}% and won't shut up about it. We get it, you're winning.",
                f"{_etf_colored(mvp)} at {mvp_ret:+.2f}%? Enjoy it while it lasts. The market humbles everyone.",
                f"{_etf_colored(mvp)} is carrying this entire draft at {mvp_ret:+.2f}%. The rest of you are just background noise.",
            ]
            bench_roasts = [
                f"{_etf_colored(bench)} at {bench_ret:+.2f}%. If this were a group project, you'd be the one who didn't show up.",
                f"{_etf_colored(bench)} is at {bench_ret:+.2f}%. Even a random number generator would do better.",
                f"{_etf_colored(bench)} at {bench_ret:+.2f}%. At this rate, you could lose money slower by literally burning it.",
            ]
            day_seed = int(hashlib.md5(datetime.date.today().isoformat().encode()).hexdigest(), 16)
            roasts.append(f"\U0001f451 {mvp_roasts[day_seed % len(mvp_roasts)]}")
            roasts.append(f"\U0001f4a9 {bench_roasts[(day_seed + 1) % len(bench_roasts)]}")

            if superlatives.get("best_day") and superlatives.get("worst_day"):
                bd = superlatives["best_day"]
                wd = superlatives["worst_day"]
                if bd["ticker"] == wd["ticker"]:
                    roasts.append(f"\U0001f3a2 {_etf_colored(bd['ticker'])} gained {bd['change']:+.2f}% and lost {wd['change']:+.2f}% in single days. This stock needs therapy.")
                else:
                    roasts.append(f"\U0001f3a2 {_etf_colored(wd['ticker'])} nosedived {wd['change']:+.2f}% in one day. That's not investing, that's bungee jumping without the cord.")

            mc = superlatives.get("middle")
            if mc and mc["ticker"]:
                roasts.append(f"\U0001fae5 {_etf_colored(mc['ticker'])} returned {mc['return']:+.2f}%. Absolute NPC energy. Doing nothing and hoping nobody notices.")

            cb = superlatives.get("comeback")
            if cb and cb["ticker"] and cb["low"] < -3:
                roasts.append(f"\U0001f9d7 {_etf_colored(cb['ticker'])} dropped to {cb['low']:+.2f}% and somehow clawed back. Plot armor is real.")

            bottom3 = sorted_rets.tail(3)
            tickers_str = ", ".join(_etf_colored(t) for t in bottom3.index)
            bottom3_roasts = [
                f"\U0001f6bd {tickers_str} \u2014 the bottom 3. Combined return: {bottom3.sum():+.2f}%. A dumpster fire would've outperformed.",
                f"\U0001f6bd {tickers_str} sitting at the bottom with {bottom3.sum():+.2f}% combined. If losing money was a sport, you'd be olympians.",
            ]
            roasts.append(bottom3_roasts[(day_seed + 2) % len(bottom3_roasts)])

            mvp_changes = len([e for e in throne["mvp_history"] if e.get("prev_ticker")])
            if mvp_changes >= 4:
                roasts.append(f"\U0001f3b0 The MVP throne changed hands {mvp_changes} times. This draft has more drama than a reality TV show.")
            elif mvp_changes <= 1:
                roasts.append(f"\U0001f3b0 <b>{html_mod.escape(mvp)}</b> has basically owned the throne the whole time. Everyone else? Participation trophies.")

            red_count = int((final_rets <= 0).sum())
            if red_count > total * 0.6:
                roasts.append(f"\U0001f534 {red_count} out of {total} stocks are in the red. This isn't a portfolio, it's a crime scene.")
            elif red_count < total * 0.3:
                roasts.append(f"\U0001f7e2 Only {red_count} out of {total} stocks are in the red. Don't get comfortable \u2014 the market is just loading the next prank.")

            return roasts

        roasts = _generate_roasts(final_returns, NAME_MAP, throne, superlatives, returns, valid_tickers)

        # Load server-side reaction counts
        all_reactions = load_reactions()

        # Compute next roast drop date
        now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
        next_drop = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et >= next_drop:
            next_drop += datetime.timedelta(days=1)
        while next_drop.weekday() >= 5 or next_drop.date() in _us_market_holidays(next_drop.year):
            next_drop += datetime.timedelta(days=1)
        next_drop_str = next_drop.strftime('%a %b %d')

        # Build roast HTML as chat bubbles — multiple bots firing shots
        BOT_PERSONAS = [
            ("\U0001f916", "linear-gradient(135deg, #0e5f3a, #19a05f)", "GreenMachine"),   # green robot
            ("\U0001f608", "linear-gradient(135deg, #6b21a8, #a855f7)", "DiabloAI"),   # purple devil
            ("\U0001f47e", "linear-gradient(135deg, #b91c1c, #ef4444)", "ChadGPT"),    # red alien
            ("\U0001f9e0", "linear-gradient(135deg, #0369a1, #38bdf8)", "BrainRot"),   # blue brain
            ("\U0001f480", "linear-gradient(135deg, #78350f, #d97706)", "DeadCat"),    # amber skull
        ]
        roast_items_html = ""
        for idx, roast in enumerate(roasts):
            roast_key = f"roast_{idx}"
            roast_counts = all_reactions.get(roast_key, {})
            btns = ""
            for emoji in REACTION_EMOJIS:
                count = roast_counts.get(emoji, 0)
                count_str = f'<span class="rcount">{count}</span>' if count > 0 else ""
                btns += (
                    f'<span class="roast-react-btn" data-roast="{roast_key}" data-emoji="{emoji}" '
                    f'onclick="toggleReact(this)">{emoji}{count_str}</span>'
                )
            bot_emoji, bot_gradient, bot_name = BOT_PERSONAS[idx % len(BOT_PERSONAS)]
            side = "right" if idx % 2 == 1 else "left"
            roast_items_html += (
                f'<div class="chat-row chat-{side}">'
                f'<div class="chat-avatar" style="background:{bot_gradient};">{bot_emoji}</div>'
                f'<div class="chat-content">'
                f'<div class="chat-name">{bot_name}</div>'
                f'<div class="chat-bubble">'
                f'<div class="chat-text">{roast}</div>'
                f'<div class="roast-reactions">{btns}</div>'
                f'</div>'
                f'</div></div>'
            )

        roast_component_html = f"""
        <html><head><style>
        html, body {{ margin:0; padding:0; background:transparent !important; overflow:hidden; }}
        .chat-container {{
            display: flex; flex-direction: column; gap: 0.6rem;
            font-family:'Space Grotesk',sans-serif;
        }}
        .chat-row {{
            display: flex; align-items: flex-start; gap: 0.6rem;
        }}
        .chat-row.chat-right {{
            flex-direction: row-reverse;
        }}
        .chat-avatar {{
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 1rem; flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.18);
        }}
        .chat-name {{
            font-size: 0.68rem; font-weight: 700; letter-spacing: 0.03em;
            color: #5d6f65; margin-bottom: 0.15rem;
            text-transform: uppercase;
        }}
        .chat-row.chat-right .chat-name {{
            text-align: right;
        }}
        .chat-content {{ max-width: calc(100% - 48px); }}
        .chat-bubble {{
            background: rgba(251,253,250,0.96);
            border: 1px solid rgba(18,51,36,0.12);
            border-radius: 0 18px 18px 18px;
            padding: 0.7rem 1rem;
            box-shadow: 0 4px 12px rgba(16,42,32,0.06);
        }}
        .chat-row.chat-right .chat-bubble {{
            border-radius: 18px 0 18px 18px;
        }}
        .chat-row.chat-right .roast-reactions {{
            justify-content: flex-end;
        }}
        .chat-text {{
            font-size: 0.85rem; line-height: 1.5;
        }}
        .roast-reactions {{
            display: flex; gap: 0.3rem; margin-top: 0.4rem; flex-wrap: wrap;
        }}
        .roast-react-btn {{
            display: inline-flex; align-items: center; gap: 0.2rem;
            padding: 0.15rem 0.45rem; border: 1px solid rgba(18,51,36,0.12);
            border-radius: 999px; background: white; font-size: 0.78rem;
            cursor: pointer; transition: all 0.15s ease; user-select: none;
            -webkit-tap-highlight-color: transparent;
        }}
        .roast-react-btn:hover, .roast-react-btn:active {{
            border-color: #0e5f3a; background: rgba(14,95,58,0.06); transform: scale(1.08);
        }}
        .roast-react-btn.active {{
            border-color: #0e5f3a; background: rgba(14,95,58,0.1);
        }}
        .roast-react-btn .rcount {{
            font-weight: 700; color: #102018; font-size: 0.75rem;
        }}
        @media (max-width: 768px) {{
            .chat-avatar {{ width: 30px; height: 30px; font-size: 0.85rem; }}
            .chat-content {{ max-width: calc(100% - 42px); }}
            .roast-react-btn {{ padding: 0.25rem 0.55rem; font-size: 0.85rem; }}
        }}
        </style></head>
        <body>
        <div class="chat-container">
            {roast_items_html}
            <div style="font-size:0.72rem;color:#5d6f65;margin-top:0.3rem;padding-left:0;text-align:left;">
                \U0001f4a5 Roasts refresh daily \u00b7 Fresh burns incoming \u00b7 Next drop: {next_drop_str} after market close
            </div>
        </div>
        <script>
        var userReacts = JSON.parse(localStorage.getItem('roast_reacts') || '{{}}'  );
        var serverCounts = JSON.parse(localStorage.getItem('roast_server_counts') || '{{}}');

        document.querySelectorAll('.roast-react-btn').forEach(function(btn) {{
            var key = btn.dataset.roast + '_' + btn.dataset.emoji;
            if (userReacts[key]) {{
                btn.classList.add('active');
                var countEl = btn.querySelector('.rcount');
                if (!countEl) {{
                    btn.innerHTML = btn.dataset.emoji + '<span class="rcount">1</span>';
                }}
            }}
        }});

        function toggleReact(btn) {{
            var roastKey = btn.dataset.roast;
            var emoji = btn.dataset.emoji;
            var key = roastKey + '_' + emoji;
            var countEl = btn.querySelector('.rcount');
            var currentCount = countEl ? parseInt(countEl.textContent) : 0;

            if (btn.classList.contains('active')) {{
                btn.classList.remove('active');
                currentCount = Math.max(0, currentCount - 1);
                delete userReacts[key];
            }} else {{
                btn.classList.add('active');
                currentCount += 1;
                userReacts[key] = true;
            }}

            localStorage.setItem('roast_reacts', JSON.stringify(userReacts));

            if (!serverCounts[roastKey]) serverCounts[roastKey] = {{}};
            serverCounts[roastKey][emoji] = currentCount;
            localStorage.setItem('roast_server_counts', JSON.stringify(serverCounts));

            if (currentCount > 0) {{
                if (countEl) {{
                    countEl.textContent = currentCount;
                }} else {{
                    btn.innerHTML = emoji + '<span class="rcount">' + currentCount + '</span>';
                }}
            }} else {{
                btn.innerHTML = emoji;
            }}

            var sheetUrl = '{REACTIONS_SHEET_URL}';
            var delta = btn.classList.contains('active') ? 1 : -1;
            fetch(sheetUrl + '?roast=' + encodeURIComponent(roastKey) + '&emoji=' + encodeURIComponent(emoji) + '&delta=' + delta)
              .catch(function() {{}});

            btn.style.transform = 'scale(1.25)';
            setTimeout(function() {{ btn.style.transform = ''; }}, 150);
        }}

        // Resize iframe and all Streamlit parent wrappers to exact content height
        function fitHeight() {{
            var h = document.querySelector('.chat-container').scrollHeight;
            var frame = window.frameElement;
            if (frame) {{
                frame.style.height = h + 'px';
                // Walk up and resize all Streamlit wrapper divs up to 5 levels
                var el = frame.parentElement;
                for (var i = 0; i < 5 && el; i++) {{
                    el.style.height = h + 'px';
                    el = el.parentElement;
                }}
            }}
        }}
        fitHeight();
        window.addEventListener('load', fitHeight);
        setTimeout(fitHeight, 50);
        setTimeout(fitHeight, 200);
        setTimeout(fitHeight, 600);
        window.addEventListener('resize', fitHeight);

        </script>
        </body></html>
        """

        components.html(roast_component_html, height=len(roasts) * 100, scrolling=False)


        # --- Weekly Report ---
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">\U0001f4cb</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Weekly Report</span></div>',
            unsafe_allow_html=True,
        )
        green_count_wr = int((final_returns > 0).sum())
        red_count_wr = int((final_returns <= 0).sum())
        avg_ret_wr = final_returns.mean()
        trading_days_wr = len(returns) - 1 if len(returns) > 1 else 0
        top5_wr = final_returns.head(5)
        bot5_wr = final_returns.tail(5)
        mvp_changes_wr = len([e for e in throne["mvp_history"] if e.get("prev_ticker")])
        pw_wr = superlatives.get("power", {})

        wr_html = (
            '<div style="background:linear-gradient(145deg,#0d2f20 0%,#1a5c3a 40%,#0d2f20 100%);'
            'border-radius:24px;padding:1.4rem 1.5rem;color:#f4f0e3;position:relative;overflow:hidden;">'
            '<div style="position:absolute;top:-30px;right:-30px;width:120px;height:120px;'
            'border-radius:50%;background:rgba(215,168,58,0.15);"></div>'
            '<div style="text-align:center;">'
            '<div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.12em;'
            'color:rgba(215,168,58,0.9);font-weight:700;">Stock Market Fantasy Draft</div>'
            f'<div style="font-size:1.3rem;font-weight:800;margin:0.3rem 0 0.1rem;">Weekly Report</div>'
            f'<div style="font-size:0.75rem;opacity:0.6;">'
            f'{start_date.strftime("%b %d")} \u2013 {end_date.strftime("%b %d, %Y")} &middot; {trading_days_wr} trading days</div>'
            '</div>'
            '<div style="height:1px;background:rgba(255,255,255,0.15);margin:0.7rem 0;"></div>'
            '<div style="display:flex;gap:1rem;margin-bottom:0.7rem;">'
            f'<div style="flex:1;background:rgba(25,160,95,0.12);border-radius:12px;padding:0.6rem 0.8rem;text-align:center;">'
            f'<div style="font-size:0.6rem;opacity:0.6;text-transform:uppercase;">\U0001f451 MVP</div>'
            f'<div style="font-size:1.2rem;font-weight:800;color:#4ade80;">{html_mod.escape(best_ticker)}</div>'
            f'<div style="font-size:0.78rem;opacity:0.8;">{html_mod.escape(NAME_MAP[best_ticker])}</div>'
            f'<div style="font-size:0.9rem;font-weight:700;color:#4ade80;margin-top:0.2rem;">{final_returns[best_ticker]:+.2f}%</div>'
            f'<div style="font-size:0.68rem;opacity:0.6;">{throne["mvp_streak"]}d streak</div>'
            f'</div>'
            f'<div style="flex:1;background:rgba(209,74,52,0.12);border-radius:12px;padding:0.6rem 0.8rem;text-align:center;">'
            f'<div style="font-size:0.6rem;opacity:0.6;text-transform:uppercase;">\U0001f4a9 Benchwarmer</div>'
            f'<div style="font-size:1.2rem;font-weight:800;color:#f87171;">{html_mod.escape(worst_ticker)}</div>'
            f'<div style="font-size:0.78rem;opacity:0.8;">{html_mod.escape(NAME_MAP[worst_ticker])}</div>'
            f'<div style="font-size:0.9rem;font-weight:700;color:#f87171;margin-top:0.2rem;">{final_returns[worst_ticker]:+.2f}%</div>'
            f'<div style="font-size:0.68rem;opacity:0.6;">{throne["bench_streak"]}d streak</div>'
            f'</div></div>'
            '<div style="display:flex;gap:0.5rem;text-align:center;margin-bottom:0.7rem;align-items:stretch;">'
            f'<div style="flex:1;background:rgba(255,255,255,0.06);border-radius:10px;padding:0.4rem;display:flex;flex-direction:column;justify-content:center;">'
            f'<div style="font-size:1.1rem;font-weight:700;">{ETF_EMOJI.get(etf_ranked[0][0], "")} {etf_ranked[0][0]}</div>'
            f'<div style="font-size:0.6rem;opacity:0.6;">\U0001f3c6 Best ETF</div></div>'
            f'<div style="flex:1;background:rgba(255,255,255,0.06);border-radius:10px;padding:0.4rem;display:flex;flex-direction:column;justify-content:center;">'
        )
        # Build throne drama for center box
        recent_drama = []
        for entry in throne["mvp_history"][:3]:
            if entry.get("prev_ticker"):
                if hasattr(entry["date"], "date"):
                    entry_date = entry["date"].date()
                else:
                    entry_date = entry["date"]
                if (end_date - entry_date).days <= 7:
                    recent_drama.append(f'{html_mod.escape(entry["ticker"])} \U0001f97e {html_mod.escape(entry["prev_ticker"])}')
        for entry in throne["bench_history"][:3]:
            if entry.get("prev_ticker"):
                if hasattr(entry["date"], "date"):
                    entry_date = entry["date"].date()
                else:
                    entry_date = entry["date"]
                if (end_date - entry_date).days <= 7:
                    recent_drama.append(f'{html_mod.escape(entry["ticker"])} \U0001f97e {html_mod.escape(entry["prev_ticker"])}')

        if recent_drama:
            drama_text = " | ".join(recent_drama[:2])
            wr_html += f'<div style="font-size:0.72rem;font-weight:600;">{drama_text}</div>'
        else:
            wr_html += f'<div style="font-size:0.9rem;font-weight:700;">\U0001f512 Stable</div>'
        wr_html += (
            f'<div style="font-size:0.6rem;opacity:0.6;">\U0001f3ac Throne Drama</div></div>'
            f'<div style="flex:1;background:rgba(255,255,255,0.06);border-radius:10px;padding:0.4rem;display:flex;flex-direction:column;justify-content:center;">'
            f'<div style="font-size:0.85rem;font-weight:700;white-space:nowrap;">{int(green_count_wr/len(final_returns)*100)}% \U0001f60e</div>'
            f'<div style="font-size:0.85rem;font-weight:700;white-space:nowrap;">{int(red_count_wr/len(final_returns)*100)}% \U0001f62d</div>'
            f'<div style="font-size:0.6rem;opacity:0.6;">\U0001f3ad Draft Mood</div></div></div>'
        )
        wr_html += '<div style="display:flex;gap:0.8rem;">'
        wr_html += '<div style="flex:1;"><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.6;margin-bottom:0.3rem;">\U0001f3c6 Top 5</div>'
        medals_wr = ["\U0001f947", "\U0001f948", "\U0001f949", "\U0001f4aa", "\U0001f44d"]
        for i, (ticker, ret) in enumerate(top5_wr.items()):
            wr_html += (
                f'<div style="display:flex;align-items:center;gap:0.4rem;padding:0.2rem 0;'
                f'border-bottom:1px solid rgba(255,255,255,0.06);font-size:0.82rem;">'
                f'<span>{medals_wr[i]}</span><b>{html_mod.escape(ticker)}</b>'
                f'<span style="margin-left:auto;color:#4ade80;font-weight:600;">{ret:+.2f}%</span></div>'
            )
        wr_html += '</div>'
        shame_wr = ["\U0001f4c9", "\U0001f921", "\U0001f5d1\ufe0f", "\U0001f6bd", "\U0001f4a9"]
        wr_html += '<div style="flex:1;"><div style="font-size:0.65rem;text-transform:uppercase;opacity:0.6;margin-bottom:0.3rem;">\U0001f4a9 Bottom 5</div>'
        for i, (ticker, ret) in enumerate(bot5_wr.items()):
            wr_html += (
                f'<div style="display:flex;align-items:center;gap:0.4rem;padding:0.2rem 0;'
                f'border-bottom:1px solid rgba(255,255,255,0.06);font-size:0.82rem;">'
                f'<span>{shame_wr[i]}</span><b>{html_mod.escape(ticker)}</b>'
                f'<span style="margin-left:auto;color:#f87171;font-weight:600;">{ret:+.2f}%</span></div>'
            )
        wr_html += '</div></div>'
        if pw_wr.get("climber") and pw_wr.get("faller"):
            wr_html += (
                '<div style="height:1px;background:rgba(255,255,255,0.1);margin:0.7rem 0;"></div>'
                '<div style="display:flex;gap:1rem;">'
                f'<div style="flex:1;font-size:0.82rem;">\U0001f525 <b>Hot:</b> {html_mod.escape(pw_wr["climber"])} '
                f'<span style="color:#4ade80;">{pw_wr["climber_change"]:+.1f}%</span> in 5d</div>'
                f'<div style="flex:1;font-size:0.82rem;">\U0001f9ca <b>Cold:</b> {html_mod.escape(pw_wr["faller"])} '
                f'<span style="color:#f87171;">{pw_wr["faller_change"]:+.1f}%</span> in 5d</div></div>'
            )
        wr_html += '</div>'
        st.markdown(wr_html, unsafe_allow_html=True)

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

        # --- Bump Charts ---
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">🚇</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Stock Subway</span></div>',
            unsafe_allow_html=True,
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

        # --- Throne History (dark timeline style) ---
        def _render_throne(history, icon, title, accent_color, current_ticker, current_name, current_ret, streak):
            _ret_color = "#19a05f" if current_ret >= 0 else "#d14a34"
            _reign_start = history[0]["date"].strftime("%b %d") if history else ""
            _today_label = "Present"
            _header = (
                f'<div style="background:var(--panel-strong);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;margin-bottom:1rem;box-shadow:0 4px 12px rgba(82,58,32,0.06);">'
                f'<div style="font-weight:800;font-size:0.95rem;margin-bottom:0.8rem;">{icon} {title}</div>'
                # Current holder
                f'<div style="display:flex;align-items:center;gap:0.8rem;padding:0.7rem 0.9rem;background:rgba({accent_color},0.06);border-radius:10px;margin-bottom:0.5rem;">'
                f'<span style="font-size:1.2rem;">{icon}</span>'
                f'<div style="flex:1;">'
                f'<div style="font-size:0.9rem;">{_etf_colored(current_ticker)} <span style="font-weight:400;color:var(--muted);font-size:0.8rem;">{html_mod.escape(current_name)}</span></div>'
                f'<div style="font-size:0.7rem;color:var(--muted);line-height:1.5;">Reigning<br>{_reign_start} – {_today_label}<br>{streak} day streak</div></div>'
                f'<div style="text-align:right;"><div style="font-weight:800;color:{_ret_color};font-size:1.1rem;">{current_ret:+.2f}%</div>'
                f'<div style="font-size:0.65rem;color:var(--muted);">Current</div></div></div>'
            )
            # Past holders with dethronement info and duration
            # history is newest-first; compute end dates for each reign
            _past = ''
            for i, entry in enumerate(history):
                t = entry["ticker"]
                # Skip the current holder (index 0) — already shown above
                if i == 0:
                    continue
                _r = entry["return_pct"]
                _rc = "#19a05f" if _r >= 0 else "#d14a34"
                _start_d = entry["date"].strftime("%b %d")
                # The reign ended when the previous entry (newer) started
                _end_d = history[i - 1]["date"].strftime("%b %d")
                _dethroner = history[i - 1]["ticker"]
                _date_range = f'{_start_d} – {_end_d}' if _start_d != _end_d else _start_d
                _past += (
                    f'<div style="display:flex;align-items:center;gap:0.8rem;padding:0.4rem 0.9rem;border-left:2px solid var(--border);margin-left:1.2rem;">'
                    f'<div style="flex:1;font-size:0.82rem;">{_etf_colored(t)} <span style="color:var(--muted);font-size:0.78rem;">{html_mod.escape(entry["name"])}</span></div>'
                    f'<div style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">{_date_range}</div>'
                    f'<div style="font-weight:600;color:{_rc};font-size:0.82rem;">{_r:+.2f}%</div></div>'
                )
            return _header + _past + '</div>'

        _mvp_t = throne['mvp_history'][0]['ticker'] if throne['mvp_history'] else best_ticker
        _mvp_n = NAME_MAP.get(_mvp_t, '')
        _mvp_r = final_returns.get(_mvp_t, 0)
        _bench_t = throne['bench_history'][0]['ticker'] if throne['bench_history'] else worst_ticker
        _bench_n = NAME_MAP.get(_bench_t, '')
        _bench_r = final_returns.get(_bench_t, 0)

        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">🏰</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Throne Room</span></div>',
            unsafe_allow_html=True,
        )
        throne_cols = st.columns(2)
        throne_cols[0].markdown(
            _render_throne(throne['mvp_history'], '👑', 'MVP Throne',
                               '34,197,94', _mvp_t, _mvp_n, _mvp_r, throne['mvp_streak']),
            unsafe_allow_html=True,
        )
        throne_cols[1].markdown(
            _render_throne(throne['bench_history'], '💩', 'Benchwarmer Throne',
                               '239,68,68', _bench_t, _bench_n, _bench_r, throne['bench_streak']),
            unsafe_allow_html=True,
        )

        # --- Portfolio Summary Cards ---
        start_date_label = returns.index[0].strftime("%m/%d/%Y")
        end_date_label = returns.index[-1].strftime("%m/%d/%Y")

        # --- Leaderboard ---
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
            '<span style="font-size:1.3rem;">\U0001f3c6</span>'
            '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
            'color:var(--accent);">Leaderboard</span></div>',
            unsafe_allow_html=True,
        )

        rows = []
        for rank, (ticker, ret) in enumerate(final_returns.items(), start=1):
            share_price = start_prices[ticker]
            shares = INVESTMENT / share_price
            div_per_share = dividends.get(ticker, 0.0)
            div_income = shares * div_per_share
            market_value = shares * end_prices[ticker]
            final_value = market_value + div_income
            total_return = (final_value / INVESTMENT - 1) * 100
            profit = final_value - INVESTMENT
            total_players = len(final_returns)
            if rank == 1:
                display_ticker = f"\U0001f451 {ticker}"
            elif rank == total_players:
                display_ticker = f"\U0001f4a9 {ticker}"
            else:
                display_ticker = ticker
            prev_rank = prev_ranks.get(ticker, rank)
            rank_diff = prev_rank - rank
            if rank_diff > 0:
                arrow = '<span style="color:#19a05f;font-size:12px;">\u25b2</span>'
            elif rank_diff < 0:
                arrow = '<span style="color:#d14a34;font-size:12px;">\u25bc</span>'
            else:
                arrow = '<span style="color:#102018;font-size:12px;display:inline-block;transform:rotate(90deg);">\u25b2</span>'

            # Signal columns
            sig = stock_signals.get(ticker, {}) if stock_signals else {}
            rsi_val = sig.get("rsi")
            if rsi_val is not None:
                if rsi_val < 30:
                    rsi_color = "#19a05f"
                elif rsi_val > 70:
                    rsi_color = "#d14a34"
                else:
                    rsi_color = "#d7a83a"
                rsi_cell = (
                    f'<div class="rsi-bar"><div class="rsi-bar-fill" style="width:{rsi_val}%;background:{rsi_color};"></div></div>'
                    f' <span style="font-size:0.75rem;">{rsi_val}</span>'
                )
            else:
                rsi_cell = '<span style="color:var(--muted);">\u2014</span>'

            sma_cross = sig.get("sma_cross")
            if sma_cross is not None:
                sma_cell = '<span style="color:#19a05f;">\u2713 Bullish</span>' if sma_cross else '<span style="color:#d14a34;">\u2717 Bearish</span>'
            else:
                sma_cell = '<span style="color:var(--muted);">\u2014</span>'

            signal_val = sig.get("signal", "")
            prev_signal = sig.get("prev_signal")
            change_date = sig.get("change_date")
            if signal_val:
                sig_class = f'signal-{signal_val.lower()}'
                if prev_signal and prev_signal != signal_val and change_date:
                    signal_cell = (
                        f'<span style="display:flex;flex-direction:column;align-items:center;gap:1px;line-height:1.2;">'
                        f'<span class="signal-badge {sig_class}">{signal_val}</span>'
                        f'<span style="font-size:0.58rem;color:#5d6f65;white-space:nowrap;">'
                        f'{prev_signal} \u2192 {signal_val} {change_date}'
                        f'</span></span>'
                    )
                else:
                    signal_cell = f'<span class="signal-badge {sig_class}">{signal_val}</span>'
            else:
                signal_cell = '<span style="color:var(--muted);">\u2014</span>'

            earn = earnings_data.get(ticker, {})
            earn_date = earn.get("next_date", "")
            eps_est = earn.get("eps_est")
            eps_actual = earn.get("eps_actual")
            earn_cell = earn_date if earn_date else '<span style="color:var(--muted);">\u2014</span>'
            eps_est_cell = f'${eps_est:.2f}' if eps_est is not None else '<span style="color:var(--muted);">\u2014</span>'
            last_earn_date = earn.get("last_earnings_date", "")
            last_eps_reported = earn.get("last_eps_reported")
            last_eps_estimate = earn.get("last_eps_estimate")
            # Build Est. EPS cell: est eps, then previous est vs actual, date, beat/miss, bar, %
            if eps_est is not None:
                eps_col_cell = f'${eps_est:.2f}'
            else:
                eps_col_cell = '<span style="color:var(--muted);">\u2014</span>'
            # Add last earnings details below on separate lines
            if last_eps_reported is not None and last_eps_estimate is not None:
                if last_eps_estimate != 0:
                    _surprise_pct = ((last_eps_reported - last_eps_estimate) / abs(last_eps_estimate)) * 100
                else:
                    _surprise_pct = 100.0 if last_eps_reported > 0 else (-100.0 if last_eps_reported < 0 else 0)
                _bar_width = min(abs(_surprise_pct), 100)
                # Line 2: previous est vs actual
                eps_col_cell += f'<br><span style="color:var(--muted);font-size:0.66rem;">${last_eps_reported:.2f} vs ${last_eps_estimate:.2f}</span>'
                # Line 3: date
                if last_earn_date:
                    eps_col_cell += f'<br><span style="color:var(--muted);font-size:0.66rem;">{last_earn_date}</span>'
                # Line 4: beat/miss badge
                if last_eps_reported > last_eps_estimate:
                    eps_col_cell += (
                        '<br><span style="display:inline-block;padding:0.05rem 0.4rem;border-radius:999px;font-size:0.6rem;font-weight:700;background:rgba(25,160,95,0.15);color:#19a05f;">BEAT</span>'
                        # Line 5: bar
                        f'<div style="height:3px;background:rgba(18,51,36,0.08);border-radius:2px;margin-top:2px;overflow:hidden;">'
                        f'<div style="width:{_bar_width}%;height:100%;background:#19a05f;border-radius:2px;"></div></div>'
                        # Line 6: percentage
                        f'<span style="font-size:0.58rem;color:#19a05f;font-weight:600;">+{abs(_surprise_pct):.1f}%</span>'
                    )
                elif last_eps_reported < last_eps_estimate:
                    eps_col_cell += (
                        '<br><span style="display:inline-block;padding:0.05rem 0.4rem;border-radius:999px;font-size:0.6rem;font-weight:700;background:rgba(209,74,52,0.12);color:#d14a34;">MISS</span>'
                        f'<div style="height:3px;background:rgba(18,51,36,0.08);border-radius:2px;margin-top:2px;overflow:hidden;">'
                        f'<div style="width:{_bar_width}%;height:100%;background:#d14a34;border-radius:2px;"></div></div>'
                        f'<span style="font-size:0.58rem;color:#d14a34;font-weight:600;">-{abs(_surprise_pct):.1f}%</span>'
                    )
                else:
                    eps_col_cell += '<br><span style="display:inline-block;padding:0.05rem 0.4rem;border-radius:999px;font-size:0.6rem;font-weight:700;background:rgba(18,51,36,0.08);color:#5d6f65;">MET</span>'

            stock_cell = f'<b>{html_mod.escape(display_ticker)}</b><br><span style="color:var(--muted);font-size:0.75rem;">{html_mod.escape(NAME_MAP[ticker])}</span>'
            price_ret_html = format_signed_percent(price_returns[ticker])
            price_ret_html = price_ret_html.replace('style="color:', 'style="font-weight:700;color:')
            total_ret_html = format_signed_percent(total_return)
            total_ret_html = total_ret_html.replace('style="color:', 'style="font-weight:700;color:')

            # vs 20d SMA
            pv_sma = sig.get("price_vs_sma")
            if pv_sma is not None:
                pv_sma_cell = '<span style="color:#19a05f;">Above</span>' if pv_sma else '<span style="color:#d14a34;">Below</span>'
            else:
                pv_sma_cell = '<span style="color:var(--muted);">\u2014</span>'

            rows.append({
                "Rank": f'<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap;">{arrow} {rank}</span>',
                "ETF": (lambda e: f'<span style="display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;font-size:0.7rem;font-weight:700;'
                       + (f'background:rgba(168,85,247,0.15);color:#a855f7;">{e}</span>' if e == "ANTY"
                          else f'background:rgba(59,130,246,0.15);color:#3b82f6;">{e}</span>' if e == "UNCL"
                          else f'background:rgba(234,179,8,0.15);color:#eab308;">{e}</span>' if e == "KIDZ"
                          else f'">{e}</span>'))(ETF_MAP.get(ticker, "")),
                "Sector": SECTOR_MAP.get(ticker, ""),
                "Stock": stock_cell,
                "Total Return (%)": total_ret_html,
                "Price Return (%)": price_ret_html,
                "RSI": rsi_cell,
                "SMA Cross": sma_cell,
                "vs 20d SMA": pv_sma_cell,
                "Signal": signal_cell,
                f"Price ({start_date_label} – {end_date_label})": f'${share_price:.2f}<br>→<br>${end_prices[ticker]:.2f}',
                "Stake": f"${INVESTMENT:.2f}",
                "Units": f"{shares:.4f}",
                "Profit/(Loss)": format_signed_currency(profit),
                "Mkt Value": f'<span style="color:{"#19a05f" if market_value >= INVESTMENT else "#d14a34"};">${market_value:.2f}</span>',
                "Dividends": f'<span style="color:#19a05f;">${div_income:.2f}</span>' if div_income > 0 else f'${div_income:.2f}',
                "Total Value": f'<span style="color:{"#19a05f" if final_value >= INVESTMENT else "#d14a34"};">${final_value:.2f}</span>',
                "Next Earnings": earn_cell,
                "Est. EPS": eps_col_cell,
            })

        # Compute totals for summary row
        _total_stake = INVESTMENT * len(final_returns)
        _total_mkt_val = sum(INVESTMENT / start_prices[t] * end_prices[t] for t in final_returns.index)
        _total_divs = sum(INVESTMENT / start_prices[t] * dividends.get(t, 0.0) for t in final_returns.index)
        _total_profit = (_total_mkt_val + _total_divs) - _total_stake
        _total_price_ret = (_total_mkt_val / _total_stake - 1) * 100
        _total_total_ret = ((_total_mkt_val + _total_divs) / _total_stake - 1) * 100
        _total_ret_color = "#19a05f" if _total_total_ret >= 0 else "#d14a34"
        _total_price_color = "#19a05f" if _total_price_ret >= 0 else "#d14a34"

        rows.append({
            "Rank": '<b>Total</b>',
            "ETF": "",
            "Sector": "",
            "Stock": f'<b>{len(final_returns)} stocks</b>',
            "Total Return (%)": format_signed_percent(_total_total_ret).replace('style="color:', 'style="font-weight:700;color:'),
            "Price Return (%)": format_signed_percent(_total_price_ret).replace('style="color:', 'style="font-weight:700;color:'),
            "RSI": "",
            "SMA Cross": "",
            "vs 20d SMA": "",
            "Signal": "",
            f"Price ({start_date_label} – {end_date_label})": "",
            "Stake": f'<b>${_total_stake:.2f}</b>',
            "Units": "",
            "Profit/(Loss)": f'<b>{format_signed_currency(_total_profit)}</b>',
            "Mkt Value": f'<b><span style="color:{"#19a05f" if _total_mkt_val >= _total_stake else "#d14a34"};">${_total_mkt_val:.2f}</span></b>',
            "Dividends": f'<b><span style="color:#19a05f;">${_total_divs:.2f}</span></b>' if _total_divs > 0 else f'<b>${_total_divs:.2f}</b>',
            "Total Value": f'<b><span style="color:{"#19a05f" if (_total_mkt_val + _total_divs) >= _total_stake else "#d14a34"};">${_total_mkt_val + _total_divs:.2f}</span></b>',
            "Next Earnings": "",
            "Est. EPS": "",
        })

        df = pd.DataFrame(rows)
        total_row_idx = len(df) - 1
        total_rows = max(total_row_idx - 1, 1)

        # Find the first row with negative total return
        first_negative_idx = next((i for i, r in enumerate(rows[:-1]) if "#d14a34" in r["Total Return (%)"]), None)

        # Build set of matching row indices for search highlight
        search_matches = set()
        if roster_search:
            for i, r in enumerate(rows[:-1]):
                stock_raw = r.get("Stock", "")
                if roster_search.upper() in stock_raw.upper():
                    search_matches.add(i)


        # Columns that use their own semantic colors (green/red) — don't override with row gradient
        _own_color_cols = {"Total Return (%)", "Price Return (%)", "RSI", "SMA Cross",
                           "vs 20d SMA", "Signal", "Profit/(Loss)", "Mkt Value", "Dividends", "Total Value"}

        def leaderboard_row_style(row):
            if row.name == total_row_idx:
                return ["font-weight:700; background:rgba(18,51,36,0.06); border-top:2px solid rgba(18,51,36,0.2);"] * len(row)
            fraction = row.name / total_rows
            color = interpolate_hex_color("#19a05f", "#d14a34", fraction)
            styles = []
            for col in row.index:
                if col in _own_color_cols:
                    styles.append("")
                else:
                    styles.append(f"color: {color};")
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
        _lb_html = (
            '<style>'
            'body { margin:0; padding:0; }'
            '.lb-wrap { overflow:scroll !important; }'
            '.lb-wrap::-webkit-scrollbar { height:10px; width:10px; -webkit-appearance:none; display:block; }'
            '.lb-wrap::-webkit-scrollbar-track { background:rgba(18,51,36,0.03); border-radius:5px; }'
            '.lb-wrap::-webkit-scrollbar-thumb { background:rgba(18,51,36,0.12); border-radius:5px; min-height:40px; min-width:40px; }'
            '.lb-wrap::-webkit-scrollbar-thumb:hover { background:rgba(18,51,36,0.22); }'
            '.lb-wrap::-webkit-scrollbar-corner { background:transparent; }'
            'table.leaderboard { min-width:max-content; width:100%; border-collapse:separate; border-spacing:0; border-radius:18px; background:rgba(251,253,250,0.96); }'
            'table.leaderboard td, table.leaderboard th { padding:10px 8px; text-align:left; border-bottom:1px solid rgba(18,51,36,0.06); border-right:1px solid rgba(18,51,36,0.04); white-space:nowrap; font-family:"Space Grotesk",sans-serif; font-size:0.82rem; }'
            'table.leaderboard th.blank, table.leaderboard td.blank { display:none; padding:0; height:0; border:none; }'
            'table.leaderboard thead tr:has(th.blank) { display:none; }'
            'table.leaderboard th { white-space:normal; background:linear-gradient(90deg,#0d2f20,#13492f); color:#f4f0e3; text-transform:uppercase; letter-spacing:0.06em; font-family:"Space Grotesk",sans-serif; font-size:0.72rem; font-weight:700; min-width:45px; max-width:100px; line-height:1.3; padding:10px 8px; position:sticky; top:0; z-index:1; cursor:pointer; user-select:none; }'
            'table.leaderboard th:hover { background:linear-gradient(90deg,#0a2518,#0f3a25); }'
            'table.leaderboard th .sort-arrow { font-size:0.6rem; margin-left:3px; opacity:0.4; }'
            'table.leaderboard th.sort-active .sort-arrow { opacity:1; }'
            'table.leaderboard tr:nth-child(even) td { background:rgba(16,95,58,0.04); }'
            'table.leaderboard tbody tr:hover td { background:rgba(14,95,58,0.08); }'
            '.signal-badge { display:inline-block; padding:0.1rem 0.5rem; border-radius:999px; font-size:0.68rem; font-weight:700; letter-spacing:0.03em; }'
            '.signal-buy { background:rgba(25,160,95,0.15); color:#19a05f; }'
            '.signal-sell { background:rgba(209,74,52,0.12); color:#d14a34; }'
            '.signal-hold { background:rgba(18,51,36,0.08); color:#5d6f65; }'
            '.rsi-bar { display:inline-block; width:50px; height:8px; background:rgba(18,51,36,0.08); border-radius:4px; vertical-align:middle; margin-right:4px; }'
            '.rsi-bar-fill { height:100%; border-radius:4px; }'
            '@media (max-width:768px) {'
            '  table.leaderboard td, table.leaderboard th { padding:6px 5px; font-size:0.7rem; }'
            '  table.leaderboard th { font-size:0.6rem; min-width:40px; }'
            '}'
            '</style>'
            '<div class="lb-wrap" style="overflow:scroll;-webkit-overflow-scrolling:touch;max-height:620px;border-radius:18px;border:1px solid rgba(18,51,36,0.12);">'
            + styled_df.to_html(escape=False)
            + '</div>'
            '<script>'
            'var w=document.querySelector(".lb-wrap");'
            'if(w){w.style.overflow="scroll";'
            'var s=document.createElement("style");'
            's.textContent=".lb-wrap::-webkit-scrollbar{height:10px;width:10px;-webkit-appearance:none;display:block}.lb-wrap::-webkit-scrollbar-track{background:rgba(18,51,36,0.03);border-radius:5px}.lb-wrap::-webkit-scrollbar-thumb{background:rgba(18,51,36,0.12);border-radius:5px;min-height:40px;min-width:40px}.lb-wrap::-webkit-scrollbar-corner{background:transparent}";'
            'document.head.appendChild(s);}'
            ''
            '/* Column sorting */'
            'var table=document.querySelector("table.leaderboard");'
            'if(table){'
            '  var headers=table.querySelectorAll("thead th");'
            '  headers.forEach(function(th,i){'
            '    th.innerHTML=th.innerHTML+\'<span class="sort-arrow">▲▼</span>\';'
            '    th.addEventListener("click",function(){sortTable(i,th);});'
            '  });'
            '}'
            'var sortCol=-1,sortAsc=true;'
            'function parseVal(cell){'
            '  var txt=cell.textContent.trim();'
            '  if(!txt)return null;'
            '  /* strip rank arrows/triangles */'
            '  txt=txt.replace(/^[▲▼►◆●■\u25B2\u25BC\u25BA]/,"").trim();'
            '  /* currency/percent */'
            '  var cleaned=txt.replace(/[$,%()]/g,"").trim();'
            '  /* handle parenthesized negatives like ($0.11) */'
            '  if(txt.indexOf("(")>-1 && txt.indexOf(")")>-1){cleaned="-"+cleaned.replace(/[()]/g,"");}'
            '  var num=parseFloat(cleaned);'
            '  if(!isNaN(num))return num;'
            '  return txt.toLowerCase();'
            '}'
            'function sortTable(colIdx,th){'
            '  var tbody=table.querySelector("tbody");'
            '  var rows=Array.from(tbody.querySelectorAll("tr"));'
            '  /* Keep last row (Total) pinned */'
            '  var totalRow=rows.pop();'
            '  if(sortCol===colIdx){sortAsc=!sortAsc;}else{sortCol=colIdx;sortAsc=true;}'
            '  rows.sort(function(a,b){'
            '    var va=parseVal(a.cells[colIdx]),vb=parseVal(b.cells[colIdx]);'
            '    if(va===null&&vb===null)return 0;'
            '    if(va===null)return 1;if(vb===null)return -1;'
            '    if(typeof va==="number"&&typeof vb==="number")return sortAsc?va-vb:vb-va;'
            '    var sa=String(va),sb=String(vb);'
            '    return sortAsc?sa.localeCompare(sb):sb.localeCompare(sa);'
            '  });'
            '  rows.forEach(function(r){tbody.appendChild(r);});'
            '  tbody.appendChild(totalRow);'
            '  /* Update header arrows */'
            '  table.querySelectorAll("thead th").forEach(function(h){h.classList.remove("sort-active");});'
            '  th.classList.add("sort-active");'
            '  th.querySelector(".sort-arrow").textContent=sortAsc?"▲":"▼";'
            '  table.querySelectorAll("thead th").forEach(function(h){'
            '    if(h!==th){var ar=h.querySelector(".sort-arrow");if(ar)ar.textContent="▲▼";}'
            '  });'
            '}'
            '</script>'
        )
        components.html(_lb_html, height=628, scrolling=False)
        st.markdown(
            '<div style="font-size:0.7rem;color:var(--muted);line-height:1.4;margin-top:-0.3rem;">'
            '<b>Price Return (%)</b> is the percentage change in share price over the period, excluding dividends. '
            '<b>Total Return (%)</b> includes dividends.</div>',
            unsafe_allow_html=True,
        )

        # --- This Week Events ---
        import datetime as _dt_mod
        _today = _dt_mod.date.today()
        # Find this week's Sunday (week starts on Sunday)
        _this_sunday = _today - _dt_mod.timedelta(days=(_today.weekday() + 1) % 7)
        _this_saturday = _this_sunday + _dt_mod.timedelta(days=6)
        _week_label = f"{_this_sunday.strftime('%b %d')} – {_this_saturday.strftime('%b %d')}"

        # Collect earnings happening this week
        _next_week_earnings = []
        for t in valid_tickers:
            earn = earnings_data.get(t, {})
            earn_date_str = earn.get("next_date", "")
            if not earn_date_str:
                continue
            try:
                # Parse "Apr 30" style date, assume current year
                _ed = _dt_mod.datetime.strptime(earn_date_str, "%b %d").date().replace(year=_today.year)
                if _this_sunday <= _ed <= _this_saturday:
                    eps_est = earn.get("eps_est")
                    _next_week_earnings.append((t, _ed, eps_est))
            except Exception:
                pass
        _next_week_earnings.sort(key=lambda x: x[1])

        # Build the events HTML — horizontal card layout
        _events_items = []
        for t, ed, eps_est in _next_week_earnings:
            _day_label = ed.strftime("%a %b %d")
            _eps_note = f' · Est. ${eps_est:.2f}' if eps_est is not None else ' · Est: N/A'
            _events_items.append(
                f'<div style="flex:1 1 auto;display:flex;align-items:center;gap:0.7rem;padding:0.6rem 1rem;'
                f'background:rgba(14,95,58,0.04);border:1px solid var(--border);border-radius:12px;min-width:200px;">'
                f'<span style="font-size:1.1rem;">📊</span>'
                f'<div style="flex:1;">'
                f'<div><span style="font-size:0.85rem;">{_etf_colored(t)}</span> '
                f'<span style="color:var(--muted);font-size:0.76rem;">{NAME_MAP.get(t, "")}</span></div>'
                f'<div style="color:var(--muted);font-size:0.72rem;">Earnings{_eps_note}</div>'
                f'</div>'
                f'<span style="font-size:0.7rem;color:var(--muted);background:rgba(18,51,36,0.06);padding:0.2rem 0.5rem;border-radius:5px;font-weight:600;white-space:nowrap;">{_day_label}</span>'
                f'</div>'
            )

        if _events_items:
            _events_html = ''.join(_events_items)
        else:
            _events_html = '<div style="color:var(--muted);font-size:0.82rem;padding:0.6rem 0;">No earnings scheduled this week for roster stocks.</div>'

        _earnings_count = len(_next_week_earnings)
        st.markdown(
            f'<div style="margin:1.2rem 0 0.8rem;">'
            f'<div style="background:rgba(251,253,250,0.96);border:1px solid rgba(18,51,36,0.12);border-radius:18px;padding:1rem 1.4rem;box-shadow:0 4px 12px rgba(82,58,32,0.06);">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.7rem;">'
            f'<div>'
            f'<div style="font-size:0.95rem;font-weight:800;">📅 This Week</div>'
            f'<div style="font-size:0.72rem;color:var(--muted);">{_week_label}</div>'
            f'</div>'
            f'<span style="font-size:0.7rem;font-weight:700;padding:0.2rem 0.6rem;border-radius:999px;background:rgba(14,95,58,0.08);color:var(--accent);">{_earnings_count} earnings</span>'
            f'</div>'
            f'<div style="display:flex;gap:0.7rem;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:0.3rem;flex-wrap:wrap;">'
            f'{_events_html}'
            f'</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        # --- Sector Reference Table ---
        from collections import defaultdict
        _sector_stocks = defaultdict(list)
        for t in sorted(SECTOR_MAP.keys()):
            _sector_stocks[SECTOR_MAP[t]].append(t)
        # Compute total return (including dividends) for each stock
        _total_ret_map = {}
        for t in valid_tickers:
            sp = start_prices[t]
            shares = INVESTMENT / sp
            div_inc = shares * dividends.get(t, 0.0)
            mv = shares * end_prices[t]
            _total_ret_map[t] = ((mv + div_inc) / INVESTMENT - 1) * 100

        # Sort sectors by average total return (best to worst)
        _sector_avgs = {}
        for sec, tickers in _sector_stocks.items():
            rets = [_total_ret_map[t] for t in tickers if t in _total_ret_map]
            _sector_avgs[sec] = sum(rets) / len(rets) if rets else 0
        _sector_order = sorted(_sector_avgs.keys(), key=lambda s: -_sector_avgs[s])

        _total_stock_count = 0
        _sector_rows = ""
        for sec in _sector_order:
            tickers = _sector_stocks.get(sec, [])
            if tickers:
                # Find best and worst stock in this sector (by total return)
                sector_rets = {t: _total_ret_map[t] for t in tickers if t in _total_ret_map}
                if sector_rets:
                    best_t = max(sector_rets, key=sector_rets.get)
                    worst_t = min(sector_rets, key=sector_rets.get)
                    best_ret = sector_rets[best_t]
                    worst_ret = sector_rets[worst_t]
                    best_color = "#19a05f" if best_ret >= 0 else "#d14a34"
                    worst_color = "#19a05f" if worst_ret >= 0 else "#d14a34"
                    best_etf = ETF_MAP.get(best_t, "")
                    worst_etf = ETF_MAP.get(worst_t, "")
                    best_etf_em = {"UNCL": "\U0001f468\u200d\U0001f9b3", "ANTY": "\U0001f469\U0001f3fb", "KIDZ": "\U0001f476\U0001f3fb"}.get(best_etf, "")
                    worst_etf_em = {"UNCL": "\U0001f468\u200d\U0001f9b3", "ANTY": "\U0001f469\U0001f3fb", "KIDZ": "\U0001f476\U0001f3fb"}.get(worst_etf, "")
                    _etf_clr_bw = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"}
                    best_ticker_clr = _etf_clr_bw.get(best_etf, "#5d6f65")
                    worst_ticker_clr = _etf_clr_bw.get(worst_etf, "#5d6f65")
                    best_html = f'{best_etf_em} <b style="color:{best_ticker_clr};">{html_mod.escape(best_t)}</b> <span style="color:{best_color};font-weight:700;">{best_ret:+.2f}%</span>'
                    worst_html = f'{worst_etf_em} <b style="color:{worst_ticker_clr};">{html_mod.escape(worst_t)}</b> <span style="color:{worst_color};font-weight:700;">{worst_ret:+.2f}%</span>'
                else:
                    best_html = "—"
                    worst_html = "—"
                _total_stock_count += len(tickers)
                # Avg return for sector
                _avg_ret = _sector_avgs.get(sec, 0)
                _avg_color = "#19a05f" if _avg_ret >= 0 else "#d14a34"
                _avg_html = f'<span style="color:{_avg_color};font-weight:700;">{_avg_ret:+.2f}%</span>'

                # Count ETFs in this sector
                _etf_counts = defaultdict(int)
                for t in tickers:
                    e = ETF_MAP.get(t, "")
                    if e:
                        _etf_counts[e] += 1
                _etf_emoji_map = {"UNCL": "\U0001f468\u200d\U0001f9b3", "ANTY": "\U0001f469\U0001f3fb", "KIDZ": "\U0001f476\U0001f3fb"}
                if _etf_counts:
                    _etf_parts = []
                    for e in sorted(_etf_counts, key=_etf_counts.get, reverse=True):
                        _em = _etf_emoji_map.get(e, "")
                        _etf_parts.append(f'{_em}{_etf_counts[e]}')
                    _top_etf_html = "<br>".join(_etf_parts)
                else:
                    _top_etf_html = "\u2014"

                _td = 'style="padding:8px 8px;border-bottom:1px solid rgba(18,51,36,0.06);font-size:0.82rem;"'
                _etf_clr = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"}
                _colored_tickers = ", ".join(
                    f'<span style="color:{_etf_clr.get(ETF_MAP.get(t, ""), "#5d6f65")};font-weight:600;">{html_mod.escape(t)}</span>'
                    for t in tickers
                )
                _sector_rows += (
                    f'<tr>'
                    f'<td style="font-weight:700;white-space:nowrap;padding:8px 8px;border-bottom:1px solid rgba(18,51,36,0.06);font-size:0.82rem;">{html_mod.escape(sec)}</td>'
                    f'<td {_td} style="text-align:center;">{len(tickers)}</td>'
                    f'<td {_td}>{_avg_html}</td>'
                    f'<td {_td} style="white-space:normal;">{_colored_tickers}</td>'
                    f'<td {_td}>{best_html}</td>'
                    f'<td {_td}>{worst_html}</td>'
                    f'<td {_td}>{_top_etf_html}</td>'
                    f'</tr>'
                )
        _th = 'style="text-align:left;padding:10px 8px;background:linear-gradient(90deg,#0d2f20,#13492f);color:#f4f0e3;font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;font-family:Space Grotesk,sans-serif;white-space:normal;line-height:1.3;"'
        st.markdown(
            f'<div class="sector-tbl" style="margin-top:0.8rem;max-width:100%;overflow:hidden;border-radius:14px;border:1px solid var(--border);background:var(--panel-strong);">'
            f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">'
            f'<table style="width:100%;min-width:900px;border-collapse:separate;border-spacing:0;font-family:Space Grotesk,sans-serif;font-size:0.82rem;">'
            f'<tr>'
            f'<th {_th}>Sector</th><th {_th}>#</th><th {_th}>Avg Total Return ({start_date.strftime("%m/%d")} - {end_date.strftime("%m/%d")})</th>'
            f'<th {_th}>Stocks</th><th {_th}>Best</th><th {_th}>Worst</th>'
            f'<th {_th}>ETF Breakdown</th>'
            f'</tr>'
            f'{_sector_rows}'
            f'<tr style="background:rgba(18,51,36,0.04);font-weight:700;">'
            f'<td style="padding:8px 8px;font-size:0.82rem;">Total</td>'
            f'<td style="padding:8px 8px;text-align:center;font-size:0.82rem;">{_total_stock_count}</td>'
            f'<td></td><td></td><td></td><td></td><td></td>'
            f'</tr>'
            f'</table></div></div>',
            unsafe_allow_html=True,
        )

        # --- Subscribe ---
        st.markdown("---")

    live_dashboard()

with tab_feud:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.5rem;margin:0.5rem 0 0.8rem;">'
        '<span style="font-size:1.5rem;">\U0001f3af</span>'
        '<span style="font-size:1.3rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
        'color:var(--accent);">Prediction Game</span></div>',
        unsafe_allow_html=True,
    )

    # Compute this week's range (Sun-Sat, week starts on Sunday)
    _now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    _today = _now_et.date()
    _this_sunday = _today - datetime.timedelta(days=(_today.weekday() + 1) % 7)
    _this_saturday = _this_sunday + datetime.timedelta(days=6)
    _week_label = f"{_this_sunday.strftime('%b %d')} – {_this_saturday.strftime('%b %d')}"

    # Voting deadline check (Monday 9 AM ET)
    _this_monday = _this_sunday + datetime.timedelta(days=1)
    _vote_cutoff = datetime.datetime.combine(_this_monday, datetime.time(9, 0), tzinfo=ZoneInfo("America/New_York"))
    _voting_open = _now_et < _vote_cutoff

    # Build stock list for JS
    _stock_list_js = json.dumps([{"ticker": p["ticker"], "name": p["name"], "etf": p.get("etf", "")} for p in PLAYERS])

    # Fetch earnings for this week's challenge
    _feud_earnings = fetch_earnings(tuple(TICKERS))
    _next_week_earnings = []
    for t, edata in _feud_earnings.items():
        edate_str = edata.get("next_date", "")
        if edate_str:
            try:
                # Parse "Apr 30" style date
                edate = datetime.datetime.strptime(f"{edate_str} {_now_et.year}", "%b %d %Y").date()
                # Check if earnings fall in this week (Sun-Sat)
                if _this_sunday <= edate <= _this_saturday:
                    _next_week_earnings.append({
                        "ticker": t,
                        "name": NAME_MAP.get(t, t),
                        "etf": ETF_MAP.get(t, ""),
                        "date": edate_str,
                        "eps_est": edata.get("eps_est"),
                    })
            except (ValueError, TypeError):
                pass
    _next_week_earnings.sort(key=lambda x: x["date"])

    # --- Challenge 1: MVP Vote ---
    # --- Challenge 2: HOH Vote ---
    # Both rendered as a single components.html block for interactivity

    # Load current votes from Google Sheets
    _vote_data = {}
    _hoh_vote_data = {}
    _earn_vote_data = {}
    with st.spinner("Loading challenges..."):
        try:
            resp = requests.get(REACTIONS_SHEET_URL + "?action=get_mvp_votes", timeout=5)
            if resp.status_code == 200:
                _vote_data = resp.json()
        except Exception:
            pass
        try:
            resp = requests.get(REACTIONS_SHEET_URL + "?action=get_hoh_votes", timeout=5)
            if resp.status_code == 200:
                _hoh_vote_data = resp.json()
        except Exception:
            pass
        try:
            resp = requests.get(REACTIONS_SHEET_URL + "?action=get_earn_votes", timeout=5)
            if resp.status_code == 200:
                _earn_vote_data = resp.json()
        except Exception:
            pass

    _mvp_votes = _vote_data.get("votes", {})
    _mvp_total = _vote_data.get("total", 0)
    _hoh_votes = _hoh_vote_data.get("votes", {})
    _hoh_total = _hoh_vote_data.get("total", 0)
    _earn_votes_js = json.dumps(_earn_vote_data)

    # Build MVP vote bars HTML
    _mvp_bars = ""
    if _mvp_votes:
        _sorted_votes = sorted(_mvp_votes.items(), key=lambda x: -x[1])
        _top_votes = _sorted_votes[:4]
        _other_count = sum(v for _, v in _sorted_votes[4:])
        if _other_count > 0:
            _top_votes.append(("Other", _other_count))
        _bar_colors = ["#19a05f", "#0e5f3a", "#13492f", "#5d6f65", "#b8b8b8"]
        for i, (ticker, count) in enumerate(_top_votes):
            pct = int(count / _mvp_total * 100) if _mvp_total > 0 else 0
            color = _bar_colors[min(i, len(_bar_colors) - 1)]
            _mvp_bars += (
                f'<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">'
                f'<span style="font-weight:700;font-size:0.85rem;min-width:4.5rem;color:{_ETF_CLR.get(ETF_MAP.get(str(ticker), ""), "inherit")};">{html_mod.escape(str(ticker))}</span>'
                f'<div style="flex:1;height:26px;background:rgba(18,51,36,0.06);border-radius:8px;overflow:hidden;">'
                f'<div style="height:100%;width:{max(pct, 5)}%;background:{color};border-radius:8px;'
                f'display:flex;align-items:center;padding-left:0.5rem;font-size:0.7rem;font-weight:700;color:#fff;">'
                f'&nbsp;{pct}%</div></div>'
                f'<span style="font-size:0.78rem;color:#5d6f65;min-width:4rem;text-align:right;">{count} votes</span>'
                f'</div>'
            )

    # Build HOH vote bars HTML
    _hoh_bars = ""
    if _hoh_votes:
        _sorted_hoh = sorted(_hoh_votes.items(), key=lambda x: -x[1])
        _bar_colors_hoh = ["#19a05f", "#0e5f3a", "#13492f"]
        for i, (etf, count) in enumerate(_sorted_hoh):
            pct = int(count / _hoh_total * 100) if _hoh_total > 0 else 0
            color = _bar_colors_hoh[min(i, len(_bar_colors_hoh) - 1)]
            _hoh_bars += (
                f'<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">'
                f'<span style="font-weight:700;font-size:0.85rem;min-width:4.5rem;color:{_ETF_CLR.get(str(etf), "inherit")};">{html_mod.escape(str(etf))}</span>'
                f'<div style="flex:1;height:26px;background:rgba(18,51,36,0.06);border-radius:8px;overflow:hidden;">'
                f'<div style="height:100%;width:{max(pct, 5)}%;background:{color};border-radius:8px;'
                f'display:flex;align-items:center;padding-left:0.5rem;font-size:0.7rem;font-weight:700;color:#fff;">'
                f'&nbsp;{pct}%</div></div>'
                f'<span style="font-size:0.78rem;color:#5d6f65;min-width:4rem;text-align:right;">{count} votes</span>'
                f'</div>'
            )

    # Pre-build conditional sections (can't use ternary with unicode in f-strings)
    if _voting_open:
        _mvp_input_html = (
            '<div style="max-width:100%;margin-bottom:0.8rem;z-index:100;position:relative;" id="mvp-search-wrap">'
            '<div style="position:relative;">'
            '<span style="position:absolute;left:0.7rem;top:50%;transform:translateY(-50%);font-size:0.9rem;color:#5d6f65;pointer-events:none;">'
            '\U0001f50d</span>'
            '<input id="mvpInput" type="text" placeholder="Search a stock to vote..." autocomplete="off" '
            'style="width:100%;padding:0.6rem 0.9rem 0.6rem 2.2rem;border:2px solid rgba(18,51,36,0.12);'
            'border-radius:12px;font-family:inherit;font-size:0.9rem;font-weight:600;background:white;'
            'color:#102018;outline:none;box-sizing:border-box;">'
            '</div>'
            '<div id="mvpDropdown" style="position:absolute;top:100%;left:0;right:0;background:white;'
            'border:1px solid rgba(18,51,36,0.12);border-radius:12px;margin-top:4px;max-height:320px;'
            'overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,0.1);z-index:9999;display:none;"></div></div>'
            '<div id="mvpPick" style="display:none;margin-bottom:0.8rem;">'
            '<span style="display:inline-flex;align-items:center;gap:0.5rem;padding:0.4rem 0.8rem;'
            'background:rgba(14,95,58,0.08);border:1px solid #0e5f3a;border-radius:12px;font-weight:700;'
            'font-size:0.9rem;color:#0e5f3a;">Your pick: <span id="mvpPickTicker">\u2014</span> '
            '<span id="mvpPickName" style="font-weight:400;color:#5d6f65;font-size:0.8rem;"></span> '
            '<span onclick="changeMvp()" style="font-size:0.7rem;color:#5d6f65;cursor:pointer;text-decoration:underline;">change</span>'
            '</span></div>'
        )
        _hoh_input_html = (
            '<div style="display:flex;gap:0.5rem;margin-bottom:0.8rem;flex-wrap:wrap;" id="hohBtns">'
            '<div class="hohBtn" onclick="selectHoh(this,\'ANTY\')" style="padding:0.5rem 1.2rem;border:2px solid rgba(18,51,36,0.12);border-radius:14px;cursor:pointer;font-weight:700;font-size:0.95rem;background:white;display:flex;align-items:center;gap:0.4rem;transition:all 0.15s;">'
            '<span style="font-size:1.1rem;">\U0001f469\U0001f3fb</span> <span style="color:#a855f7;">ANTY</span></div>'
            '<div class="hohBtn" onclick="selectHoh(this,\'UNCL\')" style="padding:0.5rem 1.2rem;border:2px solid rgba(18,51,36,0.12);border-radius:14px;cursor:pointer;font-weight:700;font-size:0.95rem;background:white;display:flex;align-items:center;gap:0.4rem;transition:all 0.15s;">'
            '<span style="font-size:1.1rem;">\U0001f468\u200d\U0001f9b3</span> <span style="color:#3b82f6;">UNCL</span></div>'
            '<div class="hohBtn" onclick="selectHoh(this,\'KIDZ\')" style="padding:0.5rem 1.2rem;border:2px solid rgba(18,51,36,0.12);border-radius:14px;cursor:pointer;font-weight:700;font-size:0.95rem;background:white;display:flex;align-items:center;gap:0.4rem;transition:all 0.15s;">'
            '<span style="font-size:1.1rem;">\U0001f476\U0001f3fb</span> <span style="color:#eab308;">KIDZ</span></div>'
            '</div>'
        )
    else:
        _mvp_input_html = (
            '<div style="padding:0.5rem 0.8rem;background:rgba(209,74,52,0.08);border:1px solid rgba(209,74,52,0.2);'
            'border-radius:12px;font-size:0.8rem;color:#8f2d1b;margin-bottom:0.8rem;">'
            '\U0001f512 Voting is closed for this week.</div>'
        )
        _hoh_input_html = _mvp_input_html

    _no_votes_html = '<div style="font-size:0.8rem;color:#5d6f65;">No votes yet \u2014 be the first!</div>'

    # Build earnings challenge cards
    _cal_emoji = "\U0001f4c5"
    _up_emoji = "\U0001f4c8"
    _down_emoji = "\U0001f4c9"
    _sleep_emoji = "\U0001f634"
    _trophy_emoji = "\U0001f3c6"
    _house_emoji = "\U0001f3e0"
    _clock_emoji = "\U0001f552"
    _chart_emoji = "\U0001f4c8"
    if _next_week_earnings:
        _earnings_cards_html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:0.7rem;">'
        for _ei, _es in enumerate(_next_week_earnings):
            _eps_str = f'Est. EPS: ${_es["eps_est"]:.2f}' if _es["eps_est"] is not None else "Est. EPS: N/A"
            _earnings_cards_html += (
                f'<div style="background:rgba(18,51,36,0.03);border:1px solid rgba(18,51,36,0.08);border-radius:12px;padding:0.8rem 1rem;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">'
                f'<div><span style="font-weight:700;font-size:0.9rem;color:{_ETF_CLR.get(ETF_MAP.get(_es["ticker"], ""), "inherit")};">{html_mod.escape(_es["ticker"])}</span> '
                f'<span style="color:#5d6f65;font-size:0.78rem;">{html_mod.escape(_es["name"])}</span></div>'
                f'<span style="font-size:0.72rem;color:#5d6f65;">{html_mod.escape(_es["date"])}</span></div>'
                f'<div style="font-size:0.75rem;color:#5d6f65;margin-bottom:0.6rem;">{_eps_str}</div>'
                f'<div style="display:flex;gap:0.4rem;">'
                f'<div class="earnVoteBtn" data-stock="{html_mod.escape(_es["ticker"])}" data-dir="up" '
                f'onclick="voteEarnings(this)" '
                f'style="flex:1;padding:0.35rem 0.5rem;border:1px solid rgba(25,160,95,0.3);border-radius:8px;'
                f'cursor:pointer;font-weight:700;font-size:0.78rem;color:#19a05f;background:rgba(25,160,95,0.06);text-align:center;transition:all 0.15s;">'
                f'{_up_emoji} Beat <span class="earnCount" style="display:none;margin-left:0.2rem;font-size:0.68rem;opacity:0.8;"></span></div>'
                f'<div class="earnVoteBtn" data-stock="{html_mod.escape(_es["ticker"])}" data-dir="down" '
                f'onclick="voteEarnings(this)" '
                f'style="flex:1;padding:0.35rem 0.5rem;border:1px solid rgba(209,74,52,0.3);border-radius:8px;'
                f'cursor:pointer;font-weight:700;font-size:0.78rem;color:#d14a34;background:rgba(209,74,52,0.06);text-align:center;transition:all 0.15s;">'
                f'{_down_emoji} Miss <span class="earnCount" style="display:none;margin-left:0.2rem;font-size:0.68rem;opacity:0.8;"></span></div>'
                f'</div></div>'
            )
        _earnings_cards_html += '</div>'
    else:
        _earnings_cards_html = f'<div style="font-size:0.85rem;color:#5d6f65;text-align:center;padding:1rem;">{_sleep_emoji} No earnings scheduled this week. Enjoy the quiet!</div>'

    _feud_html = f"""
    <style>
      .challenge-card {{
        background: rgba(251,253,250,0.96);
        border: 1px solid rgba(18,51,36,0.10);
        border-radius: 18px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 4px 16px rgba(16,42,32,0.06);
        position: relative;
        overflow: visible;
      }}
      .challenge-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px; height: 22px;
        background: #0e5f3a;
        color: white;
        font-size: 0.65rem;
        font-weight: 700;
        border-radius: 50%;
        margin-right: 0.4rem;
        vertical-align: middle;
      }}
      .challenge-label {{
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5d6f65;
        margin-bottom: 0.4rem;
        display: flex;
        align-items: center;
      }}
      .challenge-title {{
        font-size: 1.1rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
      }}
      .challenge-desc {{
        font-size: 0.78rem;
        color: #5d6f65;
        margin-bottom: 0.7rem;
      }}
      .votes-header {{
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #5d6f65;
        margin-top: 0.5rem;
        margin-bottom: 0.3rem;
        padding-top: 0.5rem;
        border-top: 1px solid rgba(18,51,36,0.06);
      }}
      .week-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-bottom: 0.8rem;
        padding-bottom: 0.6rem;
        border-bottom: 1px solid rgba(18,51,36,0.08);
      }}
    </style>
    <div style="font-family:'Space Grotesk',sans-serif;color:#102018;">

      <!-- Week header -->
      <div class="week-header">
        <span style="display:inline-block;background:rgba(14,95,58,0.1);color:#0e5f3a;font-size:0.72rem;
            font-weight:700;padding:0.2rem 0.65rem;border-radius:999px;">
          {_week_label}</span>
        <span style="font-size:0.7rem;color:#5d6f65;">
          {_clock_emoji} Voting closes Mon 9 AM ET &middot; Winner at Fri 4 PM ET</span>
      </div>

      <!-- Challenge 1: MVP -->
      <div class="challenge-card" style="z-index:30;position:relative;">
        <div class="challenge-label"><span class="challenge-num">1</span> Weekly Challenge</div>
        <div class="challenge-title">{_trophy_emoji} Who will be MVP this week?</div>
        <div class="challenge-desc">The stock with the highest total return Mon&ndash;Fri wins.</div>
        {_mvp_input_html}
        <div id="mvpVoteHeader" class="votes-header">Community Votes ({_mvp_total} total)</div>
        <div id="mvpVoteBars">{_mvp_bars if _mvp_bars else _no_votes_html}</div>
      </div>

      <!-- Challenge 2: HOH -->
      <div class="challenge-card" style="z-index:20;position:relative;">
        <div class="challenge-label"><span class="challenge-num">2</span> Weekly Challenge</div>
        <div class="challenge-title">{_house_emoji} Who will be Head of Household?</div>
        <div class="challenge-desc">The ETF with the highest average return Mon&ndash;Fri wins.</div>
        {_hoh_input_html}
        <div id="hohVoteHeader" class="votes-header">Community Votes ({_hoh_total} total)</div>
        <div id="hohVoteBars">{_hoh_bars if _hoh_bars else '<div style="font-size:0.8rem;color:#5d6f65;">No votes yet &mdash; be the first!</div>'}</div>
      </div>

      <!-- Challenge 3: Earnings -->
      <div class="challenge-card" style="margin-bottom:0;z-index:10;position:relative;">
        <div class="challenge-label"><span class="challenge-num">3</span> Weekly Challenge</div>
        <div class="challenge-title">{_chart_emoji} Earnings Roulette</div>
        <div class="challenge-desc">Will the stock go UP or DOWN after earnings? Vote before earnings day at market close.</div>
        {_earnings_cards_html}
      </div>
    </div>

    """

    # Single script block — use placeholders to inject data safely
    _feud_js = """
    <script>
    var stocks = __STOCKS_DATA__;
    var sheetUrl = '__SHEET_URL__';
    var serverEarnVotes = __EARN_VOTES__;
    var etfColors = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"};
    // One-time reset: clear old vote data from localStorage
    var FEUD_VERSION = 'v3';
    if (localStorage.getItem('feud_version') !== FEUD_VERSION) {
      localStorage.removeItem('feud_mvp_pick');
      localStorage.removeItem('feud_hoh_pick');
      localStorage.removeItem('feud_voter_id');
      // Clear all earnings votes
      Object.keys(localStorage).forEach(function(k) {
        if (k.indexOf('feud_earn_') === 0) localStorage.removeItem(k);
      });
      localStorage.setItem('feud_version', FEUD_VERSION);
    }
    console.log('Feud loaded, stocks count:', stocks.length);
    var mvpInput = document.getElementById('mvpInput');
    var mvpDropdown = document.getElementById('mvpDropdown');
    var mvpTapped = false;
    if (mvpInput) {
      mvpInput.addEventListener('pointerdown', function() { mvpTapped = true; });
      mvpInput.addEventListener('mousedown', function() { mvpTapped = true; });
      mvpInput.addEventListener('focus', function() {
        if (mvpTapped) { renderMvpDD(this.value, true); }
        mvpTapped = false;
      });
      mvpInput.addEventListener('input', function() { renderMvpDD(this.value, true); });
      mvpInput.addEventListener('keyup', function() { renderMvpDD(this.value, true); });
      if (mvpDropdown) {
        mvpDropdown.addEventListener('click', function(e) { e.stopPropagation(); });
        mvpDropdown.addEventListener('touchstart', function(e) { e.stopPropagation(); });
      }
      document.addEventListener('click', function(e) {
        if (!e.target.closest('#mvp-search-wrap')) mvpDropdown.style.display = 'none';
      });
      document.addEventListener('touchend', function(e) {
        if (!e.target.closest('#mvp-search-wrap')) mvpDropdown.style.display = 'none';
      });
      mvpInput.addEventListener('blur', function() {
        setTimeout(function() { mvpDropdown.style.display = 'none'; }, 200);
      });
      try { window.parent.document.addEventListener('click', function() { mvpDropdown.style.display = 'none'; }); } catch(e) {}
    }

    function renderMvpDD(q, showAll) {
      q = q.toLowerCase().trim();
      if (!q && !showAll) { mvpDropdown.style.display = 'none'; return; }
      var f = q ? stocks.filter(function(s) {
        return s.ticker.toLowerCase().startsWith(q);
      }).slice(0, 8) : stocks;
      if (!f.length) {
        mvpDropdown.innerHTML = '<div style="padding:0.5rem 0.9rem;color:#5d6f65;font-size:0.85rem;">No matches</div>';
      } else {
        mvpDropdown.innerHTML = f.map(function(s) {
          return '<div style="padding:0.5rem 0.9rem;cursor:pointer;font-size:0.85rem;display:flex;justify-content:space-between;align-items:center;" ' +
            'onmouseover="this.style.background=\\\'rgba(14,95,58,0.06)\\\'" onmouseout="this.style.background=\\\'\\\'" ' +
            'onclick="selectMvp(\\\'' + s.ticker + '\\\',\\\'' + s.name + '\\\')">' +
            '<span><b>' + s.ticker + '</b> <span style="color:#5d6f65;font-size:0.78rem;">' + s.name + '</span></span>' +
            '<span style="font-size:0.65rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:999px;background:rgba(14,95,58,0.08);color:' + (etfColors[s.etf] || '#0e5f3a') + ';">' + s.etf + '</span></div>';
        }).join('');
      }
      mvpDropdown.style.display = 'block';
    }

    function getVoterId() {
      var voterId = localStorage.getItem('feud_voter_id');
      if (!voterId) { voterId = 'anon_' + Math.random().toString(36).substr(2, 9); localStorage.setItem('feud_voter_id', voterId); }
      return voterId;
    }

    function selectMvp(ticker, name) {
      mvpDropdown.style.display = 'none';
      mvpInput.value = '';
      document.getElementById('mvp-search-wrap').style.display = 'none';
      document.getElementById('mvpPick').style.display = 'block';
      document.getElementById('mvpPickTicker').textContent = ticker;
      document.getElementById('mvpPickName').textContent = name;
      localStorage.setItem('feud_mvp_pick', ticker);
      var voterId = getVoterId();
      fetch(sheetUrl + '?action=mvp_vote&voter=' + encodeURIComponent(voterId) + '&pick=' + encodeURIComponent(ticker))
        .then(function() { return fetch(sheetUrl + '?action=get_mvp_votes'); })
        .then(function(r) { return r.json(); })
        .then(function(data) { renderVoteBars('mvpVoteHeader', 'mvpVoteBars', data); })
        .catch(function(){});
    }

    function renderVoteBars(headerId, barsId, data) {
      var votes = data.votes || {};
      var total = data.total || 0;
      var header = document.getElementById(headerId);
      var bars = document.getElementById(barsId);
      if (header) header.textContent = 'Community Votes (' + total + ' total)';
      if (!bars) return;
      var sorted = Object.entries(votes).sort(function(a, b) { return b[1] - a[1]; });
      var top = sorted.slice(0, 4);
      var otherCount = sorted.slice(4).reduce(function(s, x) { return s + x[1]; }, 0);
      if (otherCount > 0) top.push(['Other', otherCount]);
      var colors = ['#19a05f', '#0e5f3a', '#13492f', '#5d6f65', '#b8b8b8'];
      if (!top.length) {
        bars.innerHTML = '<div style="font-size:0.8rem;color:#5d6f65;">No votes yet \\u2014 be the first!</div>';
        return;
      }
      bars.innerHTML = top.map(function(item, i) {
        var ticker = item[0], count = item[1];
        var pct = total > 0 ? Math.round(count / total * 100) : 0;
        var color = colors[Math.min(i, colors.length - 1)];
        return '<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">' +
          '<span style="font-weight:700;font-size:0.85rem;min-width:4.5rem;color:' + (etfColors[ticker] || 'inherit') + ';">' + ticker + '</span>' +
          '<div style="flex:1;height:26px;background:rgba(18,51,36,0.06);border-radius:8px;overflow:hidden;">' +
          '<div style="height:100%;width:' + Math.max(pct, 5) + '%;background:' + color + ';border-radius:8px;' +
          'display:flex;align-items:center;padding-left:0.5rem;font-size:0.7rem;font-weight:700;color:#fff;">' +
          '\\u00a0' + pct + '%</div></div>' +
          '<span style="font-size:0.78rem;color:#5d6f65;min-width:4rem;text-align:right;">' + count + ' votes</span></div>';
      }).join('');
    }

    function changeMvp() {
      document.getElementById('mvp-search-wrap').style.display = 'block';
      document.getElementById('mvpPick').style.display = 'none';
      localStorage.removeItem('feud_mvp_pick');
      var voterId = getVoterId();
      fetch(sheetUrl + '?action=mvp_remove&voter=' + encodeURIComponent(voterId))
        .then(function() { return fetch(sheetUrl + '?action=get_mvp_votes'); })
        .then(function(r) { return r.json(); })
        .then(function(data) { renderVoteBars('mvpVoteHeader', 'mvpVoteBars', data); })
        .catch(function(){});
      if (mvpInput) mvpInput.focus();
    }

    // Restore votes from server (works across devices)
    fetch(sheetUrl + '?action=get_my_votes&voter=' + encodeURIComponent(getVoterId()))
      .then(function(r) { return r.json(); })
      .then(function(picks) {
        // Restore MVP pick
        if (picks.mvp && document.getElementById('mvpPick')) {
          var s = stocks.find(function(x) { return x.ticker === picks.mvp; });
          if (s) {
            document.getElementById('mvp-search-wrap').style.display = 'none';
            document.getElementById('mvpPick').style.display = 'block';
            document.getElementById('mvpPickTicker').textContent = s.ticker;
            document.getElementById('mvpPickName').textContent = s.name;
            localStorage.setItem('feud_mvp_pick', s.ticker);
          }
        }
        // Restore HOH pick
        if (picks.hoh) {
          localStorage.setItem('feud_hoh_pick', picks.hoh);
          document.querySelectorAll('.hohBtn').forEach(function(b) {
            if (b.textContent.trim().includes(picks.hoh)) {
              b.style.borderColor = '#0e5f3a';
              b.style.background = 'rgba(14,95,58,0.1)';
              b.style.color = '#0e5f3a';
            }
          });
        }
        // Restore earnings picks
        if (picks.earn && typeof picks.earn === 'object') {
          Object.keys(picks.earn).forEach(function(stock) {
            var val = picks.earn[stock]; // e.g. "AAPL_up"
            var dir = val.split('_').pop(); // "up" or "down"
            localStorage.setItem('feud_earn_' + stock, dir);
            document.querySelectorAll('.earnVoteBtn').forEach(function(btn) {
              if (btn.dataset.stock === stock && btn.dataset.dir === dir) {
                if (dir === 'up') {
                  btn.style.background = 'rgba(25,160,95,0.12)';
                  btn.style.borderColor = '#19a05f';
                } else {
                  btn.style.background = 'rgba(209,74,52,0.12)';
                  btn.style.borderColor = '#d14a34';
                }
              }
            });
          });
        }
      })
      .catch(function(){
        // Fallback to localStorage
        var savedMvp = localStorage.getItem('feud_mvp_pick');
        if (savedMvp && document.getElementById('mvpPick')) {
          var s = stocks.find(function(x) { return x.ticker === savedMvp; });
          if (s) {
            document.getElementById('mvp-search-wrap').style.display = 'none';
            document.getElementById('mvpPick').style.display = 'block';
            document.getElementById('mvpPickTicker').textContent = s.ticker;
            document.getElementById('mvpPickName').textContent = s.name;
          }
        }
      });

    function selectHoh(btn, etf) {
      var currentPick = localStorage.getItem('feud_hoh_pick');
      var voterId = getVoterId();
      if (currentPick === etf) {
        // Deselect: clicking same button again
        btn.style.borderColor = 'rgba(18,51,36,0.12)';
        btn.style.background = 'white';
        btn.style.color = '#102018';
        localStorage.removeItem('feud_hoh_pick');
        fetch(sheetUrl + '?action=hoh_remove&voter=' + encodeURIComponent(voterId))
          .then(function() { return fetch(sheetUrl + '?action=get_hoh_votes'); })
          .then(function(r) { return r.json(); })
          .then(function(data) { renderVoteBars('hohVoteHeader', 'hohVoteBars', data); })
          .catch(function(){});
        return;
      }
      document.querySelectorAll('.hohBtn').forEach(function(b) {
        b.style.borderColor = 'rgba(18,51,36,0.12)';
        b.style.background = 'white';
        b.style.color = '#102018';
      });
      btn.style.borderColor = '#0e5f3a';
      btn.style.background = 'rgba(14,95,58,0.1)';
      btn.style.color = '#0e5f3a';
      localStorage.setItem('feud_hoh_pick', etf);
      fetch(sheetUrl + '?action=hoh_vote&voter=' + encodeURIComponent(voterId) + '&pick=' + encodeURIComponent(etf))
        .then(function() { return fetch(sheetUrl + '?action=get_hoh_votes'); })
        .then(function(r) { return r.json(); })
        .then(function(data) { renderVoteBars('hohVoteHeader', 'hohVoteBars', data); })
        .catch(function(){});
    }

    var savedHoh = localStorage.getItem('feud_hoh_pick');
    if (savedHoh) {
      document.querySelectorAll('.hohBtn').forEach(function(b) {
        if (b.textContent.trim().includes(savedHoh)) {
          b.style.borderColor = '#0e5f3a';
          b.style.background = 'rgba(14,95,58,0.1)';
          b.style.color = '#0e5f3a';
        }
      });
    }

    // --- Earnings Vote ---
    function updateEarnCounts(stock, serverData) {
      var data = serverData || serverEarnVotes;
      var stockData = data[stock] || { up: 0, down: 0 };
      document.querySelectorAll('.earnVoteBtn').forEach(function(b) {
        if (b.dataset.stock !== stock) return;
        var countEl = b.querySelector('.earnCount');
        if (!countEl) return;
        var count = stockData[b.dataset.dir] || 0;
        if (count > 0) {
          countEl.textContent = '(' + count + ')';
          countEl.style.display = 'inline';
        } else {
          countEl.textContent = '';
          countEl.style.display = 'none';
        }
      });
    }

    function refreshEarnVotes(stock) {
      fetch(sheetUrl + '?action=get_earn_votes')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          serverEarnVotes = data;
          updateEarnCounts(stock, data);
        })
        .catch(function(){});
    }

    function voteEarnings(btn) {
      var stock = btn.dataset.stock;
      var dir = btn.dataset.dir;
      var currentVote = localStorage.getItem('feud_earn_' + stock);
      var parent = btn.parentElement;
      var voterId = getVoterId();
      var voterKey = 'earn_' + voterId + '_' + stock;

      // If clicking the same vote, deselect
      if (currentVote === dir) {
        btn.style.background = 'white';
        btn.style.borderColor = dir === 'up' ? 'rgba(25,160,95,0.3)' : 'rgba(209,74,52,0.3)';
        localStorage.removeItem('feud_earn_' + stock);
        fetch(sheetUrl + '?action=earn_remove&voter=' + encodeURIComponent(voterKey))
          .then(function() { refreshEarnVotes(stock); })
          .catch(function(){});
        return;
      }

      // Deselect siblings
      parent.querySelectorAll('.earnVoteBtn').forEach(function(b) {
        b.style.background = 'white';
        b.style.borderColor = b.dataset.dir === 'up' ? 'rgba(25,160,95,0.3)' : 'rgba(209,74,52,0.3)';
      });
      // Select this one
      if (dir === 'up') {
        btn.style.background = 'rgba(25,160,95,0.12)';
        btn.style.borderColor = '#19a05f';
      } else {
        btn.style.background = 'rgba(209,74,52,0.12)';
        btn.style.borderColor = '#d14a34';
      }
      localStorage.setItem('feud_earn_' + stock, dir);
      fetch(sheetUrl + '?action=earn_vote&voter=' + encodeURIComponent(voterKey) + '&pick=' + encodeURIComponent(stock + '_' + dir))
        .then(function() { refreshEarnVotes(stock); })
        .catch(function(){});
    }

    // Restore earnings votes and counts
    document.querySelectorAll('.earnVoteBtn').forEach(function(btn) {
      var stock = btn.dataset.stock;
      var saved = localStorage.getItem('feud_earn_' + stock);
      if (saved === btn.dataset.dir) {
        if (saved === 'up') {
          btn.style.background = 'rgba(25,160,95,0.12)';
          btn.style.borderColor = '#19a05f';
        } else {
          btn.style.background = 'rgba(209,74,52,0.12)';
          btn.style.borderColor = '#d14a34';
        }
      }
      updateEarnCounts(stock);
    });

    function resizeFrame() {
      try {
        var h = document.body.scrollHeight + 20;
        if (window.frameElement) {
          window.frameElement.style.setProperty('height', h + 'px', 'important');
        }
        // Also try the parent container
        try {
          var container = window.frameElement.parentElement;
          if (container) container.style.setProperty('height', h + 'px', 'important');
        } catch(e2) {}
      } catch(e) {}
    }
    window.addEventListener('load', resizeFrame);
    window.addEventListener('resize', resizeFrame);
    setTimeout(resizeFrame, 50);
    setTimeout(resizeFrame, 300);
    setTimeout(resizeFrame, 1000);
    </script>
    """
    _feud_js = _feud_js.replace('__STOCKS_DATA__', _stock_list_js).replace('__SHEET_URL__', REACTIONS_SHEET_URL).replace('__EARN_VOTES__', _earn_votes_js)
    _feud_html += _feud_js

    _feud_base_height = 630 + len(_next_week_earnings) * 60
    components.html(_feud_html, height=_feud_base_height, scrolling=False)

    # --- System Predictions (moved from Dashboard) ---
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.5rem;margin:1.2rem 0 0.5rem;">'
        '<span style="font-size:1.3rem;">\U0001f52e</span>'
        '<span style="font-size:1.1rem;font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
        'color:var(--accent);">This Week\'s Predictions</span></div>',
        unsafe_allow_html=True,
    )

    if "_returns" in st.session_state:
        _r = st.session_state["_returns"]
        _vt = st.session_state["_valid_tickers"]
        _sp = st.session_state["_start_prices"]
        _div = st.session_state["_dividends"]
        _ep = st.session_state["_end_prices"]
        _fr = pd.Series({
            t: ((INVESTMENT / _sp[t] * _ep[t] + INVESTMENT / _sp[t] * _div.get(t, 0.0)) / INVESTMENT - 1) * 100
            for t in _vt
        }).sort_values(ascending=False)
        preds = generate_predictions(_r, _vt, NAME_MAP, ETF_MAP, _fr, _div, _sp, INVESTMENT)
        pred_history = load_pred_history()

        if preds:
            record_predictions(preds, end_date.isoformat(), pred_history)

            pred_grid_html = '<div class="pred-grid">'
            for pred in preds:
                conf = pred.get("confidence", 50)
                pred_key = f'{pred["title"]}_{pred["ticker"]}'
                votes = pred_history.get("votes", {}).get(pred_key, {"up": 0, "down": 0})
                total_votes = votes["up"] + votes["down"]
                agree_pct = int(votes["up"] / total_votes * 100) if total_votes > 0 else 0

                vote_bar = ""
                if total_votes > 0:
                    vote_bar = (
                        f'<div style="display:flex;align-items:center;gap:0.4rem;margin-top:0.3rem;'
                        f'padding-top:0.3rem;border-top:1px solid rgba(14,95,58,0.1);">'
                        f'<span style="font-size:0.7rem;">\U0001f44d {votes["up"]}</span>'
                        f'<span style="font-size:0.7rem;">\U0001f44e {votes["down"]}</span>'
                        f'<span style="font-size:0.6rem;color:var(--muted);margin-left:auto;">{agree_pct}% agree</span>'
                        f'</div>'
                    )
                pred_grid_html += (
                    f'<div class="pred-card">'
                    f'<div class="pred-icon">{pred["icon"]}</div>'
                    f'<div class="pred-title">{html_mod.escape(pred["title"])}</div>'
                    f'<div class="pred-ticker">{pred.get("emoji", "")} <span style="color:{_ETF_CLR.get(ETF_MAP.get(pred["ticker"], ""), _ETF_CLR.get(pred["ticker"], "inherit"))};">{html_mod.escape(pred["ticker"])}</span></div>'
                    f'<div class="pred-name">{html_mod.escape(pred["name"])}</div>'
                    f'<div class="pred-detail">{html_mod.escape(pred["detail"])}</div>'
                    f'<div class="pred-confidence">{conf}% confidence</div>'
                    f'{vote_bar}'
                    f'</div>'
                )
            pred_grid_html += '</div>'
            st.markdown(pred_grid_html, unsafe_allow_html=True)

            past_results = check_past_predictions(pred_history, _fr)
            if past_results:
                scored = [r for r in past_results if r["correct"] is not None]
                if scored:
                    correct_count = sum(1 for r in scored if r["correct"])
                    total_scored = len(scored)
                    accuracy = int(correct_count / total_scored * 100)
                    st.markdown(
                        f'<div style="margin-top:0.5rem;padding:0.5rem 0.8rem;background:rgba(14,95,58,0.06);'
                        f'border:1px solid rgba(14,95,58,0.15);border-radius:12px;font-size:0.8rem;">'
                        f'\U0001f3af <b>Past Accuracy:</b> {correct_count}/{total_scored} predictions correct ({accuracy}%)'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.caption("\U0001f916 System-generated based on 5-day momentum, volatility, and trend analysis. Not financial advice!")
    else:
        st.info("Visit the Dashboard tab first to load stock data.")

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
