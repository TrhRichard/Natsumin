PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bot_config (
	key TEXT NOT NULL,
	value TEXT NOT NULL,

	PRIMARY KEY (key)
) STRICT;

CREATE TABLE IF NOT EXISTS user (
	id         TEXT NOT NULL, 
	discord_id INTEGER UNIQUE,
	username   TEXT NOT NULL,
	rep        TEXT,
	gen        INTEGER,

	PRIMARY KEY (id)
) STRICT;


CREATE TABLE IF NOT EXISTS user_alias (
	username TEXT NOT NULL,
	user_id  TEXT NOT NULL,

	PRIMARY KEY (username),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;


CREATE TABLE IF NOT EXISTS leaderboard_legacy (
	user_id	INTEGER NOT NULL,         
	exp    	INTEGER NOT NULL,

	PRIMARY KEY (user_id),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS leaderboard_new (
	user_id	INTEGER NOT NULL,
	score	INTEGER NOT NULL,

	PRIMARY KEY (user_id),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;


CREATE TABLE IF NOT EXISTS badge (
	id          TEXT NOT NULL,
	name        TEXT NOT NULL,
	description TEXT NOT NULL,
	artist      TEXT NOT NULL,
	url         TEXT NOT NULL,
	type        TEXT NOT NULL DEFAULT 'contracts',

	PRIMARY KEY (id)
) STRICT;

CREATE TABLE IF NOT EXISTS user_badge (
	user_id  TEXT NOT NULL,                     
	badge_id TEXT NOT NULL,

	PRIMARY KEY (user_id, badge_id),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (badge_id) REFERENCES badge(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS season (
	id			TEXT NOT NULL,
	name		TEXT NOT NULL,

	PRIMARY KEY (id)
) STRICT;

CREATE TABLE IF NOT EXISTS season_user (
	season_id			TEXT NOT NULL,
	user_id             TEXT NOT NULL,
	status          	INTEGER NOT NULL,
	kind            	INTEGER NOT NULL,
	rep             	TEXT,
	contractor_id		TEXT,
	contractor      	TEXT,
	list_url        	TEXT,
	veto_used       	INTEGER NOT NULL DEFAULT 0,
	accepting_manhwa	INTEGER NOT NULL DEFAULT 0,
	accepting_ln    	INTEGER NOT NULL DEFAULT 0,
	preferences     	TEXT,
	bans            	TEXT,

	PRIMARY KEY (season_id, user_id),
	FOREIGN KEY (season_id) REFERENCES season(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (contractor_id) REFERENCES user(id) ON DELETE SET NULL ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS season_contract (
	season_id		TEXT NOT NULL,
	id        		TEXT NOT NULL,
	name      		TEXT NOT NULL,
	type      		TEXT NOT NULL,
	kind      		INTEGER NOT NULL,
	status    		INTEGER NOT NULL,
	contractee_id	INTEGER NOT NULL,
	contractor		TEXT,
	optional  		INTEGER NOT NULL DEFAULT 0,
	progress  		TEXT,
	rating    		TEXT,
	review_url		TEXT,
	medium    		TEXT,

	PRIMARY KEY (season_id, id),
	FOREIGN KEY (season_id) REFERENCES season(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (contractee_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.active_season", "season_x");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.deadline_datetime", "2026-01-18T00:00:00Z");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.deadline_footer", "Season deadline in {time_till}.");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.syncing_enabled", "0");