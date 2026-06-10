"""Render a snapshot into a self-contained HTML email (and a plain-text twin).

Email-client rules: inline CSS only (clients strip <style>), single column,
~600px max width, table-based layout, no external assets.
"""

from __future__ import annotations

import html as html_mod

from smfd.config import GROUP_COLORS, GROUP_EMOJI, GROUP_NAMES

_GREEN = "#0e5f3a"
_RED = "#b3422f"
_TEXT = "#102018"
_MUTED = "#5d6f65"
_BG = "#f4f7f2"
_PANEL = "#ffffff"
_BORDER = "#dde5dc"
_GOLD = "#b8860b"


def _esc(s) -> str:
    return html_mod.escape(str(s))


def _pct(v: float) -> str:
    color = _GREEN if v >= 0 else _RED
    return f'<span style="color:{color};font-weight:700;">{v:+.1f}%</span>'


def _pick_line(p: dict, rank: int) -> str:
    emoji = GROUP_EMOJI.get(p["etf"], "")
    color = GROUP_COLORS.get(p["etf"], _TEXT)
    return (
        f'<tr><td style="padding:6px 4px;font-size:14px;color:{_MUTED};width:24px;">{rank}</td>'
        f'<td style="padding:6px 4px;font-size:14px;">{emoji} '
        f'<span style="color:{color};font-weight:700;">{_esc(p["ticker"])}</span> '
        f'<span style="color:{_MUTED};font-size:12px;">{_esc(p["name"])}</span></td>'
        f'<td style="padding:6px 4px;font-size:14px;text-align:right;">{_pct(p["total_return_pct"])}</td></tr>'
    )


def _section(title: str, body: str) -> str:
    return (
        f'<tr><td style="padding:18px 24px 0;">'
        f'<div style="font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
        f'color:{_GREEN};padding-bottom:6px;">{_esc(title)}</div>'
        f'<div style="background:{_PANEL};border:1px solid {_BORDER};border-radius:12px;'
        f'padding:14px 16px;">{body}</div></td></tr>'
    )


