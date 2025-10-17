from contextlib import asynccontextmanager
from dataclasses import dataclass
import aiosqlite
import datetime
import aiofiles
import os
import re

TIMESTAMP_REGEX = r"<t:(\d+):(\w+)>"


def to_utc_timestamp(dt: datetime.datetime) -> int:
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	else:
		dt = dt.astimezone(datetime.timezone.utc)
	return int(dt.timestamp())


def from_utc_timestamp(ts: int) -> datetime.datetime:
	return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)


def diff_to_str(dt1: datetime.datetime, dt2: datetime.datetime) -> str:
	if dt1 > dt2:
		delta = dt1 - dt2
	else:
		delta = dt2 - dt1

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

	return " ".join(parts)


def parse_duration_str(duration_str: str) -> datetime.timedelta:
	UNIT_CANONICAL = {"y", "M", "d", "h", "m", "s"}
	ALIASES = {
		"year": "y",
		"years": "y",
		"month": "M",
		"months": "M",
		"day": "d",
		"days": "d",
		"hour": "h",
		"hours": "h",
		"minute": "m",
		"minutes": "m",
		"second": "s",
		"seconds": "s",
	}
	pattern = r"(\d+)\s*(\w+)"
	matches = re.findall(pattern, duration_str.lower())
	if not matches:
		raise ValueError("Invalid duration format")

	total_days = 0
	hours = 0
	minutes = 0
	seconds = 0

	for value, unit_word in matches:
		unit = ALIASES.get(unit_word, unit_word)
		if unit not in UNIT_CANONICAL:
			raise ValueError(f"Unknown time unit: {unit_word}")
		v = int(value)
		if unit == "y":
			total_days += v * 365
		elif unit == "M":
			total_days += v * 30
		elif unit == "d":
			total_days += v
		elif unit == "h":
			hours += v
		elif unit == "m":
			minutes += v
		elif unit == "s":
			seconds += v

	return datetime.timedelta(days=total_days, hours=hours, minutes=minutes, seconds=seconds)


@dataclass
class Reminder:
	id: int
	user_id: int
	channel_id: int
	message: str
	remind_at: datetime.datetime
	hidden: bool
	created_at: datetime.datetime

	def remind_timestamp(self) -> int:
		return to_utc_timestamp(self.remind_at)

	def created_timestamp(self) -> int:
		return to_utc_timestamp(self.created_at)


class ReminderDB:
	def __init__(self, path: str):
		self.path = path

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as conn:
			conn.row_factory = aiosqlite.Row
			yield conn

	async def setup(self):
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		async with aiofiles.open("assets/schemas/Reminder.sql") as f:
			db_script = await f.read()

		async with self.connect() as conn:
			await conn.executescript(db_script)
			await conn.commit()

	async def create_reminder(self, user_id: int, channel_id: int, remind_at: datetime.datetime, message: str, hidden: bool = False) -> Reminder:
		async with self.connect() as conn:
			async with await conn.execute(
				"""
				INSERT INTO reminders (user_id, channel_id, message, remind_at, hidden)
				VALUES (?, ?, ?, ?, ?)
				""",
				(user_id, channel_id, message, to_utc_timestamp(remind_at), int(hidden)),
			) as cursor:
				await conn.commit()
				reminder_id = cursor.lastrowid

			async with await conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)) as cursor:
				row = await cursor.fetchone()

			return self._row_to_reminder(row)

	async def delete_reminder(self, id: int):
		async with self.connect() as conn:
			await conn.execute("DELETE FROM reminders WHERE id = ?", (id,))
			await conn.commit()

	async def get_reminder(self, id: int) -> Reminder | None:
		async with self.connect() as conn:
			async with await conn.execute("SELECT * FROM reminders WHERE id = ?", (id,)) as cursor:
				row = await cursor.fetchone()
				return self._row_to_reminder(row) if row else None

	async def get_reminders(self, *, user_id: int | None = None) -> list[Reminder]:
		async with self.connect() as conn:
			if user_id is None:
				cursor = await conn.execute("SELECT * FROM reminders")
			else:
				cursor = await conn.execute("SELECT * FROM reminders WHERE user_id = ?", (user_id,))

			rows = await cursor.fetchall()
			await cursor.close()
			return [self._row_to_reminder(row) for row in rows]

	async def get_due_reminders(self) -> list[Reminder]:
		async with self.connect() as conn:
			async with await conn.execute(
				"DELETe FROM reminders WHERE remind_at <= ? RETURNING *", (to_utc_timestamp(datetime.datetime.now(datetime.UTC)),)
			) as cursor:
				rows = await cursor.fetchall()

			if not rows:
				return []

			return [self._row_to_reminder(row) for row in rows]

	def _row_to_reminder(self, row: aiosqlite.Row) -> Reminder:
		return Reminder(
			id=row["id"],
			user_id=row["user_id"],
			channel_id=row["channel_id"],
			message=row["message"],
			remind_at=from_utc_timestamp(row["remind_at"]),
			hidden=bool(row["hidden"]),
			created_at=from_utc_timestamp(row["created_at"]),
		)


