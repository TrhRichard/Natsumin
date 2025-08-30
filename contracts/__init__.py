from .classes import SeasonDB
from .seasons import Winter2025
from .classes import *  # noqa: F403
from common import config
import time
import discord
import utils

AVAILABLE_SEASONS = ["Winter 2025"]


async def get_season_db(season: str = None) -> SeasonDB:
	if season is None:
		season = config.active_season

	if season not in AVAILABLE_SEASONS:
		raise ValueError(f"Invalid season: {season}")

	match season:
		case "Winter 2025":
			return await Winter2025.get_database()


async def sync_season_db(season: str = None) -> float:  # Returns duration of sync
	if season is None:
		season = config.active_season

	if season not in AVAILABLE_SEASONS:
		raise ValueError(f"Invalid season: {season}")

	db = await get_season_db(season)
	start = time.perf_counter()

	match season:
		case "Winter 2025":
			await Winter2025.sync_to_latest(db)

	return time.perf_counter() - start


async def usernames_autocomplete(ctx: discord.AutocompleteContext):
	season_db = await get_season_db()
	return await utils.contracts.get_usernames(season_db, query=ctx.value.strip(), limit=25)


async def reps_autocomplete(ctx: discord.AutocompleteContext):
	season_db = await get_season_db()
	return await utils.contracts.get_reps(season_db, query=ctx.value.strip(), limit=25)
