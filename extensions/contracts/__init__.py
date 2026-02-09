from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER
from internal.checks import whitelist_channel_only
from internal.enums import UserStatus, UserKind
from config import BOT_PREFIX, DEV_BOT_PREFIX
from internal.contracts import sync_season
from discord.ext import commands, tasks
from typing import TYPE_CHECKING

import datetime
import discord
import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot

from .User import UserCog
from .Contracts import ContractsCog
from .Badge import BadgeCog


class ContractsExt(UserCog, BadgeCog, ContractsCog, name="Contracts"):
	"""Contracts related commands"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.contracts")
		self.is_syncing_enabled = True
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

		self.sync_database.start()
		self.change_user_status.start()

	@commands.command(name="deadline", help="Get the current deadline in ur local time")
	@whitelist_channel_only()
	async def deadline(self, ctx: commands.Context):
		deadline_datetime = await self.bot.database.get_config("contracts.deadline_datetime")
		deadline_datetime = datetime.datetime.fromisoformat(deadline_datetime) if deadline_datetime else None
		if deadline_datetime:
			await ctx.reply(
				f"The current deadline is {discord.utils.format_dt(deadline_datetime, 'f')} ({discord.utils.format_dt(deadline_datetime, 'R')})"
			)
		else:
			await ctx.reply("Deadline unknown.")

	@tasks.loop(minutes=10)
	async def sync_database(self):
		if not self.is_syncing_enabled:
			return

		is_syncing_enabled = bool(await self.bot.get_config("contracts.syncing_enabled"))
		if is_syncing_enabled:
			active_season = await self.bot.get_config("contracts.active_season")
			try:
				await sync_season(self.bot.database, active_season)
			except Exception as err:
				self.is_syncing_enabled = False
				self.logger.error(f"Automatic syncing of {active_season} has failed!", exc_info=err)

	@tasks.loop(minutes=30)
	async def change_user_status(self):
		async with self.bot.database.connect() as conn:
			season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			query = """
				SELECT
					SUM(su.status = ?2 AND su.kind = ?3) AS passed,
					SUM(su.kind = ?3) AS total
				FROM season_user su
				WHERE su.season_id = ?1;
			"""
			async with conn.execute(query, (season_id, UserStatus.PASSED.value, UserKind.NORMAL.value)) as cursor:
				row = await cursor.fetchone()
				users_passed = row["passed"]
				users_total = row["total"]
		await self.bot.change_presence(
			status=discord.Status.online,
			activity=discord.CustomActivity(
				name=f"{users_passed}/{users_total} users passed | {BOT_PREFIX if self.bot.is_production else DEV_BOT_PREFIX}help"
			),
		)

	@sync_database.before_loop
	async def before_sync(self):
		await self.bot.wait_until_ready()
		await self.bot.database.wait_until_ready()

	@change_user_status.before_loop
	async def before_status(self):
		await self.bot.wait_until_ready()
		await self.bot.database.wait_until_ready()

	def cog_unload(self):
		self.change_user_status.cancel()
		self.sync_database.cancel()


def setup(bot: NatsuminBot):
	bot.add_cog(ContractsExt(bot))
