from __future__ import annotations

from internal.contracts.seasons import SeasonX
from internal.functions import diff_to_str
from typing import TYPE_CHECKING

import aiosqlite
import datetime
import discord
import time

if TYPE_CHECKING:
	from internal.database import NatsuminDatabase
	from internal.base.bot import NatsuminBot


async def sync_season(database: NatsuminDatabase, season_id: str) -> float:
	if season_id not in database.available_seasons:
		raise ValueError(f"Invalid season: {season_id}")

	start = time.perf_counter()

	match season_id:
		case "season_x":
			await SeasonX.sync_season(database)

	return time.perf_counter() - start


async def get_deadline_footer(database: NatsuminDatabase, season_id: str, *, db_conn: aiosqlite.Connection = None) -> str:
	if season_id not in database.available_seasons:
		raise ValueError(f"Invalid season: {season_id}")

	async with database.connect(db_conn) as conn:
		active_season = await database.get_config("contracts.active_season", db_conn=conn)
		if active_season is None:
			raise RuntimeError("Active season not found!")

		deadline_datetime = await database.get_config("contracts.deadline_datetime", db_conn=conn)
		deadline_datetime = datetime.datetime.fromisoformat(deadline_datetime) if deadline_datetime else None

		deadline_footer = await database.get_config("contracts.deadline_footer", db_conn=conn)
		if deadline_footer is None:
			deadline_footer = "Season deadline in {time_till}."

		async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
			season_name: str = (await cursor.fetchone())["name"]

	if season_id == active_season:
		if deadline_datetime is None:
			return f"Deadline for {season_name} unknown."

		current_datetime = datetime.datetime.now(datetime.UTC)
		difference = deadline_datetime - current_datetime
		difference_seconds = max(difference.total_seconds(), 0)

		if difference_seconds > 0:
			return deadline_footer.format(time_till=diff_to_str(deadline_datetime, current_datetime, include_seconds=False))
		else:
			return f"{season_name} has ended."
	else:
		return f"Archived data from {season_name}."


async def season_autocomplete(ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
	bot: NatsuminBot = ctx.bot
	async with bot.database.connect() as conn:
		async with conn.execute("SELECT id, name FROM season WHERE id LIKE ?1 OR name LIKE ?1", (f"%{ctx.value.strip()}%",)) as cursor:
			season_list = [discord.OptionChoice(name=row["name"], value=row["id"]) for row in await cursor.fetchall()]

	return season_list


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
