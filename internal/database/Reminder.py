from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiosqlite
import aiofiles
import datetime
import asyncio
import logging
import sqlite3


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

	def remind_timestamp(self) -> int:
		return to_utc_timestamp(self.remind_at)

	def created_timestamp(self) -> int:
		return to_utc_timestamp(self.created_at)


class ReminderDatabase:
	def __init__(self, production: bool = False):
		self.logger = logging.getLogger("bot")
		self.production = production

		self._setup_complete = asyncio.Event()

	async def open(self) -> aiosqlite.Connection:
		conn = await aiosqlite.connect("data/reminders-prod.sqlite" if self.production else "data/reminders-dev.sqlite")
		conn.row_factory = aiosqlite.Row
		return conn

	@asynccontextmanager
	async def connect(self, existing_connection: aiosqlite.Connection | None = None):
		"""
		Connect to the database with a context manager.

		Optionally takes in a existing connection that won't close when the context ends.
		"""
		conn = await self.open() if existing_connection is None else existing_connection
		try:
			yield conn
		except (aiosqlite.Error, sqlite3.Error) as err:
			self.logger.error(err, exc_info=err)
			raise err
		finally:
			if existing_connection is None:
				await conn.close()

	async def setup(self):
		async with aiofiles.open("assets/schemas/Reminder.sql") as f:
			schema = await f.read()

		async with self.connect() as conn:
			await conn.executescript(schema)
			await conn.commit()

		self._setup_complete.set()

	async def wait_until_ready(self):
		await self._setup_complete.wait()

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
