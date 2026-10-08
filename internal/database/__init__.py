from contextlib import asynccontextmanager
from datetime import datetime, date
from config import IS_PRODUCTION
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import importlib
import aiosqlite
import asyncio
import logging
import sqlite3
import json

sqlite3.register_adapter(datetime, lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(bool, int)
sqlite3.register_adapter(UUID, lambda u: str(u))
sqlite3.register_adapter(dict, lambda d: json.dumps(d, indent=None))
sqlite3.register_adapter(list, lambda ls: json.dumps(ls, indent=None))

sqlite3.register_converter("DATETIME", lambda b: datetime.fromisoformat(b.decode("utf-8")))
sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode("utf-8")))
sqlite3.register_converter("BOOLEAN", lambda b: b == b"1")
sqlite3.register_converter("UUID", lambda b: UUID(b.decode("utf-8")))
sqlite3.register_converter("JSON", lambda b: json.loads(b.decode("utf-8")))


# not exactly database related however it fixes issues with json encoding
class NatsuJSONEncoder(json.JSONEncoder):
	def default(self, obj):
		if isinstance(obj, datetime):
			return obj.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
		if isinstance(obj, date):
			return obj.isoformat()
		if isinstance(obj, UUID):
			return str(obj)
		return super().default(obj)


json.JSONEncoder = NatsuJSONEncoder


@dataclass(slots=True, kw_only=True)
class SeasonDetails:
	id: str
	name: str


MIGRATIONS_PATH = Path("assets", "migrations")


class NatsuDatabase:
	def __init__(self):
		self.logger = logging.getLogger("bot.database")

		self.available_seasons: dict[str, SeasonDetails] = {}

		self._db_path = Path("data", f"database-{'prod' if IS_PRODUCTION else 'dev'}.sqlite")
		self._setup_complete = asyncio.Event()

	async def open(self, *, enable_foreign: bool = True) -> aiosqlite.Connection:
		conn = await aiosqlite.connect(self._db_path, detect_types=sqlite3.PARSE_DECLTYPES)
		conn.row_factory = aiosqlite.Row
		if enable_foreign:
			await conn.executescript("""
				PRAGMA foreign_keys = ON;
			""")
		return conn

	@asynccontextmanager
	async def connect(self, existing_connection: aiosqlite.Connection | None = None, enable_foreign: bool = True):
		"""
		Connect to the database with a context manager.

		Optionally takes in a existing connection that won't close when the context ends.
		"""
		conn = await self.open(enable_foreign=enable_foreign) if existing_connection is None else existing_connection
		try:
			yield conn
		except (aiosqlite.Error, sqlite3.Error) as err:
			self.logger.error(err, exc_info=err)
			raise
		finally:
			if existing_connection is None:
				await conn.close()

	async def setup(self):
		async with self.connect(enable_foreign=False) as conn:
			await conn.executescript("""--sql
				PRAGMA journal_mode = WAL;

				CREATE TABLE IF NOT EXISTS migrations (
					id			TEXT NOT NULL PRIMARY KEY,
					created_at	DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
				);
			""")
			await conn.commit()

			async with conn.execute("SELECT id FROM migrations") as cursor:
				existing_migration_ids = {row["id"] for row in await cursor.fetchall()}

			pending_migrations: list[Path] = []
			for migration_file in sorted(
				(p for p in MIGRATIONS_PATH.glob("[0-9][0-9][0-9][0-9]_*") if p.suffix in (".py", ".sql")), key=lambda p: p.stem
			):
				migration_id = migration_file.stem

				if migration_id not in existing_migration_ids:
					pending_migrations.append(migration_file)

			for i, migration_file in enumerate(pending_migrations, start=1):
				migration_id = migration_file.stem
				migration_number = migration_id.split("_", 1)[0]
				migration_name = migration_id.split("_", 1)[1]

				full_migration_name = f"{migration_number} '{migration_name}'"

				self.logger.info(f"Running migration {full_migration_name} ({i}/{len(pending_migrations)})")

				try:
					if migration_file.suffix == ".sql":
						with open(migration_file, "r", encoding="utf-8") as f:
							file_content = f.read()
						await conn.executescript(f"BEGIN;\n{file_content}\n;\nINSERT INTO migrations (id) VALUES ('{migration_id}');\nCOMMIT;\n")
					else:
						migration_module = importlib.import_module(f"assets.migrations.{migration_id}")
						await migration_module.migrate(conn)
						await conn.execute("INSERT INTO migrations (id) VALUES (?)", (migration_id,))
						await conn.commit()
				except Exception as err:
					if conn.in_transaction:
						await conn.rollback()
					self.logger.error(
						f"Migration {full_migration_name} failed, stopping migration process at {i}/{len(pending_migrations)}", exc_info=err
					)
					raise

				self.logger.info(f"Migration {full_migration_name} finished successfully")

			if pending_migrations:
				self.logger.info(
					f"Migrating database finished successfully ({len(pending_migrations)} migration{'s' if len(pending_migrations) > 1 else ''} applied)"
				)

			async with conn.execute("SELECT id, name FROM season") as cursor:
				for row in await cursor.fetchall():
					self.available_seasons[row["id"]] = SeasonDetails(**row)

		self._setup_complete.set()

	async def get_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> str | None:
		async with self.connect(db_conn) as conn, conn.execute("SELECT value FROM bot_config WHERE key = ?", (key,)) as cursor:
			row = await cursor.fetchone()

		return row["value"] if row is not None else None

	async def set_config(self, key: str, value: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		async with self.connect(db_conn) as conn:
			async with conn.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES (?, ?)", (key, value)) as cursor:
				row_count = cursor.rowcount
			await conn.commit()

		return row_count == 1

	async def remove_config(self, key: str, *, db_conn: aiosqlite.Connection | None = None) -> bool:
		async with self.connect(db_conn) as conn:
			async with conn.execute("DELETE FROM bot_config WHERE key = ?", (key,)) as cursor:
				row_count = cursor.rowcount
			await conn.commit()

		return row_count == 1

	async def wait_until_ready(self):
		await self._setup_complete.wait()
