from __future__ import annotations

from internal.enums import UserKind, UserStatus, ContractStatus, ContractKind
from internal.contracts import get_deadline_footer, season_autocomplete
from internal.functions import is_channel, get_percentage_formatted
from internal.contracts.order import sort_contract_types
from internal.contracts.rep import get_rep, RepName
from internal.checks import must_be_channel
from internal.base.cog import NatsuminCog
from internal.constants import COLORS
from discord.ext import commands
from typing import TYPE_CHECKING
from config import GUILD_IDS
from discord import ui

import discord

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


async def reps_autocomplete(ctx: discord.AutocompleteContext) -> list[discord.OptionChoice | str]:
	bot: NatsuminBot = ctx.bot
	async with bot.database.connect() as conn:
		active_season = await bot.get_config("contracts.active_season", db_conn=conn)
		if active_season is None:
			return []

		async with conn.execute(
			"SELECT DISTINCT(rep) as rep FROM season_user WHERE season_id = ? AND rep LIKE ? LIMIT 25", (active_season, f"%{ctx.value.strip()}%")
		) as cursor:
			reps_list = [row["rep"] for row in await cursor.fetchall()]

	return reps_list


class StatsFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	rep: str = commands.flag(aliases=["r"], default=None, positional=True)
	season: str = commands.flag(aliases=["s"], default=None)


class StatsView(ui.DesignerView):
	def __init__(self, bot: NatsuminBot, invoker: discord.abc.User, season_id: str, rep: RepName | None = None):
		super().__init__(disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.season_id = season_id
		self.rep = rep

	@classmethod
	async def create(cls, bot: NatsuminBot, invoker: discord.abc.User, season_id: str, rep: RepName | None = None):
		self = cls(bot, invoker, season_id, rep)

		async with bot.database.connect() as conn:
			async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]

			query = f"""
				SELECT
					SUM(su.kind = ?3 AND su.status = ?2) AS normal_passed,
					SUM(su.kind = ?3) AS normal_total,
					SUM(su.kind = ?4 AND su.status = ?2) AS aid_passed,
					SUM(su.kind = ?4) AS aid_total
				FROM season_user su
				WHERE su.season_id = ?1 {"AND su.rep = ?5" if rep else ""}
			"""

			params = [season_id, UserStatus.PASSED.value, UserKind.NORMAL.value, UserKind.AID.value]
			if rep:
				params.append(rep.value)
			async with conn.execute(query, params) as cursor:
				row = await cursor.fetchone()
				normal_users_count: tuple[int, int] = (row["normal_passed"], row["normal_total"])
				aid_users_count: tuple[int, int] = (row["aid_passed"], row["aid_total"])

			query = f"""
				SELECT
					SUM(sc.kind = ?3 AND sc.status = ?2) AS normal_passed,
					SUM(sc.kind = ?3) AS normal_total,
					SUM(sc.kind = ?4 AND sc.status = ?2) AS aid_passed,
					SUM(sc.kind = ?4) AS aid_total
				FROM season_contract sc
				JOIN season_user su ON 
					su.user_id = sc.contractee_id AND su.season_id = sc.season_id
				WHERE 
					sc.season_id = ?1 
					AND sc.optional = 0 
					{"AND su.rep = ?5" if rep else ""}
			"""
			params = [season_id, ContractStatus.PASSED.value, ContractKind.NORMAL.value, ContractKind.AID.value]
			if rep:
				params.append(rep.value)
			async with conn.execute(query, params) as cursor:
				row = await cursor.fetchone()
				normal_contracts_count: tuple[int, int] = (row["normal_passed"], row["normal_total"])
				aid_contracts_count: tuple[int, int] = (row["aid_passed"], row["aid_total"])

			query = f"""
				SELECT
					sc.type,
					SUM(sc.status = ?2) AS passed,
					COUNT(*) AS total
				FROM season_contract sc
				{"JOIN season_user su ON su.user_id = sc.contractee_id AND su.season_id = sc.season_id" if rep else ""}
				WHERE sc.season_id = ?1 {"AND su.rep = ?3" if rep else ""}
				GROUP BY sc.type
			"""
			params = [season_id, ContractStatus.PASSED]
			if rep:
				params.append(rep.value)
			async with conn.execute(query, params) as cursor:
				type_completions: dict[str, tuple[int, int]] = {row["type"]: (row["passed"], row["total"]) for row in await cursor.fetchall()}

			stats_display = ui.TextDisplay(
				f"**Users passed**: {get_percentage_formatted(normal_users_count[0], normal_users_count[1])}\n"
				f"**Contracts passed**: {get_percentage_formatted(normal_contracts_count[0], normal_contracts_count[1])}\n"
				+ (
					f"**Aid Contracts passed**: {get_percentage_formatted(aid_contracts_count[0], aid_contracts_count[1])}"
					if aid_users_count[1] > 0
					else ""
				)
			)

			season_order_data = self.bot.season_orders.get(self.season_id, [])

			category_texts: list[str] = []
			for category in sort_contract_types(type_completions.keys(), season_order_data):
				passed = 0
				total = 0
				type_texts: list[str] = []

				for cat_type in category["types"]:
					type_status = type_completions.get(cat_type, (0, 0))
					passed += type_status[0]
					total += type_status[1]

					type_texts.append(f"> **{cat_type}**: {get_percentage_formatted(type_status[0], type_status[1])}")

				category_texts.append(f"### {category['name']} ({passed}/{total})\n{'\n'.join(type_texts)}")

			self.add_item(
				ui.Container(
					ui.TextDisplay(f"# Contracts {season_name}{f'\n-# {rep.value}' if rep is not None else ''}"),
					ui.Separator(),
					stats_display,
					ui.Separator(),
					ui.TextDisplay("\n".join(category_texts)),
					ui.TextDisplay(f"-# <:Kirburger:998705274074435584> {await get_deadline_footer(bot.database, season_id, db_conn=conn)}"),
					color=COLORS.DEFAULT,
				)
			)

		return self

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass


