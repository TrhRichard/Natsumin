from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER, BADGE_RARITIES, BADGE_TYPES
from internal.base.paginator import CustomPaginator, V2Paginator, V2Page
from internal.base.context import NatsuContext, NatsuAppContext
from internal.contracts import usernames_autocomplete
from internal.checks import whitelist_channel_only
from internal.functions import get_user_config
from typing import TYPE_CHECKING, Literal
from internal.base.cog import NatsuCog
from internal.schemas import BadgeData
from internal.constants import COLORS
from discord.ext import commands
from config import GUILD_IDS
from discord import ui

if TYPE_CHECKING:
	from internal.base.bot import NatsuBot

import logging
import discord


async def get_badge_members_callback(badge_data: BadgeData, interaction: discord.Interaction):
	bot: NatsuBot = interaction.client
	async with bot.database.connect() as conn:
		query = """
			SELECT 
				u.username, u.discord_id
			FROM user u
			JOIN user_badge ub ON ub.user_id = u.id
			WHERE ub.badge_id = ?
			ORDER BY 
				ub.added_at,
				u.username
		"""
		async with conn.execute(query, (badge_data["id"],)) as cursor:
			user_rows: list[tuple[str, int]] = [(row["username"], row["discord_id"]) for row in await cursor.fetchall()]

		if not user_rows:
			all_pages = [discord.Embed(title=f"Owners of {badge_data['name']} (0 users)", description="No users found!", color=COLORS.DEFAULT)]
		else:
			await interaction.response.defer(ephemeral=True)

			all_pages = []
			for start in range(0, len(user_rows), 15):
				lines = []
				for i, (username, discord_id) in enumerate(user_rows[start : start + 15], start=start):
					full_name = f"<@{discord_id}> ({username})" if discord_id else username
					line_to_add = f"{i + 1}. {full_name}"

					lines.append(line_to_add)

				embed = discord.Embed(
					title=f"Owners of {badge_data['name']} ({len(user_rows)} users)", description="\n".join(lines), color=COLORS.DEFAULT
				)
				all_pages.append(embed)

	paginator = CustomPaginator(all_pages)
	await paginator.respond(interaction, ephemeral=True)


def get_badge_page(badge: BadgeData) -> V2Page:
	if badge["url"]:
		badge_art = ui.MediaGallery()
		badge_art.add_item(badge["url"], description=badge["artist"])
	else:
		badge_art = ui.TextDisplay("No image available.")

	badge_details: tuple[str, ...] = (
		f"Artist: {badge['artist'] if badge['artist'] else 'None'}",
		f"Rarity: {badge['rarity'].upper()}",
		f"Type: {badge['type'].upper()}",
		("Owned" if badge.get("author_owns_badge", False) else "Not Owned"),
	)

	badge_members_button = ui.Button(
		style=discord.ButtonStyle.secondary,
		label=str(badge["badge_count"]),
		disabled=badge.get("badge_count", 0) <= 0,
		emoji="<:users:1463527744230133831>",
		custom_id="get_badge_users",
	)

	async def callback(interaction: discord.Interaction):
		await get_badge_members_callback(badge, interaction)

	badge_members_button.callback = callback

	return V2Page(
		[
			ui.Container(
				ui.TextDisplay(f"## {badge['name']}\n{badge['description']}"),
				ui.TextDisplay("\n".join(badge_details)),
				ui.Separator(),
				badge_art,
				color=COLORS.DEFAULT,
			)
		],
		extra_buttons=(badge_members_button,),
	)


def get_badge_pages_list(badges: list[BadgeData], badges_per_page: int = 10) -> list[V2Page]:
	pages: list[V2Page] = []

	for start in range(0, len(badges), badges_per_page):
		lines = []
		for i, badge_data in enumerate(badges[start : start + badges_per_page], start=start):
			user_owns_badge: str = "Yes" if badge_data["author_owns_badge"] else "No"
			line_to_add = f"{i + 1}. **{badge_data['name']}**\n  - Rarity: `{badge_data['rarity'].upper()}` | Type: `{badge_data['type'].upper()}` | Owned: `{user_owns_badge}`"

			lines.append(line_to_add)

		page = V2Page([ui.Container(ui.TextDisplay("\n".join(lines)))])
		pages.append(page)

	return pages


