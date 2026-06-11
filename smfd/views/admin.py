"""Admin: login, owners leaderboard, newsletter generator, roster management.

PII lives here ONLY — owner names/emails render nowhere outside this view's
password gate (CR-2), and the newsletter generator moved in from the public
tabs (CR-1). The generated newsletter HTML itself stays group-safe.
"""

from __future__ import annotations

import hashlib
import json

import streamlit as st

from smfd import owners as owners_mod
from smfd.config import GROUPS, PLAYERS_PATH
from smfd.data import GameData
from smfd.views import newsletter_view
from smfd.views.common import esc, fmt_signed_currency, ret_color, section


def _secret(key: str) -> str:
    try:
        return st.secrets.get(key, "")
    except Exception:  # no secrets file at all (e.g. fresh local checkout)
        return ""


def _password_ok(password: str) -> bool:
    """Prefer a SHA-256 hash in secrets; fall back to plaintext for compatibility."""
    stored_hash = _secret("ADMIN_PASSWORD_SHA256")
    if stored_hash:
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash.lower()
    stored = _secret("ADMIN_PASSWORD")
    return bool(stored) and password == stored


def _login():
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("#### Admin Login")
        with st.form("login_form"):
            userid = st.text_input("User ID", label_visibility="collapsed",
                                   placeholder="Enter user ID")
            password = st.text_input("Password", type="password",
                                     label_visibility="collapsed",
                                     placeholder="Enter admin password")
            if st.form_submit_button("Login", width="stretch"):
                if userid and userid == _secret("ADMIN_USERNAME") and _password_ok(password):
                    st.session_state.admin_authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect credentials.")


def _owners_leaderboard(data: GameData, computed: dict, sheets_url: str):
    section("\U0001f4c7", "Owners Leaderboard",
            "who picked what, ranked — admin-only, never shown on the public dashboard")
    admin_token = _secret("ADMIN_TOKEN")
    owners, source = owners_mod.load_owners(sheets_url, admin_token)

    if source == "sheet":
        st.caption("✅ Synced with the private Google Sheet (Owners tab).")
    elif sheets_url and admin_token:
        st.caption("⚠️ Sheet unreachable — using the local cache. Edits will sync next time.")
    else:
        st.caption("ℹ️ No SHEETS_URL/ADMIN_TOKEN in secrets — owners are stored in the "
                   "gitignored local file only, which does NOT survive a Streamlit Cloud "
                   "redeploy. Configure the Sheet for durable storage.")

    scores = computed["scores"]
    pick = st.selectbox(
        "Pick to edit",
        list(scores.index),
        format_func=lambda t: (
            f"{t} — {data.name_map.get(t, '')}"
            + (f"  ·  \U0001f464 {owners[t]['owner_name']}" if t in owners and owners[t].get("owner_name") else "")
        ),
    )
    current = owners.get(pick, {})
    with st.form("owner_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Owner name", value=current.get("owner_name", ""))
        email = c2.text_input("Owner email", value=current.get("owner_email", ""))
        if st.form_submit_button("Save owner", width="stretch"):
            if email and not owners_mod.valid_email(email):
                st.error("That doesn't look like a valid email address.")
            else:
                owners, synced = owners_mod.save_owner(
                    owners, pick, name, email, sheets_url, admin_token)
                if synced:
                    st.success(f"Saved {pick} and synced to the Sheet.")
                elif sheets_url and admin_token:
                    st.warning(f"Saved {pick} locally; Sheet sync failed — will retry on next save.")
                else:
                    st.success(f"Saved {pick} locally.")
                st.rerun()

    rows = ""
    recorded = 0
    blank = '<span style="color:var(--muted)">—</span>'
    for rank, (t, row) in enumerate(scores.iterrows(), start=1):
        o = owners.get(t, {})
        if o.get("owner_name") or o.get("owner_email"):
            recorded += 1
        owner_name = esc(o.get("owner_name", "")) or blank
        owner_email = esc(o.get("owner_email", "")) or blank
        rows += (
            f'<tr><td>{rank}</td>'
            f'<td><b>{owner_name}</b></td>'
            f'<td><b>{esc(t)}</b> <span style="color:var(--muted);font-size:0.75rem;">{esc(row["name"])}</span></td>'
            f'<td>{esc(row["group"])}</td>'
            f'<td style="color:{ret_color(row["total_return_pct"])};font-weight:700;">{row["total_return_pct"]:+.2f}%</td>'
            f'<td style="color:{ret_color(row["price_return_pct"])};">{row["price_return_pct"]:+.2f}%</td>'
            f'<td>{fmt_signed_currency(row["profit"])}</td>'
            f'<td style="color:{ret_color(row["profit"])};">${row["total_value"]:.2f}</td>'
            f'<td>{owner_email}</td></tr>'
        )
    st.markdown(f"**{recorded} of {len(scores)} picks** have an owner recorded.")
    st.markdown(
        '<div style="overflow-x:auto;max-height:480px;overflow-y:auto;border-radius:14px;'
        'border:1px solid var(--border);background:var(--panel-strong);">'
        '<table style="width:100%;min-width:760px;border-collapse:separate;border-spacing:0;font-size:0.8rem;">'
        '<tr>'
        + "".join(
            f'<th style="text-align:left;padding:9px 8px;background:linear-gradient(90deg,#0d2f20,#13492f);'
            f'color:#f4f0e3;font-size:0.68rem;font-weight:700;text-transform:uppercase;'
            f'position:sticky;top:0;white-space:nowrap;">{h}</th>'
            for h in ["#", "Owner", "Pick", "Group", "Total Return", "Price Return",
                      "Profit/(Loss)", "Total Value", "Email"])
        + f'</tr>{rows}</table></div>',
        unsafe_allow_html=True,
    )


