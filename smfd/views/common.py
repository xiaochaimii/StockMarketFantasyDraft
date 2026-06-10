"""Shared view helpers: CSS injection, hero, banners, formatting, group markup."""

from __future__ import annotations

import html as html_mod
from pathlib import Path

import streamlit as st

from smfd.config import GROUP_COLORS, GROUP_EMOJI
from smfd.data import GameData

_STYLE_PATH = Path(__file__).parent / "style.css"

FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet" />'
    '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />'
)


def inject_style():
    css = _STYLE_PATH.read_text()
    st.markdown(f"{FONT_LINKS}<style>{css}</style>", unsafe_allow_html=True)


def esc(text) -> str:
    return html_mod.escape(str(text))


def group_colored(ticker: str, group_map: dict, escaped: bool = False) -> str:
    """Ticker wrapped in its group color."""
    t = ticker if escaped else esc(ticker)
    color = GROUP_COLORS.get(group_map.get(ticker, ""), "")
    if color:
        return f'<span style="color:{color};font-weight:700;">{t}</span>'
    return f"<b>{t}</b>"


def group_emoji(ticker: str, group_map: dict) -> str:
    return GROUP_EMOJI.get(group_map.get(ticker, ""), "")


def ret_color(value: float) -> str:
    return "#19a05f" if value >= 0 else "#d14a34"


def fmt_signed_pct(value: float) -> str:
    if value >= 0:
        return f'<span style="color:#19a05f;">{value:.2f}%</span>'
    return f'<span style="color:#d14a34;">({abs(value):.2f}%)</span>'


def fmt_signed_currency(value: float) -> str:
    if value >= 0:
        return f'<span style="color:#19a05f;">${value:.2f}</span>'
    return f'<span style="color:#d14a34;">(${abs(value):.2f})</span>'


def section(icon: str, title: str, note: str = ""):
    note_html = f'<span class="sec-note">{esc(note)}</span>' if note else ""
    st.markdown(
        f'<div class="sec-head"><span class="sec-icon">{icon}</span>'
        f'<span class="sec-title">{esc(title)}</span>{note_html}</div>',
        unsafe_allow_html=True,
    )


def hero(data: GameData, days_left: int):
    window = ""
    if len(data.prices):
        window = (f"{data.prices.index[0].strftime('%b %d, %Y')} – "
                  f"{data.prices.index[-1].strftime('%b %d, %Y')}")
    as_of = data.as_of.strftime("%b %d, %I:%M %p ET") if data.as_of else "unknown"
    st.markdown(
        f"""
        <section class="hero-card">
          <h1 class="hero-title">🧷 No Diaper Change Standings</h1>
          <div class="hero-meta">
            <span class="hero-pill">Window: {window}</span>
            <span class="hero-pill">Stake: ${data.stake:.0f} per pick · {len(data.valid_tickers)} picks</span>
            <span class="hero-pill">🍼 {days_left} days to the finish (Apr 15, 2027)</span>
            <span class="hero-pill">Data as of {as_of}</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def stale_banner(data: GameData):
    """Dismissible honesty banner when the nightly fetch hiccuped."""
    if st.session_state.get("stale_banner_dismissed"):
        return
    if not (data.stale or data.fetch_errors):
        return
    as_of = data.as_of.strftime("%b %d, %I:%M %p ET") if data.as_of else "an unknown time"
    if data.stale:
        message = (f"Heads up — market data is from **{as_of}**. "
                   "Tonight's refresh may have hiccuped; standings may lag a session.")
    else:
        message = (f"Heads up — last night's refresh ({as_of}) had "
                   f"{len(data.fetch_errors)} hiccup(s); affected picks kept their previous values.")
    col_msg, col_btn = st.columns([12, 1])
    with col_msg:
        st.warning(message, icon="⚠️")
    with col_btn:
        if st.button("✕", key="dismiss_stale", help="Dismiss"):
            st.session_state["stale_banner_dismissed"] = True
            st.rerun()
