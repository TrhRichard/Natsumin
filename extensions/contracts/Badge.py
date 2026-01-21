from __future__ import annotations

from internal.checks import must_be_channel, can_modify_badges
from internal.contracts import usernames_autocomplete
from internal.functions import is_channel, frmt_iter
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
	type: Literal["contracts", "aria"] = commands.flag(aliases=["t"], default=None)


class BadgeCog(NatsuminCog):
	badge_group = discord.commands.SlashCommandGroup("badge", description="Various badge related commands", guild_ids=GUILD_IDS)

	@badge_group.command(description="Fetch badges")
	@discord.option("name", str, min_length=1, default=None)
	@discord.option("owned", bool, default=None)
	@discord.option(
		"owned_user",
		str,
		description="User to check owned status of, does nothing if owned is not set",
		default=None,
		autocomplete=usernames_autocomplete(False),
	)
	@discord.option("type", str, choices=["contracts", "aria"], parameter_name="badge_type", default=None)
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

		async with self.bot.database.connect() as conn:
			select_list: list[str] = ["b.*"]
			where_conditions: list[str] = []
			where_params = []
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(ctx.author, db_conn=conn)
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
					owned_user = ctx.author
				owned_user_id, _ = await self.bot.fetch_user_from_database(owned_user, db_conn=conn)

				if owned_user_id is None:
					return await ctx.respond("No badges found due to owned_user not being in the database.", ephemeral=True)

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
				ORDER BY b.type, b.created_at, b.name
			"""

			if joins_list:
				params.extend(joins_params)
			if where_conditions:
				params.extend(where_params)

			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return await ctx.respond("No badges found with specified filters.", ephemeral=True)

		await ctx.respond(view=BadgeDisplay(ctx.author, badges), ephemeral=hidden)

	@badge_group.command(description="Fetch the badges of a user")
	@discord.option("user", str, description="The user to fetch badges from", default=None, autocomplete=usernames_autocomplete(False))
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=True)
	async def inventory(self, ctx: discord.ApplicationContext, user: str | None = None, hidden: bool = False):
		if user is None:
			user = ctx.author

		if not is_channel(ctx, 1002056335845752864):
			hidden = True

		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.respond("User not found!", ephemeral=True)

			select_list: list[str] = ["b.*"]
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(ctx.author, db_conn=conn)
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
				ORDER BY b.type, b.created_at, b.name
			"""

			if joins_list:
				params.extend(joins_params)

			params.append(user_id)
			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return await ctx.respond(f"{"You don't" if ctx.author.id == discord_user.id else "This user doesn't"} have any badges.", ephemeral=True)

		await ctx.respond(view=BadgeDisplay(ctx.author, badges), ephemeral=hidden)

	@badge_group.command(description="Add a new badge")
	@can_modify_badges()
	@discord.option("name", str, min_length=1)
	@discord.option("description", str, default=None)
	@discord.option("artist", str, default=None)
	@discord.option("image_url", str, default=None)
	@discord.option("type", str, choices=["contracts", "aria"], parameter_name="badge_type", default="contracts")
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
	@discord.option("type", str, choices=["contracts", "aria"], parameter_name="badge_type", default=None)
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

	@commands.group("badge", help="Badges related commands", aliases=["b"], invoke_without_command=True)
	async def badge_textgroup(self, ctx: commands.Context, user: str | int | discord.abc.User = None):
		if await self.text_inventory.can_run(ctx):
			await self.text_inventory(ctx, user)

	@badge_textgroup.command("find", aliases=["list", "search", "query"], help="Fetch badges")
	@must_be_channel(1002056335845752864)
	async def text_find(self, ctx: commands.Context, *, flags: FindFlags):
		async with self.bot.database.connect() as conn:
			select_list: list[str] = ["b.*"]
			where_conditions: list[str] = []
			where_params = []
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(ctx.author, db_conn=conn)
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

			if flags.name is not None:
				where_conditions.append("name LIKE ?")
				where_params.append(f"%{flags.name}%")

			if flags.type is not None:
				where_conditions.append("type = ?")
				where_params.append(flags.type)

			if flags.owned is not None:
				owned_user = flags.owned_user
				if owned_user is None:
					owned_user = ctx.author
				owned_user_id, _ = await self.bot.fetch_user_from_database(owned_user, db_conn=conn)

				if owned_user_id is None:
					return await ctx.reply("No badges found due to owned_user not being in the database.")

				joins_list.append("""
					LEFT JOIN user_badge ub ON 
						ub.badge_id = b.id
						AND ub.user_id = ?
				""")
				joins_params.append(owned_user_id)

				where_conditions.append("ub.badge_id IS NOT NULL" if flags.owned else "ub.badge_id IS NULL")

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
				ORDER BY b.type, b.created_at, b.name
			"""

			if joins_list:
				params.extend(joins_params)
			if where_conditions:
				params.extend(where_params)

			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

		if len(badges) == 0:
			return await ctx.reply("No badges found.")

		await ctx.reply(view=BadgeDisplay(ctx.author, badges))

	@badge_textgroup.command("inventory", aliases=["inv", "i"], help="Fetch the badges of a user")
	@must_be_channel(1002056335845752864)
	async def text_inventory(self, ctx: commands.Context, user: str | int | discord.abc.User = None):
		if user is None:
			user = ctx.author

		async with self.bot.database.connect() as conn:
			user_id, discord_user = await self.bot.fetch_user_from_database(user, db_conn=conn)
			if not user_id:
				return await ctx.reply("User not found!")

			select_list: list[str] = ["b.*"]
			joins_list: list[str] = []
			joins_params = []
			params = []

			author_user_id, _ = await self.bot.fetch_user_from_database(ctx.author, db_conn=conn)
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
				ORDER BY b.type, b.created_at, b.name
			"""

			if joins_list:
				params.extend(joins_params)

			params.append(user_id)
			async with conn.execute(query, params) as cursor:
				badges: list[BadgeData] = [dict(row) for row in await cursor.fetchall()]

			if len(badges) == 0:
				return await ctx.reply(f"{"You don't" if ctx.author.id == discord_user.id else "This user doesn't"} have any badges.")

			await ctx.reply(view=BadgeDisplay(ctx.author, badges))
