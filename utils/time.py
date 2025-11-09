import datetime
import re

DURATION_PATTERN = r"(\d+)\s*((?:second|minute|hour|day|week|month|year)s?|s|m|h|d|w|y)"


def parse_duration_str(duration_str: str) -> datetime.timedelta:
	matches: list[tuple[str, str]] = re.findall(DURATION_PATTERN, duration_str.strip(), re.IGNORECASE)
	if not matches:
		raise ValueError("Invalid duration format")

	weeks = 0
	days = 0
	hours = 0
	minutes = 0
	seconds = 0

	for value, unit in matches:
		v = int(value)
		unit = unit.strip().lower()
		match unit:
			case "s" | "second" | "seconds":
				seconds += v
			case "m" | "minute" | "minutes":
				minutes += v
			case "h" | "hour" | "hours":
				hours += v
			case "d" | "day" | "days":
				days += v
			case "w" | "week" | "weeks":
				weeks += v
			case "month" | "months":
				days += v * 30
			case "y" | "year" | "years":
				days += v * 365

	return datetime.timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)


def to_utc_timestamp(dt: datetime.datetime) -> int:
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	else:
		dt = dt.astimezone(datetime.timezone.utc)
	return int(dt.timestamp())


def from_utc_timestamp(ts: int) -> datetime.datetime:
	return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
