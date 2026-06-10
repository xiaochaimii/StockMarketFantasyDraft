# Stock Market Fantasy Draft 🧷

A Streamlit app that scores a baby-shower stock-picking game. ~71 guests each
picked one stock (or commodity ETF); $10 was notionally "invested" in each pick
on **March 6, 2026**, and the game runs until the baby's first birthday,
**April 15, 2027** — leader wins, last place gets the punishment. Every pick
belongs to a group — **Uncle (UNCL)**, **Auntie (ANTY)**, **Kid (KIDZ)**
(friends are Alessi's honorary Aunties and Uncles; Kids are her peers)
— so the group meta-game runs alongside individual standings.

## Scoring (the number that decides who wins)

For each pick, on **split-adjusted** prices:

```
units            = $10 / start price (split-adjusted close, 2026-03-06)
price value      = units × current price (split-adjusted)
dividend income  = units × per-share dividends at each ex-date (basis-adjusted)
total return %   = (price value + dividend income) / $10 − 1
```

The leaderboard ranks on **total return** — price appreciation **plus**
dividends. Splits never distort returns (units are constant in split-adjusted
space) and dividends are counted once, as separate cash — never via a
dividend-adjusted price series. See `tests/test_returns.py` for the contract.

## Views

| Tab | What's in it |
| --- | --- |
| 🏆 **Standings** | Portfolio value, Hot/Not/Meh, full sortable leaderboard, bump charts |
| 🤼 **Group Battle** | Uncle vs Auntie vs Kid: standings, head-to-head chart, lead changes |
| 🏁 **Race to the Finish** | Countdown, gap-to-leader, just-for-fun projections, "still alive?" |
| 🎢 **Risk & Income** | Volatility, max drawdown, dividend-vs-price return split |
| 🎪 **Sideshow** | Bragging rights, throne room, daily roasts, predictions, trivia, sectors |
| 📬 **Newsletter** | Self-contained HTML snapshot — copy into Gmail or download, send yourself |
| 🔒 **Admin** | Password-gated: owner directory (PII) + roster fixes |

## Architecture

```
app.py                    # thin entrypoint: config, routing, cached compute
smfd/
├── config.py             # GAME_START/GAME_END/STAKE/TIMEZONE, paths, groups
├── market_calendar.py    # US market holidays, trading days, staleness logic
├── data.py               # loads players.json + data/stock_data.json (legacy + v2)
├── owners.py             # admin owner directory (PII-safe, Sheet-backed)
├── trivia.py
├── compute/              # pure functions — no Streamlit anywhere in here
│   ├── returns.py        # canonical scoring (see above)
│   ├── rankings.py       # leaderboard ranks, throne history
│   ├── groups.py         # group battle series + standings
│   ├── race.py           # countdown, gaps, projections
│   ├── risk.py           # volatility, drawdown, income split
│   ├── superlatives.py   # badges + fun stats
│   ├── predictions.py    # momentum toys + accuracy tracking
│   └── roasts.py         # daily roast generation + cache
├── charts/               # Plotly builders (data in, figure out)
├── views/                # one module per tab + shared style.css
└── newsletter/           # build.py (snapshot) + template.py (inline-CSS HTML)
fetch_data.py             # nightly pipeline (GitHub Action)
data/stock_data.json      # machine-refreshed nightly — never hand-edit
players.json              # human-maintained roster — never auto-overwritten
inputs/owners.json        # PII cache — gitignored, never committed
tests/                    # scoring contract, parity, staleness, insights
```

**Data flow.** A GitHub Action (`.github/workflows/fetch_stock_data.yml`) runs
`fetch_data.py` on weekday evenings: raw prices, splits, dated dividends,
signals, earnings, news → `data/stock_data.json` (with `as_of` +
`fetch_errors`; per-ticker failures keep the previous run's values). The app
only reads that file — no live market calls — and shows an honest "data is
from …" banner when a session was missed. The newsletter reads the same
compute layer as the dashboard, so the email can never disagree with the site.

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 fetch_data.py            # generate data/stock_data.json
python3 -m streamlit run app.py
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in:

- `ADMIN_USERNAME` + `ADMIN_PASSWORD_SHA256` (or plaintext `ADMIN_PASSWORD`) —
  Admin tab login
- `SHEETS_URL` — the Google Apps Script web-app URL (reactions + owners);
  leave empty to run without it
- `ADMIN_TOKEN` — must match the `ADMIN_TOKEN` script property in the Apps
  Script project; gates the owner-directory (PII) actions

### Google Sheet (optional but recommended)

`google_apps_script.js` is the web app bound to a **private** spreadsheet.
It serves emoji-reaction counts (public) and the **Owners** tab (PII,
token-gated). To (re)deploy: paste the script, set the `ADMIN_TOKEN` script
property, Deploy → Web app → Execute as Me / access Anyone, and put the fresh
`/exec` URL in secrets. **Rotating secrets** = redeploy for a new URL + new
token, update secrets, done.

### Security notes

- No secrets live in this repo: the admin password (hash) and the Apps Script
  URL/token are Streamlit secrets only.
- Owner names/emails render **only** inside the password-gated Admin tab,
  are stored in the private Sheet (+ a gitignored local cache), and never
  appear on the public dashboard or in the public newsletter.
- If you forked an older version of this repo: the old hardcoded Apps Script
  URL is in git history — redeploy the script (fresh URL) and rotate the
  admin password before going public.

## Tests

```bash
python3 -m pytest tests/
```

Covers the scoring contract (dividends add exactly their cash; split returns
are continuous; pre-split dividends are basis-adjusted), legacy-format parity,
session-aware staleness, and the group/race/risk math.

## Notes for posterity

- `players.json` is the human-maintained roster. The fetch job and app never
  overwrite it; the Admin tab edits it deliberately.
- `data/stock_data.json` supports two formats: the current **v2** (raw +
  split-adjusted prices, dated dividends, splits) and the pre-redesign legacy
  format (auto-adjusted prices + summed dividends), which the app reproduces
  bug-for-bug for continuity until the next nightly fetch upgrades the file.
- Intentionally cut in the 2026-06 redesign: live intraday price overlay and
  the LIVE/market-countdown bar (the app now shows last close + an honest
  staleness banner), the Family Feud voting tab, the NASDAQ-screener stock
  search in Admin, and the dead "Market Pulse" / weekly-events sections.
