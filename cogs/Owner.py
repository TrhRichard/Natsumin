from utils import CONSOLE_LOGGING_FORMATTER, FILE_LOGGING_FORMATTER, config
from discord.ext import commands
from typing import TYPE_CHECKING
from common import get_master_db
from thefuzz import process
import contracts
import logging
import discord
import json
import io
import gc

if TYPE_CHECKING:
	from main import Natsumin


class Owner(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.owner")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/owner.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)

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
	async def sync_master_ids(self, ctx: commands.Context):
		if not self.bot.anicord:
			await ctx.reply("Bot is not in Anicord!")
			return

		master_db = get_master_db()

		guild_members = await self.bot.anicord.fetch_members(limit=None).flatten()
		print(f"Received {len(guild_members)} members!")
		name_members: dict[str, discord.Member] = {m.name: m for m in guild_members}
		member_names: dict[discord.Member, str] = {m: m.name for m in guild_members}

		async with master_db.connect() as conn:
			async with conn.execute("SELECT * FROM users WHERE discord_id IS NULL") as cursor:
				users = await cursor.fetchall()
				for user in users:
					username: str = user["username"]
					if member := name_members.get(username):
						await conn.execute("UPDATE OR IGNORE users SET discord_id = ? WHERE id = ?", (member.id, user["id"]))
					else:
						fuzzy_results: list[tuple[str, int, discord.Member]] = process.extract(username, member_names, limit=1)
						if not fuzzy_results:
							print(f"Could not find a discord id for {username}, skipping...")
							continue

						_, confidence, member = fuzzy_results[0]
						if confidence >= 90:
							if username == member.name:
								await conn.execute("UPDATE OR IGNORE users SET discord_id = ? WHERE id = ?", (member.id, user["id"]))
							else:
								print(f"It appears that {username}'s actual name is {member.name}, updating that as well")
								await conn.execute(
									"UPDATE OR IGNORE users SET discord_id = ?, username = ? WHERE id = ?", (member.id, member.name, user["id"])
								)

			await conn.commit()


def setup(bot):
	bot.add_cog(Owner(bot))
