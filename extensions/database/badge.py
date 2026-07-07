from __future__ import annotations

from internal.functions import frmt_iter, badge_autocomplete
from internal.constants import BADGE_RARITIES, BADGE_TYPES
from internal.contracts import usernames_autocomplete
from internal.base.context import NatsuAppContext
from internal.schemas import BadgeData
from internal.base.cog import NatsuCog
from internal.constants import COLORS
from uuid import uuid4

import discord

from .groups import badge_subgroup


class BadgeCog(NatsuCog):
	@badge_subgroup.command(description="Add a new badge")
	@discord.option("name", str, min_length=1)
	@discord.option("description", str, default=None)
	@discord.option("artist", str, default=None)
	@discord.option("image_url", str, default=None)
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default="contracts")
	@discord.option("rarity", str, choices=BADGE_RARITIES, default="common")
	async def add(
		self,
		ctx: NatsuAppContext,
		name: str,
		description: str | None = None,
		artist: str | None = None,
		image_url: str | None = None,
		badge_type: str = "contracts",
		rarity: str = "common",
	):
		if rarity not in BADGE_RARITIES:
			return await ctx.respond(f"Rarity must be set to one of the following: {frmt_iter(rarity, final='or')}")
		if badge_type not in BADGE_TYPES:
			return await ctx.respond(f"Type must be set to one of the following: {frmt_iter(BADGE_TYPES, final='or')}")

		async with self.bot.database.connect() as conn:
			badge_id = uuid4()
			await conn.execute(
				"INSERT INTO badge (id, name, description, artist, url, type, rarity) VALUES (?, ?, ?, ?, ?, ?, ?)",
				(
					str(badge_id),
					name,
					description if description is not None else "",
					artist if artist is not None else "",
					image_url if image_url is not None else "",
					badge_type,
					rarity,
				),
			)
			await conn.commit()

		await ctx.respond(f"Created badge **{name}** ({badge_id})", ephemeral=True)

	@badge_subgroup.command(description="Edit a existing badge")
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("name", str, min_length=1, default=None)
	@discord.option("description", str, default=None)
	@discord.option("artist", str, default=None)
	@discord.option("image_url", str, default=None)
	@discord.option("type", str, choices=BADGE_TYPES, parameter_name="badge_type", default=None)
	@discord.option("rarity", str, choices=BADGE_RARITIES, default=None)
	async def edit(
		self,
		ctx: NatsuAppContext,
		id: str,
		name: str | None = None,
		description: str | None = None,
		artist: str | None = None,
		image_url: str | None = None,
		badge_type: str | None = None,
		rarity: str | None = None,
	):
		if (
			name is None and description is None and artist is None and image_url is None and badge_type is None and rarity is None
		):  # No changes only id was passed
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

			if rarity is not None:
				if rarity not in BADGE_RARITIES:
					modifications_done.append(f"Attempted to set rarity to a unknown one: **{rarity}**, no changes were made.")
				else:
					await conn.execute("UPDATE badge SET rarity = ? WHERE id = ?", (rarity, id))
					modifications_done.append(f"Changed rarity to **{rarity}**")

			embed = discord.Embed(title="Modifications", color=COLORS.DEFAULT)
			embed.set_footer(text=f"ID: {badge_row['id']}")
			if modifications_done:
				await conn.commit()
				embed.description = "\n".join(f"- {m}" for m in modifications_done)
			else:
				embed.description = "No modifications done."

			await ctx.respond("Done! Below is a list of all the modifications done.", embed=embed, ephemeral=True)

	@badge_subgroup.command(description="Delete a existing badge")
	@discord.option("id", str, autocomplete=badge_autocomplete)
	async def delete(self, ctx: NatsuAppContext, id: str):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT 1 FROM badge WHERE id = ?", (id,)) as cursor:
				badge_exists = (await cursor.fetchone()) is not None
				if not badge_exists:
					return await ctx.respond("Badge not found.", ephemeral=True)

			async with conn.execute("DELETE FROM badge WHERE id = ? RETURNING *", (id,)) as cursor:
				badge_row = await cursor.fetchone()

			await conn.commit()

		await ctx.respond(f"Deleted badge **{badge_row['name']}**", ephemeral=True)

	@badge_subgroup.command(description="Give a badge to a user/multiple users")
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("user", str, autocomplete=usernames_autocomplete(False), default=None)
	@discord.option("multiple_users", str, description="Usernames/ids separated by a comma, includes user if set", default=None)
	@discord.option(
		"users_file", discord.Attachment, description="A file full of usernames/ids, can be separated by a comma or newlines", default=None
	)
	async def give(
		self, ctx: NatsuAppContext, id: str, user: str | None = None, multiple_users: str | None = None, users_file: discord.Attachment | None = None
	):
		list_of_users: list[str] = []
		if user is not None and user.strip():
			list_of_users.append(user.strip())
		if multiple_users is not None:
			list_of_users.extend(u.strip() for u in multiple_users.split(",") if u.strip())
		if users_file is not None:
			raw_text = (await users_file.read()).decode()
			lines = raw_text.split("\n")
			for line in lines:
				list_of_users.extend(u.strip() for u in line.split(",") if u.strip())

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

		await ctx.respond(
			f"Gave **{badge_row['name']}** to **{len(valid_users)}** user{'s' if len(valid_users) > 1 else ''}!"
			+ (f"\n**{len(already_has_users)}** users already have the badge: {frmt_iter(already_has_users)}" if already_has_users else ""),
			ephemeral=True,
		)

	@badge_subgroup.command(description="Give a badge to all users that own a role")
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("role", discord.Role)
	async def giverole(self, ctx: NatsuAppContext, id: str, role: discord.Role):
		if not role.members:
			return await ctx.respond("Could not find any users with this role!", ephemeral=True)

		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT * FROM badge WHERE id = ?", (id,)) as cursor:
				badge_row = await cursor.fetchone()
				if not badge_row:
					return await ctx.respond("Badge not found.", ephemeral=True)

			valid_users: list[str] = []
			already_has_users: list[str] = []
			invalid_users: list[str] = []
			for user in role.members:
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

		await ctx.respond(
			f"Gave **{badge_row['name']}** to **{len(valid_users)}** user{'s' if len(valid_users) > 1 else ''}!"
			+ (f"\n**{len(already_has_users)}** users already have the badge: {frmt_iter(already_has_users)}" if already_has_users else ""),
			ephemeral=True,
		)

	@badge_subgroup.command(description="Remove a badge from a user")
	@discord.option("id", str, autocomplete=badge_autocomplete)
	@discord.option("user", str, autocomplete=usernames_autocomplete(False))
	async def remove(self, ctx: NatsuAppContext, id: str, user: str):
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
