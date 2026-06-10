"""Standings: the headline view — who's winning the whole thing."""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from smfd import charts
from smfd.config import GAME_START, SECTOR_MAP, GROUP_COLORS
from smfd.data import GameData
from smfd.views.common import (esc, fmt_signed_currency, fmt_signed_pct,
                               group_colored, group_emoji, ret_color, section)


def _interpolate_hex(start_hex: str, end_hex: str, fraction: float) -> str:
    s = start_hex.lstrip("#")
    e = end_hex.lstrip("#")
    rgb = tuple(
        round(int(s[i:i + 2], 16) + (int(e[i:i + 2], 16) - int(s[i:i + 2], 16)) * fraction)
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{v:02x}" for v in rgb)


def _portfolio_card(scores: pd.DataFrame, data: GameData, end_label: str):
    invested = data.stake * len(scores)
    value = scores["total_value"].sum()
    divs = scores["dividend_income"].sum()
    pl = value - invested
    ret = (value / invested - 1) * 100 if invested else 0
    grad = "#15803d,#166534" if pl >= 0 else "#b91c1c,#991b1b"
    st.markdown(
        f'<div style="background:linear-gradient(135deg,{grad});border-radius:16px;'
        f'padding:1.2rem 1.5rem;color:#fff;margin:0.5rem 0 1rem;position:relative;overflow:hidden;">'
        f'<div style="position:absolute;right:-40px;top:-40px;width:180px;height:180px;'
        f'border-radius:999px;background:rgba(255,255,255,0.05);"></div>'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;opacity:0.8;">Portfolio Value</span>'
        f'<span style="font-size:0.62rem;opacity:0.5;">as of {end_label}</span></div>'
        f'<div style="font-size:2rem;font-weight:900;letter-spacing:-0.03em;margin:0.2rem 0 0.5rem;">${value:,.2f}</div>'
        f'<div style="display:flex;gap:1.5rem;font-size:0.78rem;opacity:0.85;flex-wrap:wrap;">'
        f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;">P/L</div>'
        f'{"(" if pl < 0 else ""}${abs(pl):,.2f}{")" if pl < 0 else ""}</div>'
        f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;">P/L %</div>'
        f'{"(" if ret < 0 else ""}{abs(ret):.2f}%{")" if ret < 0 else ""}</div>'
        f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;">Dividends</div>${divs:,.2f}</div>'
        f'<div><div style="font-size:0.6rem;opacity:0.7;text-transform:uppercase;">Invested</div>'
        f'${invested:,.2f} · {len(scores)} picks × ${data.stake:.0f}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _stock_card(ticker: str, data: GameData, scores: pd.DataFrame, rank_label: str,
                streak_text: str, streak_icon: str, border_color: str) -> str:
    row = scores.loc[ticker]
    ret = row["total_return_pct"]
    raw = data.raw_prices[ticker].dropna() if ticker in data.raw_prices.columns else None
    sp = float(raw.iloc[0]) if raw is not None and len(raw) else row["start_price"]
    ep = float(raw.iloc[-1]) if raw is not None and len(raw) else row["end_price"]
    rc = ret_color(ret)
    pc = ret_color(row["profit"])
    sector = SECTOR_MAP.get(ticker, "")
    return (
        f'<div class="stock-card" style="border-left:3px solid {border_color};">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div><div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.25rem;">'
        f'<span style="font-size:0.9rem;">{rank_label}</span>'
        f'<span style="font-size:1.05rem;">{group_colored(ticker, data.group_map)}</span>'
        f'<span style="font-size:0.85rem;">{group_emoji(ticker, data.group_map)}</span></div>'
        f'<div style="font-size:0.75rem;color:var(--muted);">{esc(row["name"])}{" · " + sector if sector else ""}</div></div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:1.3rem;font-weight:800;color:{rc};">{ret:+.2f}%</div>'
        f'<div style="font-size:0.68rem;color:var(--muted);">Total Return</div></div></div>'
        f'<div style="display:flex;gap:1.2rem;margin-top:0.7rem;font-size:0.76rem;">'
        f'<div><span style="color:var(--muted);">Price</span><br><span style="font-weight:600;">${sp:.2f} → ${ep:.2f}</span></div>'
        f'<div><span style="color:var(--muted);">P/L</span><br><span style="font-weight:600;color:{pc};">{"+" if row["profit"] >= 0 else ""}${row["profit"]:.2f}</span></div>'
        f'<div><span style="color:var(--muted);">Value</span><br><span style="font-weight:600;">${row["total_value"]:.2f}</span></div></div>'
        f'<div style="margin-top:0.5rem;font-size:0.7rem;"><span style="color:{rc};">{streak_icon} {streak_text}</span></div>'
        f'</div>'
    )


def _leaderboard_iframe(data: GameData, scores: pd.DataFrame, rank_deltas: dict,
                        start_date: datetime.date, end_date: datetime.date):
    """Sortable, searchable leaderboard with date-window controls (self-contained iframe)."""
    start_label = data.prices.index[0].strftime("%m/%d/%Y") if len(data.prices) else ""
    end_label = data.prices.index[-1].strftime("%m/%d/%Y") if len(data.prices) else ""

    group_badge_styles = {
        "ANTY": "background:rgba(168,85,247,0.15);color:#a855f7;",
        "UNCL": "background:rgba(59,130,246,0.15);color:#3b82f6;",
        "KIDZ": "background:rgba(234,179,8,0.15);color:#eab308;",
    }

    total = len(scores)
    first_negative_rank = next(
        (i for i, (_, r) in enumerate(scores.iterrows()) if r["total_return_pct"] < 0), None)

    body_rows = []
    for rank, (ticker, row) in enumerate(scores.iterrows(), start=1):
        raw = data.raw_prices[ticker].dropna() if ticker in data.raw_prices.columns else None
        sp = float(raw.iloc[0]) if raw is not None and len(raw) else row["start_price"]
        ep = float(raw.iloc[-1]) if raw is not None and len(raw) else row["end_price"]
        display_ticker = f"\U0001f451 {ticker}" if rank == 1 else (
            f"\U0001f4a9 {ticker}" if rank == total else ticker)
        delta = rank_deltas.get(ticker, 0)
        if delta > 0:
            arrow = '<span style="color:#19a05f;font-size:12px;">▲</span>'
        elif delta < 0:
            arrow = '<span style="color:#d14a34;font-size:12px;">▼</span>'
        else:
            arrow = '<span style="color:#102018;font-size:12px;display:inline-block;transform:rotate(90deg);">▲</span>'
        g = data.group_map.get(ticker, "")
        badge = (f'<span style="display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;'
                 f'font-size:0.7rem;font-weight:700;{group_badge_styles.get(g, "")}">{g}</span>')
        fraction = (rank - 1) / max(total - 1, 1)
        row_color = _interpolate_hex("#19a05f", "#d14a34", fraction)
        border = "border-top:3px solid #102018;" if first_negative_rank is not None and rank - 1 == first_negative_rank else ""
        div_income = row["dividend_income"]
        cells = [
            f'<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap;">{arrow} {rank}</span>',
            badge,
            SECTOR_MAP.get(ticker, ""),
            f'<b>{esc(display_ticker)}</b><br><span style="color:#5d6f65;font-size:0.75rem;">{esc(row["name"])}</span>',
            fmt_signed_pct(row["total_return_pct"]).replace('style="color:', 'style="font-weight:700;color:'),
            fmt_signed_pct(row["price_return_pct"]).replace('style="color:', 'style="font-weight:700;color:'),
            f'${sp:.2f}<br>→<br>${ep:.2f}',
            f'${data.stake:.2f}',
            f'{row["units"]:.4f}',
            fmt_signed_currency(row["profit"]),
            f'<span style="color:{ret_color(row["price_value"] - data.stake)};">${row["price_value"]:.2f}</span>',
            f'<span style="color:#19a05f;">${div_income:.2f}</span>' if div_income > 0 else f'${div_income:.2f}',
            f'<span style="color:{ret_color(row["profit"])};">${row["total_value"]:.2f}</span>',
        ]
        styled = "".join(
            f'<td style="{border}{"" if i in (4, 5, 9, 10, 11, 12) else f"color:{row_color};"}">{c}</td>'
            for i, c in enumerate(cells))
        body_rows.append(f"<tr>{styled}</tr>")

    invested = data.stake * total
    mkt = scores["price_value"].sum()
    divs = scores["dividend_income"].sum()
    headers = ["Rank", "Group", "Sector", "Stock", "Total Return (%)", "Price Return (%)",
               f"Price ({start_label} – {end_label})", "Stake", "Units", "Profit/(Loss)",
               "Mkt Value", "Dividends", "Total Value"]
    total_row = (
        '<tr class="total-row">'
        f'<td><b>Total</b></td><td></td><td></td><td><b>{total} picks</b></td>'
        f'<td>{fmt_signed_pct(((mkt + divs) / invested - 1) * 100)}</td>'
        f'<td>{fmt_signed_pct((mkt / invested - 1) * 100)}</td>'
        f'<td></td><td><b>${invested:.2f}</b></td><td></td>'
        f'<td><b>{fmt_signed_currency(mkt + divs - invested)}</b></td>'
        f'<td><b>${mkt:.2f}</b></td><td><b>${divs:.2f}</b></td><td><b>${mkt + divs:.2f}</b></td></tr>'
    )

    html = (
        '<style>'
        'body { margin:0; padding:0; font-family:"Space Grotesk",sans-serif; }'
        '.controls-bar { display:flex;align-items:center;gap:0.4rem;background:rgba(255,255,255,0.7);'
        '  border:1px solid rgba(18,51,36,0.1);border-radius:12px;padding:0.4rem 0.5rem;margin-bottom:0.5rem;flex-wrap:nowrap; }'
        '.search-wrap { position:relative;flex:1 1 auto;min-width:80px; }'
        '.search-wrap .s-icon { position:absolute;left:0.5rem;top:50%;transform:translateY(-50%);font-size:0.75rem;color:#9ca8a0;pointer-events:none; }'
        '.search-wrap input { width:100%;box-sizing:border-box;padding:0.3rem 0.4rem 0.3rem 1.6rem;border:1.5px solid rgba(18,51,36,0.1);'
        '  border-radius:8px;font-family:inherit;font-size:0.78rem;font-weight:600;background:white;color:#102018;outline:none; }'
        '.search-wrap input:focus { border-color:rgba(14,95,58,0.4); }'
        '.vdiv { width:1px;height:22px;background:rgba(18,51,36,0.12);flex-shrink:0; }'
        '.date-group { display:flex;align-items:center;gap:0.25rem;flex-shrink:0;white-space:nowrap; }'
        '.date-label { font-size:0.65rem;font-weight:700;color:#5d6f65;letter-spacing:0.04em; }'
        '.date-input { padding:0.3rem 0.4rem;border:1.5px solid rgba(18,51,36,0.1);border-radius:8px;'
        '  font-family:inherit;font-size:0.78rem;font-weight:600;color:#102018;background:white;width:105px; }'
        '.btn-apply { padding:0.3rem 0.6rem;border:none;background:#0e5f3a;color:white;border-radius:8px;'
        '  font-family:inherit;font-size:0.7rem;font-weight:700;cursor:pointer; }'
        '.btn-reset { padding:0.3rem 0.6rem;border:1.5px solid rgba(18,51,36,0.12);background:white;color:#5d6f65;'
        '  border-radius:8px;font-family:inherit;font-size:0.7rem;font-weight:700;cursor:pointer; }'
        '.lb-count { font-size:0.72rem;color:#5d6f65;margin-bottom:0.3rem;display:none; }'
        '.lb-wrap { overflow:scroll;-webkit-overflow-scrolling:touch;max-height:620px;'
        '  border-radius:18px;border:1px solid rgba(18,51,36,0.12); }'
        '.lb-wrap::-webkit-scrollbar { height:10px;width:10px;-webkit-appearance:none;display:block; }'
        '.lb-wrap::-webkit-scrollbar-track { background:rgba(18,51,36,0.03);border-radius:5px; }'
        '.lb-wrap::-webkit-scrollbar-thumb { background:rgba(18,51,36,0.12);border-radius:5px;min-height:40px;min-width:40px; }'
        'table.leaderboard { min-width:max-content;width:100%;border-collapse:separate;border-spacing:0;'
        '  border-radius:18px;background:rgba(251,253,250,0.96); }'
        'table.leaderboard td, table.leaderboard th { padding:10px 8px;text-align:left;'
        '  border-bottom:1px solid rgba(18,51,36,0.06);border-right:1px solid rgba(18,51,36,0.04);'
        '  white-space:nowrap;font-size:0.82rem; }'
        'table.leaderboard th { white-space:normal;background:linear-gradient(90deg,#0d2f20,#13492f);color:#f4f0e3;'
        '  text-transform:uppercase;letter-spacing:0.06em;font-size:0.72rem;font-weight:700;min-width:45px;'
        '  max-width:100px;line-height:1.3;position:sticky;top:0;z-index:1;cursor:pointer;user-select:none; }'
        'table.leaderboard th .sort-arrow { font-size:0.6rem;margin-left:3px;opacity:0.4; }'
        'table.leaderboard th.sort-active .sort-arrow { opacity:1; }'
        'table.leaderboard tr:nth-child(even) td { background:rgba(16,95,58,0.04); }'
        'table.leaderboard tbody tr:hover td { background:rgba(14,95,58,0.08); }'
        'table.leaderboard tr.total-row td { font-weight:700;background:rgba(18,51,36,0.06);'
        '  border-top:2px solid rgba(18,51,36,0.2); }'
        'tr.search-hidden { display:none; }'
        'tr.search-highlight td { background:rgba(215,168,58,0.25) !important; }'
        '@media (max-width:768px) {'
        '  .controls-bar{flex-wrap:wrap;} .vdiv{display:none;}'
        '  .search-wrap{width:100%;min-width:100%;margin-bottom:0.2rem;}'
        '  .date-group{width:100%;justify-content:space-between;} .date-input{flex:1;min-width:0;font-size:14px;}'
        '  table.leaderboard td, table.leaderboard th { padding:6px 5px;font-size:0.7rem; }'
        '  table.leaderboard th { font-size:0.6rem;min-width:40px; }'
        '}'
        '</style>'
        '<div class="controls-bar">'
        '  <div class="search-wrap"><span class="s-icon">\U0001f50d</span>'
        '    <input type="text" id="lbSearch" placeholder="Search ticker or name..." autocomplete="off"></div>'
        '  <div class="vdiv"></div>'
        '  <div class="date-group">'
        '    <span class="date-label">FROM</span>'
        f'    <input type="date" class="date-input" id="dateStart" value="{start_date.strftime("%Y-%m-%d")}">'
        '    <span class="date-label">TO</span>'
        f'    <input type="date" class="date-input" id="dateEnd" value="{end_date.strftime("%Y-%m-%d")}">'
        '    <button class="btn-apply" onclick="applyDates()">Apply</button>'
        '    <button class="btn-reset" onclick="resetDates()">Reset</button>'
        '  </div></div>'
        '<div class="lb-count" id="lbCount"></div>'
        '<div class="lb-wrap"><table class="leaderboard"><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in headers)
        + '</tr></thead><tbody>'
        + "".join(body_rows) + total_row
        + '</tbody></table></div>'
        '<script>'
        'var table=document.querySelector("table.leaderboard");'
        'var headers=table.querySelectorAll("thead th");'
        'headers.forEach(function(th,i){'
        '  th.innerHTML+=\'<span class="sort-arrow">▲▼</span>\';'
        '  th.addEventListener("click",function(){sortTable(i,th);});'
        '});'
        'var sortCol=-1,sortAsc=true;'
        'function parseVal(cell){'
        '  var txt=cell.textContent.trim();'
        '  if(!txt)return null;'
        '  txt=txt.replace(/^[▲▼]/,"").trim();'
        '  var cleaned=txt.replace(/[$,%()]/g,"").trim();'
        '  if(txt.indexOf("(")>-1&&txt.indexOf(")")>-1){cleaned="-"+cleaned;}'
        '  var num=parseFloat(cleaned);'
        '  if(!isNaN(num))return num;'
        '  return txt.toLowerCase();'
        '}'
        'function sortTable(colIdx,th){'
        '  var tbody=table.querySelector("tbody");'
        '  var rows=Array.from(tbody.querySelectorAll("tr"));'
        '  var totalRow=rows.pop();'
        '  if(sortCol===colIdx){sortAsc=!sortAsc;}else{sortCol=colIdx;sortAsc=true;}'
        '  rows.sort(function(a,b){'
        '    var va=parseVal(a.cells[colIdx]),vb=parseVal(b.cells[colIdx]);'
        '    if(va===null&&vb===null)return 0;'
        '    if(va===null)return 1;if(vb===null)return -1;'
        '    if(typeof va==="number"&&typeof vb==="number")return sortAsc?va-vb:vb-va;'
        '    return sortAsc?String(va).localeCompare(String(vb)):String(vb).localeCompare(String(va));'
        '  });'
        '  rows.forEach(function(r){tbody.appendChild(r);});'
        '  tbody.appendChild(totalRow);'
        '  headers.forEach(function(h){h.classList.remove("sort-active");'
        '    if(h!==th){var ar=h.querySelector(".sort-arrow");if(ar)ar.textContent="▲▼";}});'
        '  th.classList.add("sort-active");'
        '  th.querySelector(".sort-arrow").textContent=sortAsc?"▲":"▼";'
        '}'
        'var lbSearch=document.getElementById("lbSearch");'
        'var lbCount=document.getElementById("lbCount");'
        'var allRows=Array.from(table.querySelectorAll("tbody tr"));'
        'var totalR=allRows[allRows.length-1];'
        'lbSearch.addEventListener("input",function(){'
        '  var q=this.value.toLowerCase().trim();'
        '  if(!q){allRows.forEach(function(r){r.classList.remove("search-hidden","search-highlight");});'
        '    lbCount.style.display="none";return;}'
        '  var mc=0,total=0;'
        '  allRows.forEach(function(r){'
        '    if(r===totalR){r.classList.remove("search-hidden","search-highlight");return;}'
        '    total++;'
        '    var txt=r.cells[3].textContent.toLowerCase();'
        '    if(txt.indexOf(q)>-1){r.classList.remove("search-hidden");r.classList.add("search-highlight");mc++;}'
        '    else{r.classList.add("search-hidden");r.classList.remove("search-highlight");}'
        '  });'
        '  lbCount.textContent=mc+" of "+total+" picks";'
        '  lbCount.style.display="block";'
        '});'
        'function applyDates(){'
        '  var s=document.getElementById("dateStart").value;'
        '  var e=document.getElementById("dateEnd").value;'
        '  if(s&&e){window.parent.location.search="?ds="+s+"&de="+e;}'
        '}'
        f'function resetDates(){{window.parent.location.search="";}}'
        '</script>'
    )
    components.html(html, height=730, scrolling=False)
    st.markdown(
        '<div style="font-size:0.7rem;color:var(--muted);line-height:1.4;margin-top:-0.3rem;">'
        '<b>Price Return (%)</b> is the split-adjusted share-price change over the period, excluding dividends. '
        '<b>Total Return (%)</b> adds dividend cash — this is what the game ranks on.</div>',
        unsafe_allow_html=True,
    )


def render(data: GameData, computed: dict, start_date: datetime.date, end_date: datetime.date):
    scores = computed["scores"]
    total_returns = computed["total_returns"]
    throne = computed["throne"]
    rank_deltas = computed["rank_deltas"]
    superlatives = computed["superlatives"]

    end_label = data.prices.index[-1].strftime("%b %d, %Y") if len(data.prices) else ""
    _portfolio_card(scores, data, end_label)

    section("", "Who's Hot \U0001f525 Who's Not \U0001f4a9 Who's Meh \U0001f610")
    best, worst = scores.index[0], scores.index[-1]
    meh = superlatives.get("middle", {}).get("ticker", "")
    cols = st.columns(3)
    cols[0].markdown(_stock_card(best, data, scores, "\U0001f525",
                                 f"{throne['mvp_streak']}-day streak", "\U0001f525", "#19a05f"),
                     unsafe_allow_html=True)
    cols[1].markdown(_stock_card(worst, data, scores, "\U0001f4a9",
                                 f"{throne['bench_streak']}-day streak", "\U0001f4c9", "#d14a34"),
                     unsafe_allow_html=True)
    if meh and meh in scores.index:
        cols[2].markdown(_stock_card(meh, data, scores, "\U0001f610",
                                     "Closest to 0% return", "⚖️", "#a1a1aa"),
                         unsafe_allow_html=True)

    section("\U0001f3c6", "Leaderboard")
    _leaderboard_iframe(data, scores, rank_deltas, start_date, end_date)

    section("\U0001f687", "Stock Subway", "rank journeys, top + bottom 10")
    top10 = list(scores.head(10).index)
    bottom10 = list(scores.tail(10).index)
    total = len(scores)
    with st.container(key="bump-charts-desktop"):
        st.plotly_chart(
            charts.bump_chart(total_returns, top10, data.name_map, data.group_map,
                              "Top 10 — In the Money"),
            use_container_width=True, config=charts.CHART_CONFIG)
        st.plotly_chart(
            charts.bump_chart(total_returns, bottom10, data.name_map, data.group_map,
                              "Bottom 10 — Out of the Money",
                              label_rank_fn=lambda r: total - 10 + r),
            use_container_width=True, config=charts.CHART_CONFIG)

    def _mobile_row(ticker, rank):
        ret = float(scores.loc[ticker, "total_return_pct"])
        return (f'<div class="bump-mobile-row"><span class="bmr-rank">#{rank}</span>'
                f'<span>{group_emoji(ticker, data.group_map)}</span>'
                f'{group_colored(ticker, data.group_map)}'
                f'<span class="bmr-ret" style="color:{ret_color(ret)};">{ret:+.2f}%</span></div>')

    top_rows = "".join(_mobile_row(t, i + 1) for i, t in enumerate(top10))
    bot_rows = "".join(_mobile_row(t, total - 10 + i + 1) for i, t in enumerate(bottom10))
    st.markdown(
        '<div class="bump-mobile-list">'
        f'<div class="bump-mobile-card"><div class="bump-mobile-title">Top 10 In the Money</div>{top_rows}</div>'
        f'<div class="bump-mobile-card"><div class="bump-mobile-title">Bottom 10 Out of the Money</div>{bot_rows}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
