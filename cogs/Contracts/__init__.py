from discord.ext import commands, tasks
from typing import TYPE_CHECKING
import contracts
import logging
import discord
import config

if TYPE_CHECKING:
	from main import Natsumin


class Contracts(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(config.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(config.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

		self.change_user_status.start()

	@tasks.loop(minutes=30)
	async def change_user_status(self):
		season_db = await contracts.get_season_db()
		users_passed = await season_db.count_users(kind=contracts.UserKind.NORMAL, status=contracts.UserStatus.PASSED)
		users_total = await season_db.count_users(kind=contracts.UserKind.NORMAL)
		await self.bot.change_presence(
			status=discord.Status.online, activity=discord.CustomActivity(name=f"{users_passed}/{users_total} users passed | %help")
		)

	@change_user_status.before_loop
	async def before_loop(self):
		if not self.bot.is_ready():
			await self.bot.wait_until_ready()

	def cog_unload(self):
		self.change_user_status.cancel()


def setup(bot):
	bot.add_cog(Contracts(bot))
