from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from .master import MasterDB, MasterUser
from async_lru import alru_cache
from enum import Enum
import os
import aiosqlite


__all__ = ["UserStatus", "ContractStatus", "ContractKind", "Contract", "SeasonUser", "SeasonDB"]

with open("assets/schemas/Season.sql") as f:
	season_script = f.read()
CACHE_DURATION = 3 * 60


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
	_db: "SeasonDB" = None

	def __eq__(self, value):
		if isinstance(value, SeasonUser):
			return self.user_id == value.user_id
		elif isinstance(value, int):
			return self.user_id == value

		return False

	async def get_master_data(self) -> MasterUser:
		return await self._db.fetch_user_from_master(id=self.user_id)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_contracts(self) -> list["Contract"]:
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
