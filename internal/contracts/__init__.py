from __future__ import annotations

from internal.contracts.seasons import SeasonX
from typing import TYPE_CHECKING

import time

if TYPE_CHECKING:
	from internal.database import NatsuminDatabase

AVAILABLE_SEASONS = ("fall_2024", "winter_2025", "season_x")


async def sync_season(database: NatsuminDatabase, season_id: str) -> float:
	if season_id not in AVAILABLE_SEASONS:
		raise ValueError(f"Invalid season: {season_id}")

	start = time.perf_counter()

	match season_id:
		case "season_x":
			await SeasonX.sync_season(database)

	return time.perf_counter() - start


async def get_deadline_footer(database: NatsuminDatabase, season_id: str) -> str:
	if season_id not in AVAILABLE_SEASONS:
		raise ValueError(f"Invalid season: {season_id}")
