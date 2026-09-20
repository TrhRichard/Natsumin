from config import DISCORD_TOKEN, IS_PRODUCTION
from internal.logging import setup_logger
from internal.base.bot import NatsuBot
from api.app import create_app
from pathlib import Path

import asyncio
import uvicorn
import psutil
import time


async def main():
	Path("logs/").mkdir(exist_ok=True, parents=True)
	Path("data/").mkdir(exist_ok=True, parents=True)

	bot = NatsuBot()
	app = create_app()
	app.state.bot = bot

	@app.get("/health", summary="Check the health of the Bot & API", tags=["system"])
	async def health():
		bot_details = (
			{
				"ready": bot.is_ready(),
				"guilds": len(bot.guilds) if bot.is_ready() else -1,
				"user": {"id": bot.user.id, "username": bot.user.name, "discriminator": bot.user.discriminator} if bot and bot.user else None,
			}
			if bot
			else None
		)

		proc = psutil.Process()
		mem = proc.memory_info()
		process_details = {
			"memory_usage_mb": round(mem.rss / 1024**2, 2),
			"cpu_percent": proc.cpu_percent(),
			"uptime_seconds": round(time.time() - proc.create_time()),
		}
		return {"ok": True, "production": IS_PRODUCTION, "bot": bot_details, "process": process_details}

	config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
	server = uvicorn.Server(config)

	setup_logger("uvicorn", file="logs/api.log")
	setup_logger("uvicorn.error", file="logs/api.log")
	setup_logger("uvicorn.access", file="logs/api.log")

	async with bot:
		async with asyncio.TaskGroup() as tg:
			tg.create_task(bot.start(DISCORD_TOKEN))
			tg.create_task(server.serve())


if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
