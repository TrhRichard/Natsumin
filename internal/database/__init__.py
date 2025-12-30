from contextlib import asynccontextmanager

import aiosqlite
import aiofiles
import asyncio
import logging
import sqlite3


class NatsuminDatabase:
	def __init__(self, production: bool = False):
		self.logger = logging.getLogger("bot")
		self.production = production
		self.available_seasons: tuple[str, ...] = tuple()

		self._setup_complete = asyncio.Event()

	async def open(self) -> aiosqlite.Connection:
		conn = await aiosqlite.connect("data/database-prod.sqlite" if self.production else "data/database-dev.sqlite")
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
		async with aiofiles.open("assets/schemas/Database.sql") as f:
			schema = await f.read()

		async with self.connect() as conn:
			await conn.executescript(schema)
			await conn.commit()

			async with conn.execute("SELECT DISTINCT(id) FROM season") as cursor:
				self.available_seasons = tuple(row["id"] for row in await cursor.fetchall())

		self._setup_complete.set()

	async def get_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> str | None:
		async with self.connect(db_conn) as conn:
			async with conn.execute("SELECT value FROM bot_config WHERE key = ?", (key,)) as cursor:
				row = await cursor.fetchone()

		return row["value"] if row is not None else None

	async def set_config(self, key: str, value: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		async with self.connect(db_conn) as conn:
			async with conn.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value)) as cursor:
				row_count = cursor.rowcount
			await conn.commit()

		return True if row_count == 1 else False

	async def remove_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		async with self.connect(db_conn) as conn:
			async with conn.execute("DELETE FROM bot_config WHERE key = ?", (key,)) as cursor:
				row_count = cursor.rowcount
			await conn.commit()

		return True if row_count == 1 else False

	async def wait_until_ready(self):
		await self._setup_complete.wait()