def render_html(snapshot: dict) -> str:
    s = snapshot

    standings_rows = "".join(_pick_line(p, i + 1) for i, p in enumerate(s["standings_top"]))
    n = s["n_picks"]
    bottom_rows = "".join(
        _pick_line(p, n - len(s["standings_bottom"]) + i + 1)
        for i, p in enumerate(s["standings_bottom"]))

    group_rows = ""
    medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
    for g in s["group_standings"]:
        color = GROUP_COLORS.get(g["etf"], _TEXT)
        change = g["change_vs_last"]
        if change.startswith("+"):
            change_html = f'<span style="color:{_GREEN};font-size:12px;">▲ up {change[1:]}</span>'
        elif change.startswith("-"):
            change_html = f'<span style="color:{_RED};font-size:12px;">▼ down {change[1:]}</span>'
        else:
            change_html = f'<span style="color:{_MUTED};font-size:12px;">— steady</span>'
        group_rows += (
            f'<tr><td style="padding:6px 4px;font-size:15px;">{medals.get(g["rank"], "")} '
            f'{GROUP_EMOJI.get(g["etf"], "")} <span style="color:{color};font-weight:700;">'
            f'{_esc(GROUP_NAMES.get(g["etf"], g["etf"]))}</span></td>'
            f'<td style="padding:6px 4px;text-align:center;">{change_html}</td>'
            f'<td style="padding:6px 4px;font-size:15px;text-align:right;">{_pct(g["avg_return_pct"])}</td></tr>'
        )

    movers = ""
    for m in s["top_movers"]:
        movers += (f'<tr><td style="padding:4px;font-size:14px;">\U0001f680 <b>{_esc(m["ticker"])}</b></td>'
                   f'<td style="padding:4px;font-size:14px;text-align:right;">{_pct(m["period_change_pct"])}</td></tr>')
    for m in s["bottom_movers"]:
        movers += (f'<tr><td style="padding:4px;font-size:14px;">\U0001f9ca <b>{_esc(m["ticker"])}</b></td>'
                   f'<td style="padding:4px;font-size:14px;text-align:right;">{_pct(m["period_change_pct"])}</td></tr>')

    pl = s["total_value"] - s["total_invested"]

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:{_BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};">
<tr><td align="center" style="padding:18px 8px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;font-family:Helvetica,Arial,sans-serif;color:{_TEXT};">

  <tr><td style="background:linear-gradient(135deg,#0d2f20,#13492f);background-color:#0d2f20;
                 border-radius:16px;padding:22px 24px;color:#f4f0e3;">
    <div style="font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#d7a83a;">
      \U0001f9f7 Stock Market Fantasy Draft</div>
    <div style="font-size:24px;font-weight:800;margin:6px 0 4px;">Alessi's Stock Draft</div>
    <div style="font-size:13px;opacity:0.85;">{_esc(s["period_label"])}</div>
    <div style="font-size:13px;margin-top:10px;background:rgba(255,255,255,0.1);display:inline-block;
                padding:5px 12px;border-radius:999px;">
      \U0001f37c <b>{s["days_remaining"]} days</b> until Alessi decides it all</div>
  </td></tr>

  {_section("The Headline", f'<div style="font-size:16px;line-height:1.45;font-weight:600;">{_esc(s["headline_stat"])}</div>')}

  {_section("State of the Pot", f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="font-size:13px;color:{_MUTED};">Draft portfolio</td>
      <td style="font-size:13px;color:{_MUTED};text-align:right;">Dividends collected</td>
    </tr>
    <tr>
      <td style="font-size:20px;font-weight:800;color:{_GREEN if pl >= 0 else _RED};">${s["total_value"]:,.2f}
        <span style="font-size:12px;font-weight:400;color:{_MUTED};">on ${s["total_invested"]:,.0f} in</span></td>
      <td style="font-size:20px;font-weight:800;text-align:right;color:{_GOLD};">${s["total_dividends"]:,.2f}</td>
    </tr></table>''')}

  {_section("Group Battle", f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{group_rows}</table>')}

  {_section("Top of the Table", f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{standings_rows}</table>')}

  {_section("…and the Basement", f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{bottom_rows}</table>')}

  {_section("Movers This Period", f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{movers}</table>')}

  {_section("Today's Roast", f'<div style="font-size:14px;line-height:1.5;font-style:italic;">{_esc(s["roast"])}</div>')}

  {_section("The Word", f'<div style="font-size:14px;line-height:1.55;">{_esc(s["narrative"])}</div>')}

  <tr><td style="padding:18px 24px;text-align:center;color:{_MUTED};font-size:12px;line-height:1.5;">
    $10 per pick, all notional, zero diapers changed by the market.<br>
    Game ends <b>April 15, 2027</b> \U0001f37c · numbers as of {_esc(s["as_of"])}
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def render_plain_text(snapshot: dict) -> str:
    s = snapshot
    lines = [
        "STOCK MARKET FANTASY DRAFT — Alessi's Stock Draft",
        s["period_label"],
        f"{s['days_remaining']} days until Alessi decides it all",
        "",
        f"THE HEADLINE: {s['headline_stat']}",
        "",
        f"Draft portfolio: ${s['total_value']:,.2f} on ${s['total_invested']:,.0f} invested "
        f"(dividends collected: ${s['total_dividends']:,.2f})",
        "",
        "GROUP BATTLE",
    ]
    for g in s["group_standings"]:
        change = {"=": "steady"}.get(g["change_vs_last"], g["change_vs_last"])
        lines.append(f"  {g['rank']}. {GROUP_NAMES.get(g['etf'], g['etf'])}: "
                     f"{g['avg_return_pct']:+.1f}% ({change})")
    lines += ["", "TOP OF THE TABLE"]
    for i, p in enumerate(s["standings_top"], start=1):
        lines.append(f"  {i}. {p['ticker']} ({p['name']}): {p['total_return_pct']:+.1f}%")
    lines += ["", "...AND THE BASEMENT"]
    n = s["n_picks"]
    for i, p in enumerate(s["standings_bottom"]):
        lines.append(f"  {n - len(s['standings_bottom']) + i + 1}. {p['ticker']} "
                     f"({p['name']}): {p['total_return_pct']:+.1f}%")
    lines += ["", "MOVERS THIS PERIOD"]
    for m in s["top_movers"]:
        lines.append(f"  up: {m['ticker']} {m['period_change_pct']:+.1f} pp")
    for m in s["bottom_movers"]:
        lines.append(f"  down: {m['ticker']} {m['period_change_pct']:+.1f} pp")
    lines += [
        "",
        f"TODAY'S ROAST: {s['roast']}",
        "",
        s["narrative"],
        "",
        f"Game ends April 15, 2027. Numbers as of {s['as_of']}.",
    ]
    return "\n".join(lines)
