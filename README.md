# Stock Market Fantasy Draft

A Streamlit app that turns a stock-picking pool into a live standings board. Each stock gets the same entry stake, the app tracks price return plus dividends over a selectable date range, and the table ranks every pick from MVP to Benchwarmer.

## Features

- **Standings-style Dashboard** — Sports-inspired Streamlit layout with league-table styling
- **MVP / Benchwarmer Tracking** — Displays top and worst performers with streak counters and historical throne transitions
- **Bump Charts** — Top 10 and Bottom 10 ranking visualizations over time with smooth sigmoid curve transitions
- **ETF Standing** — Stocks grouped into ETF buckets (`UNCL`, `ANTY`, `KIDZ`) with medal rankings and average performance bars
- **Leaderboard** — Full ranking with start/end prices, stake, units, profit/(loss), dividends, total return, price return, total return percentage, and rank change arrows
- **Dividend Tracking** — Fetches actual dividend payments and calculates income based on shares purchased
- **Ticker Management** — Password-protected admin panel to add and remove stocks directly from the sidebar UI with persistent changes to `players.json`
- **Stock Search** — Search for stocks from the sidebar and highlight them on the leaderboard
- **Flexible Date Range** — Pick any start and end date (MM/DD/YYYY) from the sidebar, defaults to PST
- **Live Market Status** — Shows when market is open or closed with a countdown timer and auto-refresh every hour during market hours
- **Mobile Responsive** — Optimized for phone viewing with responsive CSS, touch-friendly charts, and scrollable tables

## Tech Stack

- **Python** + **Streamlit**
- **Plotly**
- **yfinance**
- **pandas**

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Optionally, create `.streamlit/secrets.toml` with an admin password:

```toml
ADMIN_PASSWORD = "your_password_here"
```

## Configuration

Edit `players.json` to set the entry stake and starting roster:

```json
{
  "investment_amount": 10.00,
  "players": [
    { "etf": "KIDZ", "name": "Apple", "ticker": "AAPL" },
    { "etf": "UNCL", "name": "NVIDIA", "ticker": "NVDA" }
  ]
}
```

`investment_amount` is the amount assigned to each stock. You can also add and remove tickers from the admin panel in the running app.

## UI Overview

- **League Office** sidebar for date selection, ticker management, and stock search
- **MVP / Benchwarmer** summary cards with ETF emoji markers and streak counters
- **Bump Charts** showing ranking movement over time for top and bottom performers
- **ETF Standing** showing ETF division performance with medal rankings
- **Leaderboard** with row colors fading from green (positive) to red (negative), rank change arrows, and a divider line between positive and negative returns

## Project Structure

```text
├── app.py              # Streamlit application
├── .streamlit/
│   ├── config.toml     # Streamlit theme configuration
│   └── secrets.toml    # Admin password (not in Git)
├── players.json        # Player/ticker configuration
├── requirements.txt    # Python dependencies
└── README.md
```
