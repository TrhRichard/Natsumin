from __future__ import annotations

from internal.database import NatsuminDatabase
from internal.contracts.sheet import fetch_sheets
from internal.functions import get_user_id
from internal.contracts.rep import get_rep

import argparse
import asyncio

# =IFS(AJ2 = 1, "Ⅰ", AL2 = 1, "Ⅱ",AP2 = 1, "Ⅲ", AU2 = 1, "Ⅳ", BC2 = 1, "Ⅴ", BO2 = 1, "Ⅵ", CA2 = 1, "Ⅶ",CJ2 = 1, "Ⅷ",CU2 = 1, "Ⅸ",DH2 = 1, "Ⅹ")

ROMAN_TO_NUMBER = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "Ⅵ": 6, "Ⅶ": 7, "Ⅷ": 8, "Ⅸ": 9, "Ⅹ": 10}


async def main(*, production: bool):
	database = NatsuminDatabase(production)
	await database.setup()

	master_sheet = await fetch_sheets("15M2jJ46tI3Dy5VC_zPPT-whUt7cFjwXTxOdBga8EL6A", "Legacy Rank (Season 1-10)!A2:G889")

	async with database.connect() as conn:
		for row in master_sheet.rows:
			rep: str = row.get_value("A")
			gen: int | None = ROMAN_TO_NUMBER.get(row.get_value("B"), None)
			username: str = row.get_value("D")
			legacy_exp: int = row.get_value("G")

			if gen is None:
				continue

			rep_name = get_rep(rep)
			if rep_name is None:
				continue

			user_id = await get_user_id(conn, username)
			if user_id is None:
				continue

			await conn.execute("UPDATE user SET rep = ?, gen = ? WHERE id = ?", (rep_name.value, gen, user_id))
			await conn.execute(
				"INSERT INTO leaderboard_legacy (user_id, exp) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET exp=excluded.exp",
				(user_id, legacy_exp),
			)

		await conn.commit()

	print("Finished!")


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--production", action="store_true")
	args = parser.parse_args()

	asyncio.run(main(production=args.production))
