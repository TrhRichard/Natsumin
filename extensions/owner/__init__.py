from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER, COLORS
from internal.functions import frmt_iter, get_user_id
from internal.base.cog import NatsuminCog
from discord.ext import commands
from typing import TYPE_CHECKING

import discord
import logging
import json
import io

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


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
		embed.set_author(name=f"{self.bot.user.name}'s configuration", icon_url=self.bot.user.avatar.url)

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

	@commands.command(aliases=["sui", "seasonuserinfo"])
	async def season_user_info(self, ctx: commands.Context, id_or_username: str | discord.abc.User = None, season_id: str = None):
		id_or_username = id_or_username or ctx.author.name
		if isinstance(id_or_username, discord.abc.User):
			id_or_username = id_or_username.name

		async with self.bot.database.connect() as conn:
			user_id = await get_user_id(conn, id_or_username)

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
		if isinstance(id_or_username, discord.abc.User):
			id_or_username = id_or_username.name

		async with self.bot.database.connect() as conn:
			user_id = await get_user_id(conn, id_or_username)

			if user_id is None:
				return await ctx.reply("no user")

			async with conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)) as cursor:
				user_row = await cursor.fetchone()

			async with conn.execute("SELECT b.* FROM user_badge ub JOIN badge b ON ub.badge_id = b.id WHERE ub.user_id = ?", (user_id,)) as cursor:
				badge_rows = await cursor.fetchall()

			json_data = json.dumps(dict(user_row) | {"badges": list(dict(row) for row in badge_rows)}, indent=4)

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
			user_id = await get_user_id(conn, id_or_username)

			if user_id is None:
				return await ctx.reply("no user")

			async with conn.execute("SELECT username, id FROM user WHERE id = ?", (user_id,)) as cursor:
				user_row = await cursor.fetchone()

			await conn.execute("INSERT OR IGNORE INTO user_alias (username, user_id) VALUES (?, ?)", (alias, user_id))
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
				user_id = await get_user_id(conn, id_or_username)
				if user_id is None:
					return await ctx.reply("no user")

				async with conn.execute("SELECT * FROM user_alias WHERE user_id = ?", (user_id,)) as cursor:
					user_aliases: tuple[(str, str), ...] = [(row["username"], row["user_id"]) for row in await cursor.fetchall()]

			if not user_aliases:
				return await ctx.reply("No aliases found.")

			await ctx.reply(
				f"Aliases: {', '.join([f'`{alias}` ({u_id})' if id_or_username is None else f'`{alias}`' for alias, u_id in user_aliases])}"
			)


def setup(bot: NatsuminBot):
	bot.add_cog(OwnerExt(bot))
