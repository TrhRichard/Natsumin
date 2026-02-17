from __future__ import annotations

from internal.functions import frmt_iter, get_user_id, get_legacy_rank
from internal.constants import FILE_LOGGING_FORMATTER, COLORS
from internal.contracts import sync_season
from internal.base.cog import NatsuminCog
from discord.ext import commands
from typing import TYPE_CHECKING
from discord import ui

import aiosqlite
import sqlite3
import discord
import logging
import json
import io
import re

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


class SQLOutputView(ui.DesignerView):
	def __init__(self, output: str | Exception):
		super().__init__(store=False)

		if isinstance(output, Exception):
			main_display = ui.TextDisplay(f"### {output.__class__.__name__}\n```{str(output)}```")
		else:
			main_display = ui.TextDisplay(f"```json\n{output}```")

		self.add_item(ui.Container(main_display, color=COLORS.ERROR if isinstance(output, Exception) else COLORS.DEFAULT))


CODEBLOCK_PATTERN = r"(?<!\\)(?P<start>```)(?<=```)(?:(?P<lang>[a-z][a-z0-9]*)\s)?(?P<content>.*?)(?<!\\)(?=```)(?P<end>(?:\\\\)*```)"


class OwnerExt(NatsuminCog, name="Owner", command_attrs=dict(hidden=True)):
	"""Owner-only commands"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.owner")
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/owner.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

	async def cog_check(self, ctx: commands.Context | discord.ApplicationContext):
		if await self.bot.is_owner(ctx.author):
			return True

		raise commands.NotOwner()

	@commands.command(aliases=["r"])
	async def reload(self, ctx: commands.Context, extension: str | None = None):
		if extension is not None:
			try:
				self.bot.reload_extension(extension)
			except (discord.ExtensionNotFound, discord.ExtensionNotLoaded):
				await ctx.reply(f"Extension {extension} not found.")
			except discord.ExtensionFailed as err:
				await ctx.reply(f"Failed to reload {extension}. For details check the terminal.")
				self.logger.error(f"Failed to reload {extension}", exc_info=err)
			else:
				await ctx.reply(f"Succesfully reloaded {extension}!", mention_author=False)
		else:
			failed_reloads = []

			for extension in list(self.bot.extensions.keys()):
				try:
					self.bot.reload_extension(extension)
				except discord.ExtensionFailed as err:
					failed_reloads.append(extension)
					self.logger.error(f"Failed to reload {extension}", exc_info=err)

			if failed_reloads:
				await ctx.reply(
					f"Failed to reload the following extensions: {frmt_iter(failed_reloads)}!\nFor details check the terminal.", mention_author=False
				)
			else:
				await ctx.reply("Succesfully reloaded all extensions!", mention_author=False)

	@commands.command(aliases=["rsc"])
	async def resync_slash_commands(self, ctx: commands.Context):
		await self.bot.sync_commands()
		await ctx.reply("Successfully synced bot application commands.", mention_author=False)

	@commands.group(name="config", invoke_without_command=True)
	async def config(self, ctx: commands.Context):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT key, value FROM bot_config LIMIT 25") as cursor:
				rows = await cursor.fetchall()

		embed = discord.Embed(description="", color=COLORS.DEFAULT)
		embed.set_author(name=f"{self.bot.user.name}'s configuration", icon_url=self.bot.user.display_avatar.url)

		embed.description = "\n".join(f"- **`{row['key']}`**: `{row['value']}`" for row in rows)

		await ctx.reply(embed=embed)

	@config.command(name="set")
	async def config_set(self, ctx: commands.Context, key: str, *, value: str):
		async with self.bot.database.connect() as conn:
			previous_value = await self.bot.get_config(key, db_conn=conn)
			await self.bot.set_config(key, value, db_conn=conn)

		if previous_value is None:
			await ctx.reply(f"Set **`{key}`** to `{value}`")
		else:
			await ctx.reply(f"Updated **`{key}`** from `{previous_value}` to `{value}`")

	@config.command(name="get")
	async def config_get(self, ctx: commands.Context, key: str):
		current_value = await self.bot.get_config(key)

		if current_value:
			await ctx.reply(f"`{current_value}`")
		else:
			await ctx.reply(f"Key **`{key}`** not found in config!")

	@config.command(name="delete", aliases=["del", "remove"])
	async def config_delete(self, ctx: commands.Context, key: str):
		removed_succesfully = await self.bot.remove_config(key)

		if removed_succesfully:
			await ctx.reply(f"Deleted **`{key}`** from the config")
		else:
			await ctx.reply(f"Key **`{key}`** not found in config!")

	@commands.group(name="whitelist", invoke_without_command=True)
	async def whitelist(self, ctx: commands.Context):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT guild_id, channel_id FROM whitelist_channel LIMIT 25") as cursor:
				rows = await cursor.fetchall()

		per_guild_channels: dict[int, list[int]] = {}
		for row in rows:
			per_guild_channels.setdefault(row["guild_id"], []).append(row["channel_id"])

		embed = discord.Embed(description="", color=COLORS.DEFAULT)
		embed.set_author(name=f"{self.bot.user.name}'s whitelisted channels", icon_url=self.bot.user.display_avatar.url)

		for guild_id, channel_ids in per_guild_channels.items():
			guild = await self.bot.get_or_fetch(discord.Guild, guild_id)

			embed.add_field(name=str(guild.name if guild else guild_id), value=frmt_iter(f"<#{c}>" for c in channel_ids), inline=False)

		await ctx.reply(embed=embed)

	@whitelist.command(name="add")
	async def whitelist_add(self, ctx: commands.Context, channel: discord.abc.GuildChannel):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT COUNT(*) as count FROM whitelist_channel WHERE guild_id = ?", (channel.guild.id,)) as cursor:
				server_had_whitelist = (await cursor.fetchone())["count"] == 0

			await conn.execute("INSERT OR IGNORE INTO whitelist_channel (guild_id, channel_id) VALUES (?, ?)", (channel.guild.id, channel.id))
			await conn.commit()

		if not server_had_whitelist:
			await ctx.reply(f"Added {channel.mention} as a whitelisted channel in **{channel.guild.name}**")
		else:
			await ctx.reply(f"Added {channel.mention} as a whitelisted channel in **{channel.guild.name}**, the server is now in whitelist mode!")

	@whitelist.command(name="remove")
	async def whitelist_remove(self, ctx: commands.Context, channel: discord.abc.GuildChannel):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT COUNT(*) as count FROM whitelist_channel WHERE guild_id = ?", (channel.guild.id,)) as cursor:
				server_had_whitelist = (await cursor.fetchone())["count"] - 1 == 0

			await conn.execute("DELETE FROM whitelist_channel WHERE guild_id = ? AND channel_id = ?", (channel.guild.id, channel.id))
			await conn.commit()

		if not server_had_whitelist:
			await ctx.reply(f"Removed {channel.mention} as a whitelisted channel in **{channel.guild.name}**")
		else:
			await ctx.reply(
				f"Removed {channel.mention} as a whitelisted channel in **{channel.guild.name}**, the server is no longer in whitelist mode!"
			)

	@commands.group(name="blacklist", invoke_without_command=True)
	async def blacklist(self, ctx: commands.Context):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT discord_id, reason FROM blacklist_user LIMIT 25") as cursor:
				rows: dict[int, str | None] = {row["discord_id"]: row["reason"] for row in await cursor.fetchall()}

		embed = discord.Embed(description="", color=COLORS.DEFAULT)
		embed.set_author(name=f"{self.bot.user.name}'s blacklisted users", icon_url=self.bot.user.display_avatar.url)

		for discord_id, reason in rows.items():
			embed.description += f"<@{discord_id}>{f' - `{reason}`' if reason else ''}\n"

		await ctx.reply(embed=embed)

	@blacklist.command(name="add")
	async def blacklist_add(self, ctx: commands.Context, user: discord.User, *, reason: str = None):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT 1 FROM blacklist_user WHERE discord_id = ?", (user.id,)) as cursor:
				is_user_already_blacklisted = (await cursor.fetchone()) is not None

			if not is_user_already_blacklisted:
				await conn.execute("INSERT OR IGNORE INTO blacklist_user (discord_id, reason) VALUES (?, ?)", (user.id, reason))
				await conn.commit()

		if not is_user_already_blacklisted:
			await ctx.reply(f"Added {user.mention} to the blacklist{f' with the reason: `{reason}`' if reason else ''}!")
		else:
			await ctx.reply(f"{user.mention} is already blacklisted{f' for `{reason}`' if reason else ''}!")

	@blacklist.command(name="remove")
	async def blacklist_remove(self, ctx: commands.Context, user: discord.User):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT 1 FROM blacklist_user WHERE discord_id = ?", (user.id,)) as cursor:
				is_user_already_blacklisted = (await cursor.fetchone()) is not None

			await conn.execute("DELETE FROM blacklist_user WHERE discord_id = ?", (user.id,))
			await conn.commit()

		if is_user_already_blacklisted:
			await ctx.reply(f"Removed {user.mention} from the blacklist.")
		else:
			await ctx.reply(f"{user.mention} was not blacklisted!")

	@commands.command(aliases=["sui", "seasonuserinfo"])
	async def season_user_info(self, ctx: commands.Context, id_or_username: str | discord.abc.User = None, season_id: str = None):
		id_or_username = id_or_username or ctx.author.name

		async with self.bot.database.connect() as conn:
			user_id, _ = await self.bot.fetch_user_from_database(id_or_username, invoker=ctx.author, season_id=season_id, db_conn=conn)

			if user_id is None:
				return await ctx.reply("no user")

			active_season = await self.bot.get_config("contracts.active_season", db_conn=conn)
			season_id = season_id or active_season
			if season_id is None or season_id not in self.bot.database.available_seasons:
				return await ctx.reply("invalid season")

			async with conn.execute(
				"SELECT u.username, u.discord_id, su.* FROM season_user su LEFT JOIN user u ON su.user_id = u.id  WHERE season_id = ? AND user_id = ?",
				(season_id, user_id),
			) as cursor:
				user_row = await cursor.fetchone()

			if user_row is None:
				return await ctx.reply(f"user not in {season_id}")

			async with conn.execute("SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ?", (season_id, user_id)) as cursor:
				rows = await cursor.fetchall()

			json_data = json.dumps(dict(user_row) | {"contracts": list(dict(row) for row in rows)}, indent=4)

			if len(json_data) < 1900:
				await ctx.reply(f"```json\n{json_data}\n```")
			else:
				json_file = discord.File(io.BytesIO(json_data.encode("utf-8")), f"{season_id}-{user_id}.json")
				await ctx.reply(file=json_file)

	@commands.command(aliases=["ui", "userinfo", "mui", "masteruserinfo"])
	async def user_info(self, ctx: commands.Context, id_or_username: str | discord.abc.User = None):
		id_or_username = id_or_username or ctx.author.name

		async with self.bot.database.connect() as conn:
			user_id, _ = await self.bot.fetch_user_from_database(id_or_username, invoker=ctx.author, db_conn=conn)

			if user_id is None:
				return await ctx.reply("no user")

			async with conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)) as cursor:
				user_row = await cursor.fetchone()

			async with conn.execute("SELECT b.* FROM user_badge ub JOIN badge b ON ub.badge_id = b.id WHERE ub.user_id = ?", (user_id,)) as cursor:
				badge_rows = await cursor.fetchall()

			async with conn.execute("SELECT exp FROM leaderboard_legacy WHERE user_id = ?", (user_id,)) as cursor:
				legacy_row = await cursor.fetchone()

			leaderboards: dict[str, int] = {
				"legacy": {"rank": get_legacy_rank(legacy_row["exp"]).value, "exp": legacy_row["exp"]} if legacy_row is not None else None,
				"new": None,
			}

			json_data = json.dumps(dict(user_row) | {"leaderboards": leaderboards, "badges": list(dict(row) for row in badge_rows)}, indent=4)

			if len(json_data) < 1900:
				await ctx.reply(f"```json\n{json_data}\n```")
			else:
				json_file = discord.File(io.BytesIO(json_data.encode("utf-8")), f"{user_id}.json")
				await ctx.reply(file=json_file)

	@commands.command(hidden=True, aliases=["bi", "badgeinfo"])
	async def badge_info(self, ctx: commands.Context, id_or_name: str):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT * FROM badge WHERE id = ? OR LOWER(name) = ?", (id_or_name, id_or_name.lower())) as cursor:
				badge_row = await cursor.fetchone()

			if badge_row is None:
				return await ctx.reply("no badge")

			json_data = json.dumps(dict(badge_row), indent=4)

			if len(json_data) < 1900:
				await ctx.reply(f"```json\n{json_data}\n```")
			else:
				json_file = discord.File(io.BytesIO(json_data.encode("utf-8")), f"{badge_row['id']}.json")
				await ctx.reply(file=json_file)

	@commands.command(aliases=["addalias"])
	async def setalias(self, ctx: commands.Context, id_or_username: str, alias: str):
		async with self.bot.database.connect() as conn:
			user_id, _ = await self.bot.fetch_user_from_database(id_or_username, invoker=ctx.author, db_conn=conn)

			if user_id is None:
				return await ctx.reply("no user")

			async with conn.execute("SELECT username, id FROM user WHERE id = ?", (user_id,)) as cursor:
				user_row = await cursor.fetchone()

			await conn.execute("INSERT OR IGNORE INTO user_alias (username, user_id) VALUES (?, ?)", (alias, user_id))
			await conn.commit()

		await ctx.reply(f"Succesfully added alias `{alias}` to {user_row['username']} ({user_row['id']})")

	@commands.command(aliases=["deletealias"])
	async def removealias(self, ctx: commands.Context, alias: str):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT 1 FROM user_alias WHERE username = ?", (alias,)) as cursor:
				row = await cursor.fetchone()

			if row is None:
				return await ctx.reply("Alias not found.")

			await conn.execute("DELETE FROM user_alias WHERE username = ?", (alias,))
			await conn.commit()

		await ctx.reply(f"Removed alias `{alias}`")

	@commands.command()
	async def getaliases(self, ctx: commands.Context, id_or_username: str = None):
		async with self.bot.database.connect() as conn:
			if id_or_username is None:
				async with conn.execute("SELECT * FROM user_alias") as cursor:
					user_aliases: tuple[(str, str), ...] = [(row["username"], row["user_id"]) for row in await cursor.fetchall()]
			else:
				user_id, _ = await self.bot.fetch_user_from_database(id_or_username, invoker=ctx.author, db_conn=conn)
				if user_id is None:
					return await ctx.reply("no user")

				async with conn.execute("SELECT * FROM user_alias WHERE user_id = ?", (user_id,)) as cursor:
					user_aliases: tuple[(str, str), ...] = [(row["username"], row["user_id"]) for row in await cursor.fetchall()]

			if not user_aliases:
				return await ctx.reply("No aliases found.")

			await ctx.reply(
				f"Aliases: {', '.join([f'`{alias}` ({u_id})' if id_or_username is None else f'`{alias}`' for alias, u_id in user_aliases])}"
			)

	@commands.command()
	async def sync_season(self, ctx: commands.Context, *, season: str | None = None):
		async with self.bot.database.connect() as conn:
			if season is None:
				season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			else:
				season_id = season

			if season_id not in self.bot.database.available_seasons:
				return await ctx.reply(f"Could not find season with the id **{season_id}**.")

			async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]

		async with ctx.typing():
			try:
				duration = await sync_season(self.bot.database, season_id)
				self.logger.info(f"{season_id} has been manually synced by {ctx.author.name} in {duration:.2f} seconds.")
				await ctx.reply(
					embed=discord.Embed(description=f"✅ **{season_name}** has been synced in {duration:.2f} seconds!", color=COLORS.DEFAULT)
				)
			except Exception as e:
				self.logger.error(f"Manual sync of {season_id} invoked by {ctx.author.name} failed.", exc_info=e)
				await ctx.reply(embed=discord.Embed(description=f"❌ Failed to sync **{season_name}**:\n```{e}```", color=COLORS.ERROR))

	@commands.command()
	async def sql(self, ctx: commands.Context, *, query: str):
		codeblock_match = re.match(CODEBLOCK_PATTERN, query, re.DOTALL)
		if not codeblock_match:
			return await ctx.reply("Queries must be inside codeblocks, like:\n```sql\nSELECT * FROM user LIMIT 1\n```")

		query = codeblock_match.group("content").strip()
		async with self.bot.database.connect() as conn:
			try:
				statements = [s.strip() for s in query.split(";") if s.strip()]
				rows = []

				for i, statement in enumerate(statements, start=1):
					async with conn.execute(statement) as cursor:
						if i == len(statements):
							rows = await cursor.fetchall()

				await conn.commit()
			except (aiosqlite.Error, sqlite3.Error) as err:
				await conn.rollback()
				return await ctx.reply(view=SQLOutputView(err))

		formatted_rows = (dict(row) for row in rows)
		str_output = json.dumps(list(formatted_rows), indent=4)

		if len(str_output) < 1900:
			await ctx.reply(view=SQLOutputView(str_output))
		else:
			file = discord.File(io.BytesIO(str_output.encode("utf-8")), filename="result.json")
			await ctx.reply("", file=file)

	@commands.command()  # temporary
	async def cleanup_media(self, ctx: commands.Context, media_type: str = "anilist"):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT type, id, description FROM media WHERE type = ?", (media_type,)) as cursor:
				rows = await cursor.fetchall()

			for row in rows:
				description: str = row["description"]
				if not description:
					continue

				new_desc = description.replace("<br>", "").replace("<i>", "*").replace("</i>", "*").replace("<b>", "**").replace("</b>", "**")
				new_desc = new_desc.replace("<BR>", "")
				new_desc = new_desc.strip()

				await conn.execute("UPDATE media SET description = ? WHERE type = ? AND id = ?", (new_desc, row["type"], row["id"]))

			await conn.commit()
			await ctx.reply(f"Cleaned up {len(rows)} rows!")


def setup(bot: NatsuminBot):
	bot.add_cog(OwnerExt(bot))
