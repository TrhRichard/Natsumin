from api.models import User, Badge, UserLegacyLeaderboard, UserLeaderboards
from fastapi import APIRouter, HTTPException, status
from internal.functions import get_legacy_rank
from api.deps import BotDep, CurrentUserDep
from internal.constants import BADGE_ORDER
from internal.base.bot import NatsuBot
from internal.sql import select
from uuid import UUID

import aiosqlite

router = APIRouter()


async def fetch_user_badges(bot: NatsuBot, user_id: UUID, *, db_conn: aiosqlite.Connection | None = None) -> list[Badge]:
	query = (
		select("user_badge", "ub")
		.join("badge b ON b.id = ub.badge_id")
		.where("ub.user_id = ?", user_id)
		.columns("b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.created_at", "b.updated_at")
		.order_by(*BADGE_ORDER)
	)
	async with bot.database.connect(db_conn) as conn:
		async with conn.execute(*query.build()) as cursor:
			return [Badge(**dict(row)) for row in await cursor.fetchall()]


async def user_exists(bot: NatsuBot, user_id: UUID, *, db_conn: aiosqlite.Connection | None = None) -> bool:
	async with bot.database.connect(db_conn) as conn:
		async with conn.execute("SELECT 1 FROM user WHERE id = ?", (user_id,)) as cursor:
			return await cursor.fetchone() is not None


@router.get("/@me", summary="Get the details of the account you are logged in as")
async def get_self(current_user: CurrentUserDep) -> User:
	return current_user


@router.get("/@me/badges", summary="Get badges that you own", tags=["users", "badges"])
async def get_self_badges(bot: BotDep, current_user: CurrentUserDep) -> list[Badge]:
	return await fetch_user_badges(bot, current_user.id)


@router.get("/{user_id}", summary="Fetch one user", responses={404: {"description": "User not found"}})
async def get_user(bot: BotDep, user_id: UUID) -> User:
	async with bot.database.connect() as conn:
		query = (
			select("user", "u")
			.join("leaderboard_legacy ll ON ll.user_id = u.id")
			.columns("u.id", "u.discord_id", "u.username", "u.rep", "u.gen", "u.created_at", "u.updated_at", "ll.exp AS legacy_exp")
			.where("u.id = ?", user_id)
		)

		async with conn.execute(*query.build()) as cursor:
			row = await cursor.fetchone()

		if row is None:
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

		legacy = None
		if row["legacy_exp"] is not None:
			legacy = UserLegacyLeaderboard(exp=row["legacy_exp"], rank=get_legacy_rank(row["legacy_exp"]).value)

		return User(
			**{k: row[k] for k in ("id", "discord_id", "username", "rep", "gen", "created_at", "updated_at")},
			leaderboard=UserLeaderboards(legacy=legacy),
		)


@router.get("/{user_id}/badges", summary="Get badges that a user owns", tags=["users", "badges"], responses={404: {"description": "User not found"}})
async def get_user_badges(bot: BotDep, user_id: UUID) -> list[Badge]:
	async with bot.database.connect() as conn:
		if not await user_exists(bot, user_id, db_conn=conn):
			raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
		return await fetch_user_badges(bot, user_id, db_conn=conn)
