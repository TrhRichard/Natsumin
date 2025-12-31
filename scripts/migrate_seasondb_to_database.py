from __future__ import annotations

from internal.database import NatsuminDatabase
from pathlib import Path
from uuid import uuid4

import aiosqlite
import argparse
import asyncio
import os


async def main(db_path: os.PathLike, *, production: bool, season_id: str = "winter2025"):
	db_path = Path(db_path)
	if not db_path.is_file():
		raise ValueError("Season database not found")

	database = NatsuminDatabase(production)

	user_ids: dict[int, str] = {}

	await database.setup()

	async with database.connect() as conn:
		async with conn.execute("SELECT COUNT(*) as count FROM season_user WHERE season_id = ?", (season_id,)) as cursor:
			existing_users_in_seasonid: int = (await cursor.fetchone())["count"]
			if existing_users_in_seasonid > 0:
				raise ValueError(f"Season {season_id} already has users.")

		async with aiosqlite.connect("data/master.db") as master_conn:
			master_conn.row_factory = aiosqlite.Row

			async with master_conn.execute("SELECT * FROM users") as cursor:
				user_rows = await cursor.fetchall()

				for row in user_rows:
					async with conn.execute(
						"SELECT id FROM user WHERE username = ? OR discord_id = ?", (row["username"], row["discord_id"])
					) as cursor:
						id_row = await cursor.fetchone()

					user_ids[row["id"]] = id_row["id"]

		async with aiosqlite.connect(db_path) as season_conn:
			season_conn.row_factory = aiosqlite.Row

			async with season_conn.execute("SELECT * FROM users") as cursor:
				user_rows = await cursor.fetchall()
				for row in user_rows:
					user_id = user_ids.get(row["id"])
					contractor_id = user_ids.get(row["contractor_id"])
					if user_id is None:
						print(f"{row['id']} HAS NO USER ID")
						continue
					if contractor_id is None and row["contractor_id"] is not None:
						print(f"{row['id']} HAS NO CONTRACTOR ID ({row['contractor_id']})")
						continue

					keys = (
						"season_id",
						"user_id",
						"status",
						"kind",
						"rep",
						"contractor_id",
						"list_url",
						"veto_used",
						"accepting_manhwa",
						"accepting_ln",
						"preferences",
						"bans",
					)
					values = (
						season_id,
						user_id,
						row["status"],
						row["kind"],
						row["rep"],
						contractor_id,
						row["list_url"],
						row["veto_used"],
						row["accepting_manhwa"],
						row["accepting_ln"],
						row["preferences"],
						row["bans"],
					)
					await conn.execute(f"INSERT OR IGNORE INTO season_user ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", values)

			async with season_conn.execute("SELECT * FROM contracts") as cursor:
				contract_rows = await cursor.fetchall()
				for row in contract_rows:
					contractee_id = user_ids.get(row["contractee"])
					if contractee_id is None:
						print(f"{row['id']} HAS NO CONTRACTEE ID")
						continue

					keys = (
						"season_id",
						"id",
						"name",
						"type",
						"kind",
						"status",
						"contractee_id",
						"contractor",
						"optional",
						"progress",
						"rating",
						"review_url",
						"medium",
					)
					values = (
						season_id,
						str(uuid4()),
						row["name"],
						row["type"],
						row["kind"],
						row["status"],
						contractee_id,
						row["contractor"],
						row["optional"],
						row["progress"],
						row["rating"],
						row["review_url"],
						row["medium"],
					)
					await conn.execute(f"INSERT OR IGNORE INTO season_contract ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", values)

		await conn.commit()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("db_path", help="Path to database")
	parser.add_argument("season_id", nargs="?", default="winter2025", help="Season id to put data on")
	parser.add_argument("--production", action="store_true")
	args = parser.parse_args()

	asyncio.run(main(args.db_path, production=args.production, season_id=args.season_id))
