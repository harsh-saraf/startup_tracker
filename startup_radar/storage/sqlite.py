"""SqliteStorage — single-connection SQLite backend for Startup Radar.

One ``sqlite3.Connection`` per process. WAL. ``check_same_thread=False``
so Streamlit's thread pool can share reads across reruns.

*All writes* wrap ``with self._conn:`` for atomic commit-or-rollback
(`.claude/rules/storage.md` bullet 2). Read methods do not — they are not
transactional by design.

Schema versioning: ``PRAGMA user_version`` drives the homegrown migrator
in ``startup_radar/storage/migrator.py``. Alembic explicitly rejected per
``docs/CRITIQUE_APPENDIX.md`` §4.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd

from startup_radar.models import JobMatch, Startup
from startup_radar.observability.logging import get_logger
from startup_radar.storage.migrator import apply_pending

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

log = get_logger(__name__)


class SqliteStorage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # --- schema ------------------------------------------------------------

    def migrate_to_latest(self) -> list[int]:
        applied = apply_pending(self._conn, _MIGRATIONS_DIR)
        if applied:
            log.info(
                "storage.migrated",
                versions=applied,
                path=str(self._path),
            )
        return applied

    def user_version(self) -> int:
        (v,) = self._conn.execute("PRAGMA user_version").fetchone()
        return int(v)

    def close(self) -> None:
        self._conn.close()

    # --- dedup helpers -----------------------------------------------------

    def get_existing_companies(self) -> set[str]:
        rows = self._conn.execute("SELECT company_name FROM startups").fetchall()
        return {r[0].lower().strip() for r in rows}

    def get_rejected_companies(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT company_name FROM startups WHERE LOWER(TRIM(status)) = 'not interested'"
        ).fetchall()
        return {r[0].lower().strip() for r in rows}

    def get_existing_job_keys(self) -> set[str]:
        rows = self._conn.execute("SELECT company_name, role_title FROM job_matches").fetchall()
        return {f"{r[0].lower().strip()}|{r[1].lower().strip()}" for r in rows}

    def is_processed(self, source: str, item_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_items WHERE source = ? AND item_id = ?",
            (source, item_id),
        ).fetchone()
        return row is not None

    def mark_processed(self, source: str, item_ids: Iterable[str]) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO processed_items (source, item_id) VALUES (?, ?)",
                [(source, i) for i in item_ids],
            )

    # --- inserts -----------------------------------------------------------

    def insert_startups(self, startups: list[Startup | dict]) -> int:
        if not startups:
            return 0
        count = 0
        with self._conn:
            for s in startups:
                if isinstance(s, Startup):
                    values = (
                        s.company_name,
                        s.description,
                        s.funding_stage,
                        s.amount_raised,
                        s.location,
                        s.website,
                        s.source,
                        s.source_url,
                        (s.date_found or datetime.now()).strftime("%Y-%m-%d"),
                        "",
                    )
                else:
                    values = (
                        s["company_name"],
                        s.get("description", ""),
                        s.get("funding_stage", ""),
                        s.get("amount_raised", ""),
                        s.get("location", ""),
                        s.get("website", ""),
                        s.get("source", ""),
                        s.get("source_url", ""),
                        s.get("date_found", datetime.now().strftime("%Y-%m-%d")),
                        s.get("status", ""),
                    )
                try:
                    self._conn.execute(
                        """INSERT INTO startups
                           (company_name, description, funding_stage, amount_raised,
                            location, website, source, source_url, date_found, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    pass
        return count

    def insert_job_matches(self, jobs: list[JobMatch | dict]) -> int:
        if not jobs:
            return 0
        count = 0
        with self._conn:
            for j in jobs:
                if isinstance(j, JobMatch):
                    values = (
                        j.company_name,
                        j.company_description,
                        j.role_title,
                        j.location,
                        j.url,
                        j.priority,
                        j.source,
                        "",
                        (j.date_found or datetime.now()).strftime("%Y-%m-%d"),
                    )
                else:
                    values = (
                        j["company_name"],
                        j.get("company_description", ""),
                        j.get("role_title", ""),
                        j.get("location", ""),
                        j.get("url", ""),
                        j.get("priority", ""),
                        j.get("source", ""),
                        j.get("status", ""),
                        j.get("date_found", datetime.now().strftime("%Y-%m-%d")),
                    )
                try:
                    self._conn.execute(
                        """INSERT INTO job_matches
                           (company_name, company_description, role_title, location,
                            url, priority, source, status, date_found)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    pass
        return count

    def update_startup_website(self, company_name: str, website: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE startups SET website = ? WHERE company_name = ? COLLATE NOCASE",
                (website, company_name),
            )

    # --- reads -------------------------------------------------------------

    def get_all_startups(self) -> pd.DataFrame:
        df = pd.read_sql_query(
            """SELECT company_name, website, description, funding_stage, amount_raised,
                      location, source, date_found, status
               FROM startups ORDER BY date_found DESC, id DESC""",
            self._conn,
        )
        df.columns = [
            "Company Name",
            "Website",
            "Description",
            "Funding Stage",
            "Amount Raised",
            "Location",
            "Source",
            "Date Found",
            "Status",
        ]
        df["Website"] = df["Website"].fillna("")
        df["Website"] = df["Website"].apply(
            lambda x: f"https://{x}" if x and not x.startswith("http") else x
        )
        df["Status"] = df["Status"].fillna("")
        return df

    def get_all_job_matches(self) -> pd.DataFrame:
        df = pd.read_sql_query(
            """SELECT company_name, company_description, role_title,
                      location, url, priority, status, date_found, notes
               FROM job_matches ORDER BY date_found DESC, id DESC""",
            self._conn,
        )
        df.columns = [
            "Company",
            "Company Description",
            "Role",
            "Location",
            "Link",
            "Priority",
            "Status",
            "Date Found",
            "Notes",
        ]
        df["Status"] = df["Status"].fillna("")
        df["Notes"] = df["Notes"].fillna("")
        return df

    # --- status updates ----------------------------------------------------

    def update_startup_status(self, company_name: str, status: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE startups SET status = ? WHERE company_name = ? COLLATE NOCASE",
                (status, company_name),
            )

    def update_job_status(self, company_name: str, role_title: str, status: str) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE job_matches SET status = ?
                   WHERE company_name = ? COLLATE NOCASE
                     AND role_title = ? COLLATE NOCASE""",
                (status, company_name, role_title),
            )

    def update_job_notes(self, company_name: str, role_title: str, notes: str) -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE job_matches SET notes = ?
                   WHERE company_name = ? COLLATE NOCASE
                     AND role_title = ? COLLATE NOCASE""",
                (notes, company_name, role_title),
            )

    def delete_startup(self, company_name: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM startups WHERE company_name = ? COLLATE NOCASE",
                (company_name,),
            )

    def delete_job_match(self, company_name: str, role_title: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM job_matches WHERE company_name = ? COLLATE NOCASE AND role_title = ? COLLATE NOCASE",
                (company_name, role_title),
            )

    # --- activities --------------------------------------------------------

    def insert_activity(self, activity: dict) -> int:
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO activities
                   (company_name, role_title, activity_type, contact_name,
                    contact_title, contact_email, date, follow_up_date, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    activity["company_name"],
                    activity.get("role_title", ""),
                    activity["activity_type"],
                    activity.get("contact_name", ""),
                    activity.get("contact_title", ""),
                    activity.get("contact_email", ""),
                    activity["date"],
                    activity.get("follow_up_date", ""),
                    activity.get("notes", ""),
                ),
            )
            return cur.lastrowid

    def get_activities(self, company_name: str | None = None) -> pd.DataFrame:
        if company_name:
            return pd.read_sql_query(
                """SELECT id, company_name, role_title, activity_type,
                          contact_name, contact_title, contact_email,
                          date, follow_up_date, notes
                   FROM activities WHERE company_name = ? COLLATE NOCASE
                   ORDER BY date DESC, id DESC""",
                self._conn,
                params=(company_name,),
            )
        return pd.read_sql_query(
            """SELECT id, company_name, role_title, activity_type,
                      contact_name, contact_title, contact_email,
                      date, follow_up_date, notes
               FROM activities ORDER BY date DESC, id DESC""",
            self._conn,
        )

    def get_overdue_followups(self, today: str) -> pd.DataFrame:
        return pd.read_sql_query(
            """SELECT id, company_name, role_title, activity_type,
                      contact_name, contact_title, date, follow_up_date, notes
               FROM activities
               WHERE follow_up_date != '' AND follow_up_date <= ?
               ORDER BY follow_up_date ASC""",
            self._conn,
            params=(today,),
        )

    # --- tracker -----------------------------------------------------------

    def get_tracker_status(self, company_name: str) -> dict:
        row = self._conn.execute(
            "SELECT status, role, notes FROM tracker_status WHERE company_name = ? COLLATE NOCASE",
            (company_name,),
        ).fetchone()
        return {"status": row[0], "role": row[1], "notes": row[2]} if row else {}

    def upsert_tracker_status(
        self, company_name: str, status: str, role: str = "", notes: str = ""
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO tracker_status (company_name, status, role, notes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(company_name) DO UPDATE SET
                       status = excluded.status,
                       role = excluded.role,
                       notes = excluded.notes""",
                (company_name, status, role, notes),
            )

    def get_all_tracker_statuses(self) -> dict:
        rows = self._conn.execute(
            "SELECT company_name, status, role, notes FROM tracker_status"
        ).fetchall()
        return {r[0]: {"status": r[1], "role": r[2], "notes": r[3]} for r in rows}

    def delete_tracker_entry(self, company_name: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM tracker_status WHERE company_name = ? COLLATE NOCASE",
                (company_name,),
            )
            self._conn.execute(
                "DELETE FROM activities WHERE company_name = ? COLLATE NOCASE",
                (company_name,),
            )

    def get_tracker_summary(self) -> pd.DataFrame:
        companies = self._conn.execute(
            "SELECT DISTINCT company_name FROM activities ORDER BY company_name"
        ).fetchall()
        rows = []
        for (name,) in companies:
            ts = self._conn.execute(
                "SELECT status, role, notes FROM tracker_status WHERE company_name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            status = ts[0] if ts else "In Progress"
            role = ts[1] if ts else ""
            tracker_notes = ts[2] if ts else ""

            acts = self._conn.execute(
                """SELECT activity_type, contact_name, contact_title, date, follow_up_date, notes, role_title
                   FROM activities WHERE company_name = ? COLLATE NOCASE ORDER BY date ASC""",
                (name,),
            ).fetchall()

            contacts: list[str] = []
            for a in acts:
                if a[1]:
                    c = f"{a[1]} ({a[2]})" if a[2] else a[1]
                    if c not in contacts:
                        contacts.append(c)

            timeline = []
            for a in acts:
                entry = f"{a[3]}: {a[0]}"
                if a[1]:
                    entry += f" {a[1]}"
                timeline.append(entry)

            follow_ups = [a[4] for a in acts if a[4]]
            next_followup = min(follow_ups) if follow_ups else ""

            if not role:
                for a in acts:
                    if a[6]:
                        role = a[6]
                        break

            notes_parts = []
            if tracker_notes:
                notes_parts.append(tracker_notes)
            for a in acts:
                if a[5]:
                    notes_parts.append(f"{a[3]}: {a[5]}")

            rows.append(
                {
                    "Company": name,
                    "Status": status,
                    "Role": role,
                    "Contacts": ", ".join(contacts),
                    "Activities": " → ".join(timeline),
                    "Follow-up": next_followup,
                    "Notes": " | ".join(notes_parts),
                }
            )

        return (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=[
                    "Company",
                    "Status",
                    "Role",
                    "Contacts",
                    "Activities",
                    "Follow-up",
                    "Notes",
                ]
            )
        )

    # --- connections -------------------------------------------------------

    def import_connections(self, rows: list[dict]) -> int:
        count = 0
        with self._conn:
            self._conn.execute("DELETE FROM connections")
            for r in rows:
                self._conn.execute(
                    """INSERT INTO connections
                       (first_name, last_name, url, email, company, position, connected_on)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r.get("First Name", ""),
                        r.get("Last Name", ""),
                        r.get("URL", ""),
                        r.get("Email Address", ""),
                        r.get("Company", ""),
                        r.get("Position", ""),
                        r.get("Connected On", ""),
                    ),
                )
                count += 1
            self._conn.execute("DELETE FROM connections_meta")
            self._conn.execute(
                "INSERT INTO connections_meta (id, last_uploaded) VALUES (1, ?)",
                (datetime.now().isoformat(),),
            )
        return count

    def get_connections_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM connections").fetchone()
        return row[0] if row else 0

    def get_connections_last_uploaded(self) -> str:
        row = self._conn.execute(
            "SELECT last_uploaded FROM connections_meta WHERE id = 1"
        ).fetchone()
        return row[0] if row else ""

    def search_connections_by_company(self, company_name: str) -> pd.DataFrame:
        return pd.read_sql_query(
            """SELECT first_name, last_name, url, company, position
               FROM connections
               WHERE company LIKE ? COLLATE NOCASE
               ORDER BY last_name""",
            self._conn,
            params=(f"%{company_name}%",),
        )

    def search_connections_by_companies(self, company_names: list[str]) -> pd.DataFrame:
        if not company_names:
            return pd.DataFrame()
        placeholders = " OR ".join(["company LIKE ? COLLATE NOCASE"] * len(company_names))
        params = [f"%{n}%" for n in company_names]
        return pd.read_sql_query(
            f"""SELECT first_name, last_name, url, company, position
                FROM connections WHERE {placeholders}
                ORDER BY last_name""",
            self._conn,
            params=params,
        )

    def hide_intro(self, connection_url: str, company_name: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO hidden_intros (connection_url, company_name) VALUES (?, ?)",
                (connection_url, company_name),
            )

    def get_hidden_intros(self, company_name: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT connection_url FROM hidden_intros WHERE company_name = ? COLLATE NOCASE",
            (company_name,),
        ).fetchall()
        return {r[0] for r in rows}

    # --- runs / telemetry (Phase 11) ---------------------------------------

    def record_run(
        self,
        source: str,
        *,
        started_at: str,
        ended_at: str,
        items_fetched: int,
        items_kept: int,
        error: str | None,
        user_version_at_run: int,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO runs
                   (source, started_at, ended_at, items_fetched, items_kept,
                    error, user_version_at_run)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    source,
                    started_at,
                    ended_at,
                    items_fetched,
                    items_kept,
                    error,
                    user_version_at_run,
                ),
            )
            return int(cur.lastrowid or 0)

    def last_run(self, source: str) -> dict | None:
        row = self._conn.execute(
            """SELECT id, source, started_at, ended_at, items_fetched, items_kept,
                      error, user_version_at_run
               FROM runs WHERE source = ? ORDER BY id DESC LIMIT 1""",
            (source,),
        ).fetchone()
        if row is None:
            return None
        cols = (
            "id",
            "source",
            "started_at",
            "ended_at",
            "items_fetched",
            "items_kept",
            "error",
            "user_version_at_run",
        )
        return dict(zip(cols, row, strict=True))

    def failure_streak(self, source: str) -> int:
        """Count consecutive rows with error IS NOT NULL, newest-first, stop
        at first success. Short-circuits — never reads past the streak+1."""
        streak = 0
        for (err,) in self._conn.execute(
            "SELECT error FROM runs WHERE source = ? ORDER BY id DESC",
            (source,),
        ):
            if err is None:
                break
            streak += 1
        return streak
