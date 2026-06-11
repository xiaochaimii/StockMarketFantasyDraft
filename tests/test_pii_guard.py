"""PII guardrails (CR-1/CR-2): owner names live behind the admin login ONLY.

Static checks on the import graph plus a content check on the newsletter
output. If a public view or the newsletter ever grows a path to smfd.owners,
these fail before the leak ships.
"""

from __future__ import annotations

import re
from pathlib import Path

from smfd.compute import returns
from smfd.newsletter import build, template

ROOT = Path(__file__).resolve().parent.parent

# Everything that renders publicly (or produces the group email). admin.py is
# the one view allowed to touch smfd.owners.
PUBLIC_SOURCES = (
    [ROOT / "app.py"]
    + [p for p in (ROOT / "smfd" / "views").glob("*.py") if p.name != "admin.py"]
    + list((ROOT / "smfd" / "newsletter").glob("*.py"))
    + list((ROOT / "smfd" / "compute").glob("*.py"))
    + list((ROOT / "smfd" / "charts").glob("*.py"))
)

OWNERS_IMPORT = re.compile(
    r"from\s+smfd\s+import\s+[^\n]*\bowners\b"
    r"|from\s+smfd\.owners\s+import"
    r"|import\s+smfd\.owners"
)


def test_no_public_module_imports_owners():
    offenders = [p.relative_to(ROOT) for p in PUBLIC_SOURCES
                 if OWNERS_IMPORT.search(p.read_text())]
    assert not offenders, f"PII leak risk — smfd.owners imported by: {offenders}"


def test_newsletter_is_not_a_public_tab():
    app_src = (ROOT / "app.py").read_text()
    tabs = re.search(r"st\.tabs\(\[(.*?)\]\)", app_src, re.DOTALL)
    assert tabs, "could not find the st.tabs([...]) call in app.py"
    assert "Newsletter" not in tabs.group(1), "Newsletter must not be a public tab (CR-1)"


def test_newsletter_output_contains_no_owner_fields(fixture_roster):
    data = fixture_roster
    scores = returns.compute_scores(data)
    total = returns.total_return_series(data)
    snapshot = build.build_snapshot(data, {"scores": scores, "total_returns": total},
                                    period="all")

    def keys_of(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys_of(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys_of(v)

    assert not [k for k in keys_of(snapshot) if "owner" in k.lower()]
    assert "owner" not in template.render_html(snapshot).lower()
    assert "owner" not in template.render_plain_text(snapshot).lower()