@dataclass
class Giveaway:
	message_id: int
	author_id: int
	reward: int
	winners: int
	ends_at: datetime.datetime
	created_at: datetime.datetime
	_db: "GiveawayDB"

	def ends_timestamp(self) -> int:
		return to_utc_timestamp(self.ends_at)

	def created_timestamp(self) -> int:
		return to_utc_timestamp(self.created_at)

	async def get_users_entered(self) -> list[int]:
		async with self._db.connect() as conn:
			async with conn.execute("SELECT user_id FROM users_entered WHERE giveaway_id = ?", (self.message_id,)) as conn:
				return [row["user_id"] for row in await conn.fetchall()]

	async def get_role_requirements(self) -> list[int]:
		async with self._db.connect() as conn:
			async with conn.execute("SELECT role_id FROM role_requirements WHERE giveaway_id = ?", (self.message_id,)) as conn:
				return [row["role_id"] for row in await conn.fetchall()]


class GiveawayDB:
	def __init__(self, path: str):
		self.path = path

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as conn:
			conn.row_factory = aiosqlite.Row
			yield conn

	async def setup(self):
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		async with aiofiles.open("assets/schemas/Giveaway.sql") as f:
			db_script = await f.read()

		async with self.connect() as db:
			await db.executescript(db_script)
			await db.commit()

	async def create_giveaway(self, message_id: int, author_id: int, reward: str, ends_at: datetime.datetime, winners: int = 1) -> Reminder:
		async with self.connect() as conn:
			async with await conn.execute(
				"""
				INSERT INTO giveaways (message_id, author_id, reward, winners, ends_at)
				VALUES (?, ?, ?, ?, ?)
				RETURNING *
				""",
				(message_id, author_id, reward, winners, to_utc_timestamp(ends_at)),
			) as cursor:
				row = await cursor.fetchone()

			await conn.commit()
			return self._row_to_giveaway(row)

	async def delete_giveaway(self, giveaway_id: int):
		async with self.connect() as conn:
			await conn.execute("DELETE FROM giveaways WHERE message_id = ?", (giveaway_id,))
			await conn.commit()

	async def add_user_to_giveaway(self, giveaway_id: int, user_id: int) -> bool:
		async with self.connect() as conn:
			async with conn.execute("INSERT OR IGNORE INTO users_entered (giveaway_id, user_id) VALUES (?, ?)", (giveaway_id, user_id)) as cursor:
				changes_succeded = cursor.rowcount != 0

			await conn.commit()
			return changes_succeded

	async def remove_user_from_giveaway(self, giveaway_id: int, user_id: int) -> bool:
		async with self.connect() as conn:
			async with conn.execute("DELETE FROM users_entered WHERE giveaway_id = ? AND user_id = ?", (giveaway_id, user_id)) as cursor:
				changes_succeded = cursor.rowcount != 0
			await conn.commit()
			return changes_succeded

	async def get_giveaway(self, id: int) -> Reminder | None:
		async with self.connect() as conn:
			async with await conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (id,)) as cursor:
				row = await cursor.fetchone()
				return self._row_to_giveaway(row) if row else None

	async def get_entered_giveaways(self, user_id: int) -> list[Giveaway]:
		async with self.connect() as conn:
			async with conn.execute(
				"SELECT g.* FROM giveaways AS g JOIN users_entered AS ue ON ue.giveaway_id = g.message_id WHERE ue.user_id = ?;", (user_id,)
			) as cursor:
				rows = await cursor.fetchall()
				return [self._row_to_giveaway(row) for row in rows]

	async def get_due_giveaways(self) -> list[Giveaway]:
		async with self.connect() as conn:
			async with await conn.execute(
				"DELETE FROM giveaways WHERE ends_at <= ? RETURNING *", (to_utc_timestamp(datetime.datetime.now(datetime.UTC)),)
			) as cursor:
				rows = await cursor.fetchall()

			if not rows:
				return []

			return [self._row_to_giveaway(row) for row in rows]

	def _row_to_giveaway(self, row: aiosqlite.Row) -> Giveaway:
		return Giveaway(
			message_id=row["id"],
			author_id=row["author_id"],
			reward=row["reward"],
			winners=row["winners"],
			ends_at=from_utc_timestamp(row["ends_at"]),
			created_at=from_utc_timestamp(row["created_at"]),
			_db=self,
		)
