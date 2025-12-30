from __future__ import annotations

from internal.enums import UserStatus, ContractStatus, LegacyRank
from typing import TYPE_CHECKING, overload
from .exceptions import WrongChannel
from discord.ext import commands
from config import OWNER_IDS
from thefuzz import process

import aiosqlite
import datetime
import re

if TYPE_CHECKING:
	from collections.abc import Iterable
	from typing import Callable


def get_percentage(num: float, total: float) -> float:
	return 100 * float(num) / float(total)


def get_percentage_formatted(num: int | float, total: int | float) -> str:
	return f"{num}/{total} ({get_percentage(num, total):.2f}%)"


def shorten(text: str, max_len: int) -> str:
	return text if len(text) <= max_len else text[: max_len - 3] + "..."


def frmt_iter(iter: Iterable) -> str:
	iter = tuple(iter)
	if not iter:
		return ""

	if len(iter) == 1:
		return str(iter[0])
	elif len(iter) == 2:
		return " and ".join(iter)
	else:
		return f"{', '.join(iter[:-1])} and {iter[-1]}"


@overload
def get_cell[T](row: list, index: int, default: None = ..., return_type: None = ...) -> str | None: ...
@overload
def get_cell[T](row: list, index: int, default: T = ..., return_type: Callable[[any], T] = ...) -> T: ...
def get_cell[T](row: list, index: int, default: T = None, return_type: Callable[[any], T] = None) -> str | T:
	try:
		value = row[index]
		if value is None:
			return default
		if return_type is not None:
			try:
				return return_type(value)
			except (ValueError, TypeError):
				return default
		return value
	except IndexError:
		return default


def get_url(text: str) -> str:
	match = re.search(r"(https?:\/\/[^\s]+)", text)
	if match:
		return match.group(0)
	return ""


def diff_to_str(dt1: datetime.datetime, dt2: datetime.datetime) -> str:
	delta = dt1 - dt2

	total_seconds = int(delta.total_seconds())

	years, remainder = divmod(total_seconds, 365 * 86400)
	months, remainder = divmod(remainder, 30 * 86400)
	days, remainder = divmod(remainder, 86400)
	hours, remainder = divmod(remainder, 3600)
	minutes, seconds = divmod(remainder, 60)

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
	if seconds > 0:
		parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

	if not parts:
		return "0 seconds"

	return frmt_iter(parts)


def is_channel(
	ctx: commands.Context, *channel_ids: int, guild_id: int = 994071728017899600, raise_exception: bool = False, bypass_roles: list[int] = None
) -> bool:
	bypass_roles = bypass_roles or []
	channel_ids: list[int] = list(set(channel_ids))  # Make sure the list only has unique ids

	if ctx.author.id in OWNER_IDS:
		return True

	if not ctx.guild or ctx.guild.id != guild_id:
		return True

	author_perms = ctx.channel.permissions_for(ctx.author)
	if author_perms and author_perms.administrator:
		return True

	if bypass_roles and any(ctx.author.get_role(role_id) for role_id in bypass_roles):
		return True

	if ctx.channel.id not in channel_ids:
		if raise_exception:
			raise WrongChannel(f"This command can only be used in {', '.join(f'<#{channel_id}>' for channel_id in channel_ids)}")
		else:
			return False

	return True


async def get_user_id(conn: aiosqlite.Connection, username: str, *, score_cutoff: int = 91) -> str | None:
	if username == "":
		return None

	async with conn.execute(
		"""
		SELECT id FROM user WHERE username = ?1 OR id = ?1
		UNION ALL
		SELECT user_id as id FROM user_alias WHERE username = ?1
		""",
		(username,),
	) as cursor:
		row = await cursor.fetchone()
		if row:
			return row["id"]

	async with conn.execute("""
		SELECT id, username FROM user
		UNION ALL
		SELECT user_id as id, username FROM user_alias
		""") as cursor:
		id_username = {row["id"]: row["username"] for row in await cursor.fetchall()}

		fuzzy_result = process.extractOne(username, id_username, score_cutoff=score_cutoff)
		if fuzzy_result:
			return fuzzy_result[2]
		else:
			return None


def get_status_name(status: UserStatus | ContractStatus, is_optional: bool = False) -> str:
	match status:
		case UserStatus.PASSED | ContractStatus.PASSED:
			if is_optional:
				return "Passed (Optional)"
			else:
				return "Passed"
		case UserStatus.LATE_PASS | ContractStatus.LATE_PASS:
			return "Passed late"
		case UserStatus.FAILED | ContractStatus.FAILED:
			return "Failed"
		case UserStatus.PENDING | ContractStatus.PENDING:
			if is_optional:
				return "Pending (Optional)"
			else:
				return "Pending"
		case UserStatus.INCOMPLETE:
			return "Incomplete"
		case ContractStatus.UNVERIFIED:
			return "Unverified"
		case _:
			return "N/A"


def get_status_emote(status: UserStatus | ContractStatus, is_optional: bool = False) -> str:
	match status:
		case UserStatus.PASSED | ContractStatus.PASSED:
			if is_optional:
				return "🏆"
			else:
				return "✅"
		case UserStatus.LATE_PASS | ContractStatus.LATE_PASS:
			return "☑️"
		case UserStatus.FAILED | UserStatus.INCOMPLETE | ContractStatus.FAILED:
			return "❌"
		case ContractStatus.UNVERIFIED:
			return "❓"
		case _:
			if is_optional:
				return "➖"
			else:
				return "❔"


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
