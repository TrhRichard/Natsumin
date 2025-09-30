from dotenv import load_dotenv
import contracts
import aiofiles
import asyncio
import json

load_dotenv()


async def main():
	master_db = contracts.MasterDB.get_database()

	async with aiofiles.open("master.json", "w", encoding="utf-8") as f:
		await f.write(json.dumps(await master_db.to_dict(), indent=4))


asyncio.run(main())
