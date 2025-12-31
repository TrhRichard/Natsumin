from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER
from typing import TYPE_CHECKING

import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot

from .Errors import Errors


class InternalExt(Errors, name="Internal", command_attrs=dict(hidden=True)):
	"""Internal related commands and listeners"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.internal")
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/internal.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)


def setup(bot: NatsuminBot):
	bot.add_cog(InternalExt(bot))
