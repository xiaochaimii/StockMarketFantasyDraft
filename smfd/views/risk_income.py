"""Risk & Income: who's gambling, who's coasting, who's collecting checks."""

from __future__ import annotations

import streamlit as st

from smfd import charts
from smfd.compute import risk
from smfd.config import GROUP_EMOJI, GROUP_NAMES
from smfd.data import GameData
from smfd.views.common import esc, group_colored, group_emoji, ret_color, section


def _leader_card(title: str, icon: str, ticker: str, data: GameData,
                 value_html: str, note: str) -> str:
    return (
        f'<div class="stock-card">'
        f'<div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.06em;color:var(--muted);">{icon} {esc(title)}</div>'
        f'<div style="font-size:1.15rem;font-weight:800;margin-top:0.25rem;">'
        f'{group_emoji(ticker, data.group_map)} {group_colored(ticker, data.group_map)}</div>'
        f'<div style="font-size:0.95rem;font-weight:700;margin-top:0.1rem;">{value_html}</div>'
        f'<div style="font-size:0.7rem;color:var(--muted);margin-top:0.15rem;">{esc(note)}</div></div>'
    )


def render(data: GameData, computed: dict):
    scores = computed["scores"]
    total_returns = computed["total_returns"]

    table = risk.risk_table(total_returns, scores)
    if table.empty:
        st.info("No risk data yet.")
        return

    st.markdown('<div style="margin-top:0.6rem;"></div>', unsafe_allow_html=True)
    wildest = table["annualized_vol_pct"].idxmax()
    calmest = table["annualized_vol_pct"].idxmin()
    deepest = table["max_drawdown_pct"].idxmin()
    payers = table[table["dividend_return_pct"] > 0]
    cols = st.columns(4)
    cols[0].markdown(_leader_card(
        "Wildest Ride", "\U0001f3a2", wildest, data,
        f'{table.loc[wildest, "annualized_vol_pct"]:.0f}% annualized vol',
        "Highest volatility in the draft"), unsafe_allow_html=True)
    cols[1].markdown(_leader_card(
        "Steadiest Hand", "\U0001f9d8", calmest, data,
        f'{table.loc[calmest, "annualized_vol_pct"]:.0f}% annualized vol',
        "Lowest volatility in the draft"), unsafe_allow_html=True)
    cols[2].markdown(_leader_card(
        "Deepest Dip", "\U0001f573️", deepest, data,
        f'<span style="color:#d14a34;">{table.loc[deepest, "max_drawdown_pct"]:.1f}% max drawdown</span>',
        "Worst peak-to-trough slide"), unsafe_allow_html=True)
    if len(payers):
        king = payers["dividend_return_pct"].idxmax()
        cols[3].markdown(_leader_card(
            "Dividend King", "\U0001f4b0", king, data,
            f'<span style="color:#19a05f;">${scores.loc[king, "dividend_income"]:.2f} collected</span>',
            f'+{table.loc[king, "dividend_return_pct"]:.2f}% of return from dividends'),
            unsafe_allow_html=True)

    section("\U0001f3af", "Risk vs Reward", "up + left = free lunch · down + right = pain")
    st.plotly_chart(charts.risk_scatter(table, data.group_map),
                    use_container_width=True, config=charts.CHART_CONFIG)

    section("\U0001f4b8", "Where Returns Came From", "price moves vs dividend checks")
    if len(payers):
        st.plotly_chart(charts.income_split_chart(table),
                        use_container_width=True, config=charts.CHART_CONFIG)
        total_divs = scores["dividend_income"].sum()
        st.markdown(
            f'<div class="panel-card" style="font-size:0.85rem;">'
            f'\U0001f4b0 The family has collected <b style="color:#19a05f;">${total_divs:.2f}</b> in dividends '
            f'across {len(payers)} dividend-paying picks. Every cent counts toward the final score.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No dividends collected yet — this crowd picked pure growth.")

    section("\U0001f46a", "Risk by Family Group")
    agg = risk.group_risk(table, data.group_map)
    rows = "".join(
        f'<tr><td style="font-weight:700;">{GROUP_EMOJI.get(g, "")} {GROUP_NAMES.get(g, g)}</td>'
        f'<td style="color:{ret_color(row["total_return_pct"])};font-weight:700;">{row["total_return_pct"]:+.2f}%</td>'
        f'<td>{row["annualized_vol_pct"]:.0f}%</td>'
        f'<td style="color:#d14a34;">{row["max_drawdown_pct"]:.1f}%</td>'
        f'<td style="color:#19a05f;">{row["dividend_return_pct"]:+.2f}%</td></tr>'
        for g, row in agg.iterrows()
    )
    st.markdown(
        '<div style="overflow-x:auto;border-radius:14px;border:1px solid var(--border);'
        'background:var(--panel-strong);">'
        '<table style="width:100%;min-width:520px;border-collapse:separate;border-spacing:0;font-size:0.82rem;">'
        '<tr>'
        + "".join(
            f'<th style="text-align:left;padding:9px 10px;background:linear-gradient(90deg,#0d2f20,#13492f);'
            f'color:#f4f0e3;font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;">{h}</th>'
            for h in ["Group", "Avg Return", "Avg Volatility", "Avg Max Drawdown", "Avg Dividend Return"])
        + f'</tr>{rows}</table></div>',
        unsafe_allow_html=True,
    )
