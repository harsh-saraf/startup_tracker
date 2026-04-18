# Startup Radar Template

A personal daily scanner that finds startups matching your criteria (industry, funding stage, location) and flags open roles that fit your target job titles. Pulls from free public sources out of the box — no API keys required. Optional Gmail integration for curated VC newsletters.

> Built by [Xaviera Ho](https://github.com/xavierahojjx-afk) — originally as a personal Stanford MBA job search tool, then generalized for public use.

---

## What you get

- **Automatic startup discovery** — scans TechCrunch, Hacker News, SEC filings, and more for funding announcements matching your criteria
- **Job matching** — flags open roles at those companies that fit your target titles and locations
- **Interactive dashboard** — browse companies, track applications, find warm intros via LinkedIn connections
- **DeepDive reports** — generate a one-page company research brief (.docx) scored against your personal fit criteria
- **Daily scheduling** — runs automatically so new matches are waiting for you each morning
- **Optional Gmail integration** — pull curated VC newsletters (StrictlyVC, Term Sheet, etc.) for even higher-signal results

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
pip install -r requirements.txt
```

The first line downloads the project to your computer. The second line moves you into the project folder. The third line installs the libraries the project needs.

### Step 2: Run the setup wizard

While still in the same terminal (inside the `startup-radar-template` folder), type:

```
claude
```

This opens Claude Code. You should see a prompt where you can type messages to Claude. Now type:

```
/setup-radar
```

Claude will walk you through a series of questions to configure your radar:
- What roles are you looking for?
- What locations?
- What industries?
- How do you want to run it daily?

This takes about 5–15 minutes. At the end, Claude will run the pipeline once and ask if you'd like to see the Dashboard.

> **If `/setup-radar` is not recognized:** Make sure you ran `claude` from inside the project folder (after the `cd startup-radar-template` step). Claude Code only finds the setup wizard when it's launched from the right place.

### Step 3: Browse your results

The dashboard opens in your web browser. From here you can:
- Browse discovered startups and mark them as Interested, Wishlist, or Not Interested
- See matching job openings and click through to apply
- Generate DeepDive research briefs for companies you care about
- Find warm intros via your LinkedIn connections
- Track your applications and follow-ups

To reopen the dashboard later, go to the project folder in your terminal and run:

```
streamlit run app.py
```

## Where does the data come from?

Out of the box, Startup Radar pulls from these free public sources — no accounts or API keys needed:

| Source | What it finds |
|---|---|
| **RSS feeds** (TechCrunch, VentureBeat, Crunchbase News) | Funding announcements from major tech publications |
| **Hacker News** | Community-submitted funding threads (surprisingly good signal) |
| **SEC EDGAR Form D** | Official US regulatory filings — catches raises that never get press coverage |
| **Gmail newsletters** (optional) | Curated VC newsletters like StrictlyVC, Term Sheet, etc. Highest signal, but requires a 10-min Google OAuth setup |

The `/setup-radar` wizard lets you pick which sources to enable.

## Claude Code skills

When you run `claude` from this project folder, two special commands are available:

- **`/setup-radar`** — the setup wizard (first-time configuration)
- **`/deepdive CompanyName`** — research any company and generate a one-page .docx brief scored against your criteria (e.g. `/deepdive Anthropic`)

You can also generate DeepDive reports directly from the dashboard without opening Claude Code.

## Running it daily

During setup, Claude will ask how you want to schedule automatic daily runs. Options:

- **GitHub Actions** (recommended) — runs in the cloud for free, even when your computer is off
- **Windows Task Scheduler** — runs on your PC at a set time each day
- **Mac launchd** — same idea, for Mac
- **Linux cron** — same idea, for Linux
- **Manual** — just run `python daily_run.py` whenever you want

## Customizing with Claude Code

Everything in this project is meant to be edited. The easiest way to customize is to open `claude` in the project folder and ask for what you want in plain English:

- *"Add a new column to the dashboard showing company website"*
- *"Change the filter to also include biotech companies"*
- *"Add a new RSS feed for [some publication]"*
- *"Make the DeepDive report include a section about the company's tech stack"*

Claude Code will read your code and make the changes for you. That's the point of this template — you don't need to be a programmer to customize it.

## Optional: Gmail newsletters

If you subscribe to VC newsletters (StrictlyVC, Term Sheet, Venture Daily Digest, etc.), they're a gold mine of curated signal. The `/setup-radar` wizard will walk you through enabling this if you want it. It takes about 10 minutes and involves creating a free Google Cloud project for email access.

## Troubleshooting

Each daily run writes a log file to `logs/`. If something isn't working, check the latest log. You can also ask Claude for help — run `claude` in the project folder and describe the problem.

| Problem | What to do |
|---|---|
| `/setup-radar` not recognized | Make sure you ran `claude` from inside the `startup-radar-template` folder |
| No results after running the pipeline | Your filters might be too strict — try broadening your industries or locations in `config.yaml` |
| Gmail stopped working | Your Google login expired — delete `token.json` and run `python main.py` to re-login |
| Dashboard won't open | Make sure you installed dependencies: `pip install -r requirements.txt` |

For real-time troubleshooting, run `python main.py` in your terminal — it prints each step as it happens.

## License

MIT — see [LICENSE](LICENSE).
