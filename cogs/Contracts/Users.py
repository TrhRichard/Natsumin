from utils.contracts import get_common_embed, get_slash_reps, get_reps
from discord.ext import commands, pages
from typing import TYPE_CHECKING
from thefuzz import process
import contracts
import logging
import discord
import config

if TYPE_CHECKING:
	from main import Natsumin


def get_user_symbol(user: contracts.User) -> str:
	symbol = ""
	match user.status:
		case contracts.UserStatus.FAILED:
			symbol = "❌"
		case contracts.UserStatus.PASSED:
			symbol = "✅"
		case contracts.UserStatus.LATE_PASS:
			symbol = "⌛☑️"
		case contracts.UserStatus.INCOMPLETE:
			symbol = "⛔"
	return symbol


class ChangePageModal(discord.ui.Modal):
	def __init__(self, paginator: "UsersPaginator"):
		super().__init__(title="Change Page", timeout=60)
		self.paginator = paginator
		self.page_input = discord.ui.InputText(
			label="Page Number",
			placeholder=f"Enter a page number (1-{len(paginator.pages)})",
			required=True,
			max_length=3,
			min_length=1,
			style=discord.InputTextStyle.short,
		)
		self.add_item(self.page_input)

	async def callback(self, interaction: discord.Interaction):
		try:
			page_number = int(self.page_input.value) - 1
			if 0 <= page_number < len(self.paginator.pages):
				await self.paginator.goto_page(page_number)
				await interaction.respond(
					embed=discord.Embed(description=":white_check_mark: Page changed!", color=config.BASE_EMBED_COLOR), ephemeral=True
				)

			else:
				await interaction.response.send_message(
					embed=discord.Embed(description=":x: Invalid page number!", color=discord.Color.red()), ephemeral=True
				)
		except ValueError:
			await interaction.response.send_message(
				embed=discord.Embed(description=":x: Please enter a valid number!", color=discord.Color.red()), ephemeral=True
			)


class UsersPaginator(pages.Paginator):
	def __init__(self, *args, ephemeral=False, **kwargs):
		super().__init__(*args, **kwargs, timeout=600, show_disabled=True, show_indicator=True, author_check=True, use_default_buttons=False)
		self.add_button(pages.PaginatorButton("prev", label="Previous", style=discord.ButtonStyle.primary))

		page_indicator = pages.PaginatorButton("page_indicator", custom_id="page_indicator", style=discord.ButtonStyle.secondary, disabled=True)
		if len(self.pages) > 1 and not ephemeral:
			page_indicator.disabled = False
			page_indicator.callback = self.page_indicator_callback
		self.add_button(page_indicator)

		self.add_button(pages.PaginatorButton("next", label="Next", style=discord.ButtonStyle.primary))

	async def page_indicator_callback(self, interaction: discord.Interaction):
		if not self.pages:
			return await interaction.response.send_message(
				embed=discord.Embed(description=":x: No pages to display.", color=discord.Color.red()), ephemeral=True
			)
		await interaction.response.send_modal(ChangePageModal(self))


async def create_embed(
	bot: "Natsumin",
	status: contracts.UserStatus,
	rep: str,
	current_page: int,
	total_pages: int,
	offset: int = 0,
	season: str = config.BOT_CONFIG.active_season,
) -> discord.Embed:
	season_db = await contracts.get_season_db(season)
	query_params = {}
	if status:
		query_params["status"] = status
	if rep != "ALL":
		query_params["rep"] = rep

	users = await season_db.fetch_users(limit=25, offset=offset, sort=("status",), **query_params, kind=contracts.UserKind.NORMAL)

	status_name = (f"{status.name}" if status else "All").capitalize().replace("_", " ")
	embed = get_common_embed(season=season)
	embed.title = f"Contracts {season} - **{rep}** - {len(users)} {status_name} Users"
	if len(users) > 0:
		embed.description += "\n\n"
		usernames_to_display: list[str] = []
		for i, user in enumerate(users, 1):
			username = user.username

			usernames_to_display.append(f"{offset + i}. {username.replace('_', '\\_')} {get_user_symbol(user)}")
		embed.description += "\n".join(usernames_to_display)

	return embed


