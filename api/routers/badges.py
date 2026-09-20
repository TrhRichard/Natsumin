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
