from __future__ import annotations

from internal.functions import get_legacy_rank, get_rank_emoteid, is_channel, get_status_emote, get_status_name, frmt_iter
from internal.contracts import get_deadline_footer, season_autocomplete, usernames_autocomplete
from internal.contracts.order import OrderContractData, sort_contract_types
from internal.enums import UserKind, UserStatus, ContractStatus
from internal.checks import must_be_channel
from internal.base.view import BadgeDisplay
from internal.base.cog import NatsuminCog
from internal.schemas import BadgeData
from internal.constants import COLORS
from discord.ext import commands
from typing import TYPE_CHECKING
from config import GUILD_IDS
from discord import ui

import discord

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


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
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

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
				"SELECT u.username, u.discord_id, su.* FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND su.user_id = ?",
				(season_id, user_id),
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
					"SELECT u.username FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND su.contractor_id = ?",
					(season_id, user_id),
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
				await interaction.respond(
					view=await SeasonUserContracts.create(self.bot, interaction.user, self.season_id, self.user_id), ephemeral=True
				)
			case _:
				return


def get_formatted_contract(contract: OrderContractData, *, is_unselected: bool = False, include_review_url: bool = True) -> str:
	contract_name = f"[{contract['name']}]({contract['review_url']})" if (contract["review_url"] and include_review_url) else contract["name"]
	status_emote: str = ""
	if is_unselected:
		status_emote = "⚠️"
		contract_name = f"**__{contract_name}__**"
	else:
		status_emote = get_status_emote(ContractStatus(contract["status"]), contract["optional"])

	return f"> {status_emote} **{contract['type']}**: {contract_name}"


class SeasonUserContracts(ui.DesignerView):
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
				"SELECT u.username, u.discord_id, su.contractor_id, su.status, su.kind FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND su.user_id = ?",
				(season_id, user_id),
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
				user_description += f"- **Contractor**: {contractor_username or 'None'}\n"

			header_content = f"## {username}'s Contracts\n{user_description}"

			async with conn.execute(
				"SELECT name, type, kind, status, optional, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ?",
				(season_id, user_id),
			) as cursor:
				user_contracts: dict[str, OrderContractData] = {row["type"]: dict(row) for row in await cursor.fetchall()}

			async with conn.execute(
				"SELECT COUNT(*) as count FROM season_contract WHERE season_id = ? AND contractee_id = ? AND (review_url IS NOT NULL AND review_url != '')",
				(season_id, user_id),
			) as cursor:
				total_contracts_with_reviews: int = (await cursor.fetchone())["count"]

			season_order_data = self.bot.season_orders.get(self.season_id, [])
			footer_messages: list[str] = []
			unselected_types: list[str] = []

			category_texts: list[str] = []
			include_reviews: bool = total_contracts_with_reviews <= 20
			for category in sort_contract_types(user_contracts.keys(), season_order_data):
				passed = 0
				total = 0
				type_texts: list[str] = []

				for cat_type in category["types"]:
					contract = user_contracts.get(cat_type)
					if contract is None:
						continue
					total += 1
					if contract["status"] == ContractStatus.PASSED or contract["status"] == ContractStatus.LATE_PASS:
						passed += 1

					is_unselected = False
					if contract["name"].strip().lower() in ("please select", "undecided", "pending"):
						unselected_types.append(contract["type"])
						is_unselected = True

					type_texts.append(get_formatted_contract(contract, is_unselected=is_unselected, include_review_url=include_reviews))

				if passed == total:
					footer_messages.append(
						f"{'You have' if invoker.name == user_row['username'] else 'This user has'} finished all **{category['name']}**!"
					)

				category_texts.append(f"### {category['name']} ({passed}/{total})\n{'\n'.join(type_texts)}")

			sorted_categories_text = "\n".join(category_texts)

			if not include_reviews:
				footer_messages.append(
					f"{'You have' if invoker.name == user_row['username'] else 'This user has'} way too many contracts to display in one message, review urls have been disabled."
				)

			if unselected_types:
				footer_messages.append(
					f"{"You haven't" if invoker.name == user_row['username'] else "This user hasn't"} picked anything for {frmt_iter(f'**{type}**' for type in unselected_types)}!"
				)

			container = ui.Container(
				(
					ui.Section(ui.TextDisplay(header_content), accessory=ui.Thumbnail(discord_user.avatar.url))
					if discord_user and discord_user.avatar
					else ui.TextDisplay(header_content)
				),
				ui.Separator(),
				ui.TextDisplay(sorted_categories_text),
				color=COLORS.DEFAULT,
			)

			if footer_messages:
				container.add_text("\n".join([f"-# {msg}" for msg in footer_messages]))
			container.add_separator()
			container.add_text(f"-# <:Kirburger:998705274074435584> {await get_deadline_footer(self.bot.database, season_id, db_conn=conn)}")

		self.add_item(container)
		return self

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass


class SeasonUserFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	user: str | int | discord.abc.User = commands.flag(aliases=["u"], default=None, positional=True)
	season: str = commands.flag(aliases=["s"], default=None)


class UserCog(NatsuminCog):
	user_group = discord.commands.SlashCommandGroup("user", description="Various user related commands", guild_ids=GUILD_IDS)
	contracts_subgroup = user_group.create_subgroup("contracts", description="Various user contracts related commands")

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

	@contracts_subgroup.command(name="profile", description="Fetch the seasonal profile of a user")
	@discord.option(
		"user",
		str,
		description="The user to see profile of, only autocompletes from active season",
		default=None,
		autocomplete=usernames_autocomplete(True),
	)
	@discord.option("season", str, description="Season to get data from, defaults to active", default=None, autocomplete=season_autocomplete)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def profile(self, ctx: discord.ApplicationContext, user: str | None = None, season: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

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

			user_id, _ = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.respond("User not found!", ephemeral=True)

			async with conn.execute(
				"SELECT (SELECT name FROM season WHERE id = ?) as name, (SELECT username FROM user WHERE id = ?) as username", (season_id, user_id)
			) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]
				username = row["username"]

			async with conn.execute("SELECT 1 FROM season_user WHERE season_id = ? AND user_id = ?", (season_id, user_id)) as cursor:
				is_user_in_season = await cursor.fetchone()

			if not is_user_in_season:
				return await ctx.respond(f"{username} has not participated in {season_name}!", ephemeral=True)

		await ctx.respond(view=await SeasonUserProfile.create(self.bot, ctx.author, season_id, user_id), ephemeral=hidden)

	@contracts_subgroup.command(name="get", description="Fetch the contracts of a user")
	@discord.option(
		"user",
		str,
		description="The user to see contracts of, only autocompletes from active season",
		default=None,
		autocomplete=usernames_autocomplete(True),
	)
	@discord.option("season", str, description="Season to get data from, defaults to active", default=None, autocomplete=season_autocomplete)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def contracts(self, ctx: discord.ApplicationContext, user: str | None = None, season: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

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

			user_id, _ = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.respond("User not found!", ephemeral=True)

			async with conn.execute(
				"SELECT (SELECT name FROM season WHERE id = ?) as name, (SELECT username FROM user WHERE id = ?) as username", (season_id, user_id)
			) as cursor:
				row = await cursor.fetchone()
				season_name = row["name"]
				username = row["username"]

			async with conn.execute("SELECT 1 FROM season_user WHERE season_id = ? AND user_id = ?", (season_id, user_id)) as cursor:
				is_user_in_season = await cursor.fetchone()

			if not is_user_in_season:
				return await ctx.respond(f"{username} has not participated in {season_name}!", ephemeral=True)

		await ctx.respond(view=await SeasonUserContracts.create(self.bot, ctx.author, season_id, user_id), ephemeral=hidden)

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
	async def text_profile(self, ctx: commands.Context, *, flags: SeasonUserFlags):
		user = flags.user
		if user is None:
			user = ctx.author

		async with self.bot.database.connect() as conn:
			if flags.season is None:
				season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			else:
				season_id = flags.season

			if season_id not in self.bot.database.available_seasons:
				return await ctx.reply(
					f"Could not find season with the id **{season_id}**. If this is a real season it's likely the bot does not have any data about it."
				)

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

	@commands.command("contracts", aliases=["c"], help="Fetch the status of your contracts")
	@must_be_channel(1002056335845752864)
	async def text_contracts(self, ctx: commands.Context, *, flags: SeasonUserFlags):
		user = flags.user
		if user is None:
			user = ctx.author

		async with self.bot.database.connect() as conn:
			if flags.season is None:
				season_id = await self.bot.get_config("contracts.active_season", db_conn=conn)
			else:
				season_id = flags.season

			if season_id not in self.bot.database.available_seasons:
				return await ctx.reply(
					f"Could not find season with the id **{season_id}**. If this is a real season it's likely the bot does not have any data about it."
				)

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

		await ctx.reply(view=await SeasonUserContracts.create(self.bot, ctx.author, season_id, user_id))
