"""DuckDuckGo company lookup.

Hoisted out of the Companies / DeepDive pages so the ``duckduckgo_search``
import happens once at module load instead of per Streamlit rerun. Missing
dep fails loud once at startup, not silently per click.
"""

from __future__ import annotations

import re

from startup_radar.observability.logging import get_logger

try:
    from duckduckgo_search import DDGS

    _DDG_AVAILABLE = True
except ImportError:
    _DDG_AVAILABLE = False

log = get_logger(__name__)


def lookup_company(name: str) -> dict:
    if not _DDG_AVAILABLE:
        return {}
    try:
        results = list(DDGS().text(f"{name} startup funding raised", max_results=5))
    except Exception as e:
        log.warning("lookup.failed", company=name, err=str(e))
        return {}
    if not results:
        return {}
    snippets = " ".join(r.get("body", "") for r in results)
    info: dict = {}
    first_body = results[0].get("body", "")
    if first_body:
        info["description"] = first_body[:200].rstrip()
    amt = re.search(r"\$[\d,.]+\s*[BM]\b|\$[\d,.]+\s*(?:million|billion)", snippets, re.IGNORECASE)
    if amt:
        info["amount_raised"] = amt.group(0).strip()
    stage = re.search(r"Series\s+[A-F]\d?\+?|Pre-[Ss]eed|Seed", snippets)
    if stage:
        info["funding_stage"] = stage.group(0).strip()
    loc = re.search(
        r"(?:based in|headquartered in)\s+([^,.\n]+(?:,\s*[A-Za-z. ]+)?)",
        snippets,
        re.IGNORECASE,
    )
    if loc:
        info["location"] = loc.group(1).strip()
    return info
