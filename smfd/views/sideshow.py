"""Sideshow: the fun stuff — bragging rights, throne room, roasts, predictions,
trivia, and the sector scoreboard."""

from __future__ import annotations

import json
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components

from smfd import trivia
from smfd.compute import predictions as preds_mod
from smfd.compute import roasts as roasts_mod
from smfd.config import GROUP_COLORS, GROUP_EMOJI, SECTOR_MAP
from smfd.data import GameData
from smfd.views.common import esc, group_colored, group_emoji, ret_color, section

_BADGE_TONES = {
    "Diamond Hands": "green", "Moonshot": "green", "Dark Horse": "green",
    "Comeback Kid": "green", "Steady Eddie": "green", "The Terminator": "green",
    "Dividend King": "green", "Iron Throne": "green",
    "Bag Holder": "red", "Crash Landing": "red", "Dead Weight": "red",
    "Fallen Angel": "red", "All Talk": "red", "Bottom Feeder": "red",
    "Rollercoaster": "amber", "Middle Child": "amber", "Rivalry": "amber",
    "Group War": "amber", "Photo Finish": "amber",
}
_TONE_STYLES = {
    "green": ("rgba(25,160,95,0.12)", "rgba(25,160,95,0.05)", "rgba(25,160,95,0.10)"),
    "red": ("rgba(209,74,52,0.12)", "rgba(209,74,52,0.05)", "rgba(209,74,52,0.10)"),
    "amber": ("rgba(215,168,58,0.15)", "rgba(215,168,58,0.06)", "rgba(215,168,58,0.12)"),
}

REACTION_EMOJIS = ["\U0001f602", "\U0001f480", "\U0001f525"]


def _color_tickers(text: str, group_map: dict) -> str:
    escaped = esc(text)
    for t in sorted(group_map, key=len, reverse=True):
        color = GROUP_COLORS.get(group_map.get(t, ""), "")
        if color and t in escaped:
            escaped = escaped.replace(t, f'<span style="color:{color};font-weight:700;">{t}</span>')
    return escaped


