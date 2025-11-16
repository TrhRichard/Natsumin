from .contracts import *  # noqa: F403
from .rep import get_rep, RepName  # noqa: F401
from common import config  # noqa: F401
from typing import TypeVar, Callable, overload
from discord.ext import commands
import datetime
import logging
import time

FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
FILE_LOGGING_FORMATTER.converter = time.gmtime
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
CONSOLE_LOGGING_FORMATTER.converter = time.gmtime


T = TypeVar("T")


def get_percentage(num: float, total: float) -> float:
	return 100 * float(num) / float(total)


def get_percentage_formatted(num: int | float, total: int | float) -> str:
	return f"{num}/{total} ({get_percentage(num, total):.2f}%)"


def filter_list(to_filter: list[T], **kwargs) -> list[T]:
	filtered = []
	for item in to_filter:
		if all(getattr(item, k, None) == v for k, v in kwargs.items()):
			filtered.append(item)

	return filtered


@overload
def get_cell(row: list, index: int, default: None = ..., return_type: None = ...) -> str | None: ...
@overload
def get_cell(row: list, index: int, default: T = ..., return_type: Callable[[any], T] = ...) -> T: ...
def get_cell(row: list, index: int, default: T = None, return_type: Callable[[any], T] = None) -> str | T:
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


class WrongChannel(commands.CommandError): ...


def is_channel(
	ctx: commands.Context, *channel_ids: int, guild_id: int = 994071728017899600, raise_exception: bool = False, bypass_roles: list[int] = None
) -> bool:
	bypass_roles = bypass_roles or []
	channel_ids: list[int] = list(set(channel_ids))  # Make sure the list only has unique ids

	if ctx.author.id in config.owner_ids:
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


def must_be_channel(*channel_ids: int, guild_id: int = 994071728017899600, bypass_roles: list[int] = None) -> Callable[[T], T]:
	async def predicate(ctx: commands.Context) -> bool:
		return is_channel(ctx, *channel_ids, guild_id=guild_id, raise_exception=True, bypass_roles=bypass_roles)

	return commands.check(predicate)


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

	formatted_time = ""
	if len(parts) == 1:
		formatted_time = parts[0]
	elif len(parts) == 2:
		formatted_time = " and ".join(parts)
	else:
		formatted_time = f"{', '.join(parts[:-1])} and {parts[-1]}"

	return formatted_time


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
