PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bot_config (
	key 		TEXT NOT NULL,
	value 		TEXT NOT NULL,
	created_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at	TEXT,

	PRIMARY KEY (key)
) STRICT;

CREATE TABLE IF NOT EXISTS blacklist_user (
	discord_id	INTEGER NOT NULL,
	reason		TEXT,

	PRIMARY KEY (discord_id)
) STRICT;

CREATE TABLE IF NOT EXISTS whitelist_channel (
	guild_id 	INTEGER NOT NULL,
	channel_id	INTEGER NOT NULL,

	PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS user (
	id        	TEXT NOT NULL, 
	discord_id	INTEGER UNIQUE,
	username  	TEXT NOT NULL,
	rep       	TEXT,
	gen       	INTEGER,
	created_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at	TEXT,

	PRIMARY KEY (id)
) STRICT;

CREATE TABLE IF NOT EXISTS user_config (
	user_id					TEXT NOT NULL,
	badge_display_type		TEXT NOT NULL DEFAULT 'one',
	track_username_history	INTEGER NOT NULL DEFAULT 1,
	updated_at	TEXT,

	PRIMARY KEY (user_id),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS user_alias (
	username 	TEXT NOT NULL,
	user_id  	TEXT NOT NULL,
	created_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

	PRIMARY KEY (username),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;


CREATE TABLE IF NOT EXISTS leaderboard_legacy (
	user_id	TEXT NOT NULL,         
	exp    	INTEGER NOT NULL,

	PRIMARY KEY (user_id),
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS leaderboard_new (
	user_id			TEXT NOT NULL,
	contract_score	INTEGER NOT NULL,

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
	rarity		TEXT NOT NULL DEFAULT 'common',
	created_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at	TEXT,

	PRIMARY KEY (id)
) STRICT;

CREATE TABLE IF NOT EXISTS user_badge (
	user_id		TEXT NOT NULL,                     
	badge_id	TEXT NOT NULL,
	added_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

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
	list_url        	TEXT,
	veto_used       	INTEGER NOT NULL DEFAULT 0,
	accepting_manhwa	INTEGER NOT NULL DEFAULT 0,
	accepting_ln    	INTEGER NOT NULL DEFAULT 0,
	preferences     	TEXT,
	bans            	TEXT,
	created_at			TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at			TEXT,

	PRIMARY KEY (season_id, user_id),
	FOREIGN KEY (season_id) REFERENCES season(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (contractor_id) REFERENCES user(id) ON DELETE SET NULL ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS season_user_fantasy (
	season_id		TEXT NOT NULL,
	user_id			TEXT NOT NULL,
	total_score		INTEGER NOT NULL DEFAULT 0,
	member1_id		TEXT NOT NULL,
	member1_score	INTEGER NOT NULL DEFAULT 0,
	member2_id		TEXT NOT NULL,
	member2_score	INTEGER NOT NULL DEFAULT 0,
	member3_id		TEXT NOT NULL,
	member3_score	INTEGER NOT NULL DEFAULT 0,
	member4_id		TEXT NOT NULL,
	member4_score	INTEGER NOT NULL DEFAULT 0,
	member5_id		TEXT NOT NULL,
	member5_score	INTEGER NOT NULL DEFAULT 0,
	created_at		TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at		TEXT,

	PRIMARY KEY (season_id, user_id),
	FOREIGN KEY (season_id) REFERENCES season(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (member1_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (member2_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (member3_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (member4_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (member5_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS season_contract (
	season_id		TEXT NOT NULL,
	id        		TEXT NOT NULL,
	name      		TEXT NOT NULL,
	type      		TEXT NOT NULL,
	type_label		TEXT,
	kind      		INTEGER NOT NULL,
	status    		INTEGER NOT NULL,
	contractee_id	TEXT NOT NULL,
	contractor		TEXT,
	optional  		INTEGER NOT NULL DEFAULT 0,
	progress  		TEXT,
	rating    		TEXT,
	review_url		TEXT,
	medium    		TEXT,
	media_type		TEXT,
	media_id		TEXT,
	created_at		TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at		TEXT,

	PRIMARY KEY (season_id, id),
	UNIQUE (season_id, type, contractee_id),
	FOREIGN KEY (season_id) REFERENCES season(id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY (contractee_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS media (
	type		TEXT NOT NULL,
	id			TEXT NOT NULL,
	name		TEXT NOT NULL,
	description	TEXT,
	medium		TEXT,
	url			TEXT NOT NULL,
	created_at	TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
	updated_at	TEXT NOT NULL,

	PRIMARY KEY (type, id)
) STRICT;

CREATE TABLE IF NOT EXISTS media_no_match (
	type	TEXT NOT NULL,
	id		TEXT NOT NULL,

	PRIMARY KEY (type, id)
) STRICT;

CREATE TABLE IF NOT EXISTS media_anilist (
	type			TEXT NOT NULL DEFAULT 'anilist', -- here because sqlite
	id				TEXT NOT NULL,

	format			TEXT NOT NULL,
	is_adult		INTEGER NOT NULL DEFAULT 0,
	cover_image		TEXT,
	cover_color		TEXT,
	mal_id			TEXT,
	start_date		TEXT,
	end_date		TEXT,

	romaji_name		TEXT,
	english_name	TEXT,
	native_name		TEXT,

	episodes		INTEGER,
	chapters		INTEGER,
	volumes			INTEGER,

	PRIMARY KEY (id),
	FOREIGN KEY (type, id) REFERENCES media(type, id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS media_steam (
	type			TEXT NOT NULL DEFAULT 'steam', -- here because sqlite
	id				TEXT NOT NULL,

	developer		TEXT NOT NULL,
	publisher		TEXT,
	release_date	TEXT,
	header_image	TEXT,

	PRIMARY KEY (id),
	FOREIGN KEY (type, id) REFERENCES media(type, id) ON DELETE CASCADE ON UPDATE CASCADE
) STRICT;

-- Automated updated_at triggers

CREATE TRIGGER IF NOT EXISTS bot_config_updated_at
	AFTER UPDATE ON bot_config FOR EACH ROW
BEGIN
    UPDATE bot_config SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE key = OLD.key;
END;

CREATE TRIGGER IF NOT EXISTS user_updated_at
	AFTER UPDATE ON user FOR EACH ROW
BEGIN
    UPDATE user SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS user_config_updated_at
	AFTER UPDATE ON user_config FOR EACH ROW
BEGIN
    UPDATE user_config SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS badge_updated_at
	AFTER UPDATE ON badge FOR EACH ROW
BEGIN
    UPDATE badge SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS season_user_updated_at
	AFTER UPDATE ON season_user FOR EACH ROW
BEGIN
    UPDATE season_user SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE season_id = OLD.season_id AND user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS season_user_fantasy_updated_at
	AFTER UPDATE ON season_user_fantasy FOR EACH ROW
BEGIN
    UPDATE season_user_fantasy SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE season_id = OLD.season_id AND user_id = OLD.user_id;
END;

CREATE TRIGGER IF NOT EXISTS season_contract_updated_at
	AFTER UPDATE ON season_contract FOR EACH ROW
BEGIN
    UPDATE season_contract SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE season_id = OLD.season_id AND id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS media_updated_at
    AFTER UPDATE ON media FOR EACH ROW
BEGIN
    UPDATE media SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) WHERE type = OLD.type AND id = OLD.id;
END;

-- Add default config
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.active_season", "season_xi");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.deadline_datetime", "2030-01-15T00:00:00.000Z");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.syncing_enabled", "1");

INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.deadline_footer", "Season deadline in {time_till}.");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.season_ended_footer", "{season_name} has ended.");
INSERT OR IGNORE INTO bot_config (key, value) VALUES ("contracts.archived_season_footer", "Archived data from {season_name}.");

-- Add supported seasons 
INSERT OR IGNORE INTO season (id, name) VALUES ("winter_2025", "Winter 2025");
INSERT OR IGNORE INTO season (id, name) VALUES ("season_x", "Season X");
INSERT OR IGNORE INTO season (id, name) VALUES ("season_xi", "Season XI");