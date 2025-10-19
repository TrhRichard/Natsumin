from dotenv import load_dotenv
import contracts
import aiofiles
import asyncio
import json

load_dotenv()


async def main():
	season_db = await contracts.get_season_db()
	time = await contracts.sync_season_db()
	print(f"Finished in {time:.2f} seconds")


asyncio.run(main())