def _badges_data(data: GameData, computed: dict) -> list:
    """Assemble bragging-rights pairs from superlatives + achievements."""
    sup = computed["superlatives"]
    achievements = computed["achievements"]
    throne = computed["throne"]
    scores = computed["scores"]
    total_returns = computed["total_returns"]
    final_returns = scores["total_return_pct"]

    def find(name):
        return next((b for b in achievements if b["name"] == name), None)

    out = []

    diamond = find("Diamond Hands")
    if diamond and diamond["unlocked"] and throne.get("mvp_longest", {}).get("ticker"):
        lg = throne["mvp_longest"]
        rng = (f"{lg['start'].strftime('%b %d')} – {lg['end'].strftime('%b %d')}"
               if lg["start"] is not None else "")
        out.append(("\U0001f48e", "Diamond Hands", f"{lg['ticker']} ({lg['streak']}d), {rng}",
                    "Longest MVP streak"))
    bottom = find("Bottom Feeder")
    if bottom and bottom["unlocked"] and throne.get("bench_longest", {}).get("ticker"):
        lg = throne["bench_longest"]
        rng = (f"{lg['start'].strftime('%b %d')} – {lg['end'].strftime('%b %d')}"
               if lg["start"] is not None else "")
        out.append(("\U0001f9fb", "Bag Holder", f"{lg['ticker']} ({lg['streak']}d), {rng}",
                    "Longest benchwarmer streak"))

    bd, wd = sup.get("best_day"), sup.get("worst_day")
    if bd:
        out.append(("\U0001f315", "Moonshot",
                    f"{bd['ticker']} ({bd['change']:+.2f}% on {bd['date'].strftime('%b %d')})",
                    "Biggest single-day gain"))
    if wd:
        out.append(("\U0001f4a5", "Crash Landing",
                    f"{wd['ticker']} ({wd['change']:+.2f}% on {wd['date'].strftime('%b %d')})",
                    "Biggest single-day loss"))

    coaster, steady = find("Rollercoaster"), find("Steady Eddie")
    if coaster:
        out.append(("\U0001f3a2", "Rollercoaster", coaster["holder"], "Most volatile pick"))
    if steady:
        out.append(("\U0001f9d8", "Steady Eddie", steady["holder"], "Least volatile pick"))

    cb = sup.get("comeback", {})
    if cb.get("ticker"):
        out.append(("\U0001f9d7", "Comeback Kid",
                    f"{cb['ticker']} ({cb['low']:+.2f}% → {cb['final']:+.2f}%)",
                    "Biggest recovery from a low"))
    losers = final_returns[final_returns < 0]
    if len(losers):
        dead = losers.idxmin()
        low = float(total_returns[dead].min())
        out.append(("\U0001faa8", "Dead Weight",
                    f"{dead} ({low:+.2f}% → {final_returns[dead]:+.2f}%)",
                    "Went down and stayed down"))

    horse = find("Dark Horse")
    if horse and horse["unlocked"]:
        out.append(("\U0001f40e", "Dark Horse", horse["holder"], "Bottom 25% → Top 25%"))
    fa = sup.get("fallen", {})
    if fa.get("ticker"):
        out.append(("\U0001f607", "Fallen Angel",
                    f"{fa['ticker']} (#{fa['start_rank']}→#{fa['end_rank']})",
                    "Top half → dropped the most"))

    term = find("The Terminator")
    if term:
        out.append(("\U0001f916", "The Terminator", term["holder"], "Took MVP throne most times"))
    mc = sup.get("middle", {})
    if mc.get("ticker"):
        out.append(("\U0001fae5", "Middle Child", f"{mc['ticker']} ({mc['return']:+.2f}%)",
                    "Closest to 0%"))

    rv = sup.get("rivalry", {})
    if rv.get("ticker1"):
        out.append(("⚔️", "Rivalry", f"{rv['ticker1']} vs {rv['ticker2']} ({rv['swaps']}x)",
                    "Most throne swaps"))
    ew = sup.get("etf_war", {})
    if ew.get("etf"):
        out.append(("⚡", "Group War",
                    f"{GROUP_EMOJI.get(ew['etf'], '')} {ew['etf']} ({ew['streak']}d)",
                    "Longest daily win streak"))

    divking = find("Dividend King")
    if divking and divking["unlocked"]:
        out.append(("\U0001f4b0", "Dividend King", divking["holder"], "Most dividend income"))
    zero_div = scores[scores["dividend_income"] == 0]
    if len(zero_div):
        all_talk = zero_div["total_return_pct"].idxmax()
        out.append(("\U0001f4ac", "All Talk",
                    f"{all_talk} ({final_returns[all_talk]:+.2f}%, $0 divs)",
                    "Best return, zero dividends"))

    photo = find("Photo Finish")
    if photo:
        out.append(("\U0001f4f8", "Photo Finish", photo["holder"], "Closest return gap"))
    return out


def _render_badges(badges_data: list, data: GameData):
    def cell(icon, name, holder, desc):
        tone = _BADGE_TONES.get(name, "green")
        bg_from, bg_to, shadow = _TONE_STYLES[tone]
        return (
            f'<td style="padding:0.85rem 1.2rem;vertical-align:middle;">'
            f'<div style="display:flex;align-items:center;gap:0.9rem;">'
            f'<div style="width:42px;height:42px;border-radius:12px;'
            f'background:linear-gradient(135deg,{bg_from},{bg_to});display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;box-shadow:0 2px 6px {shadow};">'
            f'<span style="font-size:1.5rem;line-height:1;">{icon}</span></div>'
            f'<div><div style="font-weight:800;font-size:0.82rem;">{esc(name)}</div>'
            f'<div style="font-size:0.78rem;color:#2d4a3a;margin-top:0.1rem;">'
            f'{_color_tickers(holder, data.group_map)}</div>'
            f'<div style="font-size:0.62rem;color:#5d6f65;opacity:0.8;margin-top:0.1rem;">{esc(desc)}</div>'
            f'</div></div></td>'
        )

    # Multi-award bar
    ticker_badges = defaultdict(list)
    for icon, name, holder, _ in badges_data:
        base = holder.split(" (")[0] if holder else ""
        parts = [p.strip() for p in base.split(" vs ")] if " vs " in base else [base.split(" ")[0]]
        for p in parts:
            if p in data.group_map:
                ticker_badges[p].append(icon)
    multi = {t: icons for t, icons in ticker_badges.items() if len(icons) > 1}
    if multi:
        chips = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:0.25rem;background:rgba(255,255,255,0.6);'
            f'border-radius:999px;padding:0.15rem 0.55rem;font-size:0.72rem;">'
            f'{group_colored(t, data.group_map)} {"".join(icons)}</span>'
            for t, icons in sorted(multi.items(), key=lambda x: -len(x[1])))
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;padding:0.5rem 0.8rem;'
            f'background:rgba(215,168,58,0.08);border:1px solid rgba(215,168,58,0.2);border-radius:12px;'
            f'font-size:0.78rem;margin-bottom:0.5rem;">'
            f'<span style="font-weight:700;color:#b45309;">\U0001f3af Multi-Award:</span>{chips}</div>',
            unsafe_allow_html=True,
        )

    rows = ""
    for i in range(0, len(badges_data), 2):
        left = badges_data[i]
        right = badges_data[i + 1] if i + 1 < len(badges_data) else None
        rows += "<tr>" + cell(*left)
        if right:
            rows += ('<td style="width:1px;padding:0;"><div style="width:1px;height:100%;'
                     'background:rgba(18,51,36,0.08);"></div></td>') + cell(*right)
        rows += "</tr>"
    st.markdown(
        f'<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">'
        f'<table style="width:100%;border-collapse:separate;border-spacing:0;border-radius:18px;'
        f'overflow:hidden;background:linear-gradient(180deg,rgba(251,253,250,0.98),rgba(237,245,238,0.95));'
        f'border:1px solid rgba(18,51,36,0.12);box-shadow:0 8px 32px rgba(14,95,58,0.06);">{rows}</table></div>',
        unsafe_allow_html=True,
    )


