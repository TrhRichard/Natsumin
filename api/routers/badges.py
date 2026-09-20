from api.deps import BotDep, CurrentUserDep
from internal.constants import BADGE_ORDER
from internal.sql import select
from fastapi import APIRouter
from api.models import Badge

router = APIRouter()


@router.get("/", summary="Fetch all badges")
async def get_badges(bot: BotDep) -> list[Badge]:
	async with bot.database.connect() as conn:
		query = (
			select("badge", "b")
			.columns(
				"b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.value", "b.created_at", "b.updated_at"
			)
			.order_by(*BADGE_ORDER)
		)
		async with conn.execute(*query.build()) as cursor:
			rows = await cursor.fetchall()
	return [dict(r) for r in rows]


@router.get("/@me", summary="Get badges that you own")
async def get_self_badges(bot: BotDep, current_user: CurrentUserDep) -> list[Badge]:
	async with bot.database.connect() as conn:
		query = (
			select("user_badge", "ub")
			.join("badge b ON b.id = ub.badge_id")
			.where("ub.user_id = ?", current_user.id)
			.columns("b.id", "b.name", "b.description", "b.artist", "b.url", "b.type", "b.rarity", "b.value", "b.created_at", "b.updated_at")
			.order_by(*BADGE_ORDER)
		)
		async with conn.execute(*query.build()) as cursor:
			badges = [Badge(**dict(row)) for row in await cursor.fetchall()]

		return badges

	return current_user
