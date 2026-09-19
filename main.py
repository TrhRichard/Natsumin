from config import DISCORD_TOKEN, IS_PRODUCTION
from internal.logging import setup_logger
from internal.base.bot import NatsuBot
from api.app import create_app
from pathlib import Path

import asyncio
import uvicorn


async def main():
	Path("logs/").mkdir(exist_ok=True, parents=True)
	Path("data/").mkdir(exist_ok=True, parents=True)

	bot = NatsuBot()
	app = create_app()
	app.state.bot = bot

	@app.get("/health", summary="Check the health of the Bot & API", tags=["bot"])
	async def health():
		return {
			"ok": True,
			"production": IS_PRODUCTION,
			"bot": {
				"ready": bot.is_ready() if bot else False,
				"guilds": len(bot.guilds) if bot else -1,
				"user": {"id": bot.user.id, "username": bot.user.name, "discriminator": bot.user.discriminator} if bot and bot.user else None,
			},
		}

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
	asyncio.run(main())
