from discord.ui import View, Container, TextDisplay, Separator
from contracts import UserStatus, ContractKind, ContractStatus
from utils import get_percentage_formatted, filter_list
from discord.ext import commands
from typing import TYPE_CHECKING
from common import config
import contracts
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


def reps_autocomplete(seasonal: bool = True):
	async def callback(ctx: discord.AutocompleteContext):
		return await utils.contracts.get_reps(query=ctx.value.strip(), limit=25, seasonal=seasonal)

	return callback


class StatsView(View):
	def __init__(self, bot: "Natsumin", invoker: discord.User, rep: str | None = None, season: str | None = None):
		super().__init__(timeout=180, disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.rep = rep
		self.season = season

	# async initializer needed for this im not passing a billion values
	@classmethod
	async def create(cls, bot: "Natsumin", invoker: discord.User, rep: str | None = None, season: str | None = None):
		if season is None:
			season = config.active_season
		s_view = cls(bot, invoker, rep, season)

		season_db = await contracts.get_season_db(season)
		order_data = await season_db.get_order_data()

		async with season_db.connect() as conn:
			if rep:
				async with conn.execute("SELECT * FROM users WHERE rep = ? AND kind = ?", (rep, contracts.UserKind.NORMAL.value)) as cursor:
					total_users = [contracts.SeasonUser.new(**row, _db=season_db) for row in await cursor.fetchall()]

				async with conn.execute(
					"SELECT * FROM contracts WHERE contractee in (SELECT id FROM users WHERE rep = ? AND kind = ?)",
					(rep, contracts.UserKind.NORMAL.value),
				) as cursor:
					total_contracts = [contracts.Contract.new(**row, _db=season_db) for row in await cursor.fetchall()]
			else:
				async with conn.execute("SELECT * FROM users WHERE kind = ?", (contracts.UserKind.NORMAL.value,)) as cursor:
					total_users = [contracts.SeasonUser.new(**row, _db=season_db) for row in await cursor.fetchall()]

				async with conn.execute(
					"SELECT * FROM contracts WHERE contractee in (SELECT id FROM users WHERE kind = ?)", (contracts.UserKind.NORMAL.value,)
				) as cursor:
					total_contracts = [contracts.Contract.new(**row, _db=season_db) for row in await cursor.fetchall()]

		normal_contracts = filter_list(total_contracts, kind=ContractKind.NORMAL)
		aid_contracts = filter_list(total_contracts, kind=ContractKind.AID)

		stats_display = TextDisplay(
			f"**Users passed**: {get_percentage_formatted(len(filter_list(total_users, status=UserStatus.PASSED)), len(total_users))}\n"
			f"**Contracts passed**: {get_percentage_formatted(len(filter_list(normal_contracts, status=ContractStatus.PASSED)), len(normal_contracts))}\n"
			+ (
				f"**Aid Contracts passed**: {get_percentage_formatted(len(filter_list(aid_contracts, status=ContractStatus.PASSED)), len(aid_contracts))}"
				if aid_contracts
				else ""
			)
		)

		category_text: str = ""
		if order_data is not None:
			contracts_in_categories: dict[str, list[contracts.Contract]] = {}

			for contract in total_contracts:
				contracts_in_categories.setdefault(utils.get_contract_category(order_data, contract.type), []).append(contract)

			for category_name, category_contracts in contracts_in_categories.items():
				type_contracts: dict[str, list[contracts.Contract]] = {}
				for contract in category_contracts:
					type_contracts.setdefault(contract.type, []).append(contract)

				text_contract_stats: list[str] = [
					f"> **{c_type}**: {get_percentage_formatted(len(filter_list(c_list, status=ContractStatus.PASSED)), len(c_list))}"
					for c_type, c_list in type_contracts.items()
				]

				category_text += f"### {category_name}\n{'\n'.join(text_contract_stats)}\n"

		else:
			category_text = "### Contracts\n"
			type_contracts: dict[str, list[contracts.Contract]] = {}
			for c in total_contracts:
				type_contracts.setdefault(c.type, []).append(c)

			for c_type in sorted(type_contracts.keys()):
				all_contracts_of_type = type_contracts.get(c_type, [])
				category_text += f"> **{c_type}**: {get_percentage_formatted(len(filter_list(all_contracts_of_type, status=ContractStatus.PASSED)), len(all_contracts_of_type))}\n"

		s_view.add_item(
			Container(
				TextDisplay(f"# Contracts {season_db.name}{f'\n-# {rep}' if rep is not None else ''}"),
				Separator(),
				stats_display,
				Separator(),
				TextDisplay(category_text),
				Separator(),
				TextDisplay(f"-# <:Kirburger:998705274074435584> {utils.get_deadline_footer(season)}"),
				color=config.base_embed_color,
			)
		)

		return s_view


class ContractsContracts(commands.Cog):  # yeah
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

	contracts_group = discord.commands.SlashCommandGroup("contracts", description="Various contracts related commands", guild_ids=config.guild_ids)

	@contracts_group.command(description="Fetch the stats of a season, optionally of a rep in that season")
	@discord.option(
		name="rep", description="The rep to get stats of, only autocompletes from active season", default=None, autocomplete=reps_autocomplete(True)
	)
	@discord.option(name="season", description="Season to get stats from, defaults to active", default=None, choices=contracts.AVAILABLE_SEASONS)
	async def stats(self, ctx: discord.ApplicationContext, rep: str = None, season: str = None):
		if season is None:
			season = config.active_season

		try:
			_ = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.respond(str(e), ephemeral=True)

		if rep is not None:
			original_rep_query: str = rep
			rep = utils.get_rep(rep, only_include_reps=await utils.get_reps(season=season))
			if isinstance(rep, utils.RepName):
				rep = rep.value

			if rep is None:
				return await ctx.respond(f"Rep {original_rep_query} cannot be found in {season}.", ephemeral=True)

		await ctx.respond(
			view=await StatsView.create(self.bot, ctx.author, rep, season),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@commands.command("stats", aliases=["s"], help="Fetch the stats of a season, optionally of a rep in that season")
	async def text_stats(self, ctx: commands.Context, *, rep: str = None):
		season = config.active_season

		try:
			_ = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.reply(str(e))

		rep_stats_wanted = rep is not None
		if rep is not None:
			original_rep_query: str = rep
			rep = utils.get_rep(rep, only_include_reps=await utils.get_reps(season=season))
			if isinstance(rep, utils.RepName):
				rep = rep.value

		if rep_stats_wanted and rep is None:
			return await ctx.reply(f"Rep {original_rep_query} cannot be found in {season}.")

		await ctx.reply(
			view=await StatsView.create(self.bot, ctx.author, rep, season),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)


def setup(bot):
	bot.add_cog(ContractsContracts(bot))
