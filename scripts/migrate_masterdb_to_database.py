from __future__ import annotations

from internal.database import NatsuminDatabase
from internal.contracts.seasons import SeasonX
from uuid import uuid4

import aiosqlite
import argparse
import asyncio


async def main(*, production: bool, sync_season: bool):
	database = NatsuminDatabase(production)

	badge_ids: dict[int, str] = {}
	user_ids: dict[int, str] = {}

	await database.setup()

	async with database.connect() as conn:
		async with aiosqlite.connect("data/master.db") as master_conn:
			master_conn.row_factory = aiosqlite.Row
			async with master_conn.execute("SELECT * FROM badges") as cursor:
				badge_rows = await cursor.fetchall()

				for row in badge_rows:
					uuid_id = str(uuid4())
					badge_ids[row["id"]] = uuid_id
					await conn.execute(
						"INSERT OR IGNORE INTO badge (id, name, description, artist, url, type) VALUES (?, ?, ?, ?, ?, ?)",
						(uuid_id, row["name"], row["description"], row["artist"], row["url"], row["type"]),
					)

			async with master_conn.execute("SELECT * FROM users") as cursor:
				user_rows = await cursor.fetchall()

				for row in user_rows:
					uuid_id = str(uuid4())
					user_ids[row["id"]] = uuid_id
					await conn.execute(
						"INSERT OR IGNORE INTO user (id, discord_id, username, rep, gen) VALUES (?, ?, ?, ?, ?)",
						(uuid_id, row["discord_id"], row["username"], row["rep"], row["gen"]),
					)

			async with master_conn.execute("SELECT * FROM user_aliases") as cursor:
				aliases_rows = await cursor.fetchall()

				for row in aliases_rows:
					uuid_id = user_ids[row["user_id"]]
					await conn.execute("INSERT OR IGNORE INTO user_alias (username, user_id) VALUES (?, ?)", (row["username"], uuid_id))

			async with master_conn.execute("SELECT * FROM legacy_leaderboard") as cursor:
				legacy_lb_rows = await cursor.fetchall()

				for row in legacy_lb_rows:
					uuid_id = user_ids[row["user_id"]]
					await conn.execute("INSERT OR IGNORE INTO leaderboard_legacy (user_id, exp) VALUES (?, ?)", (uuid_id, row["exp"]))

			async with master_conn.execute("SELECT * FROM user_badges") as cursor:
				user_badges_rows = await cursor.fetchall()

				for row in user_badges_rows:
					user_uuid_id = user_ids[row["user_id"]]
					badge_uuid_id = badge_ids[row["badge_id"]]

					await conn.execute("INSERT OR IGNORE INTO user_badge (user_id, badge_id) VALUES (?, ?)", (user_uuid_id, badge_uuid_id))

		await conn.commit()

	if sync_season:
		await SeasonX.sync_season(database)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--production", action="store_true")
	parser.add_argument("--sync-season", action="store_true")
	args = parser.parse_args()

	asyncio.run(main(production=args.production, sync_season=args.sync_season))
