from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER, CONSOLE_LOGGING_FORMATTER, COLORS
from config import BOT_PREFIX, DEV_BOT_PREFIX, OWNER_IDS, DISABLED_EXTENSIONS
from internal.database import NatsuminDatabase
from discord.ext import commands
from typing import TYPE_CHECKING
from pathlib import Path
import aiosqlite

import datetime
import discord
import logging
import os

if TYPE_CHECKING:
	from typing import Mapping, Optional


class NatsuminBot(commands.Bot):
	def __init__(self, production: bool = False):
		super().__init__(
			command_prefix=BOT_PREFIX if production else DEV_BOT_PREFIX,
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
			status=discord.Status.online,
			intents=discord.Intents.all(),
			case_insensitive=True,
			help_command=BotHelp(),
		)

		self.is_production = production
		self.started_at = datetime.datetime.now(datetime.UTC)
		self.color = COLORS.DEFAULT
		self.database = NatsuminDatabase(production)

		self.logger = logging.getLogger("bot")
		if not self.logger.hasHandlers():
			file_handler = logging.FileHandler("logs/bot.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)

			self.logger.setLevel(logging.INFO)

		for extension in Path("extensions").iterdir():
			if not extension.is_dir() or extension.stem in DISABLED_EXTENSIONS:
				continue

			extension_path = f"extensions.{extension.stem}"
			try:
				self.load_extension(extension_path)
			except discord.ExtensionFailed as err:
				self.logger.error(f"An exception occured while loading extension: {extension_path}", exc_info=err)

	async def on_ready(self):
		print("server successfully started")
		os.system("cls" if os.name == "nt" else "clear")
		self.logger.info(f"Logged in as {self.user.name}#{self.user.discriminator}!")
		await self.database.setup()

	async def is_owner(self, user: discord.abc.User) -> bool:
		if user.id in OWNER_IDS:
			return True

		return await super().is_owner(user)

	async def get_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> str | None:
		async with self.database.connect(db_conn) as conn:
			async with conn.execute("SELECT value FROM bot_config WHERE key = ?", (key,)) as cursor:
				row = await cursor.fetchone()

		return None if row is None else row["value"]

	async def set_config(self, key: str, value: str, *, db_conn: aiosqlite.Connection | None = None):
		async with self.database.connect(db_conn) as conn:
			await conn.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value))
			await conn.commit()

	async def remove_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		async with self.database.connect(db_conn) as conn:
			async with conn.execute("DELETE FROM bot_config WHERE key = ?", (key,)) as cursor:
				row_count = cursor.rowcount
			await conn.commit()

		return True if row_count == 1 else False


class BotHelp(commands.HelpCommand):
	def get_command_signature(self, command: commands.Command):
		return "**%s%s**%s" % (
			self.context.clean_prefix,
			command.qualified_name,
			(f" {command.signature}" if command.signature else " [sub-command]" if isinstance(command, commands.Group) else ""),
		)

	async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]):
		embed = discord.Embed(
			color=COLORS.DEFAULT,
			title=f"{self.context.me.name}'s commands",
			description=f"-# For more information about a command you can run: `{self.context.clean_prefix}help [command-name]`",
		)

		for cog, cog_commands in mapping.items():
			filtered: list[commands.Command] = await self.filter_commands(cog_commands, sort=True)
			command_signatures = [f"{self.get_command_signature(c)}\n  - {c.help}" if c.help else self.get_command_signature(c) for c in filtered]

			if command_signatures:
				cog_header = f"\n### {cog.qualified_name}" if cog is not None else ""
				embed.description += cog_header + "".join([f"\n- {s}" for s in command_signatures])

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_command_help(self, command: commands.Command):
		embed = discord.Embed(color=COLORS.DEFAULT, title=f"{self.context.clean_prefix}{command.qualified_name} {command.signature}", description="")

		if len(command.aliases) > 0:
			embed.description += f"\n**Aliases**: {', '.join(command.aliases)}"

		if command.description or command.help:
			embed.description += f"\n\n{command.description or command.help}"

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_cog_help(self, cog: commands.Cog):
		embed = discord.Embed(color=COLORS.DEFAULT, title=getattr(cog, "qualified_name", "Cog"), description=getattr(cog, "description", ""))

		filtered: list[commands.Command] = await self.filter_commands(cog.get_commands(), sort=True)
		command_signatures = [f"{self.get_command_signature(c)}\n  - {c.help}" if c.help else self.get_command_signature(c) for c in filtered]

		if command_signatures:
			embed.description += "".join([f"\n- {s}" for s in command_signatures])

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_group_help(self, group: commands.Group):
		embed = discord.Embed(color=COLORS.DEFAULT, title=f"{group.qualified_name.capitalize()} sub-commands", description="")
		if len(group.aliases) > 0:
			embed.description += f"\n**Aliases**: {', '.join(group.aliases)}"
		if group.description or group.help:
			embed.description += f"\n\n{group.description or group.help}"

		filtered: list[commands.Command] = await self.filter_commands(group.commands, sort=True)
		command_signatures = [f"{self.get_command_signature(c)}\n  - {c.help}" if c.help else self.get_command_signature(c) for c in filtered]

		if command_signatures:
			embed.description += "".join([f"\n- {s}" for s in command_signatures])

		channel = self.get_destination()
		await channel.send(embed=embed)
