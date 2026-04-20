-- 0001_initial.sql — baseline schema.
-- All tables use CREATE TABLE IF NOT EXISTS so this migration is safe to
-- re-apply over an already-populated pre-Phase-10 DB (user_version=0).

CREATE TABLE IF NOT EXISTS startups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    funding_stage TEXT DEFAULT '',
    amount_raised TEXT DEFAULT '',
    location TEXT DEFAULT '',
    website TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    date_found TEXT,
    status TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_startups_name
    ON startups(company_name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS job_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    company_description TEXT DEFAULT '',
    role_title TEXT DEFAULT '',
    location TEXT DEFAULT '',
    url TEXT DEFAULT '',
    priority TEXT DEFAULT 'Medium',
    source TEXT DEFAULT '',
    status TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    date_found TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_company_role
    ON job_matches(company_name COLLATE NOCASE, role_title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT DEFAULT '',
    last_name TEXT DEFAULT '',
    url TEXT DEFAULT '',
    email TEXT DEFAULT '',
    company TEXT DEFAULT '',
    position TEXT DEFAULT '',
    connected_on TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_connections_company
    ON connections(company COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS connections_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_uploaded TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS hidden_intros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_url TEXT NOT NULL,
    company_name TEXT NOT NULL,
    UNIQUE(connection_url, company_name)
);

CREATE TABLE IF NOT EXISTS processed_items (
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    processed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (source, item_id)
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    role_title TEXT DEFAULT '',
    activity_type TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    contact_title TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    date TEXT NOT NULL,
    follow_up_date TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracker_status (
    company_name TEXT PRIMARY KEY,
    status TEXT DEFAULT 'In Progress',
    role TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
