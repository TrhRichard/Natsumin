from utils.contracts import get_legacy_rank
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from async_lru import alru_cache
from typing import Literal
from enum import StrEnum
import aiosqlite


class BadgeType(StrEnum):
	CONTRACTS = "contracts"
	ARIA = "aria"


CACHE_DURATION = 3 * 60


@dataclass(slots=True)
class MasterUser:
	id: int
	discord_id: int | None
	username: str
	rep: str
	gen: int | None
	_db: "MasterDB" = field(repr=False, default=None)

	@alru_cache(ttl=CACHE_DURATION)
	async def get_legacy_exp(self) -> int | None:
		async with self._db.connect() as db:
			async with db.execute("SELECT * FROM legacy_leaderboard WHERE user_id = ? LIMIT 1", (self.id,)) as cursor:
				if row := await cursor.fetchone():
					return row["exp"]
				return None

	@alru_cache(ttl=CACHE_DURATION)
	async def get_badges(self, badge_type: BadgeType | None = None) -> list["Badge"]:
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

	async def give_badge(self, badge: "Badge"):
		async with self._db.connect() as db:
			await db.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?, ?)", (self.id, badge.id))
			await db.commit()

	@alru_cache(ttl=CACHE_DURATION)
	async def has_badge(self, badge: "Badge") -> bool:
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


class MasterDB:
	def __init__(self, name: str, path: str = "data/master.db"):
		self.name = name
		self.path = path

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
