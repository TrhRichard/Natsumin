PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
	user_id            INTEGER PRIMARY KEY, -- User id from master.db
	status             INTEGER NOT NULL,
	primary_contractor TEXT,
	list_url           TEXT,
	veto_used          BOOLEAN,
	accepting_manhwa   BOOLEAN,
	accepting_ln       BOOLEAN,
	preferences        TEXT,
	bans               TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
	id         INTEGER PRIMARY KEY AUTOINCREMENT,
	name       TEXT NOT NULL,
	type       TEXT NOT NULL,
	kind       INTEGER NOT NULL,
	status     INTEGER NOT NULL,
	user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
	contractor TEXT NOT NULL,
	optional   BOOLEAN DEFAULT FALSE,
	progress   TEXT,
	rating     TEXT,
	review_url TEXT,
	medium     TEXT
);