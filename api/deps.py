from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request, Depends, HTTPException, status
from internal.base.bot import NatsuBot
from api.models import PartialUser
from internal.sql import select
from typing import Annotated

import hashlib


def get_bot(request: Request) -> NatsuBot:
	return request.app.state.bot


bearer_scheme = HTTPBearer()

type BotDep = Annotated[NatsuBot, Depends(get_bot)]


async def get_current_user(bot: BotDep, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]) -> PartialUser:
	token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()

	query = (
		select("api_token", "t")
		.columns("u.id", "u.discord_id", "u.username", "u.rep", "u.gen", "u.created_at", "u.updated_at")
		.join("user u ON u.id = t.user_id")
		.where("t.hash = ? AND t.removed_at IS NULL", token_hash)
	)

	async with bot.database.connect() as conn:
		async with conn.execute(*query.build()) as cursor:
			row = await cursor.fetchone()

	if row is None:
		raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

	return PartialUser(**dict(row))


type CurrentUserDep = Annotated[PartialUser, Depends(get_current_user)]
