from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

if TYPE_CHECKING:
	from internal.base.bot import NatsuBot
	from internal.database import NatsuDatabase
	from logging import Logger


class NatsuCog(commands.Cog):
	bot: NatsuBot
	database: NatsuDatabase
	logger: Logger

	def __init__(self, bot: NatsuBot) -> None:
		self.bot = bot
		self.database = bot.database
		super().__init__()
