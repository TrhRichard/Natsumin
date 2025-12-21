from contextlib import asynccontextmanager

import aiosqlite
import aiofiles
import logging
import sqlite3


class NatsuminDatabase:
	def __init__(self, production: bool = False):
		self.logger = logging.getLogger("bot")
		self.production = production

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
