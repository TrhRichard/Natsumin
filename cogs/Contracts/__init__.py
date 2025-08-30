from discord.ext import commands, tasks
from typing import TYPE_CHECKING
from common import config
import contracts
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


class Contracts(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

		self.change_user_status.start()

	@commands.command(name="deadline", help="Get the current deadline in ur local time")
	async def deadline(self, ctx: commands.Context):
		await ctx.reply(f"The current deadline is <t:{config.deadline_timestamp}:f> (<t:{config.deadline_timestamp}:R>)")

	@tasks.loop(minutes=30)
	async def change_user_status(self):
		season_db = await contracts.get_season_db()
		async with season_db.connect() as db:
			async with db.execute(
				"SELECT COUNT(rep) AS total, SUM(CASE WHEN status = ? AND rep IS NOT NULL THEN 1 ELSE 0 END) as passed FROM users",
				(contracts.UserStatus.PASSED.value,),
			) as cursor:
				row = await cursor.fetchone()
				users_passed: int = row["passed"] or 0
				users_total: int = row["total"] or 0
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
