"""Game constants and paths. Single source of truth — import from here, never redefine."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# --- The game (fixed facts; do not change) ---
GAME_START = datetime.date(2026, 3, 6)   # $10 "invested" per pick at this close
GAME_END = datetime.date(2027, 4, 15)    # baby's first birthday — leader wins, last place loses
STAKE = 10.0                              # notional dollars per pick

TIMEZONE = ZoneInfo("America/New_York")  # the market's zone; all datetimes use this

# --- Groups ---
GROUPS = ["ANTY", "UNCL", "KIDZ"]
GROUP_NAMES = {"ANTY": "Auntie", "UNCL": "Uncle", "KIDZ": "Kids"}
GROUP_EMOJI = {"UNCL": "\U0001f468‍\U0001f9b3", "ANTY": "\U0001f469\U0001f3fb", "KIDZ": "\U0001f476\U0001f3fb"}
GROUP_COLORS = {"ANTY": "#a855f7", "UNCL": "#3b82f6", "KIDZ": "#eab308"}

# --- Paths ---
ROOT = Path(__file__).resolve().parent.parent
PLAYERS_PATH = ROOT / "players.json"                 # human-maintained INPUT — never auto-overwrite
STOCK_DATA_PATH = ROOT / "data" / "stock_data.json"  # machine-refreshed nightly
OWNERS_PATH = ROOT / "inputs" / "owners.json"        # PII — gitignored, admin-only
NEWSLETTER_LOG_PATH = ROOT / "data" / "newsletter_log.json"
PREDICTION_HISTORY_PATH = ROOT / "prediction_history.json"
ROASTS_CACHE_PATH = ROOT / "roasts_cache.json"

# Data older than this many hours past the most recent missed close is flagged stale
STALE_GRACE_HOURS = 24

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
