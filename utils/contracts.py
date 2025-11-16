from typing import TYPE_CHECKING
from async_lru import alru_cache
from common import config, get_master_db
from enum import StrEnum
import datetime
import re

if TYPE_CHECKING:
	from contracts import ContractOrderCategory

__all__ = [
	"LegacyRank",
	"get_rank_emoteid",
	"get_legacy_rank",
	"get_usernames",
	"get_reps",
	"get_contract_category",
	"sort_contract_categories",
	"get_deadline_footer",
	"is_season_ongoing",
	"format_list",
]


class LegacyRank(StrEnum):
	QUARTZ = "Quartz"
	CITRINE = "Citrine"
	AMETHYST = "Amethyst"
	AQUAMARINE = "Aquamarine"
	JADE = "Jade"
	TOPAZ = "Topaz"
	MORGANITE = "Morganite"
	SPINEL = "Spinel"
	EMERALD = "Emerald"
	SAPPHIRE = "Sapphire"
	RUBY = "Ruby"
	DIAMOND = "Diamond"
	ALEXANDRITE = "Alexandrite"
	PAINITE = "Painite"


def get_rank_emoteid(rank: LegacyRank | None = None) -> int | None:
	match rank:
		case LegacyRank.QUARTZ:
			return 1370358752129187891
		case LegacyRank.CITRINE:
			return 1370358870370812015
		case LegacyRank.AMETHYST:
			return 1370359411465519196
		case LegacyRank.AQUAMARINE:
			return 1370359420269101196
		case LegacyRank.JADE:
			return 1370359433514848367
		case LegacyRank.TOPAZ:
			return 1370359441265786911
		case LegacyRank.MORGANITE:
			return 1370359449528565770
		case LegacyRank.SPINEL:
			return 1370908107861004419
		case LegacyRank.EMERALD:
			return 1370359457917308958
		case LegacyRank.SAPPHIRE:
			return 1370359466519826505
		case LegacyRank.RUBY:
			return 1370359475080400926
		case LegacyRank.DIAMOND:
			return 1370359483531919461
		case LegacyRank.ALEXANDRITE:
			return 1370359491438051328
		case LegacyRank.PAINITE:
			return 1370359499151638530
		case _:
			return None


def get_legacy_rank(exp: int | None) -> LegacyRank | None:
	if exp is None:
		return None

	if exp >= 34000:
		return LegacyRank.PAINITE
	elif exp >= 29000:
		return LegacyRank.ALEXANDRITE
	elif exp >= 24400:
		return LegacyRank.DIAMOND
	elif exp >= 20200:
		return LegacyRank.RUBY
	elif exp >= 16400:
		return LegacyRank.SAPPHIRE
	elif exp >= 13000:
		return LegacyRank.EMERALD
	elif exp >= 10000:
		return LegacyRank.SPINEL
	elif exp >= 7400:
		return LegacyRank.MORGANITE
	elif exp >= 5200:
		return LegacyRank.TOPAZ
	elif exp >= 3400:
		return LegacyRank.JADE
	elif exp >= 2000:
		return LegacyRank.AQUAMARINE
	elif exp >= 1000:
		return LegacyRank.AMETHYST
	elif exp >= 150:
		return LegacyRank.CITRINE
	else:
		return LegacyRank.QUARTZ


def is_season_ongoing() -> bool:
	current_datetime = datetime.datetime.now(datetime.UTC)
	difference = config.deadline_datetime - current_datetime
	difference_seconds = max(difference.total_seconds(), 0)
	return difference_seconds > 0


