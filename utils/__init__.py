from .contracts import *  # noqa: F403
from .rep import get_rep, RepName  # noqa: F401
from common import config  # noqa: F401
from typing import TypeVar, Callable, overload
import datetime
import logging
import math


def get_percentage(num: float, total: float) -> int:
	return math.floor(100 * float(num) / float(total))


def is_season_ongoing() -> bool:
	current_datetime = datetime.datetime.now(datetime.UTC)
	difference = config.deadline_datetime - current_datetime
	difference_seconds = max(difference.total_seconds(), 0)
	return difference_seconds > 0


T = TypeVar("T")


@overload
def get_cell(row: list, index: int, default: None = ..., return_type: None = ...) -> str: ...
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


FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
