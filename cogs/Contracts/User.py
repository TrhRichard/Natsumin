from discord.ui import View, Container, TextDisplay, Separator, MediaGallery, Section, Thumbnail, Button
from discord.ext import commands
from discord.commands import SlashCommandGroup
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


def reps_autocomplete(seasonal: bool = True):
	async def callback(ctx: discord.AutocompleteContext):
		return await utils.contracts.get_reps(query=ctx.value.strip(), limit=25, seasonal=seasonal)

	return callback


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
			TextDisplay(f"-# Badge ID: {badge.id}"),
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


class ContractsUser(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.contracts")

	user_group = SlashCommandGroup("user", description="Various user related commands", guild_ids=config.guild_ids)

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


def setup(bot):
	bot.add_cog(ContractsUser(bot))
