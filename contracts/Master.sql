PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
	id         INTEGER PRIMARY KEY AUTOINCREMENT, 
	discord_id INTEGER NOT NULL UNIQUE,          
	username   TEXT NOT NULL,
	rep        TEXT NOT NULL,
	gen        INTEGER -- since we include aria badges theres a high chance some people in there might not be in contracts so no gen
);

-- Legacy leaderboard, no plans for new leaderboard since it's still wip according to the sheet
CREATE TABLE IF NOT EXISTS legacy (
	user_id INTEGER PRIMARY KEY NOT NULL,         
	exp     INTEGER NOT NULL,
	FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Badge definitions, urls are done manually cause google sucks ass
CREATE TABLE IF NOT EXISTS badges (
	id      	INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
	name    	TEXT NOT NULL,
	description TEXT NOT NULL,
	artist  	TEXT NOT NULL,
	url     	TEXT NOT NULL, -- URL to image/gif/video/etc
	type        TEXT NOT NULL DEFAULT 'contracts'
);

-- Which user owns which badges, so that I don't have to use json to keep track
CREATE TABLE IF NOT EXISTS user_badges (
	user_id		INTEGER NOT NULL,                     
	badge_id	INTEGER NOT NULL,
	PRIMARY KEY (user_id, badge_id),
	FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
	FOREIGN KEY (badge_id) REFERENCES badges(id) ON DELETE CASCADE
);
