from __future__ import annotations

from config import BOT_PREFIX, EDITOR_IDS, OWNER_IDS, IS_PRODUCTION, DISABLED_EXTENSIONS
from internal.constants import FILE_LOGGING_FORMATTER, CONSOLE_LOGGING_FORMATTER, COLORS
from internal.base.context import NatsuAutoContext, NatsuAppContext, NatsuContext
from internal.exceptions import BlacklistedUser, NotWhitelistedChannel
from internal.contracts.rep import get_rep_from_member, RepName
from internal.functions import get_user_id, get_user_config
from internal.database.reminder import ReminderDatabase
from internal.contracts.order import OrderCategory
from internal.database import NatsuDatabase
from typing import TYPE_CHECKING, Literal
from discord.ext import commands
from pathlib import Path
from uuid import uuid4

import aiosqlite
import aiofiles
import datetime
import discord
import logging
import json
import os
import re

if TYPE_CHECKING:
	from collections.abc import Mapping


class NatsuBot(commands.Bot):
	def __init__(self, production: bool = False):
		super().__init__(
			command_prefix=BOT_PREFIX,
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
			status=discord.Status.online,
			intents=discord.Intents.all(),
			case_insensitive=True,
			help_command=BotHelp(),
		)

		self.is_production = IS_PRODUCTION
		self.started_at = datetime.datetime.now(datetime.UTC)
		self.color = COLORS.DEFAULT
		self.database = NatsuDatabase()
		self.reminders = ReminderDatabase()
		self.anicord: discord.Guild | None = None
		self.season_orders: dict[str, list[OrderCategory]] = {}

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
		os.system("cls" if os.name == "nt" else "clear")  # noqa: ASYNC221
		self.logger.info(f"Logged in as {self.user.name}#{self.user.discriminator}!")
		await self.database.setup()
		await self.reminders.setup()
		self.anicord = self.get_guild(994071728017899600)
		async with self.database.connect() as conn:
			async with conn.execute("SELECT id FROM season") as cursor:
				season_ids: list[str] = [row["id"] for row in await cursor.fetchall()]

			for season_id in season_ids:
				order_path = Path(f"assets/orders/{season_id}.json")
				if order_path.is_file():
					async with aiofiles.open(order_path, "r") as f:
						self.season_orders[season_id] = json.loads(await f.read())

		self.add_check(self.user_blacklist_check)

	async def user_blacklist_check(self, ctx: NatsuContext):
		is_blacklisted, _ = await self.is_blacklisted(ctx, raise_exception=True, ignore_channel=True)
		return not is_blacklisted

	async def on_user_update(self, old: discord.User, new: discord.User):
		if old.name == new.name:
			return

		async with self.database.connect() as conn:
			user_id = await get_user_id(conn, old.name)

			if not user_id:
				return

			user_config = await get_user_config(conn, user_id)

			await conn.execute("UPDATE user SET username = ? WHERE id = ?", (new.name, user_id))
			if user_config.track_username_history:
				await conn.execute("INSERT OR IGNORE INTO user_alias (username, user_id) VALUES (?, ?)", (old.name, user_id))

			await conn.commit()

	async def is_owner(self, user: discord.abc.User) -> bool:
		if user.id in OWNER_IDS:
			return True

		return await super().is_owner(user)

	async def is_editor(self, user: discord.abc.User) -> bool:
		return bool(user.id in EDITOR_IDS or user.id in OWNER_IDS)

	async def get_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> str | None:  # Shortcut
		return await self.database.get_config(key, db_conn=db_conn)

	async def set_config(self, key: str, value: str, *, db_conn: aiosqlite.Connection | None = None):  # Shortcut
		return await self.database.set_config(key, value, db_conn=db_conn)

	async def remove_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:  # Shortcut
		return await self.database.remove_config(key, db_conn=db_conn)

	async def ensure_user(self, user: discord.abc.User | int, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		"""Ensures that a discord user is in the database, returns `True` if just created"""

		if isinstance(user, int):
			user_id = user
			if self.anicord:
				user: discord.Member | None = await self.anicord.get_or_fetch(discord.Member, user_id)
				if user is None:
					user: discord.User = await self.get_or_fetch(discord.User, user_id)
			else:
				user: discord.User = await self.get_or_fetch(discord.User, user_id)

		async with self.database.connect(db_conn) as conn:
			async with conn.execute("SELECT 1 FROM user WHERE discord_id = ? OR username = ?", (user.id, user.name)) as cursor:
				row = await cursor.fetchone()
				if row is not None:
					return False

			user_rep = RepName.UNKNOWN
			if isinstance(user, discord.Member):
				user_rep = get_rep_from_member(user)

			await conn.execute("INSERT INTO user (id, discord_id, username, rep) VALUES (?, ?, ?, ?)", (uuid4(), user.id, user.name, user_rep.value))
			await conn.commit()
			return True

	async def is_blacklisted(
		self, ctx: NatsuContext | NatsuAppContext | discord.abc.User, *, raise_exception: bool = False, ignore_channel: bool = False
	) -> tuple[bool, str | None]:
		if isinstance(ctx, (NatsuContext, NatsuAppContext)):
			if await self.is_owner(ctx.author):
				return False, None
		else:
			if await self.is_owner(ctx):
				return False, None

		async with self.database.connect() as conn:
			if isinstance(ctx, (NatsuContext, NatsuAppContext)):
				discord_id = ctx.author.id

				if ctx.guild is not None and not ignore_channel:
					if isinstance(ctx.channel, discord.PartialMessageable):
						return False, None

					author_perms = ctx.channel.permissions_for(ctx.author)
					if author_perms and author_perms.administrator:
						return False, None

					async with conn.execute("SELECT channel_id FROM whitelist_channel WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
						rows = await cursor.fetchall()

						if rows:
							valid_channel_ids: list[int] = [row["channel_id"] for row in rows]

							if ctx.channel.id not in valid_channel_ids:
								if raise_exception:
									raise NotWhitelistedChannel(valid_channel_ids)
								else:
									return True, None
			else:
				discord_id = ctx.id

			async with conn.execute("SELECT reason FROM blacklist_user WHERE discord_id = ?", (discord_id,)) as cursor:
				row = await cursor.fetchone()

				if row is not None:
					if raise_exception:
						raise BlacklistedUser(row["reason"])
					else:
						return True, row["reason"]

			return False, None

	async def fetch_user_from_database(
		self,
		user: str | int | discord.abc.User,
		*,
		invoker: discord.abc.User | None = None,
		season_id: str | None = None,
		db_conn: aiosqlite.Connection = None,
	) -> tuple[str | None, discord.abc.User | None]:
		discord_user: discord.Member = None

		special_tag: str | None = None

		if isinstance(user, (str, int)):
			discord_id = None
			if isinstance(user, int):
				discord_id = user
			elif match := re.match(r"<@!?(\d+)>", user):
				discord_id = int(match.group(1))
			elif match := re.match(r"(\w+)\[(\w+)]", user):
				user = match.group(1)
				special_tag = match.group(2)
			elif (match := re.match(r"\[(\w+)]", user)) and invoker is not None:
				user = invoker.name
				special_tag = match.group(1)
			elif user.isdigit():
				discord_id = int(user)

			if self.anicord and discord_id:
				discord_user = await self.anicord.get_or_fetch(discord.Member, discord_id)

			if not discord_user and discord_id:
				discord_user = await self.get_or_fetch(discord.User, discord_id)  # lol

			if discord_user:
				user = discord_user.name
		elif isinstance(user, discord.abc.User):
			discord_user = user
			user = discord_user.name

		async with self.database.connect(db_conn) as conn:
			user_id = await get_user_id(conn, user, score_cutoff=90)

			if user_id is None:
				return None, None

			if special_tag is not None and season_id is not None:
				match special_tag:
					case "contractee":
						query = """
							SELECT 
								su.user_id AS contractee_id 
							FROM season_user su 
							JOIN user u ON su.user_id = u.id 
							WHERE 
								su.season_id = ? 
								AND su.contractor_id = ? 
							ORDER BY u.username
							LIMIT 1
						"""
						async with conn.execute(query, (season_id, user_id)) as cursor:
							row = await cursor.fetchone()
							if row is None:
								return None, None
							user_id = row["contractee_id"]
					case "contractor":
						async with conn.execute(
							"SELECT contractor_id FROM season_user WHERE season_id = ? AND user_id = ?", (season_id, user_id)
						) as cursor:
							row = await cursor.fetchone()
							if row is None:
								return None, None
							user_id = row["contractor_id"]
					case _:
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

	async def get_context(self, message, *, cls=NatsuContext):
		ctx: NatsuContext = await super().get_context(message, cls=cls)
		ctx.database = self.database
		return ctx

	async def get_application_context(self, interaction, cls=NatsuAppContext):
		ctx: NatsuAppContext = await super().get_application_context(interaction, cls=cls)
		ctx.database = self.database
		return ctx

	async def get_autocomplete_context(self, interaction, cls=NatsuAutoContext):
		ctx: NatsuAutoContext = await super().get_autocomplete_context(interaction, cls=cls)
		ctx.database = self.database
		return ctx


def get_command_signature(cmd: commands.Command):
	"""Returns a POSIX-like signature useful for help command output.

	So I had to overwrite this entire thing just to get flags to show up properly
	-Richard
	"""
	from typing import Union

	if cmd.usage is not None:
		return cmd.usage

	params = cmd.clean_params
	if not params:
		return ""

	result = []
	for name, param in params.items():
		greedy = isinstance(param.annotation, commands.Greedy)
		optional = False  # postpone evaluation of if it's an optional argument

		# for typing.Literal[...], typing.Optional[typing.Literal[...]], and Greedy[typing.Literal[...]], the
		# parameter signature is a literal list of it's values
		annotation = param.annotation.converter if greedy else param.annotation
		origin = getattr(annotation, "__origin__", None)
		if not greedy and origin is Union:
			none_cls = type(None)
			union_args = annotation.__args__
			optional = union_args[-1] is none_cls
			if len(union_args) == 2 and optional:
				annotation = union_args[0]
				origin = getattr(annotation, "__origin__", None)

		if origin is Literal:
			name = " | ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in annotation.__args__)
		if param.default is not param.empty:
			# We don't want None or '' to trigger the [name=value] case, and instead it should
			# do [name] since [name=None] or [name=] are not exactly useful for the user.
			should_print = param.default if isinstance(param.default, str) else param.default is not None
			if should_print:
				result.append(f"[{name}={param.default}]" if not greedy else f"[{name}={param.default}]...")
				continue
			else:
				result.append(f"[{name}]")
		elif param.kind == param.VAR_POSITIONAL:
			if cmd.require_var_positional:
				result.append(f"<{name}...>")
			else:
				result.append(f"[{name}...]")
		elif greedy:
			result.append(f"[{name}]...")
		elif optional:
			result.append(f"[{name}]")
		elif issubclass(annotation, commands.FlagConverter):
			flags: commands.FlagConverter = annotation
			pairs = []
			positional_flag: commands.Flag | None = None
			positional_pair: str | None = None
			for flag in flags.get_flags().values():
				value: str = ""
				try:
					value = f"{getattr(flags, flag.attribute)!r}"
				except AttributeError:
					if flag.default is not discord.utils.MISSING:
						value = f"{flag.default!r}"

				should_print = (
					flag.default if isinstance(flag.default, str) else flag.default is not None
				) and flag.default is not discord.utils.MISSING
				if should_print:
					formatted_flag = f"{flag.attribute}={value}"
				else:
					formatted_flag = flag.attribute

				if flag.positional:
					positional_flag = flag
					positional_pair = formatted_flag
				else:
					pairs.append(f"--{formatted_flag}")

			if positional_pair is not None:
				if positional_flag.default is discord.utils.MISSING:
					pos_pair = f"<{positional_pair}>"
				else:
					pos_pair = f"[{positional_pair}]"

				result.append(f"{pos_pair} {' '.join(pairs)}")
			else:
				result.append(f"{' '.join(pairs)}>")
		else:
			result.append(f"<{name}>")

	return " ".join(result)


class BotHelp(commands.HelpCommand):
	def get_command_signature(self, command: commands.Command):
		signature = f"**{self.context.clean_prefix}{command.qualified_name}**"
		if isinstance(command, commands.Group):
			signature += " [sub-command]"
			if command.invoke_without_command:
				cmd_signature = get_command_signature(command)
				if cmd_signature:
					signature += f" **or** {get_command_signature(command)}"
		elif command.signature:
			signature += f" {get_command_signature(command)}"

		return signature

	async def send_bot_help(self, mapping: Mapping[commands.Cog | None, list[commands.Command]]):
		embed = discord.Embed(
			color=COLORS.DEFAULT,
			title=f"{self.context.me.name}'s commands",
			description=f"-# For more information about a command you can run: `{self.context.clean_prefix}help [command-name]`\n"
			+ f"-# For commands that have arguments that start with -- the following syntax is used: `{self.context.clean_prefix}contractinfo Base Contract --user=madfigs --season=season_x`",
		)

		category_signatures: dict[str, list[str]] = {}

		for cog, cog_commands in mapping.items():
			filtered_commands: list[commands.Command] = await self.filter_commands(cog_commands, sort=True)

			cog_name = cog.qualified_name if cog is not None else "Other"
			signatures = [f"{self.get_command_signature(c)}\n  - {c.help}" if c.help else self.get_command_signature(c) for c in filtered_commands]
			if signatures:
				category_signatures.setdefault(cog_name, []).extend(signatures)

		for cat_name, cat_signatures in category_signatures.items():
			if cat_name == "Other":
				continue
			embed.description += f"\n### {cat_name}\n{'\n'.join(f'- {s}' for s in cat_signatures)}"

		if other_signatures := category_signatures.get("Other"):
			embed.description += f"\n### Other\n{'\n'.join(f'- {s}' for s in other_signatures)}"

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_command_help(self, command: commands.Command):
		embed = discord.Embed(
			color=COLORS.DEFAULT, title=f"{self.context.clean_prefix}{command.qualified_name} {get_command_signature(command)}", description=""
		)

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
