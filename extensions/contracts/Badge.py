from __future__ import annotations

from internal.checks import must_be_channel, can_modify_badges
from internal.contracts import usernames_autocomplete
from internal.functions import is_channel, frmt_iter
from internal.base.paginator import CustomPaginator
from internal.base.view import BadgeDisplay
from internal.base.cog import NatsuminCog
from typing import TYPE_CHECKING, Literal
from internal.schemas import BadgeData
from internal.constants import COLORS
from discord.ext import commands
from config import GUILD_IDS
from uuid import uuid4

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot

import datetime
import discord

BADGE_TYPES = ["contracts", "aria", "event", "misc"]


async def badge_autocomplete(ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
	bot: NatsuminBot = ctx.bot
	async with bot.database.connect() as conn:
		query = """
			SELECT
				id, name, type
			FROM badge
			WHERE id = ?1 OR name LIKE ?1
			ORDER BY type, created_at DESC, name
			LIMIT 25
		"""
		async with conn.execute(query, (f"%{ctx.value.strip()}%",)) as cursor:
			badge_list = [discord.OptionChoice(name=f"{row['name']} ({row['type']})", value=row["id"]) for row in await cursor.fetchall()]

	return badge_list


class FindFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	name: str = commands.flag(aliases=["n"], default=None, positional=True)
	owned_user: str | int | discord.abc.User = commands.flag(aliases=["u"], default=None)
	owned: bool = commands.flag(aliases=["o"], default=None)
	type: Literal["contracts", "aria", "event", "misc"] = commands.flag(aliases=["t"], default=None)


class BadgeCog(NatsuminCog):
	badge_group = discord.commands.SlashCommandGroup("badge", description="Various badge related commands", guild_ids=GUILD_IDS)

	async def badge_find_handler(
		self,
		invoker: discord.abc.User,
		name: str | None = None,
		owned_user: str | None = None,
		owned: bool | None = None,
		badge_type: str | None = None,
		hidden: bool = False,
	) -> tuple[str | BadgeDisplay, bool]:
		async with self.bot.database.connect() as conn:
			select_list: list[str] = ["b.*"]
			where_conditions: list[str] = []
			where_params = []
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(invoker, db_conn=conn)
			if author_user_id is not None:
				joins_list.append("""
					LEFT JOIN user_badge aub ON
						aub.badge_id = b.id
						AND aub.user_id = ?
				""")
				joins_params.append(author_user_id)
				select_list.append("(aub.badge_id IS NOT NULL) AS author_owns_badge")
			else:
				select_list.append("NULL AS author_owns_badge")

			if name is not None:
				where_conditions.append("name LIKE ?")
				where_params.append(f"%{name}%")

			if badge_type is not None:
				where_conditions.append("type = ?")
				where_params.append(badge_type)

			if owned is not None:
				if owned_user is None:
					owned_user = invoker
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
						WHEN b.type = "event" THEN 2 
						WHEN b.type = "misc" THEN 3 
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

		return BadgeDisplay(invoker, badges), hidden

	async def badge_inventory_handler(self, invoker: discord.abc.User, user: str | None, hidden: bool) -> tuple[str | BadgeDisplay, bool]:
		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return "User not found!", True

			select_list: list[str] = ["b.*"]
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(invoker, db_conn=conn)
			if author_user_id is not None:
				joins_list.append("""
					LEFT JOIN user_badge aub ON
						aub.badge_id = b.id
						AND aub.user_id = ?
				""")
				joins_params.append(author_user_id)
				select_list.append("(aub.badge_id IS NOT NULL) AS author_owns_badge")
			else:
				select_list.append("NULL AS author_owns_badge")

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
				WHERE 
					ub.user_id = ? 
				ORDER BY 
					CASE
						WHEN b.type = "contracts" THEN 0 
						WHEN b.type = "aria" THEN 1
						WHEN b.type = "event" THEN 2 
						WHEN b.type = "misc" THEN 3 
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

			params.append(user_id)
			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return f"{"You don't" if invoker.id == discord_user.id else "This user doesn't"} have any badges.", True

		return BadgeDisplay(invoker, badges), hidden

	async def badge_leaderboard_handler(
		self, invoker: discord.abc.User, leaderboard_type: Literal["badges", "users"], hidden: bool
	) -> tuple[CustomPaginator, bool]:
		async with self.bot.database.connect() as conn:
			if leaderboard_type == "users":
				query = """
						SELECT
							u.username,
							u.discord_id,
							COUNT(ub.badge_id) AS badge_count
						FROM user u
						JOIN user_badge ub ON 
							ub.user_id = u.id
						GROUP BY u.id, u.username
						ORDER BY badge_count DESC, u.username ASC
					"""

				async with conn.execute(query) as cursor:
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

						embed = discord.Embed(title="Users leaderboard", description="\n".join(lines), color=COLORS.DEFAULT)
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
	@discord.option(
		"owned_user",
		str,
		description="User to check owned status of, does nothing if owned is not set",
		default=None,
		autocomplete=usernames_autocomplete(False),
	)
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default=None)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def find(
		self,
		ctx: discord.ApplicationContext,
		name: str | None = None,
		owned_user: str | None = None,
		owned: bool | None = None,
		badge_type: str | None = None,
		hidden: bool = False,
	):
		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		content, is_hidden = await self.badge_find_handler(ctx.author, name, owned_user, owned, badge_type, hidden)
		if isinstance(content, BadgeDisplay):
			return await ctx.respond(view=content, ephemeral=is_hidden)
		else:
			return await ctx.respond(content, ephemeral=is_hidden)

	@badge_group.command(description="Get the badges of a user")
	@discord.option("user", str, description="The user to get badges from", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def inventory(self, ctx: discord.ApplicationContext, user: str | None, hidden: bool):
		if user is None:
			user = ctx.author

		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		content, is_hidden = await self.badge_inventory_handler(ctx.author, user, hidden)
		if isinstance(content, BadgeDisplay):
			return await ctx.respond(view=content, ephemeral=is_hidden)
		else:
			return await ctx.respond(content, ephemeral=is_hidden)

	@badge_group.command(description="Leaderboard of badge/user badge counts")
	@discord.option("type", str, choices=["badges", "users"], parameter_name="leaderboard_type", default="badges")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def leaderboard(self, ctx: discord.ApplicationContext, leaderboard_type: Literal["badges", "users"], hidden: bool):
		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		paginator, is_hidden = await self.badge_leaderboard_handler(ctx.author, leaderboard_type, hidden)
		await paginator.respond(ctx.interaction, ephemeral=is_hidden)

	@commands.group("badge", help="Badges related commands", aliases=["b"], invoke_without_command=True)
	async def badge_textgroup(self, ctx: commands.Context, user: str | int = None):
		if await self.text_inventory.can_run(ctx):
			await self.text_inventory(ctx, user)

	@badge_textgroup.command("find", aliases=["list", "search", "query"], help="Get badges")
	@must_be_channel(1002056335845752864)
	async def text_find(self, ctx: commands.Context, *, flags: FindFlags):
		content, _ = await self.badge_find_handler(ctx.author, flags.name, flags.owned_user, flags.owned, flags.type, False)
		if isinstance(content, BadgeDisplay):
			return await ctx.reply(view=content)
		else:
			return await ctx.reply(content)

	@badge_textgroup.command("inventory", aliases=["inv", "i"], help="Get the badges of a user")
	@must_be_channel(1002056335845752864)
	async def text_inventory(self, ctx: commands.Context, user: str | int = None):
		if user is None:
			user = ctx.author

		content, _ = await self.badge_inventory_handler(ctx.author, user, False)
		if isinstance(content, BadgeDisplay):
			return await ctx.reply(view=content)
		else:
			return await ctx.reply(content)

	@badge_textgroup.command("leaderboard", aliases=["lb"], help="Leaderboard of badge/user badge counts")
	@must_be_channel(1002056335845752864)
	async def text_leaderboard(self, ctx: commands.Context, leaderboard_type: Literal["badges", "users"] = "badges"):
		paginator, _ = await self.badge_leaderboard_handler(ctx.author, leaderboard_type, False)
		await paginator.send(ctx, reference=ctx.message)

	# Badge management commands

	@badge_group.command(description="Add a new badge")
	@can_modify_badges()
	@discord.option("name", str, min_length=1)
	@discord.option("description", str, default=None)
	@discord.option("artist", str, default=None)
	@discord.option("image_url", str, default=None)
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default="contracts")
	async def add(
		self,
		ctx: discord.ApplicationContext,
		name: str,
		description: str | None = None,
		artist: str | None = None,
		image_url: str | None = None,
		badge_type: str = "contracts",
	):
		async with self.bot.database.connect() as conn:
			badge_id = uuid4()
			await conn.execute(
				"INSERT INTO badge (id, name, description, artist, url, type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
				(
					str(badge_id),
					name,
					description if description is not None else "",
					artist if artist is not None else "",
					image_url if image_url is not None else "",
					badge_type,
					datetime.datetime.now(datetime.UTC).isoformat(" "),
				),
			)
			await conn.commit()

		await ctx.respond(f"Created badge **{name}** ({badge_id})", ephemeral=True)

	@badge_group.command(description="Edit a existing badge")
	@can_modify_badges()
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("name", str, min_length=1, default=None)
	@discord.option("description", str, default=None)
	@discord.option("artist", str, default=None)
	@discord.option("image_url", str, default=None)
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default=None)
	async def edit(
		self,
		ctx: discord.ApplicationContext,
		id: str,
		name: str | None = None,
		description: str | None = None,
		artist: str | None = None,
		image_url: str | None = None,
		badge_type: str | None = None,
	):
		if name is None and description is None and artist is None and image_url is None and badge_type is None:  # No changes only id was passed
			return await ctx.respond("No changes were specified.", ephemeral=True)

		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT * FROM badge WHERE id = ?", (id,)) as cursor:
				badge_row: BadgeData = await cursor.fetchone()
				if badge_row is None:
					return await ctx.respond("Badge not found!", ephemeral=True)

			modifications_done: list[str] = []

			if name is not None:
				await conn.execute("UPDATE badge SET name = ? WHERE id = ?", (name, id))
				modifications_done.append(f"Changed name to **{name}**")

			if description is not None:
				await conn.execute("UPDATE badge SET description = ? WHERE id = ?", (description, id))
				modifications_done.append(f"Changed description to **{description}**")

			if artist is not None:
				await conn.execute("UPDATE badge SET artist = ? WHERE id = ?", (artist, id))
				modifications_done.append(f"Changed artist to **{artist}**")

			if image_url is not None:
				await conn.execute("UPDATE badge SET url = ? WHERE id = ?", (image_url, id))
				modifications_done.append(f"Changed url to **{image_url}**")

			if badge_type is not None:
				await conn.execute("UPDATE badge SET type = ? WHERE id = ?", (badge_type, id))
				modifications_done.append(f"Changed type to **{badge_type}**")

			embed = discord.Embed(title="Modifications", color=COLORS.DEFAULT)
			embed.set_footer(text=f"ID: {badge_row['id']}")
			if modifications_done:
				await conn.commit()
				embed.description = "\n".join(f"- {m}" for m in modifications_done)
			else:
				embed.description = "No modifications done."

			await ctx.respond("Done! Below is a list of all the modifications done.", embed=embed, ephemeral=True)

	@badge_group.command(description="Delete a existing badge")
	@can_modify_badges()
	@discord.option("id", str, autocomplete=badge_autocomplete)
	async def delete(self, ctx: discord.ApplicationContext, id: str):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT 1 FROM badge WHERE id = ?", (id,)) as cursor:
				badge_exists = (await cursor.fetchone()) is not None
				if not badge_exists:
					return await ctx.respond("Badge not found.", ephemeral=True)

			async with conn.execute("DELETE FROM badge WHERE id = ? RETURNING *", (id,)) as cursor:
				badge_row = await cursor.fetchone()

			await conn.commit()

		await ctx.respond(f"Deleted badge **{badge_row['name']}**", ephemeral=True)

	@badge_group.command(description="Give a badge to a user/multiple users")
	@can_modify_badges()
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("user", str, autocomplete=usernames_autocomplete(False), default=None)
	@discord.option("multiple_users", str, description="Usernames/ids separated by a comma, includes user if set", default=None)
	async def give(self, ctx: discord.ApplicationContext, id: str, user: str | None = None, multiple_users: str | None = None):
		list_of_users: list[str] = []
		if user is not None and user.strip():
			list_of_users.append(user.strip())
		if multiple_users is not None:
			list_of_users.extend(u.strip() for u in multiple_users.split(",") if u.strip())

		list_of_users = list(set(list_of_users))

		if not list_of_users:
			return await ctx.respond("Must have at least 1 user to give the badge to.", ephemeral=True)

		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT * FROM badge WHERE id = ?", (id,)) as cursor:
				badge_row = await cursor.fetchone()
				if not badge_row:
					return await ctx.respond("Badge not found.", ephemeral=True)

			valid_users: list[str] = []
			already_has_users: list[str] = []
			invalid_users: list[str] = []
			for user in list_of_users:
				user_id, _ = await self.bot.fetch_user_from_database(user, db_conn=conn)

				if (user_id in valid_users) or (user_id in invalid_users) or (user_id in already_has_users):
					continue

				if user_id is None:
					invalid_users.append(user)
					continue

				async with conn.execute("SELECT 1 FROM user_badge WHERE user_id = ? AND badge_id = ?", (user_id, id)) as cursor:
					if (await cursor.fetchone()) is not None:
						already_has_users.append(user)
						continue

				valid_users.append(user_id)

			if invalid_users:
				return await ctx.respond(
					f"Attempted to give badge **{badge_row['name']}** to invalid users: {frmt_iter(invalid_users)}", ephemeral=True
				)

			await conn.executemany("INSERT INTO user_badge (user_id, badge_id) VALUES (?, ?)", [(user_id, id) for user_id in valid_users])
			await conn.commit()

		message = f"Gave **{badge_row['name']}** to **{len(valid_users)}** users!"
		if already_has_users:
			message += f"\n**{len(already_has_users)}** users already have the badge: {frmt_iter(already_has_users)}"

		await ctx.respond(message, ephemeral=True)

	@badge_group.command(description="Remove a badge from a user")
	@can_modify_badges()
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("user", str, autocomplete=usernames_autocomplete(False))
	async def remove(self, ctx: discord.ApplicationContext, id: str, user: str):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT * FROM badge WHERE id = ?", (id,)) as cursor:
				badge_row = await cursor.fetchone()
				if not badge_row:
					return await ctx.respond("Badge not found.", ephemeral=True)

			user_id, _ = await self.bot.fetch_user_from_database(user, db_conn=conn)
			async with conn.execute("SELECT username FROM user WHERE id = ?", (user_id,)) as cursor:
				username: str = (await cursor.fetchone())["username"]

			async with conn.execute("SELECT 1 FROM user_badge WHERE user_id = ? AND badge_id = ?", (user_id, id)) as cursor:
				if (await cursor.fetchone()) is None:
					return await ctx.respond(f"{username} doesn't have the badge!", ephemeral=True)

			await conn.execute("DELETE FROM user_badge WHERE user_id = ? AND badge_id = ?", (user_id, id))
			await conn.commit()

		await ctx.respond(f"Removed **{badge_row['name']}** from {username}!", ephemeral=True)
