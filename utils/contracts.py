from __future__ import annotations
from typing import TYPE_CHECKING
from async_lru import alru_cache
from common import config
from enum import StrEnum

if TYPE_CHECKING:
	from contracts.classes import SeasonDB

__all__ = ["LegacyRank", "get_legacy_rank", "get_usernames", "get_reps", "get_time_till_season_ends"]


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


def get_legacy_rank(exp: int | None) -> LegacyRank | None:
	if not exp:
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


@alru_cache(ttl=12 * 60 * 60)
async def get_usernames(season_db: SeasonDB, query: str = "", limit: int = None) -> list[str]:
	from contracts.classes import MasterDB

	master_db = MasterDB.get_database()
	async with master_db.connect() as db:
		async with db.execute("SELECT id, username FROM users") as cursor:
			id_usernames: dict[int, str] = {row["id"]: row["username"] for row in await cursor.fetchall()}

	async with season_db.connect() as db:
		async with db.execute("SELECT user_id FROM users") as cursor:
			season_user_ids: list[int] = [row["user_id"] for row in await cursor.fetchall()]

	usernames = [id_usernames[user_id] for user_id in season_user_ids if user_id in id_usernames]

	if query:
		usernames = [name for name in usernames if query.lower() in name.lower()]

	if limit is not None:
		usernames = usernames[:limit]

	return usernames


@alru_cache(ttl=12 * 60 * 60)
async def get_reps(season_db: SeasonDB, query: str = "", limit: int | None = None) -> list[str]:
	async with season_db.connect() as db:
		async with db.execute(
			f"SELECT DISTINCT rep FROM users WHERE upper(rep) LIKE ? {f'LIMIT {limit}' if limit else ''}", (f"%{query.upper()}%",)
		) as cursor:
			return [row[0] for row in await cursor.fetchall()]


def get_time_till_season_ends(season: str = None) -> tuple[int, int, int, int]:
	if season is None:
		season = config.active_season
	pass


"""
def get_common_embed(user: contracts.User | None = None, member: discord.Member | None = None, season: str = config.active_season) -> discord.Embed:
	embed = discord.Embed(color=config.BASE_EMBED_COLOR, description="")
	if user:
		symbol = ""
		match user.status:
			case contracts.UserStatus.FAILED:
				symbol = "❌"
			case contracts.UserStatus.PASSED:
				symbol = "✅"
			case contracts.UserStatus.LATE_PASS:
				symbol = "⌛☑️"
			case contracts.UserStatus.INCOMPLETE:
				symbol = "⛔"

		if season != config.active_season:
			symbol += f" ({season})" if symbol != "" else f"{(season)}"

		embed.set_author(
			name=f"{user.username} {symbol}",
			url=user.list_url if user.list_url != "" else None,
			icon_url=member.display_avatar.url if member else None,
		)

	if season == config.active_season:
		current_datetime = datetime.datetime.now(datetime.UTC)
		difference = config.deadline_datetime - current_datetime
		difference_seconds = max(difference.total_seconds(), 0)

		if difference_seconds > 0:
			days, remainder = divmod(difference_seconds, 86400)
			hours, remainder = divmod(remainder, 3600)
			minutes, _ = divmod(remainder, 60)
			embed.set_footer(
				text=config.deadline_footer.format(days=int(days), hours=int(hours), minutes=int(minutes)),
				icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096",
			)
		else:
			embed.set_footer(text="This season has ended.", icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096")
	else:
		embed.set_footer(text=f"Data from {season}", icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096")
	return embed

"""
