from __future__ import annotations

from internal.contracts.rep import get_rep, RepName
from internal.enums import UserStatus, UserKind
from internal.database import NatsuminDatabase
from internal.functions import get_user_id
from uuid import uuid4

import aiofiles
import argparse
import asyncio


SEASON_ID = "season_xi"


async def main(*, production: bool):
	database = NatsuminDatabase(production)
	await database.setup()

	async with aiofiles.open("scripts/preseason_list.txt") as f:
		username_list = [u for u in (await f.read()).splitlines()]

	async with database.connect() as conn:
		for username in username_list:
			user_id = await get_user_id(conn, username)
			if user_id is None:
				user_id = str(uuid4())
				await conn.execute("INSERT INTO user (id, username) VALUES (?, ?)", (user_id, username))

			user_status = UserStatus.PENDING
			user_rep = None

			async with conn.execute("SELECT rep FROM user WHERE id = ?", (user_id,)) as cursor:
				rep_row = await cursor.fetchone()
				if rep_row:
					user_rep = get_rep(rep_row["rep"])

			if user_rep is None:
				user_rep = RepName.UNKNOWN

			async with conn.execute("SELECT * FROM season_user WHERE season_id = ? AND user_id = ?", (SEASON_ID, user_id)) as cursor:
				user_row = await cursor.fetchone()

			if not user_row:
				async with conn.execute(
					"INSERT INTO season_user (season_id, user_id, status, kind, rep) VALUES (?, ?, ?, ?, ?) RETURNING *",
					(SEASON_ID, user_id, user_status.value, UserKind.NORMAL.value, user_rep),
				) as cursor:
					user_row = await cursor.fetchone()

		await conn.commit()

	print(f"Added {len(username_list)} to the database in season {SEASON_ID}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--production", action="store_true")
	args = parser.parse_args()

	asyncio.run(main(production=args.production))
