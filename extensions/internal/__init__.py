from __future__ import annotations

from internal.logging import setup_logger
from typing import TYPE_CHECKING


if TYPE_CHECKING:
	from internal.base.bot import NatsuBot

from .errors import Errors


class InternalExt(Errors, name="Internal", command_attrs={"hidden": True}):
	"""Internal related commands and listeners"""

	def __init__(self, bot: NatsuBot):
		super().__init__(bot)
		self.logger = setup_logger("bot.internal", file="logs/internal.log")


def setup(bot: NatsuBot):
	bot.add_cog(InternalExt(bot))
