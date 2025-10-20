from .contracts import *  # noqa: F403
from .rep import get_rep, RepName  # noqa: F401
from common import config  # noqa: F401
from typing import TypeVar, Callable, overload
from discord.ext import commands
import datetime
import logging
import math

T = TypeVar("T")


def get_percentage(num: float, total: float) -> int:
	return math.floor(100 * float(num) / float(total))


def get_percentage_formatted(num: int | float, total: int | float) -> str:
	return f"{num}/{total} ({get_percentage(num, total)}%)"


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


def is_in_channel(*channel_ids: int, guild_id: int = 994071728017899600) -> Callable[[T], T]:
	channel_ids: list[int] = list(set(channel_ids))

	async def predicate(ctx: commands.Context) -> bool:
		if ctx.author.id in config.owner_ids:
			return True

		if ctx.guild is None or ctx.guild.id != guild_id:
			return True

		if ctx.channel.id not in channel_ids:
			raise WrongChannel(f"This command can only be ran in {', '.join([f'<#{channel_id}>' for channel_id in channel_ids])}")

		return True

	return commands.check(predicate)


FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
