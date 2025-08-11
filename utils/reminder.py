from contextlib import asynccontextmanager
from dataclasses import dataclass
import aiosqlite
import datetime
import os

with open("assets/Reminder.sql") as f:
	db_script = f.read()


def to_utc_timestamp(dt: datetime.datetime) -> int:
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	else:
		dt = dt.astimezone(datetime.timezone.utc)
	return int(dt.timestamp())


def from_utc_timestamp(ts: int) -> datetime.datetime:
	return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)


@dataclass
class Reminder:
	id: int
	user_id: int
	channel_id: int
	message: str
	remind_at: datetime.datetime
	hidden: bool
	created_at: datetime.datetime
	# _db: "ReminderDB"

	def remind_timestamp(self) -> int:
		return to_utc_timestamp(self.remind_at)

	def created_timestamp(self) -> int:
		return to_utc_timestamp(self.created_at)


class ReminderDB:
	def __init__(self, path: str):
		self.path = path

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as db:
			db.row_factory = aiosqlite.Row
			yield db

	async def setup(self):
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		async with self.connect() as db:
			await db.executescript(db_script)
			await db.commit()

	async def create_reminder(self, user_id: int, channel_id: int, remind_at: datetime.datetime, message: str, hidden: bool = False) -> Reminder:
		async with self.connect() as db:
			async with await db.execute(
				"""
				INSERT INTO reminders (user_id, channel_id, message, remind_at, hidden)
				VALUES (?, ?, ?, ?, ?)
				""",
				(user_id, channel_id, message, to_utc_timestamp(remind_at), int(hidden)),
			) as cursor:
				await db.commit()
				reminder_id = cursor.lastrowid

			async with await db.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)) as cursor:
				row = await cursor.fetchone()

			return self._row_to_reminder(row)

	async def delete_reminder(self, id: int):
		async with self.connect() as db:
			await db.execute("DELETE FROM reminders WHERE id = ?", (id,))
			await db.commit()

	async def get_reminder(self, id: int) -> Reminder | None:
		async with self.connect() as db:
			async with await db.execute("SELECT * FROM reminders WHERE id = ?", (id,)) as cursor:
				row = await cursor.fetchone()
				return self._row_to_reminder(row) if row else None

	async def get_reminders(self, *, user_id: int | None = None) -> list[Reminder]:
		async with self.connect() as db:
			if user_id is None:
				cursor = await db.execute("SELECT * FROM reminders")
			else:
				cursor = await db.execute("SELECT * FROM reminders WHERE user_id = ?", (user_id,))

			rows = await cursor.fetchall()
			await cursor.close()
			return [self._row_to_reminder(row) for row in rows]

	async def get_due_reminders(self) -> list[Reminder]:
		async with self.connect() as db:
			async with await db.execute(
				"SELECT * FROM reminders WHERE remind_at <= ?", (to_utc_timestamp(datetime.datetime.now(datetime.UTC)),)
			) as cursor:
				rows = await cursor.fetchall()
			await cursor.close()

			if not rows:
				return []

			ids = [row["id"] for row in rows]
			placeholders = ",".join("?" for _ in ids)
			await db.execute(f"DELETE FROM reminders WHERE id IN ({placeholders})", ids)
			await db.commit()

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
