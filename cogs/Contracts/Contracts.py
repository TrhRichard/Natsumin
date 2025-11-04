from discord.ui import DesignerView, Container, TextDisplay, Separator, Button
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


class FilterFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	season: str = commands.flag(aliases=["S"], default=config.active_season)
	reps: list[str] = commands.flag(name="rep", aliases=["r"], default=None)
	statuses: list[str] = commands.flag(name="status", aliases=["s"], default=None)


class UsersView(DesignerView):
	def __init__(self):
		super().__init__(disable_on_timeout=True)

	@classmethod
	async def create(
		cls, bot: "Natsumin", invoker: discord.User, season: str | None = None, reps: list[str] | None = None, statuses: list[str] | None = None
	):
		self = cls()

		header_content = f"# Contracts {season}\n"
		if reps or statuses:
			header_content += "## Filters:\n"
			if reps:
				header_content += f"- **Reps**: {', '.join(reps)}\n"
			if statuses:
				header_content += f"- **Statuses**: {', '.join(statuses)}\n"

		buttons = (
			Button(style=discord.ButtonStyle.secondary, label="<--", disabled=True, custom_id="previous"),
			Button(style=discord.ButtonStyle.primary, label="?/?", disabled=True, custom_id="change_page"),
			Button(style=discord.ButtonStyle.secondary, label="-->", disabled=True, custom_id="next"),
		)

		self.add_item(
			Container(
				TextDisplay(header_content),
				Separator(),
				Separator(),
				*buttons,
				TextDisplay(f"-# <:Kirburger:998705274074435584> {utils.get_deadline_footer(season)}"),
				color=config.base_embed_color,
			)
		)


