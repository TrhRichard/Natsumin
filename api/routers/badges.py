from fastapi import APIRouter
from api.models import Badge
from api.deps import BotDep

router = APIRouter()


@router.get("/", summary="Fetch all badges")
async def get_badges(bot: BotDep) -> list[Badge]:
	async with bot.database.connect() as conn:
		async with conn.execute("SELECT * FROM badge") as cursor:
			rows = await cursor.fetchall()
	return [dict(r) for r in rows]
