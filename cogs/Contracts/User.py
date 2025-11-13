from discord.ui import DesignerView, Container, TextDisplay, Separator, MediaGallery, Section, Thumbnail, ActionRow, Button
from contracts import UserStatus, ContractStatus, UserKind
from common import config, STRINGS
from discord.ext import commands
from typing import TYPE_CHECKING
import contracts
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin

NEED_TO_SELECT_STRINGS = ["please select", "undecided", "pending"]


def usernames_autocomplete(seasonal: bool = True):
	async def callback(ctx: discord.AutocompleteContext) -> list[str]:
		return await utils.contracts.get_usernames(query=ctx.value.strip(), limit=25, seasonal=seasonal)

	return callback


def get_user_status_name(status: UserStatus) -> str:
	match status:
		case UserStatus.PASSED:
			return STRINGS("status.user.passed")
		case UserStatus.LATE_PASS:
			return STRINGS("status.user.late_pass")
		case UserStatus.FAILED:
			return STRINGS("status.user.failed")
		case UserStatus.INCOMPLETE:
			return STRINGS("status.user.incomplete")
		case UserStatus.PENDING:
			return STRINGS("status.user.pending")
		case _:
			return STRINGS("status.user.unknown")


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
		case ContractStatus.UNVERIFIED:
			return "❓"
		case _:
			return "❔"


class ExtraFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	season: str = commands.flag(aliases=["s"], default=config.active_season)


class UserBadges(DesignerView):
	def __init__(self, bot: "Natsumin", invoker: discord.User, user: discord.Member | discord.User, badges: list[contracts.Badge]):
		super().__init__(disable_on_timeout=True)

		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.badges: list[contracts.Badge] = badges
		self.current_badge_selected = 0

		self.add_item(self.get_badge_container(badges[self.current_badge_selected]))

	async def on_timeout(self):
		await super().on_timeout()
		self.bot = None
		self.invoker = None
		self.user = None
		self.badges = None

		for item in self.children:
			if hasattr(item, "callback"):
				item.callback = None

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
		badge_artist = TextDisplay(STRINGS("contracts.badges.artist", artist=badge.artist))
		if badge.url:
			badge_art = MediaGallery()
			badge_art.add_item(badge.url, description=badge.artist)
		else:
			badge_art = TextDisplay(STRINGS("contracts.badges.no_image"))

		page_buttons = ActionRow(
			Button(style=discord.ButtonStyle.secondary, label="<--", disabled=False, custom_id="previous"),
			Button(
				style=discord.ButtonStyle.primary,
				label=STRINGS("contracts.badges.buttons.change_page", current=self.current_badge_selected + 1, total=len(self.badges)),
				disabled=True,  # len(self.badges) == 1,
				custom_id="change_page",
			),
			Button(style=discord.ButtonStyle.secondary, label=STRINGS("contracts.badges.buttons.next"), disabled=False, custom_id="next"),
		)

		for button in page_buttons.children:
			button.callback = self.button_callback

		return Container(
			TextDisplay(STRINGS("contracts.badges.description", name=badge.name, description=badge.description)),
			Separator(),
			badge_art,
			badge_artist,
			Separator(),
			page_buttons,
			# TextDisplay(f"-# Badge ID: {badge.id}"),
			color=config.base_embed_color,
		)


