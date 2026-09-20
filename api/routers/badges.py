from fastapi import APIRouter, Depends, HTTPException, status
from api.deps import BotDep, PaginationDep, is_authenticated
from internal.schemas import BadgeType, BadgeRarity
from internal.sql import select, insert, update
from internal.constants import BADGE_ORDER
from internal.base.bot import NatsuBot
from pydantic import Field, BaseModel
from api.models import Badge
from typing import Annotated
from uuid import UUID, uuid4


import aiosqlite

router = APIRouter()


async def badge_exists(bot: NatsuBot, badge_id: UUID, *, db_conn: aiosqlite.Connection | None = None) -> bool:
	async with bot.database.connect(db_conn) as conn:
		async with conn.execute("SELECT 1 FROM badge WHERE id = ?", (badge_id,)) as cursor:
			return await cursor.fetchone() is not None


class FilterParams(BaseModel):
	query: str | None = Field(None, alias="q")
	artist: str | None = None
	type: BadgeType | None = None
	rarity: BadgeRarity | None = None


@router.get("/", summary="Get all badges")
async def get_badges(bot: BotDep, filter: Annotated[FilterParams, Depends()], pagination: PaginationDep) -> list[Badge]:
	async with bot.database.connect() as conn:
		query = (
			select("badge", "b")
			.columns("b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.created_at", "b.updated_at")
			.order_by(*BADGE_ORDER)
			.limit(pagination.limit, pagination.offset)
		)

		query.where("b.name LIKE ?", f"%{filter.query}%", cond=filter.query is not None)
		query.where("b.artist LIKE ?", f"%{filter.artist}%", cond=filter.artist is not None)
		query.where("b.type = ?", filter.type, cond=filter.type is not None)
		query.where("b.rarity = ?", filter.rarity, cond=filter.rarity is not None)

		async with conn.execute(*query.build()) as cursor:
			rows = await cursor.fetchall()
	return [dict(r) for r in rows]


@router.get("/{badge_id}", summary="Get one badge", responses={404: {"description": "Badge not found"}})
async def get_badge(bot: BotDep, badge_id: UUID) -> Badge:
	async with bot.database.connect() as conn:
		if not await badge_exists(bot, badge_id, db_conn=conn):
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Badge not found")

		query = (
			select("badge", "b")
			.columns("b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.created_at", "b.updated_at")
			.where("b.id = ?", badge_id)
		)

		async with conn.execute(*query.build()) as cursor:
			return dict(await cursor.fetchone())


class BadgeModifyRequest(BaseModel):
	name: str | None = Field(None, min_length=1, max_length=256)
	description: str | None = Field(None, max_length=1024)
	artist: str | None = None
	url: str | None = None
	type: BadgeType | None = None
	rarity: BadgeRarity | None = None
	value: int | None = None


@router.patch(
	"/{badge_id}", summary="Modify a existing badge", responses={404: {"description": "Badge not found"}}, dependencies=[Depends(is_authenticated)]
)
async def modify_badge(bot: BotDep, badge_id: UUID, modifications: BadgeModifyRequest) -> None:
	async with bot.database.connect() as conn:
		if not await badge_exists(bot, badge_id, db_conn=conn):
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Badge not found")

		query = update("badge").where("id = ?", badge_id)

		query.set("name", modifications.name, cond=modifications.name is not None)
		query.set("description", modifications.description, cond=modifications.description is not None)
		query.set("artist", modifications.artist, cond=modifications.artist is not None)
		query.set("url", modifications.url, cond=modifications.url is not None)
		query.set("type", modifications.type, cond=modifications.type is not None)
		query.set("value", modifications.value, cond=modifications.value is not None)

		await conn.execute(*query.build())
		await conn.commit()


@router.delete(
	"/{badge_id}", summary="Delete a existing badge", responses={404: {"description": "Badge not found"}}, dependencies=[Depends(is_authenticated)]
)
async def delete_badge(bot: BotDep, badge_id: UUID) -> None:
	async with bot.database.connect() as conn:
		if not await badge_exists(bot, badge_id, db_conn=conn):
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Badge not found")

		await conn.execute("DELETE FROM badge WHERE id = ?", (badge_id,))
		await conn.commit()


class BadgeCreateRequest(BaseModel):
	name: str = Field(min_length=1, max_length=256)
	description: str = Field("", max_length=1024)
	artist: str = ""
	url: str = ""
	type: BadgeType = "contracts"
	rarity: BadgeRarity = "common"
	value: int = 0


@router.post("/", summary="Create a new badge", dependencies=[Depends(is_authenticated)])
async def create_badge(bot: BotDep, data: BadgeCreateRequest) -> UUID:
	async with bot.database.connect() as conn:
		badge_id = uuid4()

		query = insert("badge").values(
			id=badge_id,
			name=data.name,
			description=data.description,
			artist=data.artist,
			url=data.url,
			type=data.type,
			rarity=data.rarity,
			value=data.value,
		)
		await conn.execute(*query.build())
		await conn.commit()

		return badge_id