class StatsView(DesignerView):
	def __init__(self):
		super().__init__(store=False)

	# async initializer needed for this im not passing a billion values
	@classmethod
	async def create(cls, bot: "Natsumin", invoker: discord.User, rep: str | None = None, season: str | None = None):
		if season is None:
			season = config.active_season
		s_view = cls()

		season_db = await contracts.get_season_db(season)
		order_data = await season_db.get_order_data()

		async with season_db.connect() as conn:
			if rep:
				async with conn.execute("SELECT * FROM users WHERE rep = ? AND kind = ?", (rep, contracts.UserKind.NORMAL.value)) as cursor:
					total_users = [contracts.SeasonUser(**row, _db=season_db) for row in await cursor.fetchall()]

				async with conn.execute(
					"SELECT * FROM contracts WHERE contractee in (SELECT id FROM users WHERE rep = ? AND kind = ?)",
					(rep, contracts.UserKind.NORMAL.value),
				) as cursor:
					total_contracts = [contracts.Contract(**row, _db=season_db) for row in await cursor.fetchall()]
			else:
				async with conn.execute("SELECT * FROM users WHERE kind = ?", (contracts.UserKind.NORMAL.value,)) as cursor:
					total_users = [contracts.SeasonUser(**row, _db=season_db) for row in await cursor.fetchall()]

				async with conn.execute(
					"SELECT * FROM contracts WHERE contractee in (SELECT id FROM users WHERE kind = ?)", (contracts.UserKind.NORMAL.value,)
				) as cursor:
					total_contracts = [contracts.Contract(**row, _db=season_db) for row in await cursor.fetchall()]

		normal_contracts = filter_list(total_contracts, kind=ContractKind.NORMAL, optional=False)
		aid_contracts = filter_list(total_contracts, kind=ContractKind.AID, optional=False)

		stats_display = TextDisplay(
			f"**Users passed**: {get_percentage_formatted(len(filter_list(total_users, status=UserStatus.PASSED)), len(total_users))}\n"
			f"**Contracts passed**: {get_percentage_formatted(len(filter_list(normal_contracts, status=ContractStatus.PASSED)), len(normal_contracts))}\n"
			+ (
				f"**Aid Contracts passed**: {get_percentage_formatted(len(filter_list(aid_contracts, status=ContractStatus.PASSED)), len(aid_contracts))}"
				if aid_contracts
				else ""
			)
		)

		category_texts: dict[str, str] = {}

		contracts_in_categories: dict[str, list[contracts.Contract]] = {}

		for contract in total_contracts:
			contracts_in_categories.setdefault(utils.get_contract_category(order_data, contract.type), []).append(contract)

		for category_name, category_contracts in contracts_in_categories.items():
			type_contracts: dict[str, list[contracts.Contract]] = {}
			optional_contracts: dict[str, bool] = {}
			for contract in category_contracts:
				type_contracts.setdefault(contract.type, []).append(contract)
				if contract.type not in optional_contracts:
					optional_contracts[contract.type] = contract.optional

			category_passed_count = 0
			category_total_count = 0
			text_contract_stats: list[str] = []
			for c_type, c_list in type_contracts.items():
				passed_count = len(filter_list(c_list, status=ContractStatus.PASSED))
				total_count = len(c_list)
				text_contract_stats.append(f"> **{c_type}**: {get_percentage_formatted(passed_count, total_count)}")
				if not optional_contracts[c_type]:
					category_passed_count += passed_count
					category_total_count += total_count

			category_texts[category_name] = f"### {category_name} ({category_passed_count}/{category_total_count})\n{'\n'.join(text_contract_stats)}"

		sorted_categories_text = "\n".join(
			category_texts[category_name] for category_name in utils.sort_contract_categories(order_data) if category_name in category_texts
		)

		s_view.add_item(
			Container(
				TextDisplay(f"# Contracts {season_db.name}{f'\n-# {rep}' if rep is not None else ''}"),
				Separator(),
				stats_display,
				Separator(),
				TextDisplay(sorted_categories_text),
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
		"rep", description="The rep to get stats of, only autocompletes from active season", default=None, autocomplete=reps_autocomplete(True)
	)
	@discord.option("season", description="Season to get stats from, defaults to active", default=None, choices=contracts.AVAILABLE_SEASONS)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def stats(self, ctx: discord.ApplicationContext, rep: str = None, season: str = None, hidden: bool = False):
		if season is None:
			season = config.active_season

		if not utils.is_channel(ctx, 1002056335845752864):
			hidden = True

		try:
			_ = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.respond(str(e), ephemeral=True)

		if rep is not None:
			original_rep_query: str = rep
			rep = utils.get_rep(rep, min_confidence=90, only_include_reps=await utils.get_reps(season=season))
			if isinstance(rep, utils.RepName):
				rep = rep.value

			if rep is None:
				global_rep = utils.get_rep(original_rep_query, min_confidence=90)
				if global_rep is None:
					return await ctx.respond(f"{original_rep_query} is not a valid rep.", ephemeral=True)
				else:
					return await ctx.respond(f"0 members of {global_rep.value} participated in {season}.", ephemeral=True)

		await ctx.respond(view=await StatsView.create(self.bot, ctx.author, rep, season), ephemeral=hidden)

	@commands.command("stats", aliases=["s"], help="Fetch the stats of a season, optionally of a rep in that season")
	@utils.must_be_channel(1002056335845752864)
	async def text_stats(self, ctx: commands.Context, *, rep: str = None):
		season = config.active_season

		try:
			_ = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.reply(str(e))

		if rep is not None:
			original_rep_query: str = rep
			rep = utils.get_rep(rep, min_confidence=90, only_include_reps=await utils.get_reps(season=season))
			if isinstance(rep, utils.RepName):
				rep = rep.value

			if rep is None:
				global_rep = utils.get_rep(original_rep_query, min_confidence=90)
				if global_rep is None:
					return await ctx.reply(f"{original_rep_query} is not a valid rep.")
				else:
					return await ctx.reply(f"0 members of {global_rep.value} participated in {season}.")

		await ctx.reply(view=await StatsView.create(self.bot, ctx.author, rep, season))

	@commands.command("users", hidden=True, aliases=["u"], help="Fetch all the users in a season, optionally with filters")
	@utils.must_be_channel(1002056335845752864)
	async def text_users(self, ctx: commands.Context, *, flags: FilterFlags):
		await ctx.reply("Currently not implemented.")

		return

		try:
			_ = await contracts.get_season_db(flags.season)
		except ValueError as e:
			return await ctx.reply(str(e))

		await ctx.reply(view=await UsersView.create(self.bot, ctx.author, flags.season, flags.reps, flags.statuses))


def setup(bot):
	bot.add_cog(ContractsContracts(bot))