async def get_embed_pages(bot: "Natsumin", raw_status: str, rep: str, season: str = config.BOT_CONFIG.active_season) -> list[discord.Embed] | None:
	status = None
	match raw_status:
		case "all":
			status = None
		case "passed":
			status = contracts.UserStatus.PASSED
		case "failed":
			status = contracts.UserStatus.FAILED
		case "pending":
			status = contracts.UserStatus.PENDING
		case "late":
			status = contracts.UserStatus.LATE_PASS
		case "incomplete":
			status = contracts.UserStatus.INCOMPLETE

	season_db = await contracts.get_season_db(season)
	query_params = {}
	if status:
		query_params["status"] = status
	if rep != "ALL":
		query_params["rep"] = rep

	user_count = await season_db.count_users(**query_params, kind=contracts.UserKind.NORMAL)
	if user_count == 0:
		return None

	pages_list: list[discord.Embed] = []
	total_pages = (user_count + 24) // 25
	for i in range(0, user_count, 25):
		current_page = i // 25
		pages_list.append(await create_embed(bot, status, rep, current_page, total_pages, i, season))

	return pages_list


valid_statuses = ["all", "passed", "failed", "pending", "late", "incomplete"]


async def create_error_embed_status(status: str) -> discord.Embed:
	error_embed = discord.Embed(color=discord.Color.red())
	error_embed.description = f":x: Invalid status! Valid statuses are: {', '.join(f'`{s}`' for s in valid_statuses)}"
	return error_embed


async def create_error_embed_rep(season_db: contracts.SeasonDB, rep: str) -> discord.Embed:
	error_embed = discord.Embed(color=discord.Color.red())

	error_embed.description = ":x: Invalid rep!"

	reps = await get_reps(season_db)

	fuzzy_results: list[tuple[str, int]] = process.extract(rep, reps, limit=1)
	if len(fuzzy_results) > 0:
		fuzzy_rep, fuzzy_confidence = fuzzy_results[0]
		error_embed.description = f":x: Invalid rep! Did you mean **{fuzzy_rep}** ({fuzzy_confidence}%)?"

	return error_embed


class ContractsUsers(commands.Cog):
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

	@commands.slash_command(name="users", description="Get users", guilds_ids=config.BOT_CONFIG.guild_ids)
	@discord.option("status", description="Optionally get users of a specific status", default="all", choices=valid_statuses)
	@discord.option("rep", description="Optionally get users of a specific rep", default="ALL", autocomplete=get_slash_reps)
	@discord.option(
		"season", description="Optionally check in another season", default=config.BOT_CONFIG.active_season, choices=contracts.AVAILABLE_SEASONS
	)
	@discord.option("hidden", description="Optionally make the response only visible to you", default=False)
	async def users(self, ctx: discord.ApplicationContext, status: str, rep: str, season: str, hidden: bool):
		status = status.lower()
		rep = rep.upper()
		if status not in valid_statuses:
			return await ctx.respond(embed=await create_error_embed_status(status), ephemeral=hidden)

		season_db = await contracts.get_season_db(season)
		reps = await get_reps(season_db)
		if rep != "ALL" and rep not in reps:
			return await ctx.respond(embed=await create_error_embed_rep(season_db, rep), ephemeral=hidden)

		pages_list = await get_embed_pages(self.bot, status, rep, season)
		if pages_list is None:
			return await ctx.respond(
				embed=discord.Embed(description=":x: No users found for the specified criteria.", color=discord.Color.red()), ephemeral=hidden
			)
		paginator = UsersPaginator(pages=pages_list, ephemeral=hidden)
		await paginator.respond(ctx.interaction, ephemeral=hidden)

	@commands.command(name="users", aliases=["u"], help="Get users")
	async def text_users(self, ctx: commands.Context, status: str = "all", *, rep: str = "ALL"):
		status = status.lower()
		rep = rep.upper()
		if status not in valid_statuses:
			return await ctx.reply(embed=await create_error_embed_status(status))

		season_db = await contracts.get_season_db()
		reps = await get_reps(season_db)
		if rep != "ALL" and rep not in reps:
			return await ctx.reply(embed=await create_error_embed_rep(season_db, rep))

		pages_list = await get_embed_pages(self.bot, status, rep)
		if pages_list is None:
			return await ctx.reply(embed=discord.Embed(description=":x: No users found for the specified criteria.", color=discord.Color.red()))
		paginator = UsersPaginator(pages=pages_list)
		await paginator.send(ctx)


def setup(bot):
	bot.add_cog(ContractsUsers(bot))