def _render_throne(history: list, icon: str, title: str, data: GameData,
                   current_ret: float, streak: int) -> str:
    if not history:
        return ""
    current = history[0]
    rc = ret_color(current_ret)
    reign_start = current["date"].strftime("%b %d")
    header = (
        f'<div class="panel-card">'
        f'<div style="font-weight:800;font-size:0.95rem;margin-bottom:0.8rem;">{icon} {esc(title)}</div>'
        f'<div style="display:flex;align-items:center;gap:0.8rem;padding:0.7rem 0.9rem;'
        f'background:rgba(18,51,36,0.04);border-radius:10px;margin-bottom:0.5rem;">'
        f'<span style="font-size:1.2rem;">{icon}</span>'
        f'<div style="flex:1;"><div style="font-size:0.9rem;">{group_colored(current["ticker"], data.group_map)} '
        f'<span style="font-weight:400;color:var(--muted);font-size:0.8rem;">{esc(current["name"])}</span></div>'
        f'<div style="font-size:0.7rem;color:var(--muted);">Reigning since {reign_start} · {streak}-day streak</div></div>'
        f'<div style="text-align:right;font-weight:800;color:{rc};font-size:1.1rem;">{current_ret:+.2f}%</div></div>'
    )
    past = ""
    for i, entry in enumerate(history):
        if i == 0:
            continue
        r = entry["return_pct"]
        start_d = entry["date"].strftime("%b %d")
        end_d = history[i - 1]["date"].strftime("%b %d")
        days = (history[i - 1]["date"] - entry["date"]).days
        date_range = f"{start_d} – {end_d}" if start_d != end_d else start_d
        past += (
            f'<div class="throne-entry-past">'
            f'<div style="flex:1;font-size:0.82rem;">{group_colored(entry["ticker"], data.group_map)} '
            f'<span style="color:var(--muted);font-size:0.78rem;">{esc(entry["name"])}</span></div>'
            f'<div style="font-size:0.75rem;color:var(--muted);white-space:nowrap;">{date_range}'
            f'{f" ({days}d)" if days > 0 else ""}</div>'
            f'<div style="font-weight:600;color:{ret_color(r)};font-size:0.82rem;">{r:+.2f}%</div></div>'
        )
    return header + past + "</div>"