def _roster_management(data: GameData):
    section("\U0001f4dd", "Roster",
            "players.json is the human-maintained input — edits here are deliberate")
    st.caption("The game roster is locked (fixed facts of a game in progress). "
               "Add/remove only to fix a data problem — e.g. a ticker symbol change.")
    with open(PLAYERS_PATH) as f:
        config = json.load(f)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Add a pick**")
        group = st.selectbox("Group", [""] + GROUPS,
                             format_func=lambda g: g or "Select a group")
        ticker = st.text_input("Ticker", placeholder="e.g. TSLA").strip().upper()
        name = st.text_input("Company name", placeholder="e.g. Tesla").strip()
        existing = {p["ticker"] for p in config["players"]}
        if st.button("Add pick", disabled=not (group and ticker and name)):
            if ticker in existing:
                st.error(f"{ticker} is already in the roster.")
            else:
                config["players"].append({"etf": group, "name": name, "ticker": ticker})
                config["players"].sort(key=lambda p: p["ticker"])
                with open(PLAYERS_PATH, "w") as f:
                    json.dump(config, f, indent=2)
                st.success(f"Added {ticker}. It will get data on the next nightly fetch.")
                st.rerun()
    with c2:
        st.markdown("**Remove a pick**")
        remove = st.selectbox("Ticker to remove", [""] + [p["ticker"] for p in config["players"]],
                              format_func=lambda t: t or "Select a ticker")
        confirm = st.checkbox("I understand this removes a real player's pick")
        if st.button("Remove pick", disabled=not (remove and confirm)):
            config["players"] = [p for p in config["players"] if p["ticker"] != remove]
            with open(PLAYERS_PATH, "w") as f:
                json.dump(config, f, indent=2)
            st.success(f"Removed {remove}.")
            st.rerun()


def render(data: GameData, computed: dict, sheets_url: str = ""):
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if not st.session_state.admin_authenticated:
        _login()
        return

    _owners_leaderboard(data, computed, sheets_url)
    st.divider()
    section("\U0001f4ec", "Newsletter", "generate + self-send — the email itself stays group-safe (no names)")
    newsletter_view.render(data, computed)
    st.divider()
    _roster_management(data)
    st.divider()
    if st.button("Logout"):
        st.session_state.admin_authenticated = False
        st.rerun()
