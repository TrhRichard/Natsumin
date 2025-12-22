from __future__ import annotations

from internal.database import NatsuminDatabase
from internal.contracts.seasons import SeasonX

import argparse
import asyncio


async def main(*, production: bool):
	database = NatsuminDatabase(production)
	await database.setup()

	await SeasonX.sync_season(database)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--production", action="store_true")
	args = parser.parse_args()

	asyncio.run(main(production=args.production))
