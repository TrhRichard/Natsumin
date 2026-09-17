from __future__ import annotations

from internal.functions import get_latest_deadline, diff_to_str
from internal.contracts.seasons import SeasonX, SeasonXI
from internal.base.context import NatsuAutoContext
from internal.sql import sanitize
from typing import TYPE_CHECKING

import aiosqlite
import datetime
import discord
import time

if TYPE_CHECKING:
	from internal.database import NatsuDatabase


async def sync_season(database: NatsuDatabase, season_id: str) -> float:
	if season_id not in database.available_seasons:
		raise ValueError(f"Invalid season: {season_id}")

	start = time.perf_counter()

	match season_id:
		case "season_x":
			await SeasonX.sync_season(database)
		case "season_xi":
			await SeasonXI.sync_season(database)

	return time.perf_counter() - start


def get_season_spreadsheet_ids(database: NatsuDatabase, season_id: str) -> tuple[str, str]:
	if season_id not in database.available_seasons:
		raise ValueError(f"Invalid season: {season_id}")

	match season_id:
		case "season_x":
			return SeasonX.SEASON_SPREADSHEET_ID, SeasonX.FANTASY_SPREADSHEET_ID
		case "season_xi":
			return SeasonXI.SEASON_SPREADSHEET_ID, SeasonXI.FANTASY_SPREADSHEET_ID

	raise RuntimeError(f"Could not find ids for season {season_id}")


async def get_deadline_footer(database: NatsuDatabase, season_id: str, *, db_conn: aiosqlite.Connection = None) -> str:
	if season_id not in database.available_seasons:
		raise ValueError(f"Invalid season: {season_id}")

	async with database.connect(db_conn) as conn:
		active_season = await database.get_config("contracts.active_season", db_conn=conn)
		if active_season is None:
			raise RuntimeError("Active season not found!")

		deadline_footer = await database.get_config("contracts.deadline_footer", db_conn=conn)
		if deadline_footer is None:
			deadline_footer = "{deadline_type} deadline in {time_till}."

		async with conn.execute("SELECT name FROM season WHERE id = ?", (season_id,)) as cursor:
			season_name: str = (await cursor.fetchone())["name"]

		if season_id == active_season:
			try:
				latest_deadline = await get_latest_deadline(conn, active_season)
			except ValueError:
				return f"Deadline for {season_name} unknown."

			current_datetime = datetime.datetime.now(datetime.UTC)
			difference = latest_deadline[1] - current_datetime
			difference_seconds = max(difference.total_seconds(), 0)

			if difference_seconds > 0:
				return deadline_footer.format(
					time_till=diff_to_str(latest_deadline[1], current_datetime, include_seconds=False), deadline_type=latest_deadline[0]
				)
			else:
				season_ended_footer = await database.get_config("contracts.season_ended_footer", db_conn=conn)
				if season_ended_footer is None:
					season_ended_footer = "{season_name} has ended."

				return season_ended_footer.format(season_name=season_name)
		else:
			archived_season_footer = await database.get_config("contracts.archived_season_footer", db_conn=conn)
			if archived_season_footer is None:
				archived_season_footer = "Archived data from {season_name}."

			return archived_season_footer.format(season_name=season_name)


async def season_autocomplete(ctx: NatsuAutoContext) -> list[discord.OptionChoice]:
	async with ctx.database.connect() as conn:  # noqa: SIM117
		async with conn.execute("SELECT id, name FROM season WHERE id LIKE ?1 OR name LIKE ?1", (f"%{sanitize(ctx.value.strip())}%",)) as cursor:
			season_list = [discord.OptionChoice(name=row["name"], value=row["id"]) for row in await cursor.fetchall()]

	return season_list


def usernames_autocomplete(seasonal: bool = True):
	async def callback(ctx: NatsuAutoContext) -> list[str]:
		async with ctx.database.connect() as conn:
			params = []
			query = "SELECT username FROM user WHERE username LIKE ?"
			if seasonal:
				query = "SELECT u.username FROM season_user su JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND u.username LIKE ?"
				params.append(await ctx.bot.get_config("contracts.active_season", db_conn=conn))
			query += " LIMIT 25"
			params.append(f"%{sanitize(ctx.value.strip())}%")

			async with conn.execute(query, params) as cursor:
				username_list: list[str] = [row["username"] for row in await cursor.fetchall()]

		return username_list

	return callback