@alru_cache(ttl=12 * 60 * 60)
async def get_usernames(query: str = "", limit: int = None, *, season: str = None, seasonal: bool = True) -> list[str]:
	if season is None:
		season = config.active_season

	master_db = get_master_db()
	async with master_db.connect() as db:
		async with db.execute("SELECT id, username FROM users") as cursor:
			id_usernames: dict[int, str] = {row["id"]: row["username"] for row in await cursor.fetchall()}

	if seasonal:
		from contracts import get_season_db

		season_db = await get_season_db(season)
		async with season_db.connect() as db:
			async with db.execute("SELECT id FROM users") as cursor:
				season_user_ids: list[int] = [row["id"] for row in await cursor.fetchall()]

		usernames = [id_usernames[user_id] for user_id in season_user_ids if user_id in id_usernames]
	else:
		usernames = list(id_usernames.values())

	if query:
		usernames = [name for name in usernames if query.lower() in name.lower()]

	if limit is not None:
		usernames = usernames[:limit]

	return usernames


@alru_cache(ttl=12 * 60 * 60)
async def get_reps(query: str = "", limit: int | None = None, *, season: str = None, seasonal: bool = True) -> list[str]:
	if season is None:
		season = config.active_season

	if seasonal:
		from contracts import get_season_db

		season_db = await get_season_db(season)
		async with season_db.connect() as db:
			async with db.execute(
				f"SELECT DISTINCT rep FROM users WHERE upper(rep) LIKE ? {f'LIMIT {limit}' if limit else ''}", (f"%{query.upper()}%",)
			) as cursor:
				return [row[0] for row in await cursor.fetchall()]
	else:
		master_db = get_master_db()
		async with master_db.connect() as db:
			async with db.execute(
				f"SELECT DISTINCT rep FROM users WHERE upper(rep) LIKE ? {f'LIMIT {limit}' if limit else ''}", (f"%{query.upper()}%",)
			) as cursor:
				return [row[0] for row in await cursor.fetchall()]


def get_contract_category(order_data: "list[ContractOrderCategory]", c_type: str) -> str:
	for category in order_data:
		for pattern in category["order"]:
			if c_type.lower() == pattern.lower() or re.fullmatch(pattern, c_type, re.IGNORECASE):
				return category["name"]

	return "Other"


def sort_contract_categories(order_data: "list[ContractOrderCategory]") -> list[str]:
	return [*[category["name"] for category in order_data], "Other"]


def format_list(items: list) -> str:
	if not items:
		return ""

	formatted_list = ""

	if len(items) == 1:
		formatted_list = items[0]
	elif len(items) == 2:
		formatted_list = " and ".join(items)
	else:
		formatted_list = f"{', '.join(items[:-1])} and {items[-1]}"

	return formatted_list


def diff_to_str(dt1: datetime.datetime, dt2: datetime.datetime) -> str:
	if dt1 > dt2:
		delta = dt1 - dt2
	else:
		delta = dt2 - dt1

	total_seconds = int(delta.total_seconds())

	years, remaining = divmod(total_seconds, 365 * 86400)
	months, remaining = divmod(remaining, 30 * 86400)
	days, remaining = divmod(remaining, 86400)
	hours, remaining = divmod(remaining, 3600)
	minutes, seconds = divmod(remaining, 60)

	parts = []
	if years > 0:
		parts.append(f"{years} year{'s' if years != 1 else ''}")
	if months > 0:
		parts.append(f"{months} month{'s' if months != 1 else ''}")
	if days > 0:
		parts.append(f"{days} day{'s' if days != 1 else ''}")
	if hours > 0:
		parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
	if minutes > 0:
		parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

	if not parts and seconds > 0:
		parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
	elif not parts:
		return "0 seconds"

	return format_list(parts)


def get_deadline_footer(season: str = None) -> str:
	if season is None:
		season = config.active_season

	if season == config.active_season:
		if config.deadline_timestamp == 0:
			return "Deadline unknown."

		current_datetime = datetime.datetime.now(datetime.UTC)
		difference = config.deadline_datetime - current_datetime
		difference_seconds = max(difference.total_seconds(), 0)

		if difference_seconds > 0:
			return config.deadline_footer.format(time_till=diff_to_str(current_datetime, config.deadline_datetime))
		else:
			return "This season has ended."
	else:
		return f"Archived data from {season}."
