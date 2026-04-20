---
paths:
  - "tests/**"
  - "**/test_*.py"
  - "**/conftest.py"
---

# Test rules

- **Must:** tests live under `tests/unit/` or `tests/integration/`. Filenames: `test_<module>.py`.
- **Must:** external HTTP is replayed via vcrpy cassettes in `tests/fixtures/cassettes/` — no live network in CI.
- **Must:** every new source ships at least one happy-path test and one empty-response test.
- **Must:** pure-function modules (`filters.py`, `parsing/funding.py`) target ≥90% line coverage; sources ≥70%.
- **Never:** write tests that touch the real `~/.config/` or write to repo-root files. Use `tmp_path`.
- **Never:** assert on log strings. Assert on structured fields when structlog lands.
- **Must:** Streamlit tests use `streamlit.testing.v1.AppTest`, not Selenium/Playwright (deferred per `docs/CRITIQUE_APPENDIX.md` §8).
- **Must:** a test that depends on Phase N work is marked `@pytest.mark.skip(reason="depends on Phase N")` until that phase ships.
- **Note:** Phase 0's `tests/test_smoke.py` is the placeholder — real coverage lands in Phase 10.
