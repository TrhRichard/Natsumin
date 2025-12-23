from __future__ import annotations

from internal.functions import get_legacy_rank, get_rank_emoteid, is_channel, get_status_emote, get_status_name, frmt_iter
from internal.contracts import get_deadline_footer
from internal.enums import UserKind, UserStatus
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


def usernames_autocomplete(seasonal: bool = True):
	async def callback(ctx: discord.AutocompleteContext) -> list[str]:
		bot: NatsuminBot = ctx.bot
		async with bot.database.connect() as conn:
			params = []
			query = "SELECT username FROM user WHERE username LIKE ?"
			if seasonal:
				query = "SELECT u.username FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND u.username LIKE ?"
				params.append(await bot.get_config("contracts.active_season", db_conn=conn))
			query += " LIMIT 25"
			params.append(f"%{ctx.value.strip()}%")

			async with conn.execute(query, params) as cursor:
				username_list: list[str] = [row["username"] for row in await cursor.fetchall()]

		return username_list

	return callback


class BadgeDisplay(ui.DesignerView):
	def __init__(self, invoker: discord.abc.User, badges: list[dict[str]]):
		super().__init__(disable_on_timeout=True)

		self.invoker = invoker
		self.badges = badges
		self.current_badge_selected = 0

		self.add_item(self.get_badge_container(badges[self.current_badge_selected]))

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass

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

	def get_badge_container(self, badge: dict[str]) -> ui.Container:
		badge_artist = ui.TextDisplay(f"-# Artist: {badge['artist']}" if badge["artist"] else "-# No artist")
		if badge["url"]:
			badge_art = ui.MediaGallery()
			badge_art.add_item(badge["url"], description=badge["artist"])
		else:
			badge_art = ui.TextDisplay("No image available.")

		page_buttons = ui.ActionRow(
			ui.Button(style=discord.ButtonStyle.secondary, label="<--", disabled=False, custom_id="previous"),
			ui.Button(
				style=discord.ButtonStyle.primary,
				label=f"{self.current_badge_selected + 1}/{len(self.badges)}",
				disabled=True,  # len(self.badges) == 1,
				custom_id="change_page",
			),
			ui.Button(style=discord.ButtonStyle.secondary, label="-->", disabled=False, custom_id="next"),
		)

		for button in page_buttons.children:
			button.callback = self.button_callback

		return ui.Container(
			ui.TextDisplay(f"## {badge['name']}\n{badge['description']}"),
			ui.TextDisplay(f"-# Type: {badge['type']}"),  # \n-# ID: {badge['id']}"),
			ui.Separator(),
			badge_art,
			badge_artist,
			ui.Separator(),
			page_buttons,
			color=COLORS.DEFAULT,
		)