def _render_roasts(data: GameData, computed: dict, sheets_url: str):
    scores = computed["scores"]
    throne = computed["throne"]
    ticker_html = {t: group_colored(t, data.group_map) for t in scores.index}
    roast_day, roasts = roasts_mod.daily_roasts(
        scores["total_return_pct"], computed["total_returns"], throne, ticker_html)

    personas = [
        ("\U0001f916", "linear-gradient(135deg, #0e5f3a, #19a05f)", "GreenMachine"),
        ("\U0001f608", "linear-gradient(135deg, #6b21a8, #a855f7)", "DiabloAI"),
        ("\U0001f47e", "linear-gradient(135deg, #b91c1c, #ef4444)", "ChadGPT"),
        ("\U0001f9e0", "linear-gradient(135deg, #0369a1, #38bdf8)", "BrainRot"),
        ("\U0001f480", "linear-gradient(135deg, #78350f, #d97706)", "DeadCat"),
    ]

    items = ""
    for idx, roast in enumerate(roasts):
        key = f"roast_{roast_day}_{idx}"
        btns = "".join(
            f'<span class="react-btn" data-roast="{key}" data-emoji="{emoji}" '
            f'onclick="toggleReact(this)">{emoji}</span>'
            for emoji in REACTION_EMOJIS)
        emoji_p, gradient, name = personas[idx % len(personas)]
        side = "right" if idx % 2 else "left"
        items += (
            f'<div class="chat-row chat-{side}">'
            f'<div class="chat-avatar" style="background:{gradient};">{emoji_p}</div>'
            f'<div class="chat-content"><div class="chat-name">{name}</div>'
            f'<div class="chat-bubble"><div class="chat-text">{roast}</div>'
            f'<div class="reactions">{btns}</div></div></div></div>'
        )

    html = f"""
    <html><head><style>
    html, body {{ margin:0; padding:0; background:transparent !important; overflow:hidden;
                  font-family:'Space Grotesk',sans-serif; }}
    .chat-container {{ display:flex; flex-direction:column; gap:0.6rem; }}
    .chat-row {{ display:flex; align-items:flex-start; gap:0.6rem; }}
    .chat-row.chat-right {{ flex-direction:row-reverse; }}
    .chat-avatar {{ width:36px; height:36px; border-radius:50%; display:flex; align-items:center;
                    justify-content:center; font-size:1rem; flex-shrink:0;
                    box-shadow:0 2px 8px rgba(0,0,0,0.18); }}
    .chat-name {{ font-size:0.68rem; font-weight:700; color:#5d6f65; margin-bottom:0.15rem;
                  text-transform:uppercase; }}
    .chat-row.chat-right .chat-name {{ text-align:right; }}
    .chat-content {{ max-width:calc(100% - 48px); }}
    .chat-bubble {{ background:rgba(251,253,250,0.96); border:1px solid rgba(18,51,36,0.12);
                    border-radius:0 18px 18px 18px; padding:0.7rem 1rem;
                    box-shadow:0 4px 12px rgba(16,42,32,0.06); }}
    .chat-row.chat-right .chat-bubble {{ border-radius:18px 0 18px 18px; }}
    .chat-row.chat-right .reactions {{ justify-content:flex-end; }}
    .chat-text {{ font-size:0.85rem; line-height:1.5; color:#102018; }}
    .reactions {{ display:flex; gap:0.3rem; margin-top:0.4rem; }}
    .react-btn {{ display:inline-flex; align-items:center; gap:0.2rem; padding:0.15rem 0.45rem;
                  border:1px solid rgba(18,51,36,0.12); border-radius:999px; background:white;
                  font-size:0.78rem; cursor:pointer; user-select:none; }}
    .react-btn.active {{ border-color:#0e5f3a; background:rgba(14,95,58,0.1); }}
    .react-btn .rcount {{ font-weight:700; font-size:0.72rem; color:#102018; }}
    </style></head><body>
    <div class="chat-container">{items}
      <div style="font-size:0.72rem;color:#5d6f65;">\U0001f4a5 Roasts refresh daily after market close</div>
    </div>
    <script>
    var sheetUrl = {json.dumps(sheets_url)};
    var roastDay = {json.dumps(roast_day)};
    if (localStorage.getItem('roast_day') !== roastDay) {{
      localStorage.removeItem('roast_reacts');
      localStorage.setItem('roast_day', roastDay);
    }}
    var userReacts = JSON.parse(localStorage.getItem('roast_reacts') || '{{}}');
    document.querySelectorAll('.react-btn').forEach(function(btn) {{
      if (userReacts[btn.dataset.roast + '_' + btn.dataset.emoji]) btn.classList.add('active');
    }});
    if (sheetUrl) {{
      fetch(sheetUrl).then(function(r) {{ return r.json(); }}).then(function(counts) {{
        document.querySelectorAll('.react-btn').forEach(function(btn) {{
          var c = (counts[btn.dataset.roast] || {{}})[btn.dataset.emoji] || 0;
          if (c > 0) btn.innerHTML = btn.dataset.emoji + '<span class="rcount">' + c + '</span>';
        }});
      }}).catch(function() {{}});
    }}
    function toggleReact(btn) {{
      var key = btn.dataset.roast + '_' + btn.dataset.emoji;
      var countEl = btn.querySelector('.rcount');
      var count = countEl ? parseInt(countEl.textContent) : 0;
      var delta;
      if (btn.classList.contains('active')) {{
        btn.classList.remove('active'); delta = -1; count = Math.max(0, count - 1);
        delete userReacts[key];
      }} else {{
        btn.classList.add('active'); delta = 1; count += 1;
        userReacts[key] = true;
      }}
      localStorage.setItem('roast_reacts', JSON.stringify(userReacts));
      btn.innerHTML = count > 0 ? btn.dataset.emoji + '<span class="rcount">' + count + '</span>'
                                : btn.dataset.emoji;
      if (sheetUrl) {{
        fetch(sheetUrl + '?roast=' + encodeURIComponent(btn.dataset.roast) +
              '&emoji=' + encodeURIComponent(btn.dataset.emoji) + '&delta=' + delta)
          .catch(function() {{}});
      }}
    }}
    function fitHeight() {{
      // Inside a hidden Streamlit tab everything measures 0px — never shrink
      // below a sane floor or the iframe collapses and stays collapsed.
      var el = document.querySelector('.chat-container');
      var h = el ? el.scrollHeight : 0;
      if (h > 80 && window.frameElement) {{
        window.frameElement.style.height = (h + 16) + 'px';
      }}
    }}
    // Re-measure whenever layout actually changes (e.g. the tab becomes visible)
    new ResizeObserver(fitHeight).observe(document.body);
    window.addEventListener('load', fitHeight);
    </script></body></html>
    """
    components.html(html, height=len(roasts) * 105 + 60, scrolling=False)


