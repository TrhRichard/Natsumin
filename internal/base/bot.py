from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER, CONSOLE_LOGGING_FORMATTER, COLORS
from config import BOT_PREFIX, DEV_BOT_PREFIX, OWNER_IDS, DISABLED_EXTENSIONS
from internal.database import NatsuminDatabase
from internal.functions import get_user_id
from discord.ext import commands
from typing import TYPE_CHECKING
from pathlib import Path
import aiosqlite

import datetime
import discord
import logging
import os
import re

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
		self.anicord: discord.Guild | None = None

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
		self.anicord = self.get_guild(994071728017899600)

	async def on_user_update(self, old: discord.User, new: discord.User):
		if old.name == new.name:
			return

		async with self.database.connect() as conn:
			user_id = await get_user_id(conn, old.name)

			if not user_id:
				return

			await conn.execute("UPDATE user SET username = ? WHERE id = ?", (new.name, user_id))
			await conn.execute("INSERT OR IGNORE INTO user_alias (username, user_id) VALUES (?, ?)", (old.name, user_id))
			await conn.commit()

	async def is_owner(self, user: discord.abc.User) -> bool:
		if user.id in OWNER_IDS:
			return True

		return await super().is_owner(user)

	async def get_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> str | None:  # Shortcut
		return await self.database.get_config(key, db_conn=db_conn)

	async def set_config(self, key: str, value: str, *, db_conn: aiosqlite.Connection | None = None):  # Shortcut
		return await self.database.set_config(key, value, db_conn=db_conn)

	async def remove_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:  # Shortcut
		return await self.database.remove_config(key, db_conn=db_conn)

	async def fetch_user_from_database(
		self, user: str | int | discord.abc.User, *, db_conn: aiosqlite.Connection = None
	) -> tuple[str | None, discord.abc.User | None]:
		discord_user: discord.Member = None

		if isinstance(user, (str, int)):
			if isinstance(user, int):
				discord_id = user
			elif match := re.match(r"<@!?(\d+)>", user):
				discord_id = int(match.group(1))
			elif user.isdigit():
				discord_id = int(user)
			else:
				discord_id = None

			if self.anicord and discord_id:
				discord_user = await self.anicord.get_or_fetch(discord.Member, discord_id)

			if not discord_user and discord_id:
				discord_user = await self.get_or_fetch(discord.User, discord_id)  # lol

			if discord_user:
				user = discord_user.name
		elif isinstance(user, (discord.User, discord.Member, discord.abc.User)):
			discord_user = user
			user = discord_user.name

		async with self.database.connect(db_conn) as conn:
			user_id = await get_user_id(conn, user, score_cutoff=90)

			if user_id is None:
				return None, None

			if discord_user is None:
				async with conn.execute("SELECT discord_id FROM user WHERE id = ?", (user_id,)) as cursor:
					row = await cursor.fetchone()
					user_discord_id: int | None = row["discord_id"] if row is not None else None

				if user_discord_id is not None and self.anicord:
					discord_user = await self.anicord.get_or_fetch(discord.Member, user_discord_id)

				if discord_user is None and user_discord_id:
					discord_user = await self.get_or_fetch(discord.User, user_discord_id)

		return user_id, discord_user


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
