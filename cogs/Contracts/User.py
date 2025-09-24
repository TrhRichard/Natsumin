from discord.ui import View, Container, TextDisplay, Separator, MediaGallery, Section, Thumbnail, Button
from contracts import UserStatus, ContractStatus, UserKind
from discord.ext import commands
from typing import TYPE_CHECKING
from common import config
import contracts
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


def usernames_autocomplete(seasonal: bool = True):
	async def callback(ctx: discord.AutocompleteContext) -> list[str]:
		return await utils.contracts.get_usernames(query=ctx.value.strip(), limit=25, seasonal=seasonal)

	return callback


def get_status_emote(status: UserStatus | ContractStatus, is_optional: bool = False) -> str:
	match status:
		case UserStatus.PASSED | ContractStatus.PASSED:
			if is_optional:
				return "🏆"
			else:
				return "✅"
		case UserStatus.LATE_PASS | ContractStatus.LATE_PASS:
			return "☑️"
		case UserStatus.FAILED | UserStatus.INCOMPLETE | ContractStatus.FAILED:
			return "❌"
		case _:
			return "❔"


class ContractsGetFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	season: str = commands.flag(aliases=["s"], default=config.active_season)


class UserBadges(View):
	def __init__(self, bot: "Natsumin", invoker: discord.User, user: discord.Member | discord.User, badges: list[contracts.Badge]):
		super().__init__(timeout=180, disable_on_timeout=True)

		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.badges: list[contracts.Badge] = badges
		self.current_badge_selected = 0

		self.add_item(self.get_badge_container(badges[self.current_badge_selected]))

	async def button_callback(self, interaction: discord.Interaction):
		match interaction.custom_id:
			case "previous":
				self.current_badge_selected = (self.current_badge_selected - 1) % len(self.badges)
			case "next":
				self.current_badge_selected = (self.current_badge_selected + 1) % len(self.badges)
			case _:
				return

		self.clear_items()
		self.add_item(self.get_badge_container(self.badges[self.current_badge_selected]))
		await interaction.edit(view=self)

	def get_badge_container(self, badge: contracts.Badge) -> Container:
		badge_artist = TextDisplay(f"-# Artist: {badge.artist}" if badge.artist else "-# No artist")
		if badge.url:
			badge_art = MediaGallery()
			badge_art.add_item(badge.url, description=badge.artist)
		else:
			badge_art = TextDisplay("No image available.")

		page_buttons = [
			Button(style=discord.ButtonStyle.secondary, label="<--", disabled=True, custom_id="previous"),
			Button(
				style=discord.ButtonStyle.primary,
				label=f"{self.current_badge_selected + 1}/{len(self.badges)}",
				disabled=True,
				custom_id="change_page",
			),
			Button(style=discord.ButtonStyle.secondary, label="-->", disabled=True, custom_id="next"),
		]

		for button in page_buttons:
			button.callback = self.button_callback
			if button.custom_id != "change_page":
				button.disabled = True if len(self.badges) == 1 else False

		return Container(
			TextDisplay(f"# {badge.name}\n{badge.description}"),
			Separator(),
			badge_art,
			badge_artist,
			Separator(),
			*page_buttons,
			# TextDisplay(f"-# Badge ID: {badge.id}"),
			color=config.base_embed_color,
		)