def render(data: GameData, computed: dict, sheets_url: str = ""):
    scores = computed["scores"]
    throne = computed["throne"]

    # News ticker
    headlines = []
    interesting = list(scores.head(15).index) + list(scores.tail(15).index)
    for t in dict.fromkeys(interesting):
        items = data.news.get(t, [])
        if items and items[0].get("title"):
            headlines.append(f"\U0001f4f0 {t}: {items[0]['title']}")
    if headlines:
        items_html = " ".join(f'<span class="ticker-item">{esc(line)}</span>' for line in headlines)
        st.markdown(
            f'<div class="news-ticker" style="margin-top:0.6rem;">'
            f'<div class="ticker-track">{items_html}{items_html}</div></div>',
            unsafe_allow_html=True,
        )

    section("\U0001f4aa", "Bragging Rights")
    _render_badges(_badges_data(data, computed), data)

    section("\U0001f3f0", "Throne Room")
    best, worst = scores.index[0], scores.index[-1]
    cols = st.columns(2)
    cols[0].markdown(
        _render_throne(throne["mvp_history"], "\U0001f451", "MVP Throne", data,
                       float(scores.loc[best, "total_return_pct"]), throne["mvp_streak"]),
        unsafe_allow_html=True)
    cols[1].markdown(
        _render_throne(throne["bench_history"], "\U0001f4a9", "Benchwarmer Throne", data,
                       float(scores.loc[worst, "total_return_pct"]), throne["bench_streak"]),
        unsafe_allow_html=True)

    section("\U0001f4a5", "Shots Fired", "fresh burns daily — react if it landed")
    _render_roasts(data, computed, sheets_url)

    section("\U0001f52e", "This Week's Predictions", "momentum-based fun, not financial advice")
    preds = preds_mod.generate_predictions(
        computed["total_returns"], scores, data.name_map, data.group_map)
    if preds:
        history = preds_mod.load_history()
        preds_mod.record_predictions(preds, history)
        cards = "".join(
            f'<div class="pred-card"><div class="pred-icon">{p["icon"]}</div>'
            f'<div class="pred-title">{esc(p["title"])}</div>'
            f'<div class="pred-ticker">{p.get("emoji", "")} '
            f'<span style="color:{GROUP_COLORS.get(data.group_map.get(p["ticker"], ""), "inherit")};">'
            f'{esc(p["ticker"])}</span></div>'
            f'<div class="pred-name">{esc(p["name"])}</div>'
            f'<div class="pred-detail">{esc(p["detail"])}</div>'
            f'<div class="pred-confidence">{p["confidence"]}% confidence</div></div>'
            for p in preds)
        st.markdown(f'<div class="pred-grid">{cards}</div>', unsafe_allow_html=True)

        past = preds_mod.check_past_predictions(history, scores["total_return_pct"])
        if past:
            correct = sum(1 for r in past if r["correct"])
            rows = "".join(
                f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.25rem 0;'
                f'font-size:0.75rem;border-bottom:1px solid rgba(18,51,36,0.06);">'
                f'<span>{"✅" if r["correct"] else "❌"}</span>'
                f'<span style="font-weight:700;min-width:3.5rem;">{esc(r["ticker"])}</span>'
                f'<span style="color:#5d6f65;">{esc(r["title"])}</span>'
                f'<span style="margin-left:auto;color:{"#19a05f" if r["correct"] else "#d14a34"};'
                f'font-size:0.72rem;">{esc(r["actual"])}</span></div>'
                for r in past[-12:])
            st.markdown(
                f'<div style="margin-top:0.5rem;padding:0.5rem 0.8rem;background:rgba(14,95,58,0.06);'
                f'border:1px solid rgba(14,95,58,0.15);border-radius:12px;font-size:0.8rem;">'
                f'\U0001f3af <b>Past Accuracy:</b> {correct}/{len(past)} correct '
                f'({int(correct / len(past) * 100)}%)'
                f'<div style="margin-top:0.4rem;">{rows}</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Predictions unlock once the game has at least 6 trading days of history.")

    section("\U0001f9e0", "Daily Trivia")
    mvp_trivia = trivia.get_daily_trivia(best)
    cols = st.columns(2)
    with cols[0]:
        if mvp_trivia:
            st.markdown(
                f'<div class="trivia-card"><div class="trivia-label">About today\'s MVP — {esc(best)}</div>'
                f'<div class="trivia-text">{esc(mvp_trivia)}</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="trivia-card"><div class="trivia-label">Market trivia</div>'
                f'<div class="trivia-text">{esc(trivia.get_generic_trivia())}</div></div>',
                unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            f'<div class="trivia-card"><div class="trivia-label">Did you know?</div>'
            f'<div class="trivia-text">{esc(trivia.get_generic_trivia())}</div></div>',
            unsafe_allow_html=True)

    section("\U0001f5fa", "Sector Scoreboard")
    sectors = defaultdict(list)
    for t in scores.index:
        if t in SECTOR_MAP:
            sectors[SECTOR_MAP[t]].append(t)
    sector_avgs = {
        sec: scores.loc[members, "total_return_pct"].mean()
        for sec, members in sectors.items()
    }
    rows = ""
    for sec in sorted(sector_avgs, key=sector_avgs.get, reverse=True):
        members = sectors[sec]
        rets = scores.loc[members, "total_return_pct"]
        best_t, worst_t = rets.idxmax(), rets.idxmin()
        tickers_html = ", ".join(group_colored(t, data.group_map) for t in sorted(members))
        rows += (
            f'<tr><td style="font-weight:700;white-space:nowrap;">{esc(sec)}</td>'
            f'<td style="text-align:center;">{len(members)}</td>'
            f'<td style="color:{ret_color(sector_avgs[sec])};font-weight:700;">{sector_avgs[sec]:+.2f}%</td>'
            f'<td style="white-space:normal;">{tickers_html}</td>'
            f'<td>{group_emoji(best_t, data.group_map)} {group_colored(best_t, data.group_map)} '
            f'<span style="color:{ret_color(rets[best_t])};font-weight:700;">{rets[best_t]:+.2f}%</span></td>'
            f'<td>{group_emoji(worst_t, data.group_map)} {group_colored(worst_t, data.group_map)} '
            f'<span style="color:{ret_color(rets[worst_t])};font-weight:700;">{rets[worst_t]:+.2f}%</span></td></tr>'
        )
    st.markdown(
        '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:14px;'
        'border:1px solid var(--border);background:var(--panel-strong);">'
        '<table style="width:100%;min-width:760px;border-collapse:separate;border-spacing:0;font-size:0.8rem;">'
        '<tr>'
        + "".join(
            f'<th style="text-align:left;padding:9px 8px;background:linear-gradient(90deg,#0d2f20,#13492f);'
            f'color:#f4f0e3;font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;">{h}</th>'
            for h in ["Sector", "#", "Avg Return", "Picks", "Best", "Worst"])
        + f'</tr>{rows}</table></div>',
        unsafe_allow_html=True,
    )