class ContractsCog(NatsuminCog):
	contracts_group = discord.commands.SlashCommandGroup("contracts", description="Various contracts related commands", guild_ids=GUILD_IDS)

	@contracts_group.command(name="stats", description="Fetch the stats of a season, optionally of a rep in that season")
	@discord.option(
		"rep", str, description="The rep to get stats of, only autocompletes from active season", default=None, autocomplete=reps_autocomplete
	)
	@discord.option("season", str, description="Season to get data from, defaults to active", default=None, autocomplete=season_autocomplete)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=False)
	async def stats(self, ctx: discord.ApplicationContext, rep: str | None = None, season: str | None = None, hidden: bool = False):
		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		async with self.bot.database.connect() as conn:
			if season is None:
				season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			else:
				season_id = season

			if season_id not in self.bot.database.available_seasons:
				return await ctx.respond(
					f"Could not find season with the id **{season_id}**. If this is a real season it's likely the bot does not have any data about it.",
					ephemeral=True,
				)

			async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]

			if rep is not None:
				async with conn.execute("SELECT DISTINCT(rep) as rep FROM season_user WHERE season_id = ?", (season_id,)) as cursor:
					season_reps = [RepName(row["rep"]) for row in await cursor.fetchall()]

				original_rep_query = rep
				rep = get_rep(original_rep_query, min_confidence=90, only_include_reps=season_reps)
				if rep is None:
					global_rep = get_rep(original_rep_query, min_confidence=90)
					if global_rep is None:
						return await ctx.respond(f"{original_rep_query} is not a valid rep.", ephemeral=True)
					else:
						return await ctx.respond(f"0 members of {global_rep.value} participated in {season_name}.", ephemeral=True)

			await ctx.respond(view=await StatsView.create(self.bot, ctx.author, season_id, rep), ephemeral=hidden)

	@commands.command("stats", aliases=["s"], help="Fetch the stats of a season, optionally of a rep in that season")
	@must_be_channel(1002056335845752864)
	async def text_stats(self, ctx: commands.Context, *, flags: StatsFlags):
		rep = flags.rep
		async with self.bot.database.connect() as conn:
			if flags.season is None:
				season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			else:
				season_id = flags.season

			if season_id not in self.bot.database.available_seasons:
				return await ctx.reply(
					f"Could not find season with the id **{season_id}**. If this is a real season it's likely the bot does not have any data about it."
				)

			async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]

			if rep is not None:
				async with conn.execute("SELECT DISTINCT(rep) as rep FROM season_user WHERE season_id = ?", (season_id,)) as cursor:
					season_reps = [RepName(row["rep"]) for row in await cursor.fetchall()]

				original_rep_query = rep
				rep = get_rep(original_rep_query, min_confidence=90, only_include_reps=season_reps)
				if rep is None:
					global_rep = get_rep(original_rep_query, min_confidence=90)
					if global_rep is None:
						return await ctx.reply(f"{original_rep_query} is not a valid rep.")
					else:
						return await ctx.reply(f"0 members of {global_rep.value} participated in {season_name}.")

			await ctx.reply(view=await StatsView.create(self.bot, ctx.author, season_id, rep))