class MasterUserProfile(View):
	def __init__(
		self,
		bot: "Natsumin",
		invoker: discord.User,
		user: discord.Member | discord.User,
		master_user: contracts.MasterUser,
		legacy_exp: int | None = None,
	):
		super().__init__(timeout=180, disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.master_user = master_user

		top_section = Section(accessory=Thumbnail(user.display_avatar.url))

		legacy_rank = utils.get_legacy_rank(legacy_exp)

		top_section.add_text( 
			f"# <@{user.id}>'s Profile\n" +
			(f"- **Rep**: {master_user.rep}\n" if master_user.rep else "") +
			(f"- **Generation**: {master_user.gen}\n" if master_user.gen else "") +
			(
				"### Legacy Leaderboard\n" +
				f"- **Rank**: {legacy_rank} <a:{legacy_rank.value}:{utils.get_rank_emoteid(legacy_rank)}>\n" +
				f"- **EXP**: {legacy_exp}"
			) if legacy_exp else ""
			
		)  # fmt: skip
		badges_button = Button(style=discord.ButtonStyle.secondary, label="Check badges", custom_id="check_badges")
		badges_button.callback = self.button_callback

		self.add_item(Container(top_section, Separator(), badges_button, color=config.base_embed_color))

	async def button_callback(self, interaction: discord.Interaction):
		if interaction.custom_id != "check_badges":
			return

		badges = await self.master_user.get_badges()
		if len(badges) == 0:
			return await interaction.respond("No badges found.", ephemeral=True)

		await interaction.respond(view=UserBadges(self.bot, interaction.user, self.user, badges), ephemeral=True)


class UserContracts(View):
	def __init__(
		self,
		bot: "Natsumin",
		invoker: discord.User,
		user: discord.Member | discord.User | None,
		season_user: contracts.SeasonUser,
		master_user: contracts.MasterUser,
		season: str,
		user_contracts: list[contracts.Contract],
		order_data: list[contracts.ContractOrderCategory] | None = None,
	):
		super().__init__(timeout=180, disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.season_user = season_user
		self.season = season
		self.order_data = order_data

		top_section = Section(accessory=Thumbnail(user.display_avatar.url))

		username = f"<@{self.user.id}>" if user else master_user.username

		footer_messages: list[str] = []

		user_description = f"> **Status**: {get_status_emote(UserStatus(season_user.status))}\n"
		if UserKind(season_user.kind) == UserKind.NORMAL:
			user_description += f"> **Contractor**: {season_user.contractor}"

		top_section.add_text(f"## {username}'s Contracts\n{user_description}")

		category_text: str = ""
		if order_data is not None:
			contracts_in_categories: dict[str, list[contracts.Contract]] = {}
			category_counts: dict[str, list[int]] = {}

			for contract in user_contracts:
				category_name = utils.get_contract_category(order_data, contract.type)
				category_counts[category_name] = [0, 0]  # (TotalContracts, PassedContracts)
				contracts_in_categories.setdefault(category_name, []).append(contract)

			for category_name, category_contracts in contracts_in_categories.items():
				type_contracts: dict[str, contracts.Contract] = {}
				for contract in category_contracts:
					category_counts[category_name][0] += 1
					if contract.status in (ContractStatus.PASSED, ContractStatus.LATE_PASS):
						category_counts[category_name][1] += 1
					type_contracts[contract.type] = contract

				text_contract_stats: list[str] = []
				for contract in type_contracts.values():
					contract_name = f"[{contract.name}]({contract.review_url})" if contract.review_url else contract.name
					text_contract_stats.append(f"> {get_status_emote(contract.status, contract.optional)} **{contract.type}**: {contract_name}")

				category_text += f"### {category_name} ({category_counts[category_name][1]}/{category_counts[category_name][0]})\n{'\n'.join(text_contract_stats)}\n"
				if category_counts[category_name][1] == category_counts[category_name][0]:
					footer_messages.append(f"This user has finished all **{category_name}**!")

		else:
			contracts_passed = len(utils.filter_list(user_contracts, status=ContractStatus.PASSED)) + len(
				utils.filter_list(user_contracts, status=ContractStatus.LATE_PASS)
			)  # idc
			category_text = f"### Contracts ({len(user_contracts)}/{len(contracts_passed)})\n"
			type_contracts: dict[str, contracts.Contract] = {}
			for contract in user_contracts:
				type_contracts[contract.type] = contract

			for contract in sorted(type_contracts.values()):
				contract_name = f"[{contract.name}]({contract.review_url})" if contract.review_url else contract.name
				category_text += f"> {get_status_emote(contract.status)} **{contract.type}**: {contract_name}\n"

		container = Container(top_section, Separator(), TextDisplay(category_text), color=config.base_embed_color)
		if footer_messages:
			container.add_text("\n".join([f"-# {msg}" for msg in footer_messages]))
		container.add_separator()
		container.add_text(f"-# <:Kirburger:998705274074435584> {utils.get_deadline_footer(season)}")

		self.add_item(container)


class ContractsUser(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

	user_group = discord.commands.SlashCommandGroup("user", description="Various user related commands", guild_ids=config.guild_ids)
	contracts_subgroup = user_group.create_subgroup("contracts", description="Various user contracts related commands", guild_ids=config.guild_ids)

	@user_group.command(description="Fetch the global profile of a user")
	@discord.option(name="user", description="The user to get profile of", default=None, autocomplete=usernames_autocomplete(False))
	async def profile(self, ctx: discord.ApplicationContext, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond("User is currently not in the database.", ephemeral=True)

		legacy_exp = await m_user.get_legacy_exp()

		await ctx.respond(
			view=MasterUserProfile(self.bot, ctx.author, selected_user, m_user, legacy_exp=legacy_exp),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@user_group.command(description="Fetch the badges of a user")
	@discord.option(name="user", description="The user to see badges from", default=None, autocomplete=usernames_autocomplete(False))
	async def badges(self, ctx: discord.ApplicationContext, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond("User is currently not in the database.", ephemeral=True)

		badges = await m_user.get_badges()
		if len(badges) == 0:
			return await ctx.respond("No badges found.", ephemeral=True)

		await ctx.respond(
			view=UserBadges(self.bot, ctx.author, selected_user, badges),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@contracts_subgroup.command(name="get", description="Fetch the badges of a user")
	@discord.option(
		name="user",
		description="The user to see contracts of, only autocompletes from active season",
		default=None,
		autocomplete=usernames_autocomplete(True),
	)
	@discord.option(name="season", description="Season to get data from, defaults to active", default=None, choices=contracts.AVAILABLE_SEASONS)
	async def contracts(self, ctx: discord.ApplicationContext, user: str = None, season: str = None):
		if user is None:
			user = ctx.author
		if season is None:
			season = config.active_season

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond("User is currently not in the database.", ephemeral=True)

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.respond(f"There is no {season} in Ba Sing Se ||(No data for such season found)||", ephemeral=True)
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.respond(f"User is not part of Contracts {season}!", ephemeral=True)

		order_data = await season_db.get_order_data()
		user_contracts = await s_user.get_contracts()

		await ctx.respond(
			view=UserContracts(self.bot, ctx.author, selected_user, s_user, m_user, season, user_contracts, order_data),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@commands.command("badges", aliases=["b"], help="Fetch the badges of a user")
	async def text_badges(self, ctx: commands.Context, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply("User is currently not in the database.")

		badges = await m_user.get_badges()
		if len(badges) == 0:
			return await ctx.reply("No badges found.")

		await ctx.reply(
			view=UserBadges(self.bot, ctx.author, selected_user, badges),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@commands.command("globalprofile", aliases=["gp"], help="Fetch the global profile of a user")
	async def text_profile(self, ctx: commands.Context, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply("User is currently not in the database.")

		legacy_exp = await m_user.get_legacy_exp()

		await ctx.reply(
			view=MasterUserProfile(self.bot, ctx.author, selected_user, m_user, legacy_exp=legacy_exp),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)

	@commands.command("contracts", aliases=["c"], help="Fetch the status of your contracts")
	async def text_contracts(self, ctx: commands.Context, user: str = None, *, flags: ContractsGetFlags):
		season = flags.season
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply("User is currently not in the database.")

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.reply(f"There is no {season} in Ba Sing Se ||(No data for such season found)||")
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.reply(f"User is not part of Contracts {season}!")

		order_data = await season_db.get_order_data()
		user_contracts = await s_user.get_contracts()

		await ctx.reply(
			view=UserContracts(self.bot, ctx.author, selected_user, s_user, m_user, season, user_contracts, order_data),
			allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
		)


def setup(bot):
	bot.add_cog(ContractsUser(bot))
