from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum, Enum
import os
import aiosqlite
from async_lru import alru_cache

__all__ = ["UserStatus", "UserKind", "ContractType", "ContractStatus", "ContractKind", "Contract", "User", "SeasonDB", "SeasonSyncContext"]

with open("contracts/Season.sql") as f:
	season_script = f.read()
CACHE_DURATION_MINUTES = 3


class UserStatus(Enum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3
	INCOMPLETE = 4


class UserKind(Enum):
	"""
	NORMAL - A normal user that is in the current season

	AID - A user that isn't in the current season and is in aids
	"""

	NORMAL = 0
	AID = 1


class ContractType(StrEnum):
	BASE_CONTRACT = "Base Contract"
	CHALLENGE_CONTRACT = "Challenge Contract"
	BASE_BUDDY = "Base Buddy"
	CHALLENGE_BUDDY = "Challenge Buddy"
	VETERAN_SPECIAL = "Veteran Special"
	MOVIE_SPECIAL = "Movie Special"
	VN_SPECIAL = "VN Special"
	INDIE_SPECIAL = "Indie Special"
	EXTREME_SPECIAL = "Extreme Special"
	TRASH_SPECIAL = "Trash Special"
	COMMUNITY_SPECIAL = "Community Special"
	MYSTERY_SPECIAL = "Mystery Special"
	AID_CONTRACT_1 = "Aid Contract 1"
	AID_CONTRACT_2 = "Aid Contract 2"


class ContractStatus(Enum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3


class ContractKind(Enum):
	NORMAL = 0
	AID = 1


@dataclass(slots=True)
class Contract:
	id: int
	name: str
	type: ContractType
	kind: ContractKind
	status: ContractStatus
	contractee: str
	optional: bool = field(default=False, repr=False)
	contractor: str = field(default="", repr=False)
	progress: str = field(default="", repr=False)
	rating: str = field(default="", repr=False)
	review_url: str = field(default="", repr=False)
	medium: str = field(default="", repr=False)

	def __eq__(self, value):
		if isinstance(value, Contract):
			return self.id == value.id
		elif isinstance(value, int):
			return self.id == value

		return False


@dataclass(slots=True)
class User:
	username: str
	status: UserStatus
	kind: UserKind
	discord_id: int = field(default=None, repr=False)
	rep: str = field(default="")
	contractor: str = field(default="", repr=False)
	list_url: str = field(default="", repr=False)
	veto_used: bool = field(default=False, repr=False)
	accepting_manhwa: bool = field(default=False, repr=False)
	accepting_ln: bool = field(default=False, repr=False)
	preferences: str = field(default="", repr=False)
	bans: str = field(default="", repr=False)

	def __eq__(self, value):
		if isinstance(value, User):
			return self.username == value.username
		elif isinstance(value, str):
			return self.username == value

		return False


def _construct_user(row: list) -> User:
	return User(
		username=row[0],
		status=UserStatus(row[1]),
		kind=UserKind(row[2]),
		discord_id=row[3],
		rep=row[4],
		contractor=row[5],
		list_url=row[6],
		veto_used=bool(row[7]),
		accepting_manhwa=bool(row[8]),
		accepting_ln=bool(row[9]),
		preferences=row[10],
		bans=row[11],
	)


def _construct_contract(row: list) -> Contract:
	return Contract(
		id=row[0],
		name=row[1],
		type=ContractType(row[2]),
		kind=ContractKind(row[3]),
		status=ContractStatus(row[4]),
		contractee=row[5],
		optional=bool(row[6]),
		contractor=row[7],
		progress=row[8],
		rating=row[9],
		review_url=row[10],
		medium=row[11],
	)


def _build_query_conditions(kwargs: dict[str]) -> tuple[str, dict]:
	query_conditions = []
	params = {}
	param_counter = 0

	for key, value in kwargs.items():
		if isinstance(value, tuple):
			placeholders = []
			operator = "NOT IN" if key.startswith("not_") else "IN"
			actual_key = key[4:] if key.startswith("not_") else key
			for v in value:
				param_key = f"{actual_key}_{param_counter}"
				param_counter += 1
				placeholders.append(f":{param_key}")
				params[param_key] = v.value if isinstance(v, Enum) else v
			query_conditions.append(f"{actual_key} {operator} ({', '.join(placeholders)})")
		else:
			operator = "!=" if key.startswith("not_") else "="
			actual_key = key[4:] if key.startswith("not_") else key
			params[key] = value.value if isinstance(value, Enum) else value
			query_conditions.append(f"{actual_key} {operator} :{key}")

	where_clause = " AND ".join(query_conditions) if query_conditions else ""
	return where_clause, params


class SeasonDB:
	def __init__(self, name: str, path: str):
		self.name = name
		self.path = path

	@asynccontextmanager
	async def connect(self):
		async with aiosqlite.connect(self.path) as db:
			yield db

	async def setup(self):
		os.makedirs(os.path.dirname(self.path), exist_ok=True)
		async with self.connect() as db:
			await db.executescript(season_script)
			await db.commit()

	async def create_user(self, username: str, status: UserStatus, kind: UserKind, **kwargs):
		columns = ["username", "status", "kind"]
		values = {"username": username, "status": status.value, "kind": kind.value}

		for key, value in kwargs.items():
			columns.append(key)
			values[key] = value.value if isinstance(value, Enum) else value

		columns_str = ", ".join(columns)
		placeholders_str = ", ".join(f":{col}" for col in columns)

		query = f"""
		INSERT INTO users ({columns_str})
		VALUES ({placeholders_str})
		"""

		async with self.connect() as db:
			await db.execute(query, values)
			await db.commit()

	async def create_contract(self, name: str, type: ContractType, kind: ContractKind, status: ContractStatus, contractee: str, **kwargs) -> int:
		columns = ["name", "type", "kind", "status", "contractee"]
		values = {"name": name, "type": type.value, "kind": kind.value, "status": status.value, "contractee": contractee}

		for key, value in kwargs.items():
			columns.append(key)
			values[key] = value.value if isinstance(value, Enum) else value

		columns_str = ", ".join(columns)
		placeholders_str = ", ".join(f":{col}" for col in columns)

		query = f"""
		INSERT INTO contracts ({columns_str})
		VALUES ({placeholders_str})
		"""

		async with self.connect() as db:
			cursor = await db.execute(query, values)
			await db.commit()
			return cursor.lastrowid

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def fetch_user(self, **kwargs) -> User | None:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT * FROM users"
		if where_clause:
			query += f" WHERE {where_clause}"
		query += " LIMIT 1"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				row = await cursor.fetchone()
				if row:
					return _construct_user(row)
				return None

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def fetch_contract(self, **kwargs) -> Contract | None:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT * FROM contracts"
		if where_clause:
			query += f" WHERE {where_clause}"
		query += " LIMIT 1"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				row = await cursor.fetchone()
				if row:
					return _construct_contract(row)
				return None

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def fetch_users(self, limit: int = None, **kwargs) -> list[User]:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT * FROM users"
		if where_clause:
			query += f" WHERE {where_clause}"
		if limit is not None:
			query += f" LIMIT {limit}"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [_construct_user(row) for row in rows]

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def fetch_contracts(self, limit: int = None, **kwargs) -> list[Contract]:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT * FROM contracts"
		if where_clause:
			query += f" WHERE {where_clause}"
		if limit is not None:
			query += f" LIMIT {limit}"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				rows = await cursor.fetchall()
				return [_construct_contract(row) for row in rows]

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def count_users(self, **kwargs) -> int:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT COUNT(*) FROM users"
		if where_clause:
			query += f" WHERE {where_clause}"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				row = await cursor.fetchone()
				return row[0]

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def count_contracts(self, **kwargs) -> int:
		where_clause, params = _build_query_conditions(kwargs)
		query = "SELECT COUNT(*) FROM contracts"
		if where_clause:
			query += f" WHERE {where_clause}"

		async with self.connect() as db:
			async with db.execute(query, params) as cursor:
				row = await cursor.fetchone()
				return row[0]

	async def update_user(self, username: str, **kwargs):
		for key, value in kwargs.items():
			if isinstance(value, Enum):
				kwargs[key] = value.value
		query_set = ", ".join(f"{key} = :{key}" for key in kwargs)
		query = f"UPDATE users SET {query_set} WHERE username = :username"

		async with self.connect() as db:
			await db.execute(query, {"username": username, **kwargs})
			await db.commit()

	async def update_contract(self, id: int, **kwargs):
		for key, value in kwargs.items():
			if isinstance(value, Enum):
				kwargs[key] = value.value
		query_set = ", ".join(f"{key} = :{key}" for key in kwargs)
		query = f"UPDATE contracts SET {query_set} WHERE id = :id"

		async with self.connect() as db:
			await db.execute(query, {"id": id, **kwargs})
			await db.commit()

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def has_user(self, username: str) -> bool:
		async with self.connect() as db:
			async with db.execute("SELECT 1 FROM users WHERE username = :username", {"username": username}) as cursor:
				return await cursor.fetchone() is not None

	@alru_cache(ttl=CACHE_DURATION_MINUTES * 60)
	async def has_contract(self, id: int) -> bool:
		async with self.connect() as db:
			async with db.execute("SELECT 1 FROM contracts WHERE id = :id", {"id": id}) as cursor:
				return await cursor.fetchone() is not None


class SeasonSyncContext:
	def __init__(self):
		self.users: dict[str, User] = {}
		self.contracts: dict[str, dict[ContractType, Contract]] = {}

	async def load(self, db: SeasonDB):
		db.fetch_users.cache_clear()
		db.fetch_contracts.cache_clear()
		self.users = {u.username: u for u in await db.fetch_users()}
		self.contracts = {}
		for contract in await db.fetch_contracts():
			self.contracts.setdefault(contract.contractee, {})[contract.type] = contract
