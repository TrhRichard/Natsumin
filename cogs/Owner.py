from utils import FILE_LOGGING_FORMATTER, config
from discord.ext import commands
from typing import TYPE_CHECKING
from common import get_master_db
from discord import ui
import contracts
import aiosqlite
import logging
import discord
import json
import io
import gc
import re

if TYPE_CHECKING:
	from main import Natsumin

DATABASE_PATHS = {"master": "data/master.db", "winter_2025": "data/seasons/Winter2025.db", "season_x": "data/seasons/SeasonX.db"}
CODEBLOCK_PATTERN = r"(?<!\\)(?P<start>```)(?<=```)(?:(?P<lang>[a-z][a-z0-9]*)\s)?(?P<content>.*?)(?<!\\)(?=```)(?P<end>(?:\\\\)*```)"


class SQLOutputView(ui.DesignerView):
	def __init__(self, output: str | Exception):
		super().__init__(store=False)

		if isinstance(output, Exception):
			main_display = ui.TextDisplay(f"### {output.__class__.__name__}\n```{str(output)}```")
		else:
			main_display = ui.TextDisplay(f"```json\n{output}```")

		self.add_item(ui.Container(main_display, color=discord.Color.red() if isinstance(output, Exception) else config.base_embed_color))


class SQLQueryFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	query: str = commands.flag(positional=True, aliases=["q"])
	database: str = commands.flag(aliases=["db", "d"], default=config.active_season.replace(" ", "_"))
	row_factory: bool = commands.flag(aliases=["rf", "dict"], default=True)


