# Stock Market Fantasy Draft

A Streamlit app that turns a stock-picking pool into a live standings board. Each stock gets the same entry stake, the app tracks price return plus dividends over a selectable date range, and the table ranks every pick from highest performing to lowest performing.

## Features

- **Standings-style Dashboard** — Sports-inspired Streamlit layout with league-table styling
- **Top 10 / Bottom 10 Charts** — Side-by-side Plotly charts for stocks in the money and out of the money
- **ETF Divisions** — Stocks grouped into ETF buckets (`UNCL`, `ANTY`, `KIDZ`) with average performance summaries
- **League Table** — Full ranking with start/end prices, stake, units, profit/(loss), dividends, total return, price return, and total return percentage
- **Dividend Tracking** — Fetches actual dividend payments and calculates income based on shares purchased
- **Ticker Management** — Add and remove stocks directly from the sidebar UI and persist changes to `players.json`
- **Flexible Date Range** — Pick any start and end date from the sidebar
- **Email Updates** — Subscribe to weekly, monthly, or quarterly standings emails

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

`investment_amount` is the amount assigned to each stock. You can also add and remove tickers from the sidebar in the running app.

## UI Overview

- **League Office** sidebar for date selection, ticker management, and roster search
- **Highest Performing / Lowest Performing** summary cards with ETF emoji markers
- **Matchday Report** showing ETF division performance
- **League Table** with row colors fading from green at the top to red at the bottom
- **Matchday Alerts** subscription form for email updates

## Project Structure

```text
├── app.py              # Streamlit application
├── players.json        # Player/ticker configuration
├── subscribers.json    # Email subscriber list
├── send_emails.py      # Email sending script
├── requirements.txt    # Python dependencies
└── README.md
```
