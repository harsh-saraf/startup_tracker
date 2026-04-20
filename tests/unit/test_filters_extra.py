"""Phase 8: targeted branch coverage for StartupFilter / JobFilter.

Existing tests/unit/test_filters.py covers the happy path for StartupFilter.
These cover the remaining branches: JobFilter entirely, plus the
empty-location / empty-industry / any-stage / unknown-rank paths
in StartupFilter, plus the filter() list comprehensions.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from startup_radar.config import AppConfig
from startup_radar.filters import JobFilter, StartupFilter, _stage_rank
from startup_radar.models import JobMatch, Startup

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.yaml"


def _cfg() -> AppConfig:
    with open(EXAMPLE, encoding="utf-8") as f:
        return AppConfig.model_validate(yaml.safe_load(f))


def _empty_targets_cfg() -> AppConfig:
    cfg = _cfg()
    return cfg.model_copy(
        update={
            "targets": cfg.targets.model_copy(
                update={
                    "roles": [],
                    "seniority_exclusions": [],
                    "locations": [],
                    "industries": [],
                    "min_stage": "any",
                }
            )
        }
    )


_BASE_STARTUP = Startup(
    company_name="Anthropic",
    description="AI safety lab",
    funding_stage="Series A",
    amount_raised="$50M",
    location="San Francisco",
)


# --- _stage_rank ------------------------------------------------------------


def test_stage_rank_empty_returns_neg_one() -> None:
    assert _stage_rank("") == -1


def test_stage_rank_unknown_returns_neg_one() -> None:
    assert _stage_rank("Growth") == -1


def test_stage_rank_series_f_via_regex() -> None:
    """Line 33-35: series F isn't in _STAGE_ORDER, so the regex fallback fires."""
    assert _stage_rank("Series F") == 2 + (ord("f") - ord("a"))


# --- StartupFilter ----------------------------------------------------------


def test_startup_filter_method_returns_list() -> None:
    f = StartupFilter(_cfg())
    good = _BASE_STARTUP
    bad = replace(good, funding_stage="Seed", amount_raised="$1M")
    assert f.filter([good, bad]) == [good]


def test_stage_ok_any_min_stage_accepts_all() -> None:
    f = StartupFilter(_empty_targets_cfg())
    s = replace(_BASE_STARTUP, funding_stage="Seed", amount_raised="$1M")
    assert f.passes(s)


def test_stage_ok_empty_stage_passes() -> None:
    f = StartupFilter(_cfg())
    assert f._stage_ok("", "")


def test_stage_ok_unknown_rank_passes() -> None:
    """Line 64: rank < 0 (e.g. 'Growth') falls through to True."""
    f = StartupFilter(_cfg())
    assert f._stage_ok("Growth", "$10M")


def test_location_ok_empty_locations_accepts_all() -> None:
    f = StartupFilter(_empty_targets_cfg())
    assert f._location_ok("Nowhere")


def test_location_ok_empty_location_rejected() -> None:
    f = StartupFilter(_cfg())
    assert not f._location_ok("")


def test_industry_ok_empty_industries_accepts_all() -> None:
    f = StartupFilter(_empty_targets_cfg())
    s = replace(_BASE_STARTUP, description="meat distribution")
    assert f._industry_ok(s)


# --- JobFilter --------------------------------------------------------------


def _job(role: str = "Software Engineer", location: str = "New York") -> JobMatch:
    return JobMatch(company_name="Acme", role_title=role, location=location)


def test_job_filter_role_matches_when_in_roles() -> None:
    jf = JobFilter(_cfg())
    assert jf.role_matches("Senior Software Engineer")


def test_job_filter_role_rejects_empty_title() -> None:
    jf = JobFilter(_cfg())
    assert not jf.role_matches("")


def test_job_filter_role_rejects_on_exclusion() -> None:
    jf = JobFilter(_cfg())
    assert not jf.role_matches("VP of Engineering")


def test_job_filter_role_passes_when_roles_empty() -> None:
    jf = JobFilter(_empty_targets_cfg())
    assert jf.role_matches("Anything Goes")


def test_job_filter_role_rejects_when_not_in_roles() -> None:
    jf = JobFilter(_cfg())
    assert not jf.role_matches("Plumber")


def test_job_filter_location_empty_locations_accepts() -> None:
    jf = JobFilter(_empty_targets_cfg())
    assert jf.location_matches("Anywhere")


def test_job_filter_location_empty_string_rejected() -> None:
    jf = JobFilter(_cfg())
    assert not jf.location_matches("")


def test_job_filter_location_remote_always_passes() -> None:
    jf = JobFilter(_cfg())
    assert jf.location_matches("Fully Remote")


def test_job_filter_location_substring_hit() -> None:
    jf = JobFilter(_cfg())
    assert jf.location_matches("New York, NY")


def test_job_filter_location_substring_miss() -> None:
    jf = JobFilter(_cfg())
    assert not jf.location_matches("Tokyo")


def test_job_filter_passes_combines_role_and_location() -> None:
    jf = JobFilter(_cfg())
    assert jf.passes(_job())
    assert not jf.passes(_job(role="VP Sales"))
    assert not jf.passes(_job(location="Tokyo"))


def test_job_filter_filter_returns_only_matches() -> None:
    jf = JobFilter(_cfg())
    good = _job()
    bad = _job(role="intern engineer")
    assert jf.filter([good, bad]) == [good]
