import json
import datetime
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

# --- Config ---
st.set_page_config(page_title="Stock Market Fantasy Draft", layout="wide")

st.markdown("""
<style>
* { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji' !important; }
table td, table th { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji' !important; }
table.leaderboard { width: 100% !important; }
table.leaderboard td, table.leaderboard th { padding: 8px 12px; text-align: left; }
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
st.sidebar.title("Fantasy Draft Settings")

default_start = datetime.date(2026, 3, 6)
default_end = datetime.date.today()

start_date = st.sidebar.date_input("Start Date", value=default_start)
end_date = st.sidebar.date_input("End Date", value=default_end)

st.sidebar.markdown("---")
st.sidebar.subheader("Add / Remove Tickers")
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
st.sidebar.subheader("Stocks Picked")
roster_search = st.sidebar.text_input("Search stocks", placeholder="Filter by name or ticker")
for p in sorted(PLAYERS, key=lambda x: x['ticker'].upper()):
    if roster_search and roster_search.upper() not in p['ticker'].upper() and roster_search.upper() not in p['name'].upper():
        continue
    etf_label = f"[{p.get('etf', '')}] " if p.get('etf') else ""
    st.sidebar.write(f"{etf_label}**{p['ticker']}** — {p['name']}")

# --- Main ---
st.title("Stock Market Fantasy Draft Tracker")

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
st.markdown(f"### <span style='font-family: Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif'>🏆</span> Highest Performing: {ETF_EMOJI.get(ETF_MAP.get(best_ticker, ''), '')} <span style='color:green'>{NAME_MAP[best_ticker]} ({best_ticker}) {final_returns[best_ticker]:+.2f}%</span> &nbsp;&nbsp; <span style='font-family: Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif'>📉</span> Lowest Performing: {ETF_EMOJI.get(ETF_MAP.get(worst_ticker, ''), '')} <span style='color:red'>{NAME_MAP[worst_ticker]} ({worst_ticker}) {final_returns[worst_ticker]:+.2f}%</span>", unsafe_allow_html=True)

st.markdown("### " + " &nbsp;&nbsp; ".join(parts))

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
    title="Top 10 Winners — Cumulative % Return Over Time",
    xaxis_title="Date",
    yaxis_title="Return (%)",
    legend_title="Rank",
    hovermode="x unified",
    height=500,
)

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
    title="Top 10 Losers — Cumulative % Return Over Time",
    xaxis_title="Date",
    yaxis_title="Return (%)",
    legend_title="Rank",
    hovermode="x unified",
    height=500,
)

col2.plotly_chart(fig_bottom, use_container_width=True)

# --- Leaderboard ---
st.subheader("Leaderboard")

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
        "Company": NAME_MAP[ticker],
        "Ticker": display_ticker,
        f"Start Price ({start_date_label})": f"${share_price:.2f}",
        f"End Price ({end_date_label})": f"${end_prices[ticker]:.2f}",
        "Total Return (%)": f"{total_return:+.2f}%",
        "Price Return (%)": f"{ret:+.2f}%",
        "Dividends": f"${div_income:.2f}",
        "Invested": f"${INVESTMENT:.2f}",
        "Final Value": f"${final_value:.2f}",
        "Profit / Loss": f"${profit:+.2f}",
    })

df = pd.DataFrame(rows)
st.markdown(df.to_html(escape=False, index=False, classes="leaderboard"), unsafe_allow_html=True)
