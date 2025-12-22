from __future__ import annotations

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


async def get_user_id(conn: aiosqlite.Connection, username: str) -> str | None:
	if username == "":
		return None

	async with conn.execute(
		"""
		SELECT id FROM user WHERE username = ?1 
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

		fuzzy_result = process.extractOne(username, id_username, score_cutoff=91)
		if fuzzy_result:
			return fuzzy_result[2]
		else:
			return None
