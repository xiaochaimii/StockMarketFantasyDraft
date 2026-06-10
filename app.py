"""Stock Market Fantasy Draft — thin entrypoint.

Layout, view routing, and cross-view compute only. All logic lives in smfd/:
data loading (smfd.data), scoring (smfd.compute), charts (smfd.charts),
views (smfd.views), newsletter (smfd.newsletter).
"""

from __future__ import annotations

import datetime
import os

import streamlit as st

from smfd.compute import rankings, returns, superlatives
from smfd.config import STOCK_DATA_PATH
from smfd.data import load_game_data
from smfd.views import (admin, common, group_battle, newsletter_view, race_view,
                        risk_income, sideshow, standings)
from smfd.compute.race import days_remaining

st.set_page_config(page_title="Stock Market Fantasy Draft", layout="wide",
                   initial_sidebar_state="collapsed")

common.inject_style()


def _sheets_url() -> str:
    return st.secrets.get("SHEETS_URL", "")


@st.cache_data(ttl=900, show_spinner=False)
def _load(_mtime: float):
    return load_game_data()


@st.cache_data(ttl=900, show_spinner=False)
def _compute(_mtime: float, start: datetime.date | None, end: datetime.date | None):
    data = _load(_mtime)
    scores = returns.compute_scores(data, start=start, end=end)
    total = returns.total_return_series(data, start=start, end=end)
    throne = rankings.compute_throne_history(total, data.name_map)
    return {
        "scores": scores,
        "total_returns": total,
        "throne": throne,
        "rank_deltas": rankings.rank_changes(total),
        "superlatives": superlatives.compute_superlatives(
            total, throne, data.name_map, data.group_map),
        "achievements": superlatives.compute_achievements(total, throne, scores),
    }


def _window_from_query() -> tuple:
    qp = st.query_params
    try:
        if "ds" in qp and "de" in qp:
            return (datetime.date.fromisoformat(qp["ds"]),
                    datetime.date.fromisoformat(qp["de"]))
    except ValueError:
        pass
    return None, None


def main():
    try:
        mtime = os.path.getmtime(STOCK_DATA_PATH)
    except OSError:
        mtime = 0.0

    data = _load(mtime)
    if data.prices.empty:
        st.error("No stock data found. Run `python fetch_data.py` to generate "
                 "data/stock_data.json, then reload.")
        st.stop()

    start, end = _window_from_query()
    if start and end and start >= end:
        st.error("Start date must be before end date.")
        start, end = None, None

    computed = _compute(mtime, start, end)
    if computed["scores"].empty:
        st.warning("No data in the selected window.")
        st.stop()

    invalid = [t for t in data.tickers if t not in data.valid_tickers]
    for t in invalid:
        st.warning(f"No data for **{t}** ({data.name_map.get(t, '')}) — excluded from results.")

    common.hero(data, days_remaining())
    common.stale_banner(data)

    window_start = start or data.prices.index[0].date()
    window_end = end or data.prices.index[-1].date()

    tabs = st.tabs(["\U0001f3c6 Standings", "\U0001f93c Group Battle",
                    "\U0001f3c1 Race to the Finish", "\U0001f3a2 Risk & Income",
                    "\U0001f3aa Sideshow", "\U0001f4ec Newsletter", "\U0001f512 Admin"])
    with tabs[0]:
        standings.render(data, computed, window_start, window_end)
    with tabs[1]:
        group_battle.render(data, computed)
    with tabs[2]:
        race_view.render(data, computed)
    with tabs[3]:
        risk_income.render(data, computed)
    with tabs[4]:
        sideshow.render(data, computed, sheets_url=_sheets_url())
    with tabs[5]:
        newsletter_view.render(data, computed)
    with tabs[6]:
        admin.render(data, computed, sheets_url=_sheets_url())


main()
