from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER
from internal.contracts import sync_season
from internal.base.cog import NatsuminCog
from discord.ext import commands, tasks
from typing import TYPE_CHECKING

import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


class ContractsExt(NatsuminCog, name="Contracts"):
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

	@sync_database.before_loop
	async def before_sync(self):
		await self.bot.wait_until_ready()


def setup(bot: NatsuminBot):
	bot.add_cog(ContractsExt(bot))
