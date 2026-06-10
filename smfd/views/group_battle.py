"""Group Battle: Uncle vs Auntie vs Kid, the family meta-game."""

from __future__ import annotations

import streamlit as st

from smfd import charts
from smfd.compute import groups
from smfd.config import GROUP_COLORS, GROUP_EMOJI, GROUP_NAMES
from smfd.data import GameData
from smfd.views.common import group_colored, ret_color, section


def _standing_card(s: dict, data: GameData) -> str:
    g = s["etf"]
    color = GROUP_COLORS.get(g, "#5d6f65")
    rc = ret_color(s["avg_return_pct"])
    medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
    change = s["change_vs_last"]
    if change.startswith("+"):
        change_html = f'<span style="color:#19a05f;font-weight:700;">▲ {change[1:]} this week</span>'
    elif change.startswith("-"):
        change_html = f'<span style="color:#d14a34;font-weight:700;">▼ {change[1:]} this week</span>'
    else:
        change_html = '<span style="color:var(--muted);">— holding steady</span>'
    losers = s["members"] - s["winners"]
    win_pct = int(s["winners"] / s["members"] * 100) if s["members"] else 0
    pl = s["total_value"] - s["invested"]
    pc = ret_color(pl)
    return (
        f'<div class="group-card" style="border-left:3px solid {color};">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.7rem;">'
        f'<div><div style="font-size:1.1rem;font-weight:800;">{medals.get(s["rank"], "")} '
        f'{GROUP_EMOJI.get(g, "")} <span style="color:{color};">{g}</span></div>'
        f'<div style="font-size:0.7rem;color:var(--muted);">{s["members"]} picks · Team {GROUP_NAMES.get(g, g)}</div></div>'
        f'<div style="text-align:right;"><div style="font-size:1.2rem;font-weight:800;color:{rc};">{s["avg_return_pct"]:+.2f}%</div>'
        f'<div style="font-size:0.68rem;color:var(--muted);">Avg Total Return</div></div></div>'
        f'<div style="font-size:0.74rem;margin-bottom:0.6rem;">{change_html}</div>'
        f'<div style="display:flex;gap:0.5rem;margin-bottom:0.6rem;">'
        f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
        f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;color:var(--muted);">Value</div>'
        f'<div style="font-size:0.95rem;font-weight:700;color:{pc};">${s["total_value"]:,.2f}</div></div>'
        f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
        f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;color:var(--muted);">P/L</div>'
        f'<div style="font-size:0.95rem;font-weight:700;color:{pc};">{"+" if pl >= 0 else ""}${pl:,.2f}</div></div>'
        f'<div style="flex:1;background:rgba(18,51,36,0.03);border-radius:8px;padding:0.5rem 0.6rem;">'
        f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;color:var(--muted);">Win Rate</div>'
        f'<div style="font-size:0.95rem;font-weight:700;">{win_pct}%</div></div></div>'
        f'<div style="display:flex;border-radius:6px;overflow:hidden;height:24px;">'
        f'<div style="width:{win_pct}%;background:rgba(25,160,95,0.12);display:flex;align-items:center;'
        f'justify-content:center;font-size:0.68rem;font-weight:700;color:#19a05f;">{s["winners"]} ↑</div>'
        f'<div style="width:{100 - win_pct}%;background:rgba(209,74,52,0.1);display:flex;align-items:center;'
        f'justify-content:center;font-size:0.68rem;font-weight:700;color:#d14a34;">{losers} ↓</div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-top:0.5rem;">'
        f'<span>Best: {group_colored(s["best_ticker"], data.group_map)} '
        f'<b style="color:#19a05f;">{s["best_return_pct"]:+.2f}%</b></span>'
        f'<span>Worst: {group_colored(s["worst_ticker"], data.group_map)} '
        f'<b style="color:#d14a34;">{s["worst_return_pct"]:+.2f}%</b></span></div></div>'
    )


def render(data: GameData, computed: dict):
    total_returns = computed["total_returns"]
    scores = computed["scores"]

    standings = groups.group_standings(total_returns, scores, data.group_map)
    if not standings:
        st.info("No group data yet.")
        return

    spread = groups.group_spread(standings)
    leader = standings[0]
    st.markdown(
        f'<div class="panel-card" style="margin-top:0.6rem;">'
        f'<span style="font-size:1rem;font-weight:700;">{GROUP_EMOJI.get(leader["etf"], "")} '
        f'Team {GROUP_NAMES.get(leader["etf"], leader["etf"])} leads the family</span>'
        f'<span style="color:var(--muted);font-size:0.85rem;"> — up {leader["avg_return_pct"]:+.2f}% on average, '
        f'{spread:.2f} pp ahead of last place.</span></div>',
        unsafe_allow_html=True,
    )

    section("\U0001f93c", "Current Standings", "rank change vs 5 trading days ago")
    cols = st.columns(len(standings))
    for col, s in zip(cols, standings):
        col.markdown(_standing_card(s, data), unsafe_allow_html=True)

    section("\U0001f4c8", "Head-to-Head Over Time", "average total return per group")
    series = groups.group_return_series(total_returns, data.group_map)
    st.plotly_chart(charts.group_battle_chart(series), use_container_width=True,
                    config=charts.CHART_CONFIG)

    changes = groups.lead_changes(total_returns, data.group_map)
    section("\U0001f6a9", "Lead Changes", f"{len(changes)} so far")
    if changes:
        items = "".join(
            f'<div style="display:flex;align-items:center;gap:0.7rem;padding:0.35rem 0;'
            f'border-bottom:1px solid rgba(18,51,36,0.06);font-size:0.82rem;">'
            f'<span style="font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:var(--muted);">'
            f'{c["date"].strftime("%b %d")}</span>'
            f'<span>{GROUP_EMOJI.get(c["etf"], "")} <b style="color:{GROUP_COLORS.get(c["etf"], "")};">'
            f'{c["etf"]}</b> took the lead from '
            f'{GROUP_EMOJI.get(c["prev_etf"], "")} <b style="color:{GROUP_COLORS.get(c["prev_etf"], "")};">'
            f'{c["prev_etf"]}</b></span></div>'
            for c in reversed(changes[-12:])
        )
        st.markdown(f'<div class="panel-card">{items}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="panel-card" style="color:var(--muted);font-size:0.85rem;">'
            f'{GROUP_EMOJI.get(standings[0]["etf"], "")} {standings[0]["etf"]} has led wire to wire. '
            f'Someone do something.</div>',
            unsafe_allow_html=True,
        )
