"""Owner directory — maps each pick to the real person who chose it.

PII rules: owner names/emails render ONLY inside the password-protected admin
view (and, later, a personalized-newsletter path). Never on the public
dashboard, never in public newsletter HTML, never in logs, never in git.

Storage: the private Google Sheet ("Owners" tab via the Apps Script, gated by
ADMIN_TOKEN) is the source of truth — it survives Streamlit Cloud redeploys.
inputs/owners.json is a gitignored local cache/fallback.
"""

from __future__ import annotations

import json
import re

import requests

from smfd.config import OWNERS_PATH

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


# --- Local cache (gitignored) ---

def load_local() -> dict:
    try:
        with open(OWNERS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_local(owners: dict) -> bool:
    try:
        OWNERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OWNERS_PATH, "w") as f:
            json.dump(owners, f, indent=2, sort_keys=True)
        return True
    except OSError:
        return False


# --- Google Sheet sync (authoritative when configured) ---

def fetch_remote(sheets_url: str, admin_token: str) -> dict | None:
    """Pull the Owners tab. Returns None when unconfigured/unreachable."""
    if not sheets_url or not admin_token:
        return None
    try:
        resp = requests.get(sheets_url, params={"action": "get_owners",
                                                "token": admin_token}, timeout=8)
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, dict) and not payload.get("error"):
                return {
                    t: {"owner_name": v.get("owner_name", ""),
                        "owner_email": v.get("owner_email", "")}
                    for t, v in payload.items()
                    if isinstance(v, dict)
                }
    except (requests.RequestException, ValueError):
        pass
    return None


def push_remote(sheets_url: str, admin_token: str, ticker: str,
                owner_name: str, owner_email: str) -> bool:
    """Upsert one owner row in the Sheet. Returns success."""
    if not sheets_url or not admin_token:
        return False
    try:
        resp = requests.get(sheets_url, params={
            "action": "set_owner", "token": admin_token, "ticker": ticker,
            "name": owner_name, "email": owner_email,
        }, timeout=8)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except (requests.RequestException, ValueError):
        return False


def load_owners(sheets_url: str = "", admin_token: str = "") -> tuple[dict, str]:
    """Owners + source ("sheet" or "local"). Sheet wins and refreshes the cache."""
    remote = fetch_remote(sheets_url, admin_token)
    if remote is not None:
        save_local(remote)
        return remote, "sheet"
    return load_local(), "local"


def save_owner(owners: dict, ticker: str, owner_name: str, owner_email: str,
               sheets_url: str = "", admin_token: str = "") -> tuple[dict, bool]:
    """Upsert one pick's owner locally + remotely. Returns (owners, synced)."""
    owner_name = owner_name.strip()
    owner_email = owner_email.strip()
    if owner_name or owner_email:
        owners[ticker] = {"owner_name": owner_name, "owner_email": owner_email}
    else:
        owners.pop(ticker, None)
    save_local(owners)
    synced = push_remote(sheets_url, admin_token, ticker, owner_name, owner_email)
    return owners, synced