class MasterUserProfile(ui.DesignerView):
	def __init__(self, bot: NatsuminBot, invoker: discord.abc.User, user_id: str):
		super().__init__(disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.user_id = user_id

	@classmethod
	async def create(cls, bot: NatsuminBot, invoker: discord.abc.User, user_id: str):
		self = cls(bot, invoker, user_id)

		async with bot.database.connect() as conn:
			async with conn.execute(
				"SELECT u.*, lbl.exp FROM user u LEFT JOIN leaderboard_legacy lbl ON u.id = lbl.user_id WHERE id = ?", (user_id,)
			) as cursor:
				user_row = await cursor.fetchone()

			if user_row is None:
				self.add_item(ui.TextDisplay("User data not found!"))

				return self

			_, discord_user = await bot.fetch_user_from_database(user_id, db_conn=conn)

			legacy_rank = get_legacy_rank(user_row["exp"])
			username = f"<@{discord_user.id}>" if discord_user else user_row["username"]

			profile_data = (
				(f"- **Rep**: {user_row['rep']}\n" if user_row["rep"] else "")
				+ (f"- **Generation**: {user_row['gen']}\n" if user_row["gen"] else "")
				+ (
					(
						"### Legacy Leaderboard\n"
						+ f"- **Rank**: {legacy_rank} <a:{legacy_rank.value}:{get_rank_emoteid(legacy_rank)}>\n"
						+ f"- **EXP**: {user_row['exp']}"
					)
					if user_row["exp"]
					else ""
				)
			)

			header_content = f"# {username}'s Profile\n{profile_data.strip() or 'No information available.'}"

			badges_button = ui.Button(style=discord.ButtonStyle.secondary, label="Check badges", custom_id="check_badges")
			badges_button.callback = self.button_callback

			self.add_item(
				ui.Container(
					(
						ui.Section(ui.TextDisplay(header_content), accessory=ui.Thumbnail(discord_user.avatar.url))
						if discord_user and discord_user.avatar
						else ui.TextDisplay(header_content)
					),
					ui.Separator(),
					ui.ActionRow(badges_button),
					color=COLORS.DEFAULT,
				)
			)

		return self

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass

	async def button_callback(self, interaction: discord.Interaction):
		if interaction.custom_id != "check_badges":
			return

		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT discord_id FROM user WHERE id = ?", (self.user_id,)) as cursor:
				discord_id: int | None = (await cursor.fetchone())["discord_id"]

			async with conn.execute(
				"SELECT b.* FROM user_badge ub JOIN badge b ON ub.badge_id = b.id WHERE ub.user_id = ?", (self.user_id,)
			) as cursor:
				badges = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return await interaction.respond(
				f"{"You don't" if interaction.user.id == discord_id else "This user doesn't"} have any badges.", ephemeral=True
			)

		await interaction.respond(view=BadgeDisplay(interaction.user, badges), ephemeral=True)


class SeasonUserProfile(ui.DesignerView):
	def __init__(self, bot: NatsuminBot, invoker: discord.abc.User, season_id: str, user_id: str):
		super().__init__(disable_on_timeout=True)
		self.bot = bot
		self.invoker = invoker
		self.season_id = season_id
		self.user_id = user_id

	@classmethod
	async def create(cls, bot: NatsuminBot, invoker: discord.abc.User, season_id: str, user_id: str):
		self = cls(bot, invoker, season_id, user_id)

		async with bot.database.connect() as conn:
			async with conn.execute(
				"SELECT u.username, u.discord_id, su.* FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.user_id = ?", (user_id,)
			) as cursor:
				user_row = await cursor.fetchone()

			if user_row is None:
				self.add_item(ui.TextDisplay("User data not found!"))

				return self

			if user_row["contractor_id"]:
				async with conn.execute("SELECT username FROM user WHERE id = ?", (user_row["contractor_id"],)) as cursor:
					row = await cursor.fetchone()
					contractor_username: str | None = row["username"]

			_, discord_user = await bot.fetch_user_from_database(user_id, db_conn=conn)

			username = f"<@{discord_user.id}>" if discord_user else user_row["username"]
			user_description = f"- **Status**: {get_status_name(UserStatus(user_row['status']))} {get_status_emote(UserStatus(user_row['status']))}\n"

			if user_row["kind"] == UserKind.NORMAL:
				user_description += f"- **Rep**: {user_row['rep'] or 'Unknown'}\n"
				user_description += f"- **Contractor**: {contractor_username or 'None'}\n"

				async with conn.execute(
					"SELECT u.username FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.contractor_id = ?", (user_id,)
				) as cursor:
					contractees = tuple(row["username"] for row in await cursor.fetchall())

				if contractees:
					user_description += f"- **Contractee{'s' if len(contractees) > 1 else ''}**: {frmt_iter(contractees)}\n"

				user_description += f"- **List**: {user_row['list_url'] or 'N/A'}\n"
				user_description += f"- **Preferences**: {(user_row['preferences'] or 'N/A').replace('\n', ', ')}\n"
				user_description += f"- **Bans**: {(user_row['bans'] or 'N/A').replace('\n', ', ')}\n"
				user_description += (
					f"- **Accepting**: LN={'Yes' if user_row['accepting_ln'] else 'No'} - MANHWA={'Yes' if user_row['accepting_manhwa'] else 'No'}\n"
				)
				user_description += f"- **Veto used**: {'Yes' if user_row['veto_used'] else 'No'}\n"
			else:
				user_description += "-# Information limited for people that joined this season for aids."

			header_content = f"## {username}'s Profile\n{user_description}"

			buttons = ui.ActionRow(
				ui.Button(
					style=discord.ButtonStyle.secondary,
					label="Get Contractor",
					disabled=user_row["contractor_id"] is None,
					custom_id="get_contractor_profile",
				),
				ui.Button(style=discord.ButtonStyle.secondary, label="Get Contractee", custom_id="get_contractee_profile"),
				ui.Button(style=discord.ButtonStyle.secondary, label="Check Contracts", custom_id="get_contracts"),
			)

			for button in buttons.children:
				button.callback = self.button_callback

			self.add_item(
				ui.Container(
					(
						ui.Section(ui.TextDisplay(header_content), accessory=ui.Thumbnail(discord_user.avatar.url))
						if discord_user and discord_user.avatar
						else ui.TextDisplay(header_content)
					),
					ui.Separator(),
					buttons,
					ui.TextDisplay(f"-# <:Kirburger:998705274074435584> {await get_deadline_footer(self.bot.database, season_id, db_conn=conn)}"),
					color=COLORS.DEFAULT,
				)
			)

		return self

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass

	async def button_callback(self, interaction: discord.Interaction):
		match interaction.custom_id:
			case "get_contractor_profile":
				async with self.bot.database.connect() as conn:
					async with conn.execute(
						"SELECT u.username, su.contractor_id FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND su.user_id = ? LIMIT 1",
						(self.season_id, self.user_id),
					) as cursor:
						row = await cursor.fetchone()

					if row is None:
						return await interaction.respond("Unknown user.", ephemeral=True)

					contractor_id: str | None = row["contractor_id"]
					username: str = row["username"]

					if contractor_id is None:
						return await interaction.respond(f"{username} does not have a contractor.", ephemeral=True)

				await interaction.respond(
					view=await SeasonUserProfile.create(self.bot, interaction.user, self.season_id, contractor_id), ephemeral=True
				)

			case "get_contractee_profile":
				async with self.bot.database.connect() as conn:
					async with conn.execute("SELECT username FROM user WHERE id = ?", (self.user_id,)) as cursor:
						row = await cursor.fetchone()

					if row is None:
						return await interaction.respond("Unknown user.", ephemeral=True)

					username = row["username"]

					async with conn.execute(
						"SELECT user_id as contractee_id FROM season_user WHERE season_id = ? AND contractor_id = ? LIMIT 1",
						(self.season_id, self.user_id),
					) as cursor:
						row = await cursor.fetchone()

					if row is None:
						return await interaction.respond(f"{username} does not have a contractee.", ephemeral=True)

					contractee_id: str | None = row["contractee_id"]

				await interaction.respond(
					view=await SeasonUserProfile.create(self.bot, interaction.user, self.season_id, contractee_id), ephemeral=True
				)
			case "get_contracts":
				pass
			case _:
				return


class User(NatsuminCog):
	user_group = discord.commands.SlashCommandGroup("user", description="Various user related commands", guild_ids=GUILD_IDS)

	@user_group.command(name="profile", description="Fetch the global profile of a user")
	@discord.option("user", str, description="The user to get profile of", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def globalprofile(self, ctx: discord.ApplicationContext, user: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		user_id, _ = await self.bot.fetch_user_from_database(user)
		if not user_id:
			return await ctx.respond("User not found!", ephemeral=True)

		await ctx.respond(view=await MasterUserProfile.create(self.bot, ctx.author, user_id), ephemeral=hidden)

	@user_group.command(description="Fetch the badges of a user")
	@discord.option("user", str, description="The user to see badges from", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def badges(self, ctx: discord.ApplicationContext, user: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.respond("User not found!", ephemeral=True)

			async with conn.execute("SELECT b.* FROM user_badge ub JOIN badge b ON ub.badge_id = b.id WHERE ub.user_id = ?", (user_id,)) as cursor:
				badges = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return await ctx.respond(f"{"You don't" if ctx.author.id == discord_user.id else "This user doesn't"} have any badges.", ephemeral=True)

		await ctx.respond(view=BadgeDisplay(ctx.author, badges), ephemeral=hidden)

	@commands.command("badges", aliases=["b"], help="Fetch the badges of a user")
	@must_be_channel(1002056335845752864)
	async def text_badges(self, ctx: commands.Context, user: str | int | discord.abc.User = None):
		if user is None:
			user = ctx.author

		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.reply("User not found!")

			async with conn.execute("SELECT b.* FROM user_badge ub JOIN badge b ON ub.badge_id = b.id WHERE ub.user_id = ?", (user_id,)) as cursor:
				badges = [dict(row) for row in await cursor.fetchall()]

			if len(badges) == 0:
				return await ctx.reply(f"{"You don't" if ctx.author.id == discord_user.id else "This user doesn't"} have any badges.")

			await ctx.reply(view=BadgeDisplay(ctx.author, badges))

	@commands.command("globalprofile", aliases=["gp"], help="Fetch the global profile of a user")
	@must_be_channel(1002056335845752864)
	async def text_globalprofile(self, ctx: commands.Context, user: str | int | discord.abc.User = None):
		if user is None:
			user = ctx.author

		user_id, _ = await self.bot.fetch_user_from_database(user)
		if not user_id:
			return await ctx.reply("User not found!")

		await ctx.reply(view=await MasterUserProfile.create(self.bot, ctx.author, user_id))

	@commands.command("seasonprofile", aliases=["sp", "p", "profile"], help="Fetch the seasonal profile of a user")
	@must_be_channel(1002056335845752864)
	async def text_profile(self, ctx: commands.Context, user: str | int | discord.abc.User = None):
		if user is None:
			user = ctx.author
		season_id = "season_x"

		if season_id not in self.bot.database.available_seasons:
			return await ctx.reply(
				f"Could not find season with the id **{season_id}**. If this is a real season it's likely the bot does not have any data about it."
			)

		async with self.bot.database.connect() as conn:
			user_id, _ = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.reply("User not found!")

			async with conn.execute(
				"SELECT (SELECT name FROM season WHERE id = ?) as name, (SELECT username FROM user WHERE id = ?) as username", (season_id, user_id)
			) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]
				username = row["username"]

			async with conn.execute("SELECT 1 FROM season_user WHERE season_id = ? AND user_id = ?", (season_id, user_id)) as cursor:
				is_user_in_season = await cursor.fetchone()

			if not is_user_in_season:
				return await ctx.reply(f"{username} has not participated in {season_name}!")

		await ctx.reply(view=await SeasonUserProfile.create(self.bot, ctx.author, season_id, user_id))
