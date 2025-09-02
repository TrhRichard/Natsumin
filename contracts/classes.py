from __future__ import annotations
from typing import Literal, overload, get_type_hints
from utils.contracts import get_legacy_rank
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from async_lru import alru_cache
from thefuzz import process
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


class UserKind(Enum):
	NORMAL = 0
	AID = 1


@dataclass(slots=True, eq=False)
class SeasonUser:
	id: int
	status: UserStatus
	kind: UserKind
	rep: str | None = None
	contractor: str | None = field(default=None, repr=False)
	list_url: str | None = field(default=None, repr=False)
	veto_used: bool = field(default=False, repr=False)
	accepting_manhwa: bool = field(default=False, repr=False)
	accepting_ln: bool = field(default=False, repr=False)
	preferences: str | None = field(default=None, repr=False)
	bans: str | None = field(default=None, repr=False)
	_db: SeasonDB = None

	def __hash__(self):
		return hash(self.id)

	def __eq__(self, value):
		if isinstance(value, SeasonUser):
			return self.id == value.id
		elif isinstance(value, int):
			return self.id == value

		return False

	@classmethod
	def new(cls, **kwargs):
		cls_types = get_type_hints(cls)
		for k, v in kwargs.items():
			if k in cls_types:
				k_type = cls_types.get(k)
				if issubclass(k_type, Enum):
					v = k_type(v)

				kwargs[k] = v

		return cls(**kwargs)

	async def get_master_data(self) -> MasterUser:
		return await self._db.fetch_user_from_master(id=self.id)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_contracts(self) -> list[Contract]:
		async with self._db.connect() as db:
			async with db.execute("SELECT * FROM contracts WHERE contractee = ?", (self.id,)) as cursor:
				rows = await cursor.fetchall()
				return [Contract(**row, _db=self._db) for row in rows]

		return []

	async def to_dict(self, *, include_contracts: bool = False):
		master_user = await self.get_master_data()
		return {
			"user": await master_user.to_dict(include_badges=False),
			"status": self.status.name,
			"kind": self.kind.name,
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


@dataclass(slots=True, eq=False)
class Contract:
	id: int
	name: str
	type: str
	kind: ContractKind
	status: ContractStatus
	contractee: int
	contractor: str | None = field(default=None)
	optional: bool = field(default=False, repr=False)
	progress: str | None = field(default=None, repr=False)
	rating: str | None = field(default=None, repr=False)
	review_url: str | None = field(default=None, repr=False)
	medium: str | None = field(default=None, repr=False)
	_db: "SeasonDB" = None

	def __hash__(self):
		return hash((self.name, self.type, self.contractee))

	@classmethod
	def new(cls, **kwargs):
		cls_types = get_type_hints(cls)
		for k, v in kwargs.items():
			if k in cls_types:
				k_type = cls_types.get(k)
				if issubclass(k_type, Enum):
					v = k_type(v)

				kwargs[k] = v

		return cls(**kwargs)

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
			async with db.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,)) as cursor:
				if user := await cursor.fetchone():
					return SeasonUser(**user, _db=self)

	@alru_cache(ttl=CACHE_DURATION)
	async def fetch_user_from_master(self, *, id: int | None = None, username: str | None = None) -> MasterUser | None:
		if not self._master_db:
			return None

		return await self._master_db.fetch_user(id=id, username=username)


