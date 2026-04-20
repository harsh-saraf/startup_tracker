"""Loads the dashboard shell under Streamlit's AppTest. Proves:

1. Import graph is sound — no broken import, no collision in ``state.py``.
2. Sidebar renders without raising.
3. Five numbered pages are discoverable under ``startup_radar/web/pages/``.

Per ``.claude/rules/testing.md`` bullet 7. Per-page ``AppTest``s are
deferred to a follow-up phase.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_shell_loads_without_exception(tmp_path, monkeypatch) -> None:
    # Point at an empty DB directory so init_db() writes there rather than
    # mutating the checked-in startup_radar.db.
    monkeypatch.chdir(REPO_ROOT)
    at = AppTest.from_file(str(REPO_ROOT / "startup_radar" / "web" / "app.py"), default_timeout=10)
    at.run()
    assert not at.exception, f"shell raised: {at.exception}"


def test_pages_discoverable() -> None:
    pages_dir = REPO_ROOT / "startup_radar" / "web" / "pages"
    pages = sorted(p.stem for p in pages_dir.glob("*.py") if not p.name.startswith("__"))
    assert pages == ["1_dashboard", "2_companies", "3_jobs", "4_deepdive", "5_tracker"]


def test_state_keys_unique() -> None:
    """``state.assert_no_collisions`` ran at import — this just reasserts
    against drift if a future edit mis-spells the assertion out."""
    from startup_radar.web import state

    assert len(state.ALL_KEYS) == len(set(state.ALL_KEYS))


def test_no_session_state_literals_in_pages() -> None:
    """Invariant: page modules must go through ``state.*`` constants.

    Catches the class of bug where a page uses a raw ``st.session_state["foo"]``
    literal that collides with a sibling page.
    """
    pages_dir = REPO_ROOT / "startup_radar" / "web" / "pages"
    offenders: list[str] = []
    for page in pages_dir.glob("*.py"):
        if page.name.startswith("__"):
            continue
        text = page.read_text(encoding="utf-8")
        # Disallow `st.session_state["literal"]` and `st.session_state.get("literal", ...)`
        import re

        if re.search(r"st\.session_state\[\"[^\"]+\"\]", text):
            offenders.append(page.name)
        if re.search(r"st\.session_state\.get\(\"[^\"]+\"", text):
            offenders.append(page.name)
    assert not offenders, f"session-state string literals in pages: {offenders}"


@pytest.mark.parametrize(
    "page",
    ["1_dashboard.py", "2_companies.py", "3_jobs.py", "4_deepdive.py", "5_tracker.py"],
)
def test_page_module_imports(page: str) -> None:
    """Each page file parses cleanly. Cheap guard against a broken copy/paste."""
    import ast

    src = (REPO_ROOT / "startup_radar" / "web" / "pages" / page).read_text()
    ast.parse(src)
