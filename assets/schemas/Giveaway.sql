PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS giveaways (
	message_id	INTEGER PRIMARY KEY,
	channel_id	INTEGER NOT NULL,
	guild_id	INTEGER NOT NULL,
	author_id	INTEGER NOT NULL,
	prize		TEXT NOT NULL,
	host		TEXT NOT NULL,
	winners		INTEGER NOT NULL CHECK(winners > 0),
	ends_at		INTEGER NOT NULL CHECK(ends_at > created_at),
	created_at	INTEGER NOT NULL DEFAULT (strftime('%s','now')),
	ended		BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS role_requirements (
	giveaway_id INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
	role_id 	INTEGER NOT NULL,
	PRIMARY KEY (giveaway_id, role_id)
);

CREATE TABLE IF NOT EXISTS users_entered (
	giveaway_id	INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
	user_id		INTEGER NOT NULL,
	PRIMARY KEY	(giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS winners (
	giveaway_id 	INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
	winner_index	INTEGER NOT NULL CHECK(winner_index > 0),
	user_id			INTEGER NOT NULL,
	PRIMARY KEY (giveaway_id, winner_index),
	UNIQUE (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS tags (
	giveaway_id INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
	tag			TEXT NOT NULL,
	PRIMARY KEY	(giveaway_id, tag)
)

CREATE INDEX IF NOT EXISTS giveaways_ends_at ON giveaways(ends_at);
CREATE INDEX IF NOT EXISTS users_entered_user_id ON users_entered(user_id);