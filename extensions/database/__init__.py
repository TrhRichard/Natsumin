from __future__ import annotations

from internal.contracts.rep import get_rep, get_rep_from_member
from internal.base.context import NatsuAppContext, NatsuContext
from internal.constants import FILE_LOGGING_FORMATTER
from internal.exceptions import UnauthorizedUser
from internal.functions import rep_autocomplete
from typing import TYPE_CHECKING
from uuid import uuid4

import discord
import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuBot

from .groups import database_group
from .badge import BadgeCog


class DatabaseExt(BadgeCog, name="Database"):
	"""Database modification related commands"""

	def __init__(self, bot: NatsuBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.database")
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/database.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

	async def cog_before_invoke(self, ctx: NatsuContext | NatsuAppContext):
		await ctx.bot.ensure_user(ctx.author)

	async def cog_check(self, ctx: NatsuContext | NatsuAppContext):
		if not await self.bot.is_editor(ctx.author):
			raise UnauthorizedUser()

		return True

	database_group = database_group

	@database_group.command(name="create-user", description="Create a new user")
	@discord.option("user", discord.Member)
	@discord.option("rep", str, default=None, autocomplete=rep_autocomplete)
	async def create_user(self, ctx: NatsuAppContext, user: discord.Member, rep: str | None = None, gen: int | None = None):
		async with self.bot.database.connect() as conn:
			async with conn.execute("SELECT id FROM user WHERE username = ? or discord_id = ?", (user.name, user.id)) as cursor:
				row = await cursor.fetchone()
				if row:
					return await ctx.respond("User already exists!", ephemeral=True)

			if rep is None:
				user_rep = get_rep_from_member(user)
				if user_rep == "UNKNOWN":
					return await ctx.respond("Could not identify a rep from the user's roles, please specify a rep manually.", ephemeral=True)
			else:
				user_rep = get_rep(rep, 90)
				if not user_rep:
					return await ctx.respond(f"Could not identify a proper rep for {rep}", ephemeral=True)

			user_id = str(uuid4())

			await conn.execute(
				"INSERT INTO user (id, username, discord_id, rep, gen) VALUES (?, ?, ?, ?, ?)", (user_id, user.name, user.id, user_rep.value, gen)
			)
			await conn.commit()

			await ctx.respond(f"Added {user.name} to the database ({user_id})", ephemeral=True)


def setup(bot: NatsuBot):
	bot.add_cog(DatabaseExt(bot))
