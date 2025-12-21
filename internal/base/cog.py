from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot
	from logging import Logger


class NatsuminCog(commands.Cog):
	bot: NatsuminBot
	logger: Logger

	def __init__(self, bot: NatsuminBot) -> None:
		self.bot = bot
		super().__init__()
