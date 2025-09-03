from discord.ext import commands
from typing import TYPE_CHECKING
from common import config
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


class ContractsContracts(commands.Cog):  # yeah
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")


def setup(bot):
	bot.add_cog(ContractsContracts(bot))
