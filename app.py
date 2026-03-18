import html as html_mod
import json
import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import plotly.graph_objects as go


def is_market_open():
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


REFRESH_INTERVAL = timedelta(seconds=60) if is_market_open() else None


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
st.set_page_config(page_title="Stock Market Fantasy Draft", layout="wide")

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
    padding: 1.6rem 1.75rem;
    border-radius: 28px;
    margin-bottom: 1.25rem;
    position: relative;
    overflow: hidden;
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
    padding: 1rem 1.2rem 1.25rem;
    margin-top: 1rem;
}
.metric-card {
    background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(242, 248, 241, 0.96) 100%);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 1rem 1.1rem;
    box-shadow: 0 12px 24px rgba(82, 58, 32, 0.08);
    position: relative;
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

@st.cache_data(ttl=60)
def fetch_returns(tickers, start, end):
    """Download adjusted prices and compute daily cumulative % return."""
    data = yf.download(
        tickers,
        start=start,
        end=end + datetime.timedelta(days=1),
        auto_adjust=True,
        progress=False,
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

    mvp_streak, mvp_history = _streak_and_history(mvp_series)
    bench_streak, bench_history = _streak_and_history(bench_series)
    return {
        "mvp_streak": mvp_streak,
        "bench_streak": bench_streak,
        "mvp_history": mvp_history,
        "bench_history": bench_history,
    }


tab_dashboard, tab_admin = st.tabs(["Dashboard", "Admin"])

with tab_dashboard:
    st.markdown("""
    <section class="hero-card">
      <h1 class="hero-title">Stock Market Draft Standings</h1>
      <div class="hero-meta">
        <span class="hero-pill">Window: """ + start_date.strftime("%b %d, %Y") + """ to """ + end_date.strftime("%b %d, %Y") + """</span>
        <span class="hero-pill">Entry stake: $""" + f"{INVESTMENT:.0f}" + """ per stock</span>
        <span class="hero-pill">Stocks tracked: """ + str(len(TICKERS)) + """</span>
      </div>
    </section>
    """, unsafe_allow_html=True)

    @st.fragment(run_every=REFRESH_INTERVAL)
    def live_dashboard():
        # --- Live status indicator ---
        now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
        timestamp = now_et.strftime("%I:%M:%S %p ET")
        if is_market_open():
            import streamlit.components.v1 as components
            components.html(
                f'<div style="display:flex;align-items:center;gap:0.5rem;font-family:sans-serif;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#19a05f;'
                f'box-shadow:0 0 6px #19a05f;"></span>'
                f'<span style="font-size:0.82rem;color:#888;">'
                f'<strong style="color:#19a05f;">LIVE</strong> &middot; Updated {timestamp} &middot; '
                f'Next refresh in <span id="refresh-countdown">60</span>s'
                f'</span></div>'
                f'<script>'
                f'(function() {{'
                f'  var el = document.getElementById("refresh-countdown");'
                f'  if (!el) return;'
                f'  var seconds = 60;'
                f'  var timer = setInterval(function() {{'
                f'    seconds--;'
                f'    if (seconds <= 0) {{ clearInterval(timer); el.textContent = "0"; return; }}'
                f'    el.textContent = seconds;'
                f'  }}, 1000);'
                f'}})()'
                f'</script>',
                height=30,
            )
        else:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.75rem;">'
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--muted);"></span>'
                f'<span style="font-size:0.82rem;color:var(--muted);">'
                f'Market closed &middot; Last updated {timestamp}'
                f'</span></div>',
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
        parts = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (etf, total) in enumerate(etf_ranked):
            label = medals[i] if i < len(medals) else ""
            parts.append(f"{label} {ETF_EMOJI.get(etf, '')} {html_mod.escape(etf)} ({total:+.2f}%)")
        best_ticker = final_returns.index[0]
        worst_ticker = final_returns.index[-1]
        throne = compute_throne_history(returns, valid_tickers, NAME_MAP)
        metric_cols = st.columns(2)
        metric_cols[0].markdown(
            f"""
            <div class="metric-card mvp">
              <div class="metric-label">MVP</div>
              <div class="metric-value positive">{ETF_EMOJI.get(ETF_MAP.get(best_ticker, ''), '')} {html_mod.escape(best_ticker)}</div>
              <div class="metric-detail">{html_mod.escape(NAME_MAP[best_ticker])} <span class="positive">{final_returns[best_ticker]:+.2f}%</span></div>
              <div class="metric-detail">🔥 {throne['mvp_streak']} day streak</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        metric_cols[1].markdown(
            f"""
            <div class="metric-card bench">
              <div class="metric-label">Benchwarmer</div>
              <div class="metric-value negative">{ETF_EMOJI.get(ETF_MAP.get(worst_ticker, ''), '')} {html_mod.escape(worst_ticker)}</div>
              <div class="metric-detail">{html_mod.escape(NAME_MAP[worst_ticker])} <span class="negative">({abs(final_returns[worst_ticker]):.2f}%)</span></div>
              <div class="metric-detail">📉 {throne['bench_streak']} day streak</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <section class="section-card" style="text-align: center;">
              <div class="section-heading">ETF Standing ({start_date.strftime('%b %d, %Y')} – {end_date.strftime('%b %d, %Y')})</div>
              {''.join(f'<p class="section-copy">{p}</p>' for p in parts)}
            </section>
            """,
            unsafe_allow_html=True,
        )

        # --- Throne History ---
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

            # Build y-axis tick labels from final-day ranks
            tick_labels = {}
            for i, ticker in enumerate(tickers):
                rank_vals = ranks_df[ticker].values
                final_bump_rank = int(rank_vals[-1])
                final_rank = label_rank_fn(final_bump_rank) if label_rank_fn else final_bump_rank
                final_ret = float(final_returns[ticker])
                color = colors[i % len(colors)]
                tick_labels[final_bump_rank] = f"<span style='color:{color}'><b>#{final_rank}</b> {NAME_MAP[ticker]} {final_ret:.2f}%</span>"

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
                       gridcolor="rgba(31, 26, 23, 0.06)", side="right"),
            hovermode="x",
            hoverlabel=dict(bgcolor="white", font_color="#102018", font_size=13, bordercolor="#ccc"),
            height=500, showlegend=False,
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
        col1, col2 = st.columns(2)
        col1.plotly_chart(fig_top, use_container_width=True, config=chart_config)

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

        col2.plotly_chart(fig_bottom, use_container_width=True, config=chart_config)

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
            arrow = "▲" if total_return >= 0 else "▼"
            rows.append({
                "Rank": f"{arrow} {rank}",
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

        # Find the first row with a down arrow (negative total return)
        first_negative_idx = next((i for i, r in enumerate(rows) if r["Rank"].startswith("▼")), None)

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
        st.markdown(f'<div style="overflow-x: auto;">{styled_df.to_html(escape=True)}</div>', unsafe_allow_html=True)

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
                password_input = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter admin password")
                submitted = st.form_submit_button("Login", use_container_width=True)
                if submitted:
                    if password_input == st.secrets.get("ADMIN_PASSWORD", ""):
                        st.session_state.admin_authenticated = True
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
    else:
        st.markdown("")
        col_mgmt = st.columns([1, 2, 1])[1]
        with col_mgmt:
            st.markdown("#### Add Ticker")
            new_ticker = st.text_input("Ticker symbol", placeholder="e.g. TSLA", label_visibility="collapsed")
            if st.button("Add Ticker", use_container_width=True) and new_ticker:
                ticker_upper = new_ticker.strip().upper()
                existing = {p["ticker"] for p in config["players"]}
                if ticker_upper in existing:
                    st.warning(f"{ticker_upper} is already in the list.")
                else:
                    config["players"].append({"etf": "", "name": ticker_upper, "ticker": ticker_upper})
                    with open("players.json", "w") as f:
                        json.dump(config, f, indent=2)
                    st.success(f"Added {ticker_upper}!")
                    st.rerun()

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
