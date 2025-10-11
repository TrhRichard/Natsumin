from .classes import SeasonDB
from .seasons import Winter2025, SeasonX
from .classes import *  # noqa: F403
from common import config
import time

AVAILABLE_SEASONS = ["Season X", "Winter 2025"]


async def get_season_db(season: str = None) -> SeasonDB:
	if season is None:
		season = config.active_season

	match season:
		case "Winter 2025":
			return await Winter2025.get_database()
		case "Season X":
			return await SeasonX.get_database()
		case _:
			raise ValueError(f"Invalid season: {season}")


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
		case "Season X":
			await SeasonX.sync_to_latest(db)

	return time.perf_counter() - start
