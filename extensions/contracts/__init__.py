from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER
from internal.base.cog import NatsuminCog
from typing import TYPE_CHECKING

import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


class ContractsExt(NatsuminCog, name="Contracts"):
	"""Contracts related commands"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.contracts")
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)


def setup(bot: NatsuminBot):
	bot.add_cog(ContractsExt(bot))
