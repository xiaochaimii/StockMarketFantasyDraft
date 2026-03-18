import json
import os
import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go


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
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="select"],
[data-testid="stSidebar"] .stDateInput {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] textarea {
    color: #102018 !important;
    -webkit-text-fill-color: #102018 !important;
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
    background: linear-gradient(180deg, var(--accent-2) 0%, var(--accent) 100%);
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
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"],
.stDateInput input {
    border-radius: 14px !important;
}
div[data-testid="stButton"] button {
    border-radius: 999px;
    border: 0;
    background: linear-gradient(90deg, var(--accent) 0%, #0f8773 100%);
    color: #fff;
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

st.sidebar.markdown("---")
st.sidebar.subheader("Add/Remove Tickers")
new_ticker = st.sidebar.text_input("Add a ticker symbol", placeholder="e.g. TSLA")
if st.sidebar.button("Add Ticker") and new_ticker:
    ticker_upper = new_ticker.strip().upper()
    existing = {p["ticker"] for p in config["players"]}
    if ticker_upper in existing:
        st.sidebar.warning(f"{ticker_upper} is already in the list.")
    else:
        config["players"].append({"etf": "", "name": ticker_upper, "ticker": ticker_upper})
        with open("players.json", "w") as f:
            json.dump(config, f, indent=2)
        st.sidebar.success(f"Added {ticker_upper}!")
        st.rerun()

# Remove ticker
remove_options = [p["ticker"] for p in config["players"]]
remove_ticker = st.sidebar.selectbox("Remove a ticker", [""] + remove_options, format_func=lambda x: "Select a ticker" if x == "" else x)
if st.sidebar.button("Remove Ticker") and remove_ticker:
    config["players"] = [p for p in config["players"] if p["ticker"] != remove_ticker]
    with open("players.json", "w") as f:
        json.dump(config, f, indent=2)
    st.sidebar.success(f"Removed {remove_ticker}!")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("Search Stocks")
search_options = [""] + [f"{p['ticker']} — {p['name']}" for p in sorted(PLAYERS, key=lambda x: x['ticker'].upper())]
roster_selection = st.sidebar.selectbox("Search stocks", search_options, format_func=lambda x: "Select a stock" if x == "" else x, label_visibility="collapsed", key="stock_search")
roster_search = roster_selection.split(" — ")[0] if roster_selection else ""
if roster_search:
    st.sidebar.button("Reset Search", on_click=lambda: st.session_state.update({"stock_search": ""}))

# --- Main ---
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

if start_date >= end_date:
    st.error("Start date must be before end date.")
    st.stop()


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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
    parts.append(f"{label} {ETF_EMOJI.get(etf, '')} {etf} ({total:+.2f}%)")
best_ticker = final_returns.index[0]
worst_ticker = final_returns.index[-1]
metric_cols = st.columns(2)
metric_cols[0].markdown(
    f"""
    <div class="metric-card">
      <div class="metric-label">MVP</div>
      <div class="metric-value positive">{ETF_EMOJI.get(ETF_MAP.get(best_ticker, ''), '')} {best_ticker}</div>
      <div class="metric-detail">{NAME_MAP[best_ticker]} <span class="positive">{final_returns[best_ticker]:+.2f}%</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)
metric_cols[1].markdown(
    f"""
    <div class="metric-card">
      <div class="metric-label">Benchwarmer</div>
      <div class="metric-value negative">{ETF_EMOJI.get(ETF_MAP.get(worst_ticker, ''), '')} {worst_ticker}</div>
      <div class="metric-detail">{NAME_MAP[worst_ticker]} <span class="negative">({abs(final_returns[worst_ticker]):.2f}%)</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="section-card">
      <div class="section-heading">ETF Standing ({start_date.strftime('%b %d, %Y')} – {end_date.strftime('%b %d, %Y')})</div>
      {''.join(f'<p class="section-copy">{p}</p>' for p in parts)}
    </section>
    """,
    unsafe_allow_html=True,
)

# --- Plotly Line Chart: Top 10 Winners ---
fig_top = go.Figure()

for rank, ticker in enumerate(top10_tickers, start=1):
    ret = final_returns[ticker]
    fig_top.add_trace(go.Scatter(
        x=returns.index,
        y=returns[ticker],
        mode="lines",
        name=f"#{rank} {NAME_MAP[ticker]} ({ticker}) {ret:+.2f}%",
    ))

fig_top.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.6)

fig_top.update_layout(
    title="Top 10 Stocks In the Money",
    xaxis_title="Trading Window",
    yaxis_title="Total Return (%)",
    legend_title="Stock",
    hovermode="x unified",
    height=500,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#fbfdf9",
    font=dict(family="Space Grotesk, sans-serif", color="#1f1a17"),
    title_font=dict(size=20),
    legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, xanchor="left"),
    margin=dict(t=90, r=24, b=90, l=40),
)
fig_top.update_xaxes(showgrid=False)
fig_top.update_yaxes(gridcolor="rgba(31, 26, 23, 0.08)", zeroline=False)

col1, col2 = st.columns(2)

col1.plotly_chart(fig_top, use_container_width=True)

# --- Plotly Line Chart: Top 10 Losers ---
fig_bottom = go.Figure()

total = len(final_returns)
for i, ticker in enumerate(bottom10_tickers):
    rank = total - len(bottom10_tickers) + i + 1
    ret = final_returns[ticker]
    fig_bottom.add_trace(go.Scatter(
        x=returns.index,
        y=returns[ticker],
        mode="lines",
        name=f"#{rank} {NAME_MAP[ticker]} ({ticker}) {ret:+.2f}%",
    ))

fig_bottom.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.6)

fig_bottom.update_layout(
    title="Bottom 10 Stocks Out of the Money",
    xaxis_title="Trading Window",
    yaxis_title="Total Return (%)",
    legend_title="Stock",
    hovermode="x unified",
    height=500,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#fbfdf9",
    font=dict(family="Space Grotesk, sans-serif", color="#1f1a17"),
    title_font=dict(size=20),
    legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, xanchor="left"),
    margin=dict(t=90, r=24, b=90, l=40),
)
fig_bottom.update_xaxes(showgrid=False)
fig_bottom.update_yaxes(gridcolor="rgba(31, 26, 23, 0.08)", zeroline=False)

col2.plotly_chart(fig_bottom, use_container_width=True)

# --- Leaderboard ---
st.markdown("""
<section class="section-card">
  <div class="section-heading">Leaderboard</div>
  <p class="section-copy"><strong>Price Return (%)</strong> is the percentage change in share price over the period, excluding dividends: <code>(End Price - Start Price) / Start Price × 100</code>.</p>
  <p class="section-copy"><strong>Total Return (%)</strong> is the percentage return including both share price change and dividend payouts: <code>((End Price - Start Price) + Dividends) / Start Price × 100</code>.</p>
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
    # Final value = price return + dividends
    price_value = INVESTMENT * (1 + ret / 100)
    final_value = price_value + div_income
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
        "Dividends": format_signed_currency(div_income),
        "Total Return": format_signed_currency(final_value),
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
st.markdown(styled_df.to_html(escape=False), unsafe_allow_html=True)

# --- Subscribe ---
st.markdown("---")
