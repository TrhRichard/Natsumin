PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS giveaways (
    message_id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL,
    reward TEXT NOT NULL,
    winners INTEGER NOT NULL DEFAULT 0 CHECK(winners >= 0),
    ends_at INTEGER NOT NULL CHECK(ends_at > created_at),
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS role_requirements (
    giveaway_id INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, role_id)
);

CREATE TABLE IF NOT EXISTS users_entered (
    giveaway_id INTEGER NOT NULL REFERENCES giveaways(message_id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE INDEX IF NOT EXISTS giveaways_ends_at ON giveaways(ends_at);
CREATE INDEX IF NOT EXISTS users_entered_user_id ON users_entered(user_id);