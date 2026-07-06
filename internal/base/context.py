from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

import discord

if TYPE_CHECKING:
	from internal.database import NatsuDatabase
	from internal.base.bot import NatsuBot


class NatsuContext(commands.Context):
	database: NatsuDatabase
	bot: NatsuBot


class NatsuAppContext(discord.ApplicationContext):
	database: NatsuDatabase
	bot: NatsuBot


class NatsuAutoContext(discord.AutocompleteContext):
	database: NatsuDatabase
	bot: NatsuBot