class SeasonDBSyncContext:
	def __init__(self, season_db: SeasonDB):
		self.season_db: SeasonDB = season_db
		self.master_db: MasterDB = MasterDB.get_database()

		self.total_users: dict[int, SeasonUser] = {}
		self.total_contracts: list[Contract] = []

		self._changes_required: dict[Contract | SeasonUser, dict[str]] = {}
		self._to_be_created: list[Contract | SeasonUser] = []

		self._username_to_id: dict[str, int] = None
		self._id_to_username: dict[int, str] = None

	async def setup(self):
		async with self.master_db.connect() as conn:
			async with conn.execute("SELECT id, username FROM users") as cursor:
				rows = await cursor.fetchall()
				self._username_to_id = {row["username"]: row["id"] for row in rows}
				self._id_to_username = {row["id"]: row["username"] for row in rows}

		async with self.season_db.connect() as conn:
			async with conn.execute("SELECT * FROM users") as cursor:
				self.total_users = {row["id"]: SeasonUser(**row, _db=self.season_db) for row in await cursor.fetchall()}

			async with conn.execute("SELECT * FROM contracts") as cursor:
				self.total_contracts = [Contract(**row, _db=self.season_db) for row in await cursor.fetchall()]

	def get_user_id(self, username: str) -> int | None:
		if username in self._username_to_id:
			return self._username_to_id.get(username)
		else:
			fuzzy_result = process.extractOne(username, self._id_to_username, score_cutoff=90)
			if fuzzy_result:
				return fuzzy_result[2]
			else:
				return None

	def get_user(self, id: int) -> SeasonUser | None:
		return self.total_users.get(id)

	def get_or_create_user(self, user_id: int, **kwargs) -> tuple[SeasonUser, bool]:
		"""Raises `ValueError` if there is no user with id in master.db"""

		if user_id not in self._id_to_username:
			raise ValueError("User does not exist.")

		if found_user := self.get_user(user_id):
			return found_user, True
		else:
			return self.create_user(id=user_id, **kwargs), False

	@overload
	def get_user_contracts(self, user_id: int, as_dict: Literal[True]) -> dict[str, Contract]: ...
	@overload
	def get_user_contracts(self, user_id: int, as_dict: Literal[False] = ...) -> list[Contract]: ...

	def get_user_contracts(self, user_id: int, as_dict: bool = False) -> list[Contract] | dict[str, Contract]:
		if not as_dict:
			contracts_found: list[Contract] = []

			for contract in self.total_contracts:
				if contract.contractee == user_id:
					contracts_found.append(contract)

			return contracts_found
		else:
			contract_list: dict[str, Contract] = {}

			for contract in self.total_contracts:
				if contract.contractee == user_id:
					contract_list[contract.type] = contract

			return contract_list

	def update_user(self, user: SeasonUser, **kwargs):
		if user in self._to_be_created:
			for k, v in kwargs.items():
				setattr(user, k, v)
			return

		for k, v in kwargs.items():
			setattr(user, k, v)
		if user in self._changes_required:
			self._changes_required[user].update(kwargs)
		else:
			self._changes_required[user] = kwargs

	def update_contract(self, contract: Contract, **kwargs):
		if contract in self._to_be_created:
			for k, v in kwargs.items():
				setattr(contract, k, v)
			return

		for k, v in kwargs.items():
			setattr(contract, k, v)
		if contract in self._changes_required:
			self._changes_required[contract].update(kwargs)
		else:
			self._changes_required[contract] = kwargs

	def create_user(self, **kwargs) -> SeasonUser:
		if "id" not in kwargs:
			raise ValueError("ID required to create a user.")
		user = SeasonUser(**kwargs, _db=self.season_db)
		self.total_users[kwargs["id"]] = user
		self._to_be_created.append(user)
		return user

	async def create_master_user(self, username: str) -> int:
		username = username.strip().lower()
		user_id = await self.master_db.create_user(username)
		self._username_to_id[username] = user_id
		self._id_to_username[user_id] = username
		return user_id

	def create_contract(self, **kwargs) -> Contract:
		contract = Contract(id=-1, **kwargs, _db=self.season_db)
		self.total_contracts.append(contract)
		self._to_be_created.append(contract)
		return contract

	def _convert_value(self, value: any) -> any:
		if isinstance(value, bool):
			return int(value)
		elif isinstance(value, Enum):
			return value.value
		else:
			return value

	async def commit(self):
		user_cols = ["id", "status", "kind", "rep", "contractor", "list_url", "veto_used", "accepting_manhwa", "accepting_ln", "preferences", "bans"]
		contract_cols = ["name", "type", "kind", "status", "contractee", "contractor", "optional", "progress", "rating", "review_url", "medium"]
		try:
			async with self.season_db.connect() as conn:
				for obj, changes in self._changes_required.items():
					if not changes:
						continue

					if isinstance(obj, SeasonUser):
						table = "users"
					elif isinstance(obj, Contract):
						table = "contracts"
					else:
						continue

					set_clause = ", ".join(f"{col} = ?" for col in changes.keys())
					values = [self._convert_value(v) for v in changes.values()]

					where_clause = "id = ?"
					if isinstance(obj, SeasonUser):
						values.append(obj.id)
					elif isinstance(obj, Contract):
						where_clause = "contractee = ? AND type = ? AND name = ?" if obj.id == -1 else "id = ?"
						if getattr(obj, "id", -1) == -1:
							values.append(obj.contractee)
							values.append(obj.type)
							values.append(obj.name)
						else:
							values.append(obj.id)

					await conn.execute(f"UPDATE {table} SET {set_clause} WHERE {where_clause}", values)

				user_values = [
					[self._convert_value(getattr(obj, col)) for col in user_cols] for obj in self._to_be_created if isinstance(obj, SeasonUser)
				]
				if user_values:
					placeholders = ", ".join("?" for _ in user_cols)
					await conn.executemany(f"INSERT INTO users ({', '.join(user_cols)}) VALUES ({placeholders})", user_values)

				contract_objs = [obj for obj in self._to_be_created if isinstance(obj, Contract)]
				if contract_objs:
					contract_values = [[self._convert_value(getattr(obj, col)) for col in contract_cols] for obj in contract_objs]
					placeholders = ", ".join("?" for _ in contract_cols)
					await conn.executemany(f"INSERT INTO contracts ({', '.join(contract_cols)}) VALUES ({placeholders})", contract_values)

				await conn.commit()
		except Exception as e:
			raise e
		finally:
			self._changes_required.clear()
			self._to_be_created.clear()