class MasterUserProfile(DesignerView):
	def __init__(
		self,
		bot: "Natsumin",
		invoker: discord.User,
		user: discord.Member | discord.User,
		master_user: contracts.MasterUser,
		legacy_exp: int | None = None,
	):
		super().__init__(disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.master_user = master_user

		legacy_rank = utils.get_legacy_rank(legacy_exp)
		username = f"<@{self.user.id}>" if user else master_user.username

		user_details = (
			STRINGS("contracts.globalprofile.description.header", user=username)
			+ "\n"
			+ STRINGS("contracts.globalprofile.description.normal", rep=master_user.rep, gen=master_user.gen)
		)
		if legacy_exp:
			user_details += STRINGS(
				"contracts.globalprofile.description.legacy_lb",
				rank=legacy_rank.value,
				rank_emote_id=utils.get_rank_emoteid(legacy_rank),
				exp=legacy_exp,
			)

		badges_button = Button(
			style=discord.ButtonStyle.secondary, label=STRINGS("contracts.globalprofile.buttons.check_badges"), custom_id="check_badges"
		)
		badges_button.callback = self.button_callback

		self.add_item(
			Container(
				Section(TextDisplay(user_details), accessory=Thumbnail(user.display_avatar.url)) if user else TextDisplay(user_details),
				Separator(),
				ActionRow(badges_button),
				color=config.base_embed_color,
			)
		)

	async def on_timeout(self):
		await super().on_timeout()
		self.bot = None
		self.invoker = None
		self.user = None
		self.master_user = None

		self.get_item("check_badges").callback = None

	async def button_callback(self, interaction: discord.Interaction):
		if interaction.custom_id != "check_badges":
			return

		badges = await self.master_user.get_badges()
		if len(badges) == 0:
			return await interaction.respond(
				STRINGS("generic.badges_not_found", is_author=self.master_user.discord_id == interaction.user.id), ephemeral=True
			)

		await interaction.respond(view=UserBadges(self.bot, interaction.user, self.user, badges), ephemeral=True)


class ContractsProfile(DesignerView):
	def __init__(
		self,
		bot: "Natsumin",
		invoker: discord.User,
		user: discord.Member | discord.User,
		master_user: contracts.MasterUser,
		season_user: contracts.SeasonUser,
		*,
		season: str = config.active_season,
	):
		super().__init__(disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.user = user
		self.master_user = master_user
		self.season_user = season_user
		self.season = season

		username = f"<@{user.id}>" if user else master_user.username
		user_details = (
			STRINGS("contracts.seasonprofile.description.header", user=username)
			+ "\n"
			+ STRINGS(
				"contracts.seasonprofile.description.common",
				status_name=get_user_status_name(UserStatus(season_user.status)),
				status_emote=get_status_emote(UserStatus(season_user.status)),
			)
		)

		if season_user.kind == UserKind.AID:
			user_details += STRINGS("contracts.seasonprofile.description.kind.aid")
		else:
			user_details += STRINGS(
				"contracts.seasonprofile.description.kind.normal",
				rep=season_user.rep,
				contractor=season_user.contractor,
				list_url=season_user.list_url,
				preferences=season_user.preferences,
				bans=season_user.bans,
				accepting_ln=season_user.accepting_ln,
				accepting_manhwa=season_user.accepting_manhwa,
				veto_used=season_user.veto_used,
			)

		buttons = ActionRow(
			Button(
				style=discord.ButtonStyle.secondary,
				label=STRINGS("contracts.seasonprofile.buttons.get_contractor_profile"),
				disabled=season_user.contractor is None,
				custom_id="get_contractor_profile",
			),
			# Button(style=discord.ButtonStyle.secondary, label=STRINGS("contracts.seasonprofile.buttons.get_contractee_profile"), disabled=True, custom_id="get_contractee_profile"),
			Button(style=discord.ButtonStyle.secondary, label=STRINGS("contracts.seasonprofile.buttons.get_contracts"), custom_id="get_contracts"),
		)

		for button in buttons.children:
			button.callback = self.button_callback

		self.add_item(
			Container(
				Section(TextDisplay(user_details), accessory=Thumbnail(user.display_avatar.url)) if user else TextDisplay(user_details),
				Separator(),
				buttons,
				TextDisplay(f"-# <:Kirburger:998705274074435584> {utils.get_deadline_footer(season)}"),
				color=config.base_embed_color,
			)
		)

	async def on_timeout(self):
		await super().on_timeout()

		self.bot = None
		self.invoker = None
		self.user = None
		self.master_user = None
		self.season_user = None
		self.season = None

		for item in self.children:
			if hasattr(item, "callback"):
				item.callback = None

	async def button_callback(self, interaction: discord.Interaction):
		match interaction.custom_id:
			case "get_contractor_profile":
				if not self.season_user.contractor:
					return await interaction.respond("This user does not have a contractor!", ephemeral=True)
				user, master_user = await self.bot.get_targeted_user(self.season_user.contractor, return_as_master=True)
				if not master_user:
					return await interaction.respond("Could not find the contractor!", ephemeral=True)

				season_user = await self.season_user._db.fetch_user(master_user.id)
				if not season_user:
					return await interaction.respond("Could not find the contractor!", ephemeral=True)

				await interaction.respond(
					view=ContractsProfile(self.bot, interaction.user, user, master_user, season_user, season=self.season), ephemeral=True
				)
			case "get_contractee_profile":
				await interaction.respond(STRINGS("generic.unimplemented"), ephemeral=True)
			case "get_contracts":
				order_data = await self.season_user._db.get_order_data()
				user_contracts = await self.season_user.get_contracts()

				await interaction.respond(
					view=UserContracts(
						self.bot, interaction.user, self.user, self.season_user, self.master_user, self.season, user_contracts, order_data
					),
					ephemeral=True,
				)
			case _:
				return


class UserContracts(DesignerView):
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
		super().__init__(store=False)

		username = f"<@{user.id}>" if user else master_user.username

		footer_messages: list[str] = []

		user_status_name = get_user_status_name(UserStatus(season_user.status))
		user_status_emote = get_status_emote(UserStatus(season_user.status))

		user_details = (
			STRINGS("contracts.get.description.header", user=username)
			+ "\n"
			+ STRINGS("contracts.get.description.common", status_name=user_status_name, status_emote=user_status_emote)
		)

		if season_user.kind == UserKind.AID:
			user_details += STRINGS("contracts.get.description.kind.aid")
		else:
			user_details += STRINGS("contracts.get.description.kind.normal", contractor=season_user.contractor)

		category_texts: dict[str, str] = {}

		contracts_in_categories: dict[str, list[contracts.Contract]] = {}
		category_counts: dict[str, list[int]] = {}
		unselected_contracts: list[contracts.Contract] = []

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
				contract_name = contract.name

				status_emote: str = None
				if contract.name.strip().lower() in NEED_TO_SELECT_STRINGS:
					status_emote = "⚠️"
					contract_name = f"**__{contract_name}__**"
					unselected_contracts.append(contract)
				else:
					status_emote = get_status_emote(contract.status, contract.optional)
				text_contract_stats.append(
					STRINGS(
						"contracts.get.categories.entry", status_emote=status_emote, type=contract.type, name=contract_name, link=contract.review_url
					)
				)

			category_texts[category_name] = (
				STRINGS(
					"contracts.get.categories.header",
					name=category_name,
					passed=category_counts[category_name][1],
					total=category_counts[category_name][0],
				)
				+ f"\n{'\n'.join(text_contract_stats)}"
			)

			if category_counts[category_name][1] == category_counts[category_name][0]:
				footer_messages.append(
					STRINGS("contracts.get.footer_messages.category_finished", is_author=invoker.name == master_user.username, name=category_name)
				)

		sorted_categories_text = "\n".join(
			category_texts[category_name] for category_name in utils.sort_contract_categories(order_data) if category_name in category_texts
		)

		if unselected_contracts:
			formatted_unselected = utils.format_list([f"**{contract.type}**" for contract in unselected_contracts])
			footer_messages.append(
				STRINGS(
					"contracts.get.footer_messages.contract_unselected",
					is_author=invoker.name == master_user.username,
					unselected_types=formatted_unselected,
				)
			)

		container = Container(
			Section(TextDisplay(user_details), accessory=Thumbnail(user.display_avatar.url)) if user else TextDisplay(user_details),
			Separator(),
			TextDisplay(sorted_categories_text),
			color=config.base_embed_color,
		)
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

	@user_group.command(name="profile", description="Fetch the global profile of a user")
	@discord.option("user", description="The user to get profile of", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def globalprofile(self, ctx: discord.ApplicationContext, user: str = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if not utils.is_channel(ctx, 1002056335845752864):
			hidden = True

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond(STRINGS("generic.user_not_found"), ephemeral=True)

		legacy_exp = await m_user.get_legacy_exp()

		await ctx.respond(view=MasterUserProfile(self.bot, ctx.author, selected_user, m_user, legacy_exp=legacy_exp), ephemeral=hidden)

	@user_group.command(description="Fetch the badges of a user")
	@discord.option("user", description="The user to see badges from", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def badges(self, ctx: discord.ApplicationContext, user: str = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if not utils.is_channel(ctx, 1002056335845752864):
			hidden = True

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond(STRINGS("generic.user_not_found"), ephemeral=True)

		badges = await m_user.get_badges()
		if len(badges) == 0:
			return await ctx.respond(STRINGS("generic.badges_not_found", is_author=m_user.discord_id == ctx.author.id), ephemeral=True)

		await ctx.respond(view=UserBadges(self.bot, ctx.author, selected_user, badges), ephemeral=hidden)

	@contracts_subgroup.command(name="get", description="Fetch the contracts of a user")
	@discord.option(
		"user",
		description="The user to see contracts of, only autocompletes from active season",
		default=None,
		autocomplete=usernames_autocomplete(True),
	)
	@discord.option("season", description="Season to get data from, defaults to active", default=None, choices=contracts.AVAILABLE_SEASONS)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def s_contracts(self, ctx: discord.ApplicationContext, user: str = None, season: str = None, hidden: bool = False):
		if user is None:
			user = ctx.author
		if season is None:
			season = config.active_season

		if not utils.is_channel(ctx, 1002056335845752864):
			hidden = True

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond(STRINGS("generic.user_not_found"), ephemeral=True)

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.respond(STRINGS("generic.season_not_found", season=season), ephemeral=True)
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.respond(STRINGS("generic.user_not_in_season", season=season, user=m_user.username), ephemeral=True)

		order_data = await season_db.get_order_data()
		user_contracts = await s_user.get_contracts()

		await ctx.respond(
			view=UserContracts(self.bot, ctx.author, selected_user, s_user, m_user, season, user_contracts, order_data), ephemeral=hidden
		)

	@contracts_subgroup.command(name="profile", description="Fetch the seasonal profile of a user")
	@discord.option(
		"user",
		description="The user to see profile of, only autocompletes from active season",
		default=None,
		autocomplete=usernames_autocomplete(True),
	)
	@discord.option("season", description="Season to get data from, defaults to active", default=None, choices=contracts.AVAILABLE_SEASONS)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def profile(self, ctx: discord.ApplicationContext, user: str = None, season: str = None, hidden: bool = False):
		if user is None:
			user = ctx.author
		if season is None:
			season = config.active_season

		if not utils.is_channel(ctx, 1002056335845752864):
			hidden = True

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.respond(STRINGS("generic.user_not_found"), ephemeral=True)

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.respond(STRINGS("generic.season_not_found", season=season), ephemeral=True)
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.respond(STRINGS("generic.user_not_in_season", season=season, user=m_user.username), ephemeral=True)

		await ctx.respond(view=ContractsProfile(self.bot, ctx.author, selected_user, m_user, s_user, season=season), ephemeral=hidden)

	@commands.command("badges", aliases=["b"], help="Fetch the badges of a user")
	@utils.must_be_channel(1002056335845752864)
	async def text_badges(self, ctx: commands.Context, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply(STRINGS("generic.user_not_found"))

		badges = await m_user.get_badges()
		if len(badges) == 0:
			return await ctx.reply(STRINGS("generic.badges_not_found", is_author=m_user.discord_id == ctx.author.id))

		await ctx.reply(view=UserBadges(self.bot, ctx.author, selected_user, badges))

	@commands.command("globalprofile", aliases=["gp"], help="Fetch the global profile of a user")
	@utils.must_be_channel(1002056335845752864)
	async def text_globalprofile(self, ctx: commands.Context, user: str = None):
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply(STRINGS("generic.user_not_found"))

		legacy_exp = await m_user.get_legacy_exp()

		await ctx.reply(view=MasterUserProfile(self.bot, ctx.author, selected_user, m_user, legacy_exp=legacy_exp))

	@commands.command("contracts", aliases=["c"], help="Fetch the status of your contracts")
	@utils.must_be_channel(1002056335845752864)
	async def text_contracts(self, ctx: commands.Context, user: str = None, *, flags: ExtraFlags):
		season = flags.season
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply(STRINGS("generic.user_not_found"))

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.reply(STRINGS("generic.season_not_found", season=season))
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.reply(STRINGS("generic.user_not_in_season", season=season, user=m_user.username))

		order_data = await season_db.get_order_data()
		user_contracts = await s_user.get_contracts()

		await ctx.reply(view=UserContracts(self.bot, ctx.author, selected_user, s_user, m_user, season, user_contracts, order_data))

	@commands.command("seasonprofile", aliases=["sp", "p", "profile"], help="Fetch the seasonal profile of a user")
	@utils.must_be_channel(1002056335845752864)
	async def text_profile(self, ctx: commands.Context, user: str = None, *, flags: ExtraFlags):
		season = flags.season
		if user is None:
			user = ctx.author

		selected_user, m_user = await self.bot.get_targeted_user(user, return_as_master=True)
		if not m_user:
			return await ctx.reply(STRINGS("generic.user_not_found"))

		try:
			season_db = await contracts.get_season_db(season)
		except ValueError:
			return await ctx.reply(STRINGS("generic.season_not_found", season=season))
		s_user = await season_db.fetch_user(m_user.id)

		if not s_user:
			return await ctx.reply(STRINGS("generic.user_not_in_season", season=season, user=m_user.username))

		await ctx.reply(view=ContractsProfile(self.bot, ctx.author, selected_user, m_user, s_user, season=season))


def setup(bot):
	bot.add_cog(ContractsUser(bot))