class Owner(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.owner")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/owner.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.setLevel(logging.INFO)

	@commands.command(hidden=True)
	@commands.is_owner()
	async def sync_season(self, ctx: commands.Context, *, season: str = config.active_season):
		async with ctx.typing():
			try:
				duration = await contracts.sync_season_db(season)
				self.logger.info(f"{season} has been manually synced by {ctx.author.name} in {duration:.2f} seconds")
				await ctx.reply(
					embed=discord.Embed(description=f"✅ **{season}** has been synced in {duration:.2f} seconds!", color=config.base_embed_color)
				)
			except Exception as e:
				self.logger.error(f"Failed to sync season '{season}' manually by {ctx.author.name}: {e}")
				await ctx.reply(embed=discord.Embed(description=f"❌ Failed to sync **{season}**:\n```{e}```", color=discord.Color.red()))

	@commands.command(hidden=True)
	@commands.is_owner()
	async def delete_message(self, ctx: commands.Context, message_id: int, channel_id: int = None):
		message = self.bot.get_message(message_id)
		if not message:
			if channel_id is None:
				await ctx.reply("Channel ID argument required for uncached message!", delete_after=3)
				return
			message_channel = self.bot.get_channel(channel_id)
			if not message_channel:
				message_channel = await self.bot.fetch_channel(channel_id)
			message = await message_channel.fetch_message(message_id)

		if message is None:
			await ctx.reply("Could not find the message you requested!", delete_after=3)
			return

		if message.author.id != self.bot.user.id:
			await ctx.reply("This command can only be used to delete the bot's messages!", delete_after=3)
			return

		await message.delete()
		await ctx.reply("Message deleted!", delete_after=3)

	@commands.command(hidden=True, aliases=["season_json"])
	@commands.is_owner()
	async def get_season_file(self, ctx: commands.Context, season: str = config.active_season):
		try:
			season_db = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.reply(embed=discord.Embed(description=f"❌ {e}", color=discord.Color.red()), mention_author=False)

		async with ctx.typing():
			async with season_db.connect() as conn:
				async with conn.execute("SELECT * FROM users") as cursor:
					all_users = [contracts.SeasonUser(**row, _db=season_db) for row in await cursor.fetchall()]

				users_json = [await user.to_dict(include_contracts=True) for user in all_users]

				discord_file = discord.File(io.BytesIO(json.dumps({"users": users_json}, indent=4).encode("utf-8")))
				discord_file.filename = f"{season}.json"

		await ctx.reply(f"Here is {season} data:", file=discord_file)

	@commands.command(hidden=True, aliases=["r", "reload"])
	@commands.is_owner()
	async def reload_cogs(self, ctx: commands.Context):
		failed_cogs = []
		for cog in list(self.bot.extensions.keys()):
			try:
				self.bot.reload_extension(cog)
			except Exception as e:
				failed_cogs.append(f"{cog}: {e}")

		if failed_cogs:
			error_message = "❌ Reloaded all except the following cogs:\n" + "\n> ".join(failed_cogs)
			embed = discord.Embed(color=discord.Color.red(), description=error_message)
			await ctx.reply(embed=embed, mention_author=False)
		else:
			embed = discord.Embed(color=config.base_embed_color, description="✅ Successfully reloaded all cogs.")
			await ctx.reply(embed=embed, mention_author=False)

	@commands.command(hidden=True, aliases=["rsc"])
	@commands.is_owner()
	async def reload_slash_command(self, ctx: commands.Context):
		await self.bot.sync_commands()
		embed = discord.Embed(color=config.base_embed_color)
		embed.description = "✅ Successfully synced bot application commands."
		await ctx.reply(embed=embed, mention_author=False)

	@commands.command(hidden=True, aliases=["rbc"])
	@commands.is_owner()
	async def reload_bot_config(self, ctx: commands.Context):
		await config.update_from_file()

		await ctx.reply("Config has been updated to the latest version available on the system.")

	@commands.command(hidden=True, aliases=["mui", "masteruserinfo"])
	@commands.is_owner()
	async def master_user_info(self, ctx: commands.Context, username: str = None):
		if username is None:
			username = ctx.author.name
		master_db = get_master_db()
		master_user = await master_db.fetch_user_fuzzy(username)
		if not master_user:
			return await ctx.reply("User not found.")

		json_user = json.dumps(
			await master_user.to_dict(include_badges=True, include_leaderboards=True, minimal_badges=False), indent=4, ensure_ascii=False
		)

		if len(json_user) < 1900:
			await ctx.reply(f"```json\n{json_user}\n```")
		else:
			json_file = discord.File(io.BytesIO(json_user.encode("utf-8")), f"{master_user.username}.json")
			await ctx.reply(file=json_file)

	@commands.command(hidden=True, aliases=["bi", "badgeinfo"])
	@commands.is_owner()
	async def badge_info(self, ctx: commands.Context, id: int):
		master_db = get_master_db()
		badge = await master_db.fetch_badge(id)
		if not badge:
			return await ctx.reply("Badge not found.")

		json_badge = json.dumps(await badge.to_dict(), indent=4)

		if len(json_badge) < 1900:
			await ctx.reply(f"```json\n{json_badge}\n```")
		else:
			json_file = discord.File(io.BytesIO(json_badge.encode("utf-8")), f"{badge.name}.json")
			await ctx.reply(file=json_file)

	@commands.command(hidden=True, aliases=["sui", "seasonuserinfo"])
	@commands.is_owner()
	async def season_user_info(self, ctx: commands.Context, username: str = None):
		if username is None:
			username = ctx.author.name
		master_db = get_master_db()
		season_db = await contracts.get_season_db()

		m_user = await master_db.fetch_user_fuzzy(username)
		if not m_user:
			return await ctx.reply("User not found.")

		s_user = await season_db.fetch_user(m_user.id)
		if not s_user:
			return await ctx.reply(f"User not found in {season_db.name}")

		json_user = json.dumps(await s_user.to_dict(include_contracts=True), indent=4)

		if len(json_user) < 1900:
			await ctx.reply(f"```json\n{json_user}\n```")
		else:
			json_file = discord.File(io.BytesIO(json_user.encode("utf-8")), f"{m_user.username}.json")
			await ctx.reply(file=json_file)

	@commands.command(hidden=True)
	@commands.is_owner()
	async def setalias(self, ctx: commands.Context, id: int, alias: str):
		master_db = get_master_db()
		master_user = await master_db.fetch_user(id)
		if not master_user:
			return await ctx.reply("User not found.")

		await master_db.add_user_alias(id, alias, force=True)
		await ctx.reply(f"Succesfully added alias `{alias}` to {master_user.username} ({master_user.id})")

	@commands.command(hidden=True)
	@commands.is_owner()
	async def removealias(self, ctx: commands.Context, alias: str):
		master_db = get_master_db()
		async with master_db.connect() as conn:
			async with conn.execute("SELECT 1 FROM user_aliases WHERE username = ?", (alias,)) as cursor:
				row = await cursor.fetchone()

			if row is None:
				return await ctx.reply("Alias not found.")

			await conn.execute("DELETE FROM user_aliases WHERE username = ?", (alias,))
			await conn.commit()

		await ctx.reply(f"Removed alias `{alias}`")

	@commands.command(hidden=True)
	@commands.is_owner()
	async def getaliases(self, ctx: commands.Context, id: int = None):
		master_db = get_master_db()
		user_aliases = await master_db.fetch_user_aliases(id)
		if not user_aliases:
			return await ctx.reply("No aliases found.")

		await ctx.reply(f"Aliases: {', '.join([f'`{alias}` ({u_id})' if id is None else f'`{alias}`' for alias, u_id in user_aliases])}")

	@commands.command(hidden=True, aliases=["gc"])
	@commands.is_owner()
	async def forcegarbagecollect(self, ctx: commands.Context):
		count = gc.collect()
		await ctx.reply(f"Collected {count} instances from the garbage.")

	@commands.command(hidden=True)
	@commands.is_owner()
	async def sql(self, ctx: commands.Context, *, flags: SQLQueryFlags):
		flags.database = flags.database.lower()
		if flags.database not in DATABASE_PATHS:
			return await ctx.reply(f"Invalid database chosen, valid choices: {', '.join(DATABASE_PATHS)}")

		codeblock_match = re.match(CODEBLOCK_PATTERN, flags.query, re.DOTALL)
		if not codeblock_match:
			return await ctx.reply("Queries must be inside codeblocks, like:\n```sql\nSELECT * FROM users LIMIT 1\n```")

		query = codeblock_match.group("content").strip()
		async with aiosqlite.connect(DATABASE_PATHS[flags.database]) as conn:
			if flags.row_factory:
				conn.row_factory = aiosqlite.Row

			try:
				statements = [s.strip() for s in query.split(";") if s.strip()]
				rows = []

				for i, statement in enumerate(statements, start=1):
					async with conn.execute(statement) as cursor:
						if i == len(statements):
							rows = await cursor.fetchall()

				await conn.commit()
			except aiosqlite.Error as err:
				await conn.rollback()
				return await ctx.reply(view=SQLOutputView(err))

		formatted_rows = (dict(row) for row in rows) if flags.row_factory else (list(row) for row in rows)
		str_output = json.dumps(list(formatted_rows), indent=4)

		if len(str_output) < 1900:
			await ctx.reply(view=SQLOutputView(str_output))
		else:
			file = discord.File(io.BytesIO(str_output.encode("utf-8")), filename="result.json")
			await ctx.reply("", file=file)


def setup(bot):
	bot.add_cog(Owner(bot))
