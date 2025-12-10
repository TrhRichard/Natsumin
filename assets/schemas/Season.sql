PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
	id              	INTEGER PRIMARY KEY, -- User id from master.db
	status          	INTEGER NOT NULL,
	kind            	INTEGER NOT NULL,
	rep             	TEXT, -- the rep in the specific season, if none it means they aren't in the season
	contractor_id		INTEGER REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
	contractor      	TEXT,
	list_url        	TEXT,
	veto_used       	BOOLEAN NOT NULL DEFAULT FALSE,
	accepting_manhwa	BOOLEAN NOT NULL DEFAULT FALSE,
	accepting_ln    	BOOLEAN NOT NULL DEFAULT FALSE,
	preferences     	TEXT,
	bans            	TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
	id        	INTEGER PRIMARY KEY AUTOINCREMENT,
	name      	TEXT NOT NULL,
	type      	TEXT NOT NULL,
	kind      	INTEGER NOT NULL,
	status    	INTEGER NOT NULL,
	contractee	INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
	contractor	TEXT,
	optional  	BOOLEAN NOT NULL DEFAULT FALSE,
	progress  	TEXT,
	rating    	TEXT,
	review_url	TEXT,
	medium    	TEXT
);