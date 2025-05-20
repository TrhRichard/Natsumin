from utils.contracts import get_common_embed, get_slash_usernames, get_usernames, get_target
from discord.ext import commands
from typing import TYPE_CHECKING
from thefuzz import process
import contracts
import logging
import discord
import config

if TYPE_CHECKING:
	from main import Natsumin


async def create_embed(bot: "Natsumin", user: contracts.User, target: discord.Member, season: str = config.BOT_CONFIG.active_season) -> discord.Embed:
	season_db = await contracts.get_season_db(season)

	embed = get_common_embed(user, target, season)
	embed.description = f"> **Rep**: {user.rep}"

	contractor: discord.User = await bot.get_contract_user(username=user.contractor)
	embed.description += f"\n> **Contractor**: {contractor.mention if contractor else user.contractor} {f'({contractor.name})' if contractor else ''}"

	if user.kind == contracts.UserKind.NORMAL:
		contractees: list[str] = []
		for contractee in await season_db.fetch_users(contractor=user.username):
			member = await bot.get_contract_user(id=contractee.discord_id, username=contractee.username)
			contractees.append(f"{member.mention} ({member.name})" if member else contractee.username)
		embed.description += f"\n> **Contractee**: {', '.join(contractees)}"

	if url := user.list_url:
		url_lower = url.lower()
		list_username = url.rstrip("/").split("/")[-1]
		if "myanimelist" in url_lower:
			embed.description += f"\n> **MyAnimeList**: [{list_username}]({url})"
		elif "anilist" in url_lower:
			embed.description += f"\n> **AniList**: [{list_username}]({url})"
		else:
			embed.description += f"\n> **List**: {url}"
	embed.description += f"\n> **Preferences**: {user.preferences}"
	embed.description += f"\n> **Bans**: {user.bans}"
	return embed


async def create_error_embed(season_db: contracts.SeasonDB, username: str = None) -> discord.Embed:
	error_embed = discord.Embed(color=discord.Color.red())
	error_embed.description = ":x: User not found!"

	if username:
		usernames = await get_usernames(season_db)

		fuzzy_results: list[tuple[str, int]] = process.extract(username, usernames, limit=1)
		if len(fuzzy_results) > 0:
			fuzzy_username, fuzzy_confidence = fuzzy_results[0]
			error_embed.description = f":x: User not found! Did you mean **{fuzzy_username}** ({fuzzy_confidence}%)?"

	return error_embed


class ContractsProfile(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(config.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(config.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	@commands.slash_command(name="profile", description="Get a user's profile", guilds_ids=config.BOT_CONFIG.guild_ids)
	@discord.option("username", description="Optionally check for another user", default=None, autocomplete=get_slash_usernames)
	@discord.option(
		"season", description="Optionally check in another season", default=config.BOT_CONFIG.active_season, choices=contracts.AVAILABLE_SEASONS
	)
	@discord.option("hidden", description="Optionally make the response only visible to you", default=False)
	async def profile(self, ctx: discord.ApplicationContext, username: str, season: str, hidden: bool):
		target_member, username = await get_target(self.bot, ctx.author, username, season)

		season_db = await contracts.get_season_db(season)
		if target_user := await season_db.fetch_user(username=username):
			await ctx.respond(embed=await create_embed(self.bot, target_user, target_member, season), ephemeral=hidden)
		else:
			await ctx.respond(embed=await create_error_embed(season_db, username), ephemeral=hidden)

	@discord.user_command(name="Get User Profile", guild_ids=config.BOT_CONFIG.guild_ids)
	async def get_user_command(self, ctx: discord.ApplicationContext, user: discord.User):
		target_member, username = await get_target(self.bot, user)
		season_db = await contracts.get_season_db()
		if target_user := await season_db.fetch_user(username=username):
			await ctx.respond(embed=await create_embed(self.bot, target_user, target_member), ephemeral=True)
		else:
			await ctx.respond(embed=await create_error_embed(season_db), ephemeral=True)

	@commands.command(name="profile", aliases=["p"], help="Get a user's profile")
	async def text_profile(self, ctx: commands.Context, *, username: str = None):
		target_member, username = await get_target(self.bot, ctx.author, username)

		season_db = await contracts.get_season_db()
		if target_user := await season_db.fetch_user(username=username):
			await ctx.reply(embed=await create_embed(self.bot, target_user, target_member))
		else:
			await ctx.reply(embed=await create_error_embed(season_db, username))


def setup(bot):
	bot.add_cog(ContractsProfile(bot))
