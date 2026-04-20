"""Phase 8: extra edge-case tests for parsing.funding + parsing.normalize.

Coverage is already 100% on both modules via tests/unit/parsing/* — these
tests guard specific edge cases (case insensitivity, regex boundaries,
suffix iteration) that aren't asserted elsewhere.
"""

from __future__ import annotations

from startup_radar.parsing.funding import (
    AMOUNT_RE,
    COMPANY_INLINE_RE,
    COMPANY_SUBJECT_RE,
    STAGE_RE,
    parse_amount_musd,
)
from startup_radar.parsing.normalize import dedup_key, normalize_company


def test_parse_amount_lowercase_b_suffix() -> None:
    assert parse_amount_musd("$3b") == 3000.0


def test_parse_amount_comma_thousands_millions() -> None:
    assert parse_amount_musd("$1,250 million") == 1250.0


def test_parse_amount_whitespace_and_case() -> None:
    assert parse_amount_musd("  2.5 MILLION  ") == 2.5


def test_parse_amount_returns_none_on_letters() -> None:
    assert parse_amount_musd("several hundred K") is None


def test_amount_re_matches_variants() -> None:
    assert AMOUNT_RE.search("the round was $42M total") is not None
    assert AMOUNT_RE.search("no money here") is None


def test_stage_re_preseed_hyphen_variants() -> None:
    assert STAGE_RE.search("Pre-Seed") is not None
    assert STAGE_RE.search("preseed") is not None


def test_stage_re_series_with_digit_plus() -> None:
    assert STAGE_RE.search("Series B1+") is not None


def test_company_subject_re_matches_verbs() -> None:
    m = COMPANY_SUBJECT_RE.search("Acme lands $5M seed")
    assert m is not None
    assert m.group(1) == "Acme"


def test_company_inline_re_matches_past_tense() -> None:
    m = COMPANY_INLINE_RE.search("Today Foo raised $10M from investors")
    assert m is not None and m.group(1) == "Foo"


def test_normalize_handles_double_suffix() -> None:
    """LEGAL_SUFFIX_RE is applied in a loop — 'Foo Labs Inc' should strip both."""
    assert normalize_company("Foo Labs Inc") == "foo"


def test_normalize_handles_dotted_llc() -> None:
    assert normalize_company("Acme L.L.C") == "acme"


def test_normalize_strips_ampersand_and_hyphen() -> None:
    """Ampersand, hyphen, apostrophe are collapsed by the final re.sub."""
    assert normalize_company("A&B-C") == "abc"
    assert normalize_company("O'Reilly") == "oreilly"


def test_normalize_empty_string_returns_empty() -> None:
    assert normalize_company("") == ""


def test_dedup_key_is_stable_across_whitespace() -> None:
    assert dedup_key("  Anthropic  ") == dedup_key("anthropic")
