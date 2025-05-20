PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
	username TEXT PRIMARY KEY NOT NULL UNIQUE,
	status INTEGER NOT NULL,
	kind INTEGER NOT NULL,
	discord_id INTEGER,
	rep TEXT,
	contractor TEXT,
	list_url TEXT,
	veto_used BOOLEAN,
	accepting_manhwa BOOLEAN,
	accepting_ln BOOLEAN,
	preferences TEXT,
	bans TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	name TEXT NOT NULL,
	type TEXT NOT NULL,
	kind INTEGER NOT NULL,
	status INTEGER NOT NULL,
	contractee TEXT NOT NULL,
	optional BOOLEAN,
	contractor TEXT,
	progress TEXT,
	rating TEXT,
	review_url TEXT,
	medium TEXT
);