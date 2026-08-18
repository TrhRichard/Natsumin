from __future__ import annotations

from internal.contracts.seasons import SeasonXI
from internal.database import NatsuDatabase

import asyncio


async def main():
	database = NatsuDatabase()
	await database.setup()

	await SeasonXI.sync_season(database)


if __name__ == "__main__":
	asyncio.run(main())
