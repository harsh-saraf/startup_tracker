# Startup Radar Template

<!-- hero:start -->
A personal daily scanner that finds startups matching your criteria (industry, funding stage, location) and flags open roles that fit your target job titles. Pulls from free public sources out of the box — no API keys required. Optional Gmail integration for curated VC newsletters.

> Built by [Xaviera Ho](https://github.com/xavierahojjx-afk) — originally as a personal Stanford MBA job search tool, then generalized for public use.

## What you get

- **Automatic startup discovery** — scans TechCrunch, Hacker News, SEC filings, and more for funding announcements matching your criteria
- **Job matching** — flags open roles at those companies that fit your target titles and locations
- **Interactive dashboard** — browse companies, track applications, find warm intros via LinkedIn connections
- **DeepDive reports** — generate a one-page company research brief (.docx) scored against your personal fit criteria
- **Daily scheduling** — runs automatically so new matches are waiting for you each morning
- **Optional Gmail integration** — pull curated VC newsletters (StrictlyVC, Term Sheet, etc.) for even higher-signal results
<!-- hero:end -->

## Documentation

The full contributor docs site is published to GitHub Pages: <https://xavierahojjx-afk.github.io/startup-radar-template/>. Build locally with `make docs` / `make docs-serve`.

---

## Prerequisites

Before you start, make sure you have these installed on your computer:

1. **Python 3.10 or newer** — [Download here](https://www.python.org/downloads/). During installation on Windows, check the box that says "Add Python to PATH".
2. **Git** — [Download here](https://git-scm.com/downloads). Use the default settings during installation.
3. **Claude Code** — Anthropic's CLI tool. Install it by following the instructions at [claude.ai/code](https://claude.ai/code).

Not sure if you already have them? Open a terminal and type:
```
python --version
git --version
claude --version
```
If each one prints a version number, you're good.

> **How to open a terminal:** On **Windows**, search for "Terminal" or "Command Prompt" in the Start menu. On **Mac**, open "Terminal" from Applications > Utilities. On **Linux**, press Ctrl+Alt+T.

## Getting started (step by step)

### Step 1: Download this project

Open your terminal and paste these three lines one at a time, pressing Enter after each:

```
git clone https://github.com/xavierahojjx-afk/startup-radar-template.git
```

```
cd startup-radar-template
```

```
make install
```

The first line downloads the project to your computer. The second line moves you into the project folder. The third line installs the libraries the project needs (via `uv sync --all-extras`).

### Step 2: Run the setup wizard

While still in the same terminal (inside the `startup-radar-template` folder), type:

```
claude
```

This opens Claude Code. Just tell it what you want in plain English:

```
set me up
```

(or type `/radar` if you prefer the explicit skill name). Claude will walk you through a series of questions to configure your radar:
- What roles are you looking for?
- What locations?
- What industries?
- How do you want to run it daily?

This takes about 5–15 minutes. At the end, Claude will run the pipeline once and ask if you'd like to see the Dashboard.

> **If Claude doesn't find the radar skill:** Make sure you ran `claude` from inside the project folder (after the `cd startup-radar-template` step). Claude Code only discovers project skills when it's launched from the right place.

### Step 3: Browse your results

The dashboard opens in your web browser. From here you can:
- Browse discovered startups and mark them as Interested, Wishlist, or Not Interested
- See matching job openings and click through to apply
- Generate DeepDive research briefs for companies you care about
- Find warm intros via your LinkedIn connections
- Track your applications and follow-ups

To reopen the dashboard later, run `claude` in the project folder and say *"open the dashboard"* — or, if you prefer the CLI directly:

```
startup-radar serve
```

## Where does the data come from?

Out of the box, Startup Radar pulls from these free public sources — no accounts or API keys needed:

| Source | What it finds |
|---|---|
| **RSS feeds** (TechCrunch, VentureBeat, Crunchbase News) | Funding announcements from major tech publications |
| **Hacker News** | Community-submitted funding threads (surprisingly good signal) |
| **SEC EDGAR Form D** | Official US regulatory filings — catches raises that never get press coverage |
| **Gmail newsletters** (optional) | Curated VC newsletters like StrictlyVC, Term Sheet, etc. Highest signal, but requires a 10-min Google OAuth setup |

Claude's `/radar` skill lets you pick which sources to enable during onboarding.

## Talk to Claude

Once `claude` is running in the project folder, just say what you want in plain English. Claude routes to the right skill automatically:

| You say | What happens |
|---|---|
| "set me up" / "onboard me" | First-time configuration wizard |
| "run my radar" / "what's new?" / "check for funding" | Runs the discovery pipeline once |
| "open the dashboard" / "show me the UI" | Launches the Streamlit dashboard |
| "research Anthropic" / "deepdive OpenAI" | One-page company research brief (.docx) |
| "is it broken?" / "diagnose" / "doctor" | Health check (config, creds, DB, network) |
| "status" / "when did it last run?" | Last-run age + DB row counts |
| "back up my data" | Local tarball snapshot |

All pipeline/setup/ops actions route through a single skill (`/radar`). Company briefs route through `/research`. Plus a few dev-only skills:

- `/ship` — sanctioned commit path (runs CI, drafts a conventional commit, commits behind an env-var handshake)
- `/data-branch-bootstrap` — one-time GH Actions DB persistence setup (after fork)
- `/data-branch-restore` — pull the latest prod DB from the cloud

You can also generate DeepDive reports directly from the dashboard without opening Claude Code.

## Running it daily

During setup, Claude will ask how you want to schedule automatic daily runs. Options:

- **GitHub Actions** (recommended) — runs in the cloud for free, even when your computer is off
- **Windows Task Scheduler** — runs on your PC at a set time each day
- **Mac launchd** — same idea, for Mac
- **Linux cron** — same idea, for Linux
- **Manual** — ask Claude *"run my radar"* (or run `startup-radar run --scheduled` directly) whenever you want

### GH Actions scheduling & persistence

`.github/workflows/daily.yml` runs `startup-radar run --scheduled` on a cron schedule and persists `startup_radar.db` by committing it to an orphan `data` branch. First-time setup requires creating the `data` branch once — see [`docs/operations/data-branch.md`](docs/operations/data-branch.md).

To restore the prod DB locally:

```bash
git fetch origin data:data
git checkout data -- startup_radar.db
```

A separate weekly workflow (`data-branch-gc.yml`) force-pushes a fresh orphan commit on `data` to prevent binary-diff bloat.

## Resilience & maintenance

Ask Claude — *"status"*, *"diagnose"*, *"back up my data"* — or invoke the CLI directly. The three commands keep your setup healthy between runs:

- `startup-radar status` — prints the current branch, version, the age of your last scheduled run, and your DB row counts. Pure read, no network.
- `startup-radar doctor [--network]` — validates your `config.yaml`, checks the DB path is writable, verifies per-source credentials, and (with `--network`) pokes each enabled source to confirm it's reachable. Exits 0 green, 1 if anything is broken.
- `startup-radar backup [--no-secrets] [--db-only]` — writes a tarball of your DB + `config.yaml` + OAuth files into `backups/` (gitignored). Default **includes** `token.json` + `credentials.json` so you can restore after a disk loss; pass `--no-secrets` before sharing the tarball. `--db-only` packs only `startup_radar.db`.

Backups live on your own disk — they're not encrypted. If you copy one off your machine, use `--no-secrets`.

## Customizing with Claude Code

Everything in this project is meant to be edited. The easiest way to customize is to open `claude` in the project folder and ask for what you want in plain English:

- *"Add a new column to the dashboard showing company website"*
- *"Change the filter to also include biotech companies"*
- *"Add a new RSS feed for [some publication]"*
- *"Make the DeepDive report include a section about the company's tech stack"*

Claude Code will read your code and make the changes for you. That's the point of this template — you don't need to be a programmer to customize it.

## Optional: Gmail newsletters

If you subscribe to VC newsletters (StrictlyVC, Term Sheet, Venture Daily Digest, etc.), they're a gold mine of curated signal. Just tell Claude "set up Gmail" (or run `/radar` and pick Gmail at the sources step) — it takes about 10 minutes and involves creating a free Google Cloud project for email access.

## Troubleshooting

Each daily run writes a log file to `logs/`. If something isn't working, check the latest log. You can also ask Claude for help — run `claude` in the project folder and describe the problem.

| Problem | What to do |
|---|---|
| Claude can't find the radar skill | Make sure you ran `claude` from inside the `startup-radar-template` folder |
| No results after running the pipeline | Your filters might be too strict — try broadening your industries or locations in `config.yaml` |
| Gmail stopped working | Your Google login expired — delete `token.json` and run `startup-radar run` to re-login |
| Dashboard won't open | Make sure you installed dependencies: `make install` (or `uv sync --all-extras`) |

For real-time troubleshooting, run `startup-radar run` in your terminal — it prints each step as it happens.

## Development

### Running tests

```bash
make ci                                     # lint + format + typecheck + tests + coverage
make test                                   # pytest only
uv run pytest tests/unit/                   # fast — no cassettes
uv run pytest tests/integration/            # cassette-backed source tests
```

#### Re-recording vcrpy cassettes

Source tests replay network interactions from `tests/fixtures/cassettes/<source>/`. To re-record after an upstream response shape changes:

```bash
rm tests/fixtures/cassettes/<source>/<name>.yaml
uv run pytest tests/integration/test_source_<source>.py::<test_name>
```

The `vcr_config` fixture records once (first run) and replays thereafter. In CI (`CI=1`), missing cassettes fail loudly rather than silently hitting the network.

**SEC EDGAR** requires a `User-Agent` with contact info — set it via the `_USER_AGENT` constant in `startup_radar/sources/sec_edgar.py` before recording. The cassette scrubber replaces it with `startup-radar-test` on disk; do not commit a cassette containing a real email address.

### Schema changes

SQLite schema is versioned via `PRAGMA user_version` and managed by a homegrown migrator in `startup_radar/storage/migrator.py` (alembic is intentionally not used — see `docs/CRITIQUE_APPENDIX.md` §4). To evolve the schema:

1. Drop a new file into `startup_radar/storage/migrations/` named `NNNN_<slug>.sql` where `NNNN` is the next zero-padded integer (gaps and bad filenames are rejected at load time).
2. Use `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` and give every new column a `DEFAULT` — migrations must be idempotent and safe over already-populated DBs.
3. The next `startup-radar run` (or `make db-migrate`) applies pending migrations inside a single transaction and bumps `user_version` on success; failures roll back atomically. There are no down-migrations — roll back via `git revert` + restoring from `startup-radar backup`.

### Dashboard layout

The Streamlit dashboard lives under `startup_radar/web/` as a native multi-page app:

```
startup_radar/web/
├── app.py                 # shell: page-config, config load, get_storage(), sidebar
├── cache.py               # @st.cache_resource get_storage() + @st.cache_data(ttl=60) read wrappers
├── state.py               # session-state / widget key constants (collision-asserted at import)
├── lookup.py              # DuckDuckGo company lookup (optional dep)
├── connections.py         # LinkedIn CSV tier-1/tier-2 helpers
└── pages/
    ├── 1_dashboard.py     # KPIs + today's companies + today's job matches + follow-ups due
    ├── 2_companies.py     # wishlist / interested / not-interested / uncategorized tables
    ├── 3_jobs.py          # job-match buckets with inline editor
    ├── 4_deepdive.py      # AI research brief + warm-intro lookup
    └── 5_tracker.py       # application pipeline + activity log + rejected
```

Add a new page by dropping `N_name.py` into `pages/`; Streamlit discovers it automatically. Define any session-state / widget keys in `state.py` first — inline string literals in `pages/*` are forbidden (caught by `tests/unit/test_web_smoke.py`).

Launch with `uv run startup-radar serve` (or, for dev: `uv run streamlit run startup_radar/web/app.py`).

### Logging & retries

Logging goes through a single structlog pipeline at `startup_radar/observability/logging.py`. `configure_logging(json=...)` is called exactly once per process — from the CLI `@app.callback` and the Streamlit shell. Locally you get a pretty `ConsoleRenderer`; setting `CI=1` or `STARTUP_RADAR_LOG_JSON=1` flips it to line-delimited JSON for ingest tools. Emit structured events from library code with:

```python
from startup_radar.observability.logging import get_logger
log = get_logger(__name__)
log.warning("source.fetch_failed", source="rss", url=url, status=status)
```

Source network calls are wrapped in `startup_radar.sources._retry.retry(...)` — three attempts, `(1, 2, 4)` s backoff, fixed exception tuple. The pipeline records every source invocation (success or failure) in a `runs` table (`0002_runs_table.sql`). `uv run startup-radar status` renders a `Per-source health:` block (last-run age + failure streak), and `uv run startup-radar doctor` surfaces a `⚠ source.<key>.streak` row when a source has failed more than twice in a row.

## Running with Docker

The repo ships a multi-stage slim image (non-root UID 10001, stateless). All state lives on two mounted volumes — **secrets stay on the host, never in the image**:

- `/data` — the SQLite DB (point `output.sqlite.path` at `/data/startup_radar.db` in your mounted `config.yaml`).
- `/config` — `config.yaml`, `credentials.json`, `token.json`, `.env` (whatever you use).

The image's `CMD` bakes in `--config /config/config.yaml`, so the dashboard "just works" when both volumes are mounted:

```
make docker-build
mkdir -p data config
cp config.example.yaml config/config.yaml   # then edit — set sqlite.path to /data/startup_radar.db
make docker-run                              # dashboard at http://localhost:8501
```

Or without `make`:

```
docker build -t startup-radar:phase-14 .
docker run --rm -p 8501:8501 \
  -v $PWD/data:/data -v $PWD/config:/config \
  startup-radar:phase-14
```

One-shot pipeline instead of the dashboard (overrides `CMD`):

```
docker run --rm \
  -v $PWD/data:/data -v $PWD/config:/config \
  startup-radar:phase-14 \
  --config /config/config.yaml run
```

Multi-arch (amd64 + arm64):

```
docker buildx build --platform linux/amd64,linux/arm64 -t startup-radar:phase-14 .
```

`docker-compose.yml` is an optional convenience (`docker compose up` / `docker compose run --rm radar …`) — the image is the source of truth.

## License

MIT — see [LICENSE](LICENSE).
