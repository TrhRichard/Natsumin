from utils.contracts import get_common_embed, reps_autocomplete, get_reps
from utils import get_percentage, config
from discord.ext import commands
from typing import TYPE_CHECKING
from thefuzz import process
import contracts
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


async def create_embed(rep: str | None, season: str = config.active_season) -> discord.Embed:
	season_db = await contracts.get_season_db(season)

	rep_users: list[contracts.SeasonUser] = []

	if not rep:
		users_passed = await season_db.count_users(status=contracts.UserStatus.PASSED, kind=contracts.ContractKind.NORMAL)
		users_total = await season_db.count_users(kind=contracts.ContractKind.NORMAL)
		contracts_passed = await season_db.count_contracts(status=contracts.ContractStatus.PASSED, kind=contracts.ContractKind.NORMAL)
		contracts_total = await season_db.count_contracts(kind=contracts.ContractKind.NORMAL)
		contract_types: dict[contracts.ContractType, list[int]] = {}

		for contract in await season_db.fetch_contracts(kind=contracts.ContractKind.NORMAL):
			type_status = contract_types.setdefault(contract.type, [0, 0])
			type_status[1] += 1
			if contract.status == contracts.ContractStatus.PASSED:
				type_status[0] += 1
	else:
		users_passed = await season_db.count_users(rep=rep, status=contracts.UserStatus.PASSED, kind=contracts.ContractKind.NORMAL)
		users_total = await season_db.count_users(rep=rep)
		contracts_passed = contracts_total = 0

		rep_users = await season_db.fetch_users(rep=rep)
		contract_types: dict[contracts.ContractType, list[int]] = {}

		for user in rep_users:
			for contract in await season_db.fetch_contracts(contractee=user.username, kind=contracts.ContractKind.NORMAL):
				type_status = contract_types.setdefault(contract.type, [0, 0])
				contracts_total += 1
				type_status[1] += 1
				if contract.status == contracts.ContractStatus.PASSED:
					contracts_passed += 1
					type_status[0] += 1

	embed = get_common_embed(season=season)
	embed.title = f"Contracts {season}" if not rep else f"Contracts {season} - {rep}"

	embed.description = "**Passed**:"
	embed.description += f"\n> **Users passed**: {users_passed}/{users_total} ({get_percentage(users_passed, users_total)}%)"
	embed.description += f"\n> **Contracts passed**: {contracts_passed}/{contracts_total} ({get_percentage(contracts_passed, contracts_total)}%)"
	embed.description += "\n\n **Contracts**:"
	for c_type, c_stats in contract_types.items():
		embed.description += f"\n> **{c_type}**: {c_stats[0]}/{c_stats[1]} ({get_percentage(c_stats[0], c_stats[1])}%)"
	if not rep:
		total_aids = await season_db.count_contracts(kind=contracts.ContractKind.AID)
		passed_aids = await season_db.count_contracts(status=contracts.ContractStatus.PASSED, kind=contracts.ContractKind.AID)
	else:
		rep_usernames = (*[user.username for user in rep_users],)
		total_aids = await season_db.count_contracts(contractee=rep_usernames, kind=contracts.ContractKind.AID)
		passed_aids = await season_db.count_contracts(
			contractee=rep_usernames, status=contracts.ContractStatus.PASSED, kind=contracts.ContractKind.AID
		)

	if total_aids > 0:
		embed.description += f"\n> **Aids**: {passed_aids}/{total_aids} ({get_percentage(passed_aids, total_aids)}%)"

	return embed


async def create_error_embed(season_db: contracts.SeasonDB, rep: str) -> discord.Embed:
	error_embed = discord.Embed(color=discord.Color.red())
	error_embed.description = ":x: Invalid rep!"

	reps = await get_reps(season_db)

	fuzzy_results: list[tuple[str, int]] = process.extract(rep, reps, limit=1)
	if len(fuzzy_results) > 0:
		fuzzy_rep, fuzzy_confidence = fuzzy_results[0]
		error_embed.description = f":x: Invalid rep! Did you mean **{fuzzy_rep}** ({fuzzy_confidence}%)?"

	return error_embed


class ContractsStats(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/contracts.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	@commands.slash_command(name="stats", description="Check the season's stats", guilds_ids=config.guild_ids)
	@discord.option("rep", description="Optionally check stats for a specific rep", default=None, autocomplete=reps_autocomplete)
	@discord.option("season", description="Optionally check in another season", default=config.active_season, choices=contracts.AVAILABLE_SEASONS)
	@discord.option("hidden", description="Optionally make the response only visible to you", default=False)
	async def stats(self, ctx: discord.ApplicationContext, rep: str, season: str, hidden: bool):
		season_db = await contracts.get_season_db(season)
		reps = await get_reps(season_db)
		if rep and rep.upper() not in reps:
			return await ctx.respond(embed=await create_error_embed(season_db, rep.upper()), ephemeral=hidden)

		await ctx.respond(embed=await create_embed(rep.upper() if rep else None, season), ephemeral=hidden)

	@commands.command(name="stats", aliases=["s"], help="Check the season's stats")
	async def text_stats(self, ctx: commands.Context, *, rep: str = None):
		season_db = await contracts.get_season_db()
		reps = await get_reps(season_db)
		if rep and rep.upper() not in reps:
			return await ctx.reply(embed=await create_error_embed(season_db, rep.upper()))

		await ctx.reply(embed=await create_embed(rep.upper() if rep else None))


def setup(bot):
	bot.add_cog(ContractsStats(bot))
