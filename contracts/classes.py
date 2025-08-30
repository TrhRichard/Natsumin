from __future__ import annotations
from utils.contracts import get_legacy_rank
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from async_lru import alru_cache
from thefuzz import process
from typing import Literal
from enum import StrEnum
from enum import Enum
import aiosqlite
import os


__all__ = ["UserStatus", "ContractStatus", "ContractKind", "Contract", "SeasonUser", "SeasonDB", "MasterDB", "MasterUser", "BadgeType"]

with open("assets/schemas/Season.sql") as f:
	season_script = f.read()
CACHE_DURATION = 3 * 60


class BadgeType(StrEnum):
	CONTRACTS = "contracts"
	ARIA = "aria"


class UserStatus(Enum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3
	INCOMPLETE = 4


class ContractStatus(Enum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3


class ContractKind(Enum):
	NORMAL = 0
	AID = 1


@dataclass(slots=True)
class SeasonUser:
	user_id: int
	status: UserStatus
	rep: str | None = None
	contractor: str | None = field(default=None, repr=False)
	list_url: str | None = field(default=None, repr=False)
	veto_used: bool = field(default=False, repr=False)
	accepting_manhwa: bool = field(default=False, repr=False)
	accepting_ln: bool = field(default=False, repr=False)
	preferences: str | None = field(default=None, repr=False)
	bans: str | None = field(default=None, repr=False)
	_db: SeasonDB = None

	def __eq__(self, value):
		if isinstance(value, SeasonUser):
			return self.user_id == value.user_id
		elif isinstance(value, int):
			return self.user_id == value

		return False

	async def get_master_data(self) -> MasterUser:
		return await self._db.fetch_user_from_master(id=self.user_id)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_contracts(self) -> list[Contract]:
		async with self._db.connect() as db:
			async with db.execute("SELECT * FROM contracts WHERE contractee = ?", (self.user_id,)) as cursor:
				rows = await cursor.fetchall()
				return [Contract(**row, _db=self._db) for row in rows]

		return []

	async def to_dict(self, *, include_contracts: bool = False):
		master_user = await self.get_master_data()
		return {
			"user": await master_user.to_dict(include_badges=False),
			"status": self.status.name,
			"rep": self.rep,
			"contractor": self.contractor,
			"list_url": self.list_url,
			"veto_used": self.veto_used,
			"accepting_manhwa": self.accepting_manhwa,
			"accepting_ln": self.accepting_ln,
			"preferences": self.preferences,
			"bans": self.bans,
			"contracts": [await contract.to_dict(transform_contractee=False) for contract in await self.get_contracts()]
			if include_contracts
			else None,
		}


@dataclass(slots=True)
class Contract:
	id: int
	name: str
	type: str
	kind: ContractKind
	status: ContractStatus
	contractee: int
	contractor: str
	optional: bool = field(default=False, repr=False)
	progress: str | None = field(default=None, repr=False)
	rating: str | None = field(default=None, repr=False)
	review_url: str | None = field(default=None, repr=False)
	medium: str | None = field(default=None, repr=False)
	_db: "SeasonDB" = None

	def __eq__(self, value):
		if isinstance(value, Contract):
			return self.id == value.id
		elif isinstance(value, int):
			return self.id == value

		return False

	async def get_contractee(self) -> SeasonUser:
		return self._db.fetch_user(self.contractee)

	async def to_dict(self, *, transform_contractee: bool = True):
		return {
			"id": self.id,
			"name": self.name,
			"type": self.type,
			"kind": self.kind.name,
			"status": self.status.name,
			"contractee": await (await self.get_contractee()).to_dict() if transform_contractee else self.contractee,
			"optional": self.optional,
			"contractor": self.contractor,
			"progress": self.progress,
			"rating": self.rating,
			"review_url": self.review_url,
			"medium": self.medium,
		}


class SeasonDB:
	def __init__(self, name: str, path: str, master_db: MasterDB | None = None):
		self.name = name
		self.path = path
		self._master_db = master_db

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as db:
			db.row_factory = aiosqlite.Row
			yield db

	async def setup(self):
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		async with self.connect() as db:
			await db.executescript(season_script)
			await db.commit()

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_user(self, user_id: int) -> SeasonUser | None:
		async with self.connect() as db:
			async with db.execute("SELECT * FROM users WHERE user_id = ? LIMIT 1", (user_id,)) as cursor:
				if user := await cursor.fetchone():
					return SeasonUser(**user, _db=self)

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_user_from_master(self, *, id: int | None = None, username: str | None = None) -> MasterUser | None:
		if not self._master_db:
			return None

		return await self._master_db.fetch_user(id=id, username=username)


@dataclass(slots=True)
class MasterUser:
	id: int
	discord_id: int | None
	username: str
	rep: str
	gen: int | None
	_db: MasterDB = field(repr=False, default=None)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_legacy_exp(self) -> int | None:
		async with self._db.connect() as db:
			async with db.execute("SELECT * FROM legacy_leaderboard WHERE user_id = ? LIMIT 1", (self.id,)) as cursor:
				if row := await cursor.fetchone():
					return row["exp"]
				return None

	@alru_cache(ttl=CACHE_DURATION)
	async def get_badges(self, badge_type: BadgeType | None = None) -> list[Badge]:
		async with self._db.connect() as db:
			async with db.execute(
				f"""
					SELECT badges.* FROM badges b
					JOIN user_badges ub ON b.id = ub.id
					WHERE ub.user_id = ? {"AND b.type = ?" if badge_type is not None else ""}
					""",
				(self.id, badge_type) if badge_type is not None else (self.id,),
			) as cursor:
				rows = await cursor.fetchall()
				return [Badge(**row) for row in rows]

	async def give_badge(self, badge: Badge):
		async with self._db.connect() as db:
			await db.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?, ?)", (self.id, badge.id))
			await db.commit()

	@alru_cache(ttl=CACHE_DURATION)
	async def has_badge(self, badge: Badge) -> bool:
		async with self._db.connect() as db:
			async with db.execute("SELECT 1 FROM user_badges WHERE user_id = ? AND badge_id = ? LIMIT 1", (self.id, badge.id)) as cursor:
				row = await cursor.fetchone()
				return row is not None

	async def to_dict(self, *, include_badges: bool = False) -> dict:
		legacy_exp = await self.get_legacy_exp()
		return {
			"id": self.id,
			"discord_id": self.discord_id,
			"username": self.username,
			"rep": self.rep,
			"gen": self.gen,
			"legacy": {"exp": legacy_exp, "rank": get_legacy_rank(legacy_exp).value if legacy_exp is not None else None},
			"badges": [await badge.to_dict() for badge in await self.get_badges()] if include_badges else None,
		}


@dataclass(slots=True)
class Badge:
	id: int
	name: str
	description: str
	artist: str
	url: str
	type: BadgeType

	async def to_dict(self) -> dict:
		return {"id": self.id, "name": self.name, "description": self.description, "artist": self.artist, "url": self.url, "type": self.type.value}


_master_db: MasterDB = None


class MasterDB:
	def __init__(self, path: str = "data/master.db"):
		self.path = path

	@classmethod
	def get_database(cls) -> MasterDB:
		global _master_db
		if _master_db:
			return _master_db
		else:
			_master_db = cls()
			return _master_db

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as db:
			db.row_factory = aiosqlite.Row
			yield db

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_user(self, id: int | None = None, discord_id: int | None = None, username: str | None = None) -> MasterUser | None:
		async with self.connect() as db:
			query_params = []
			params = {}

			if id is not None:
				query_params.append("id = :id")
				params["id"] = id
			if discord_id is not None:
				query_params.append("discord_id = :discord_id")
				params["discord_id"] = discord_id
			if username is not None:
				query_params.append("username = :username")
				params["username"] = username

			if not query_params:
				raise ValueError("No filter specified.")

			async with db.execute(f"SELECT * FROM users WHERE {' AND '.join(query_params)} LIMIT 1", params) as cursor:
				row = await cursor.fetchone()
				if row:
					return MasterUser(**row, _db=self)

			if username is not None:
				async with db.execute(
					"""
					SELECT u.* FROM users u
					JOIN user_aliases a ON u.user_id = a.user_id
					WHERE a.username = ?
					LIMIT 1
					""",
					(username,),
				) as cursor:
					if row := await cursor.fetchone():
						return MasterUser(**row, _db=self)

			return None

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_user_fuzzy(self, username: str, min_confidence: int = 90) -> MasterUser | None:
		"""Attempts to find the user by username, if that fails then performs a fuzzy search"""
		async with self.connect() as db:
			async with db.execute("SELECT * FROM users WHERE username = ? LIMIT 1", (username.lower(),)) as cursor:
				row = await cursor.fetchone()
				if row:
					return MasterUser(**row, _db=self)

			async with db.execute("SELECT id, username FROM users") as cursor:
				id_username: dict[int, str] = {row["id"]: row["username"] for row in await cursor.fetchall()}

			fuzzy_results: list[tuple[str, int, int]] = process.extract(username.lower(), id_username, limit=1)
			if fuzzy_results:
				_, confidence, id_found = fuzzy_results[0]
				if confidence >= min_confidence:
					async with db.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (id_found,)) as cursor:
						row = await cursor.fetchone()
						return MasterUser(**row, _db=self)

		return None

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_badge(self, id: int | None = None, name: str | None = None, badge_type: BadgeType | None = None) -> Badge | None:
		async with self.connect() as db:
			query_params = []
			params = {}

			if id is not None:
				query_params.append("id = :id")
				params["id"] = id
			if name is not None:
				query_params.append("name = :name")
				params["name"] = name
			if badge_type is not None:
				query_params.append("type = :type")
				params["type"] = badge_type

			if not query_params:
				raise ValueError("No filter specified.")

			async with db.execute(f"SELECT * FROM badges WHERE {' AND '.join(query_params)} LIMIT 1", params) as cursor:
				if row := await cursor.fetchone():
					return Badge(**row)
				return None

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_legacy_leaderboard_users(self, ordering_by: Literal["ASCENDING", "DESCENDING"] = "DESCENDING") -> list[tuple[MasterUser, int]]:
		order = "ASC" if ordering_by == "ASCENDING" else "DESC"
		async with self.connect() as db:
			async with db.execute(f"""
			SELECT u.*, l.exp
			FROM legacy_leaderboard l
			JOIN users u ON u.id = l.user_id
			ORDER BY l.exp {order}
			""") as cursor:
				rows = await cursor.fetchall()
				result = []
				for row in rows:
					user_data = {k: row[k] for k in row.keys() if k in MasterUser.__annotations__}
					result.append((MasterUser(**user_data, _db=self), row["exp"]))
				return result

	async def to_dict(self) -> dict:
		master_json = {"badges": [], "users": [], "leaderboards": {"legacy": []}}

		return master_json
