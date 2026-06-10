"""Newsletter view: pick a period, preview, copy/download, self-send.

No email infrastructure — Christina pastes the HTML into Gmail (or forwards the
downloaded file) herself.
"""

from __future__ import annotations

import datetime
import json

import streamlit as st
import streamlit.components.v1 as components

from smfd.data import GameData
from smfd.newsletter import build, template
from smfd.views.common import section


def _copy_button(label: str, payload: str, key: str):
    """A small self-contained copy-to-clipboard button (iframe)."""
    components.html(
        f"""
        <style>
        body {{ margin:0; padding:0; }}
        .copy-btn {{
            font-family:'Space Grotesk',sans-serif; width:100%; padding:0.5rem 1rem;
            border:none; border-radius:999px; cursor:pointer; font-weight:700; font-size:0.85rem;
            background:linear-gradient(90deg,#0e5f3a,#0f8773); color:#fff;
        }}
        .copy-btn.copied {{ background:#19a05f; }}
        </style>
        <button class="copy-btn" id="btn_{key}">{label}</button>
        <script>
        var payload_{key} = {json.dumps(payload)};
        document.getElementById("btn_{key}").addEventListener("click", function() {{
            var btn = this;
            navigator.clipboard.writeText(payload_{key}).then(function() {{
                btn.textContent = "✓ Copied!";
                btn.classList.add("copied");
                setTimeout(function() {{
                    btn.textContent = {json.dumps(label)};
                    btn.classList.remove("copied");
                }}, 2000);
            }}).catch(function() {{
                btn.textContent = "Copy failed — use Download";
            }});
        }});
        </script>
        """,
        height=44,
    )


def render(data: GameData, computed: dict):
    st.markdown(
        '<div class="panel-card" style="margin-top:0.6rem;font-size:0.85rem;">'
        '\U0001f4ec Generate a snapshot of the game, then send it yourself: '
        '<b>Copy HTML</b> and paste straight into Gmail compose (it pastes as rich text), '
        'or <b>Download</b> the file and forward it. The newsletter reads the same numbers '
        'as the dashboard, so it can never disagree with the site.</div>',
        unsafe_allow_html=True,
    )

    last = build.last_newsletter_date()
    period_options = {
        "month": "\U0001f4c5 Last month",
        "since_last": ("\U0001f4ee Since last newsletter"
                       + (f" ({last.strftime('%b %d')})" if last else " (none sent yet)")),
        "all": "\U0001f30d All-time",
    }
    period = st.radio("Period", list(period_options),
                      format_func=period_options.get, horizontal=True,
                      label_visibility="collapsed")

    snapshot = build.build_snapshot(data, computed, period=period)
    html = template.render_html(snapshot)
    plain = template.render_plain_text(snapshot)

    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        _copy_button("\U0001f4cb Copy HTML", html, "html")
    with cols[1]:
        _copy_button("\U0001f4dd Copy plain text", plain, "plain")
    with cols[2]:
        st.download_button(
            "\U0001f4be Download .html",
            data=html,
            file_name=f"fantasy-draft-newsletter-{snapshot['as_of']}.html",
            mime="text/html",
            width="stretch",
        )
    with cols[3]:
        if st.button("\U0001f4ec Mark as sent", width="stretch",
                     help="Logs today as a newsletter date so the next "
                          "'since last newsletter' starts here"):
            build.record_newsletter(snapshot["period_label"])
            st.toast(f"Logged — next 'since last newsletter' starts "
                     f"{datetime.date.today().strftime('%b %d')}.", icon="✅")
            st.rerun()

    section("\U0001f440", "Live Preview", snapshot["period_label"])
    components.html(html, height=1450, scrolling=True)
