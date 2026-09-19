from pydantic import BaseModel, Field, PlainSerializer
from internal.schemas import BadgeType, BadgeRarity
from typing import Annotated
from uuid import UUID

import datetime as datetim

type DateTime = Annotated[datetim.datetime, PlainSerializer(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", return_type=str)]
type Date = Annotated[datetim.date, PlainSerializer(lambda d: d.isoformat(), return_type=str)]


class Badge(BaseModel):
	id: UUID
	name: str
	description: str
	artist: str
	url: str
	type: BadgeType
	rarity: BadgeRarity
	value: int
	created_at: DateTime
	updated_at: DateTime | None


class UserLegacyLeaderboard(BaseModel):
	rank: str
	exp: int


class UserLeaderboards(BaseModel):
	legacy: UserLegacyLeaderboard | None


class PartialUser(BaseModel):
	id: UUID
	discord_id: int | None
	username: str
	rep: str | None
	gen: int | None
	created_at: DateTime
	updated_at: DateTime | None


class User(PartialUser):
	leaderboard: UserLeaderboards = Field(title="leaderboard")
	badges: list[Badge]