class FindFlags(commands.FlagConverter, delimiter="=", prefix="--"):
	name: str = commands.flag(aliases=["n"], default=None, positional=True)
	owned_user: str | int | discord.abc.User = commands.flag(aliases=["u"], default=None)
	owned: bool = commands.flag(aliases=["o"], default=None)
	type: Literal["contracts", "aria", "event", "misc"] = commands.flag(aliases=["t"], default=None)
	rarity: Literal["common", "uncommon", "rare", "epic", "legendary", "limited"] = commands.flag(aliases=["r"], default=None)


class BadgesExt(NatsuCog, name="Badges"):
	"""Badges related commands"""

	def __init__(self, bot: NatsuBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.badges")
		self.is_syncing_enabled = True
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/badges.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

	async def cog_before_invoke(self, ctx: NatsuContext | NatsuAppContext):
		await ctx.bot.ensure_user(ctx.author)

	badge_group = discord.commands.SlashCommandGroup("badge", description="Various badge related commands", guild_ids=GUILD_IDS)

	async def badge_find_handler(
		self,
		invoker: discord.abc.User,
		name: str | None = None,
		owned_user: str | None = None,
		owned: bool | None = None,
		badge_type: str | None = None,
		rarity: str | None = None,
		hidden: bool = False,
	) -> tuple[str | V2Paginator, bool]:
		async with self.bot.database.connect() as conn:
			select_list: list[str] = ["b.*"]
			where_conditions: list[str] = []
			where_params = []
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(invoker, db_conn=conn)
			author_display_badge_type: Literal["one", "list"] = "one"
			if author_user_id is not None:
				joins_list.append("""
					LEFT JOIN user_badge aub ON
						aub.badge_id = b.id
						AND aub.user_id = ?
				""")
				joins_params.append(author_user_id)
				select_list.append("(aub.badge_id IS NOT NULL) AS author_owns_badge")

				user_config = await get_user_config(conn, author_user_id)
				author_display_badge_type = user_config.badge_display_type
			else:
				select_list.append("NULL AS author_owns_badge")

			if name is not None:
				where_conditions.append("name LIKE ?")
				where_params.append(f"%{name}%")

			if badge_type is not None:
				where_conditions.append("type = ?")
				where_params.append(badge_type)

			if rarity is not None:
				where_conditions.append("rarity = ?")
				where_params.append(rarity)

			if owned is not None and owned_user is None:
				owned_user = invoker

			if owned_user is not None:
				if owned is None:
					owned = True
				owned_user_id, _ = await self.bot.fetch_user_from_database(owned_user, db_conn=conn)

				if owned_user_id is None:
					return "No badges found due to owned_user not being in the database.", True

				joins_list.append("""
					LEFT JOIN user_badge ub ON 
						ub.badge_id = b.id
						AND ub.user_id = ?
				""")
				joins_params.append(owned_user_id)

				where_conditions.append("ub.badge_id IS NOT NULL" if owned else "ub.badge_id IS NULL")

			select_list.append("""
				(
					SELECT COUNT(*)
					FROM user_badge ubc
					WHERE ubc.badge_id = b.id
				) AS badge_count
			""")

			query = f"""
				SELECT
					{", ".join(select_list)}
				FROM badge b
				{"\n".join(joins_list)}
				{f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""}
				ORDER BY 
					CASE
						WHEN b.type = "contracts" THEN 0 
						WHEN b.type = "aria" THEN 1
						WHEN b.type = "blitz" THEN 2
						WHEN b.type = "event" THEN 3 
						WHEN b.type = "misc" THEN 4
						ELSE 99
					END,
					CASE
						WHEN b.rarity = "limited" THEN 0 
						WHEN b.rarity = "legendary" THEN 1
						WHEN b.rarity = "epic" THEN 2 
						WHEN b.rarity = "rare" THEN 3 
						WHEN b.rarity = "uncommon" THEN 4 
						WHEN b.rarity = "common" THEN 5 
						ELSE 99
					END,
					b.created_at,
					CASE
						WHEN b.url == "" THEN 1
						ELSE 0
					END,
					b.name
			"""

			if joins_list:
				params.extend(joins_params)
			if where_conditions:
				params.extend(where_params)

			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return "No badges found with specified filters.", True

		if author_display_badge_type == "one" or len(badges) == 1:
			pages = [get_badge_page(badge_data) for badge_data in badges]
		else:
			pages = get_badge_pages_list(badges)

		return V2Paginator(pages), hidden

	async def badge_inventory_handler(
		self, invoker: discord.abc.User, user: str | None, badge_type: str | None = None, rarity: str | None = None, hidden: bool = False
	) -> tuple[str | V2Paginator, bool]:
		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return "User not found!", True

			select_list: list[str] = ["b.*"]
			where_conditions: list[str] = ["ub.user_id = ?"]
			where_params = [user_id]
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(invoker, db_conn=conn)
			author_display_badge_type: Literal["one", "list"] = "one"
			if author_user_id is not None:
				joins_list.append("""
					LEFT JOIN user_badge aub ON
						aub.badge_id = b.id
						AND aub.user_id = ?
				""")
				joins_params.append(author_user_id)
				select_list.append("(aub.badge_id IS NOT NULL) AS author_owns_badge")

				user_config = await get_user_config(conn, author_user_id)
				author_display_badge_type = user_config.badge_display_type
			else:
				select_list.append("NULL AS author_owns_badge")

			if badge_type is not None:
				where_conditions.append("type = ?")
				where_params.append(badge_type)

			if rarity is not None:
				where_conditions.append("rarity = ?")
				where_params.append(rarity)

			select_list.append("""
				(
					SELECT COUNT(*)
					FROM user_badge ubc
					WHERE ubc.badge_id = b.id
				) AS badge_count
			""")

			query = f"""
				SELECT
					{", ".join(select_list)}
				FROM user_badge ub 
				JOIN badge b ON 
					ub.badge_id = b.id 
				{"\n".join(joins_list)}
				{f" WHERE {' AND '.join(where_conditions)}" if where_conditions else ""}
				ORDER BY 
					CASE
						WHEN b.type = "contracts" THEN 0 
						WHEN b.type = "aria" THEN 1
						WHEN b.type = "blitz" THEN 2
						WHEN b.type = "event" THEN 3 
						WHEN b.type = "misc" THEN 4
						ELSE 99
					END,
					CASE
						WHEN b.rarity = "limited" THEN 0 
						WHEN b.rarity = "legendary" THEN 1
						WHEN b.rarity = "epic" THEN 2 
						WHEN b.rarity = "rare" THEN 3 
						WHEN b.rarity = "uncommon" THEN 4 
						WHEN b.rarity = "common" THEN 5 
						ELSE 99
					END,
					b.created_at,
					CASE
						WHEN b.url == "" THEN 1
						ELSE 0
					END,
					b.name
			"""

			if joins_list:
				params.extend(joins_params)
			if where_conditions:
				params.extend(where_params)

			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return f"{"You don't" if discord_user and invoker.id == discord_user.id else "This user doesn't"} have any badges.", True

		if author_display_badge_type == "one" or len(badges) == 1:
			pages = [get_badge_page(badge_data) for badge_data in badges]
		else:
			pages = get_badge_pages_list(badges)

		return V2Paginator(pages), hidden

	async def badge_leaderboard_handler(
		self, invoker: discord.abc.User, leaderboard_type: Literal["badges", "users"], user_badge_type: str | None = None, hidden: bool = False
	) -> tuple[CustomPaginator, bool]:
		async with self.bot.database.connect() as conn:
			if user_badge_type is not None:
				leaderboard_type = "users"

			if leaderboard_type == "users":
				query = f"""
						SELECT
							u.username,
							u.discord_id,
							{"SUM(CASE WHEN b.type = ? THEN 1 ELSE 0 END)" if user_badge_type else "COUNT(ub.badge_id)"} AS badge_count
						FROM user u
						JOIN user_badge ub ON 
							ub.user_id = u.id
						{"JOIN badge b ON b.id = ub.badge_id" if user_badge_type is not None else ""}
						GROUP BY u.id, u.username
						HAVING badge_count > 0
						ORDER BY badge_count DESC, u.username ASC
					"""
				params = []
				if user_badge_type is not None:
					params.append(user_badge_type)

				async with conn.execute(query, params) as cursor:
					user_rows: list[tuple[str, int, int]] = [
						(row["username"], row["discord_id"], row["badge_count"]) for row in await cursor.fetchall()
					]

					all_pages = []
					for start in range(0, len(user_rows), 15):
						lines = []
						for i, (username, discord_id, badge_count) in enumerate(user_rows[start : start + 15], start=start):
							full_name = f"<@{discord_id}> ({username})" if discord_id else username
							line_to_add = f"{i + 1}. {full_name}: **{badge_count}**"

							lines.append(line_to_add)

						embed = discord.Embed(
							title=f"Users leaderboard{f' ({user_badge_type.upper()})' if user_badge_type is not None else ''}",
							description="\n".join(lines),
							color=COLORS.DEFAULT,
						)
						all_pages.append(embed)
			else:
				query = """
						SELECT
							b.name,
							COUNT(ub.user_id) AS user_count
						FROM badge b
						LEFT JOIN user_badge ub
							ON ub.badge_id = b.id
						GROUP BY b.id, b.name
						ORDER BY user_count DESC, b.created_at DESC, b.name ASC
					"""

				async with conn.execute(query) as cursor:
					badge_rows: list[tuple[str, int]] = [(row["name"], row["user_count"]) for row in await cursor.fetchall()]

					all_pages = []
					for start in range(0, len(badge_rows), 15):
						lines = []
						for i, (badge_name, user_count) in enumerate(badge_rows[start : start + 15], start=start):
							line_to_add = f"{i + 1}. {badge_name}: **{user_count}**"

							lines.append(line_to_add)

						embed = discord.Embed(title="Badges leaderboard", description="\n".join(lines), color=COLORS.DEFAULT)
						all_pages.append(embed)

			return CustomPaginator(all_pages), hidden

	@badge_group.command(description="Get badges")
	@discord.option("name", str, min_length=1, default=None)
	@discord.option("owned", bool, default=None)
	@discord.option("owned_user", str, description="User to check owned status of", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default=None)
	@discord.option("rarity", str, choices=BADGE_RARITIES, default=None)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def find(
		self,
		ctx: NatsuAppContext,
		name: str | None = None,
		owned_user: str | None = None,
		owned: bool | None = None,
		badge_type: str | None = None,
		rarity: str | None = None,
		hidden: bool = False,
	):
		if (await self.bot.is_blacklisted(ctx))[0]:
			hidden = True

		content, is_hidden = await self.badge_find_handler(ctx.author, name, owned_user, owned, badge_type, rarity, hidden)
		if isinstance(content, V2Paginator):
			return await content.respond(ctx.interaction, ephemeral=is_hidden)
		else:
			return await ctx.respond(content, ephemeral=is_hidden)

	@badge_group.command(description="Get the badges of a user")
	@discord.option("user", str, description="The user to get badges from", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default=None)
	@discord.option("rarity", str, choices=BADGE_RARITIES, default=None)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def inventory(self, ctx: NatsuAppContext, user: str | None, badge_type: str | None = None, rarity: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if (await self.bot.is_blacklisted(ctx))[0]:
			hidden = True

		content, is_hidden = await self.badge_inventory_handler(ctx.author, user, badge_type, rarity, hidden)
		if isinstance(content, V2Paginator):
			return await content.respond(ctx.interaction, ephemeral=is_hidden)
		else:
			return await ctx.respond(content, ephemeral=is_hidden)

	@badge_group.command(description="Leaderboard of badge/user badge counts")
	@discord.option("type", str, choices=["badges", "users"], parameter_name="leaderboard_type", default="badges")
	@discord.option("user_badge_type", str, choices=BADGE_TYPES, default=None)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def leaderboard(self, ctx: NatsuAppContext, leaderboard_type: Literal["badges", "users"], user_badge_type: str | None, hidden: bool):
		if (await self.bot.is_blacklisted(ctx))[0]:
			hidden = True

		paginator, is_hidden = await self.badge_leaderboard_handler(ctx.author, leaderboard_type, user_badge_type, hidden)
		await paginator.respond(ctx.interaction, ephemeral=is_hidden)

	@badge_group.command(name="toggle-view", description="Toggle the viewing of badges to either list or one-by-one")
	async def toggle_view(self, ctx: NatsuAppContext):
		async with self.bot.database.connect() as conn:
			user_id, _ = await self.bot.fetch_user_from_database(ctx.author, db_conn=conn)
			if user_id is None:
				return await ctx.respond("User not found!", ephemeral=True)

			user_config = await get_user_config(conn, user_id)

			badge_display_type: Literal["one", "list"] = user_config.badge_display_type
			badge_display_type = "list" if badge_display_type == "one" else "one"

			await conn.execute("UPDATE user_config SET badge_display_type = ? WHERE user_id = ?", (badge_display_type, user_id))
			await conn.commit()
			await ctx.respond(f"Changed badge display type from `{user_config.badge_display_type}` to `{badge_display_type}`!", ephemeral=True)

	@commands.group(
		"badge",
		help="Badges related commands",
		aliases=["b", "badges"],
		description="If no sub-command is specified then inventory command will run",
		invoke_without_command=True,
	)
	async def badge_textgroup(self, ctx: NatsuContext, user: str | int = None):
		if await self.text_inventory.can_run(ctx):
			await self.text_inventory(ctx, user)

	@badge_textgroup.command("find", aliases=["list", "search", "query"], help="Get badges")
	@whitelist_channel_only()
	async def text_find(self, ctx: NatsuContext, *, flags: FindFlags):
		content, _ = await self.badge_find_handler(ctx.author, flags.name, flags.owned_user, flags.owned, flags.type, flags.rarity, False)
		if isinstance(content, V2Paginator):
			return await content.reply(ctx)
		else:
			return await ctx.reply(content)

	@badge_textgroup.command("inventory", aliases=["inv", "i"], help="Get the badges of a user")
	@whitelist_channel_only()
	async def text_inventory(self, ctx: NatsuContext, user: str | int = None):
		if user is None:
			user = ctx.author

		content, _ = await self.badge_inventory_handler(ctx.author, user, None, None, False)
		if isinstance(content, V2Paginator):
			return await content.reply(ctx)
		else:
			return await ctx.reply(content)

	@badge_textgroup.command("leaderboard", aliases=["lb"], help="Leaderboard of badge/user badge counts")
	@whitelist_channel_only()
	async def text_leaderboard(self, ctx: NatsuContext, leaderboard_type: Literal["badges", "users"] = "badges"):
		paginator, _ = await self.badge_leaderboard_handler(ctx.author, leaderboard_type, None, False)
		await paginator.send(ctx, reference=ctx.message)


def setup(bot: NatsuBot):
	bot.add_cog(BadgesExt(bot))
