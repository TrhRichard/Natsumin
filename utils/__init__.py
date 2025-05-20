from .contracts import *  # noqa: F403
import datetime
import config
import math


def get_percentage(num: float, total: float) -> int:
	return math.floor(100 * float(num) / float(total))


def is_season_ongoing() -> bool:
	current_datetime = datetime.datetime.now(datetime.UTC)
	difference = config.DEADLINE_TIMESTAMP - current_datetime
	difference_seconds = max(difference.total_seconds(), 0)
	return difference_seconds > 0