@dataclass(slots=True)
class MasterUser:
	id: int
	discord_id: int | None
	username: str
	rep: str
	gen: int | None
	_db: MasterDB = field(repr=False, default=None)

	def __hash__(self):
		return hash((self.id))

	@classmethod
	def new(cls, **kwargs):
		cls_types = get_type_hints(cls)
		for k, v in kwargs.items():
			if k in cls_types:
				k_type = cls_types.get(k)
				if issubclass(k_type, Enum):
					v = k_type(v)

				kwargs[k] = v

		return cls(**kwargs)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_legacy_exp(self) -> int | None:
		async with self._db.connect() as db:
			async with db.execute("SELECT * FROM legacy_leaderboard WHERE user_id = ? LIMIT 1", (self.id,)) as cursor:
				if row := await cursor.fetchone():
					return row["exp"]
				return None

	@alru_cache(ttl=CACHE_DURATION)
	async def get_badges(self, badge_type: BadgeType | None = None) -> list[Badge]:
		async with self._db.connect() as conn:
			async with conn.execute(
				f"""
					SELECT b.* FROM badges b
					JOIN user_badges ub ON b.id = ub.badge_id
					WHERE ub.user_id = ? {"AND b.type = ?" if badge_type is not None else ""}
					""",
				(self.id, badge_type) if badge_type is not None else (self.id,),
			) as cursor:
				rows = await cursor.fetchall()
				return [Badge.new(**row) for row in rows]

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

	async def to_dict(self, *, include_badges: bool = False, include_leaderboards: bool = False) -> dict:
		legacy_exp = await self.get_legacy_exp() if include_leaderboards else None
		return {
			"id": self.id,
			"discord_id": self.discord_id,
			"username": self.username,
			"rep": self.rep,
			"gen": self.gen,
			"leaderboards": {"legacy": {"exp": legacy_exp, "rank": get_legacy_rank(legacy_exp).value if legacy_exp is not None else None}}
			if include_leaderboards
			else {},
			"badges": [await badge.to_dict(minimal=True) for badge in await self.get_badges()] if include_badges else None,
		}


@dataclass(slots=True)
class Badge:
	id: int
	name: str
	description: str
	artist: str
	url: str
	type: BadgeType

	def __hash__(self):
		return hash((self.id))

	@classmethod
	def new(cls, **kwargs):
		cls_types = get_type_hints(cls)
		for k, v in kwargs.items():
			if k in cls_types:
				k_type = cls_types.get(k)
				if issubclass(k_type, Enum):
					v = k_type(v)

				kwargs[k] = v

		return cls(**kwargs)

	async def to_dict(self, *, minimal=False) -> dict:
		return (
			{"id": self.id, "name": self.name, "description": self.description, "artist": self.artist, "url": self.url, "type": self.type.value}
			if not minimal
			else {"id": self.id}
		)


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

	async def create_user(self, username: str, discord_id: int | None = None) -> int:
		async with self.connect() as conn:
			if discord_id is not None:
				async with conn.execute("SELECT id FROM users WHERE discord_id = ? OR username = ?", (discord_id, username)) as cursor:
					row = await cursor.fetchone()
					if row:
						return row["id"]

			async with conn.execute("INSERT INTO users (discord_id, username) VALUES (?, ?)", (discord_id, username)) as cursor:
				user_id = cursor.lastrowid

			await conn.commit()
			return user_id

	@alru_cache(ttl=CACHE_DURATION)
	async def to_dict(self, *, include_badges_in_users: bool = False, include_leaderboard_in_users: bool = False) -> dict:
		master_dict = {"badges": [], "users": [], "aliases": {}, "leaderboards": {"legacy": []}}

		async with self.connect() as conn:
			async with conn.execute("SELECT * FROM users") as cursor:
				users: list[MasterUser] = [MasterUser(**row, _db=self) for row in await cursor.fetchall()]

			async with conn.execute("SELECT * FROM badges") as cursor:
				badges: list[Badge] = [Badge.new(**row) for row in await cursor.fetchall()]

			user_aliases: dict[int, list[str]] = {}
			async with conn.execute("SELECT * FROM user_aliases") as cursor:
				for row in await cursor.fetchall():
					user_aliases.setdefault(row["user_id"], []).append(row["username"])

			async with conn.execute("SELECT * FROM legacy_leaderboard") as cursor:
				legacy_lb: list[dict[str]] = [
					{"user_id": row["user_id"], "exp": row["exp"], "rank": get_legacy_rank(row["exp"])} for row in await cursor.fetchall()
				]

		master_dict["badges"] = [await badge.to_dict() for badge in badges]
		master_dict["users"] = [
			await user.to_dict(include_badges=include_badges_in_users, include_leaderboards=include_leaderboard_in_users) for user in users
		]
		master_dict["aliases"] = user_aliases
		master_dict["leaderboards"]["legacy"] = sorted(legacy_lb, key=lambda k: k["exp"], reverse=True)

		return master_dict
