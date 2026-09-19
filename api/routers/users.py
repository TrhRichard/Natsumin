from api.models import Badge, PartialUser, User, UserLegacyLeaderboard, UserLeaderboards
from internal.functions import get_legacy_rank
from internal.sql import select
from fastapi import APIRouter
from api.deps import BotDep
from uuid import UUID


router = APIRouter()


@router.get("/", summary="Fetch all users")
async def get_users(bot: BotDep) -> list[PartialUser]:
	async with bot.database.connect() as conn:
		async with conn.execute("SELECT id, discord_id, username, rep, gen, created_at, updated_at FROM user ORDER BY username") as cursor:
			rows = await cursor.fetchall()
	return [dict(r) for r in rows]


@router.get("/{user_id}", summary="Fetch 1 user")
async def get_user(bot: BotDep, user_id: UUID) -> User | None:
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
			return None

		legacy = None
		if row["legacy_exp"] is not None:
			legacy = UserLegacyLeaderboard(exp=row["legacy_exp"], rank=get_legacy_rank(row["legacy_exp"]).value)

		query = (
			select("user_badge", "ub")
			.join("badge b ON b.id = ub.badge_id")
			.where("ub.user_id = ?", user_id)
			.columns("b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.created_at", "b.updated_at")
		)
		async with conn.execute(*query.build()) as cursor:
			badges = [Badge(**dict(row)) for row in await cursor.fetchall()]

		return User(
			**{k: row[k] for k in ("id", "discord_id", "username", "rep", "gen", "created_at", "updated_at")},
			leaderboard=UserLeaderboards(legacy=legacy),
			badges=badges,
		)
