PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
	id         INTEGER PRIMARY KEY AUTOINCREMENT, 
	discord_id INTEGER UNIQUE,    
	username   TEXT NOT NULL,
	rep        TEXT, -- since we include aria badges theres a high chance some people in there might not be in contracts so no rep
	gen        INTEGER -- same as above
);

-- User aliases table, allows to find a user from a past username
CREATE TABLE IF NOT EXISTS user_aliases (
	username TEXT PRIMARY KEY,
	user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- Legacy leaderboard, no plans for new leaderboard since it's still wip according to the sheet
CREATE TABLE IF NOT EXISTS legacy_leaderboard (
	user_id INTEGER PRIMARY KEY NOT NULL REFERENCES users(id) ON DELETE CASCADE,         
	exp     INTEGER NOT NULL
);

-- Badge definitions, urls are done manually cause google sucks ass
CREATE TABLE IF NOT EXISTS badges (
	id          INTEGER PRIMARY KEY AUTOINCREMENT,
	name        TEXT NOT NULL,
	description TEXT NOT NULL,
	artist      TEXT NOT NULL,
	url         TEXT NOT NULL, -- URL to image/gif/video/etc
	type        TEXT NOT NULL DEFAULT 'contracts'
);

-- Which user owns which badges, so that I don't have to use json to keep track
CREATE TABLE IF NOT EXISTS user_badges (
	user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,                     
	badge_id INTEGER NOT NULL REFERENCES badges(id) ON DELETE CASCADE,
	PRIMARY KEY (user_id, badge_id)
);
