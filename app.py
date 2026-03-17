import json
import os
import datetime
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

SUBSCRIBERS_FILE = "subscribers.json"

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return json.load(f)
    return []

def save_subscribers(subs):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subs, f, indent=2)


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
table.leaderboard tr:first-child td:first-child::before {
    content: "▲ ";
    color: var(--accent-2);
}
table.leaderboard tr:last-child td:first-child::before {
    content: "▼ ";
    color: var(--negative);
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
default_end = datetime.date.today()

start_date = st.sidebar.date_input("Start Date", value=default_start)
end_date = st.sidebar.date_input("End Date", value=default_end)

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
remove_ticker = st.sidebar.selectbox("Remove a ticker", [""] + remove_options)
if st.sidebar.button("Remove Ticker") and remove_ticker:
    config["players"] = [p for p in config["players"] if p["ticker"] != remove_ticker]
    with open("players.json", "w") as f:
        json.dump(config, f, indent=2)
    st.sidebar.success(f"Removed {remove_ticker}!")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Current Roster")
roster_search = st.sidebar.text_input("Search stocks", placeholder="Filter by name or ticker")
for p in sorted(PLAYERS, key=lambda x: x['ticker'].upper()):
    if roster_search and roster_search.upper() not in p['ticker'].upper() and roster_search.upper() not in p['name'].upper():
        continue
    etf_label = f"[{p.get('etf', '')}] " if p.get('etf') else ""
    st.sidebar.write(f"{etf_label}**{p['ticker']}** — {p['name']}")

# --- Main ---
st.markdown("""
<section class="hero-card">
  <div class="hero-kicker">League Table</div>
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
for i, (etf, total) in enumerate(etf_ranked):
    if i == 0:
        label = "🏆"
    elif i == len(etf_ranked) - 1:
        label = "📉"
    else:
        label = "🔹"
    parts.append(f"{label} {ETF_EMOJI.get(etf, '')} {etf} ({total:+.2f}%)")
best_ticker = final_returns.index[0]
worst_ticker = final_returns.index[-1]
metric_cols = st.columns(2)
metric_cols[0].markdown(
    f"""
    <div class="metric-card">
      <div class="metric-label">Highest Performing</div>
      <div class="metric-value positive">{ETF_EMOJI.get(ETF_MAP.get(best_ticker, ''), '')} {best_ticker}</div>
      <div class="metric-detail">Table leader: {NAME_MAP[best_ticker]} {final_returns[best_ticker]:+.2f}%</div>
    </div>
    """,
    unsafe_allow_html=True,
)
metric_cols[1].markdown(
    f"""
    <div class="metric-card">
      <div class="metric-label">Lowest Performing</div>
      <div class="metric-value negative">{ETF_EMOJI.get(ETF_MAP.get(worst_ticker, ''), '')} {worst_ticker}</div>
      <div class="metric-detail">Bottom of the table: {NAME_MAP[worst_ticker]} {final_returns[worst_ticker]:+.2f}%</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="section-card">
      <div class="section-heading">Matchday Report</div>
      <p class="section-copy">Division split: {' &nbsp;&nbsp; '.join(parts)}</p>
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
    xaxis_title="Fixture Date",
    yaxis_title="Table Movement (%)",
    legend_title="Position",
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
    xaxis_title="Fixture Date",
    yaxis_title="Table Movement (%)",
    legend_title="Position",
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
  <div class="section-heading">League Table</div>
  <p class="section-copy"><strong>Price Return (%)</strong> works like raw goal difference. <strong>Total Return (%)</strong> adds dividend payouts, which is the final standings number.</p>
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
    rows.append({
        "Rank": rank,
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


def leaderboard_row_style(row):
    fraction = row.name / total_rows
    color = interpolate_hex_color("#19a05f", "#d14a34", fraction)
    return [f"color: {color};"] * len(row)


styled_df = (
    df.style
    .hide(axis="index")
    .set_table_attributes('class="leaderboard"')
    .apply(leaderboard_row_style, axis=1)
)
st.markdown(styled_df.to_html(escape=False), unsafe_allow_html=True)

# --- Subscribe ---
st.markdown("---")
st.markdown("""
<section class="section-card">
  <div class="section-heading">Matchday Alerts</div>
  <p class="section-copy">Get the updated table in your inbox after the rounds you care about.</p>
</section>
""", unsafe_allow_html=True)
sub_col1, sub_col2, sub_col3 = st.columns([2, 1, 1])
with sub_col1:
    sub_email = st.text_input("Email address", placeholder="you@example.com", key="sub_email")
with sub_col2:
    sub_frequency = st.selectbox("Frequency", ["Weekly", "Monthly", "Quarterly"], key="sub_freq")
with sub_col3:
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        subscribe_clicked = st.button("Subscribe")
    with col_btn2:
        unsubscribe_clicked = st.button("Unsubscribe")

if subscribe_clicked:
    if not sub_email or "@" not in sub_email:
        st.error("Please enter a valid email address.")
    else:
        subs = load_subscribers()
        existing = next((s for s in subs if s["email"].lower() == sub_email.lower()), None)
        if existing:
            existing["frequency"] = sub_frequency.lower()
            st.info(f"Updated subscription to {sub_frequency.lower()}.")
        else:
            subs.append({"email": sub_email, "frequency": sub_frequency.lower()})
            st.success(f"Subscribed {sub_email} for {sub_frequency.lower()} updates!")
        save_subscribers(subs)

if unsubscribe_clicked:
    if not sub_email:
        st.error("Please enter your email address.")
    else:
        subs = load_subscribers()
        new_subs = [s for s in subs if s["email"].lower() != sub_email.lower()]
        if len(new_subs) < len(subs):
            save_subscribers(new_subs)
            st.success(f"Unsubscribed {sub_email}.")
        else:
            st.warning("Email not found in subscriber list.")
