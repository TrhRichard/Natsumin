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


async def create_embed(user: contracts.User, target: discord.Member, season: str = config.BOT_CONFIG.active_season) -> discord.Embed:
	embed = get_common_embed(user, target, season)
	season_db = await contracts.get_season_db(season)

	user_contracts = await season_db.fetch_contracts(contractee=user.username, kind=contracts.ContractKind.NORMAL)
	for contract in user_contracts:
		symbol = "✅" if contract.status == contracts.ContractStatus.PASSED else "❌"
		if contract.name in ["PLEASE SELECT", "Undecided"]:
			symbol = "⚠️"
			contract_name = f"__**{contract.name}**__"
		else:
			contract_name = contract.name

		if contract.optional:
			if contract.status == contracts.ContractStatus.PASSED:
				symbol = "🏆"
			else:
				symbol = "➖"

		line = f"> {symbol} **{contract.type.value}**: "
		line += f"[{contract_name}]({contract.review_url})" if contract.review_url else contract_name
		embed.description += "\n" + line

	aid_contracts = await season_db.fetch_contracts(contractee=user.username, kind=contracts.ContractKind.AID)
	if aid_contracts:
		embed.description += f"\n### Aids ({len([a for a in aid_contracts if a.status == contracts.ContractStatus.PASSED])}/{len(aid_contracts)})"
		for contract in aid_contracts:
			symbol = "✅" if contract.status == contracts.ContractStatus.PASSED else "❌"
			line = f"> {symbol} **{contract.type.value}**: "
			line += f"[{contract.name}]({contract.review_url})" if contract.review_url else contract.name
			embed.description += "\n" + line
	embed.description += "\n\n"

	if user.status == contracts.UserStatus.PASSED:
		embed.description += f"This user has **passed** {season}.\n"
	elif user.status == contracts.UserStatus.LATE_PASS:
		embed.description += f"This user has **passed** {season} **late**.\n"

	if aid_contracts and len([a for a in aid_contracts if a.status == contracts.ContractStatus.PASSED]) == len(aid_contracts):
		embed.description += f"This user has **passed** {season} **aids**.\n"

	passed = len([c for c in user_contracts if c.status == contracts.ContractStatus.PASSED])
	total = len(user_contracts)
	if total != 0:
		embed.title = f"Contracts ({passed}/{total})"

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


class ContractsGet(commands.Cog):
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

	@commands.slash_command(name="get", description="Get the state of someone's contracts", guilds_ids=config.BOT_CONFIG.guild_ids)
	@discord.option("username", description="Optionally check for another user", default=None, autocomplete=get_slash_usernames)
	@discord.option(
		"season", description="Optionally check in another season", default=config.BOT_CONFIG.active_season, choices=contracts.AVAILABLE_SEASONS
	)
	@discord.option("hidden", description="Optionally make the response only visible to you", default=False)
	async def get(self, ctx: discord.ApplicationContext, username: str, season: str, hidden: bool):
		target_member, username = await get_target(self.bot, ctx.author, username, season)

		season_db = await contracts.get_season_db(season)
		if target_user := await season_db.fetch_user(username=username):
			await ctx.respond(embed=await create_embed(target_user, target_member, season), ephemeral=hidden)
		else:
			await ctx.respond(embed=await create_error_embed(season_db, username), ephemeral=hidden)

	@discord.user_command(name="Get User Contracts", guild_ids=config.BOT_CONFIG.guild_ids)
	async def get_user_command(self, ctx: discord.ApplicationContext, user: discord.User):
		target_member, username = await get_target(self.bot, user)
		season_db = await contracts.get_season_db()
		if target_user := await season_db.fetch_user(username=username):
			await ctx.respond(embed=await create_embed(target_user, target_member), ephemeral=True)
		else:
			await ctx.respond(embed=await create_error_embed(season_db), ephemeral=True)

	@commands.command(name="get", help="Get the state of someone's contracts", aliases=["contracts", "g", "c"])
	@commands.cooldown(rate=5, per=5, type=commands.BucketType.user)
	async def text_get(self, ctx: commands.Context, *, username: str = None):
		target_member, username = await get_target(self.bot, ctx.author, username)

		season_db = await contracts.get_season_db()
		if target_user := await season_db.fetch_user(username=username):
			await ctx.reply(embed=await create_embed(target_user, target_member))
		else:
			await ctx.reply(embed=await create_error_embed(season_db, username))


def setup(bot):
	bot.add_cog(ContractsGet(bot))
