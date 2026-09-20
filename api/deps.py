from api.models import User, UserLeaderboards, UserLegacyLeaderboard, PaginationParams
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request, Depends, HTTPException, status
from internal.functions import get_legacy_rank
from internal.base.bot import NatsuBot
from internal.sql import select
from typing import Annotated

import hashlib


def get_bot(request: Request) -> NatsuBot:
	return request.app.state.bot


bearer_scheme = HTTPBearer(
	scheme_name="API Key", description="The token cannot be received from any endpoint and can only come from asking the owner"
)

type BotDep = Annotated[NatsuBot, Depends(get_bot)]
type PaginationDep = Annotated[PaginationParams, Depends()]


async def get_current_user(bot: BotDep, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]) -> User:
	token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()

	query = (
		select("api_token", "t")
		.columns("u.id", "u.discord_id", "u.username", "u.rep", "u.gen", "u.created_at", "u.updated_at", "ll.exp AS legacy_exp")
		.join("user u ON u.id = t.user_id")
		.join("leaderboard_legacy ll ON ll.user_id = u.id")
		.where("t.hash = ? AND t.removed_at IS NULL", token_hash)
	)

	async with bot.database.connect() as conn:
		async with conn.execute(*query.build()) as cursor:
			row = await cursor.fetchone()

	if row is None:
		raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

	legacy = None
	if row["legacy_exp"] is not None:
		legacy = UserLegacyLeaderboard(exp=row["legacy_exp"], rank=get_legacy_rank(row["legacy_exp"]).value)

	return User(
		**{k: row[k] for k in ("id", "discord_id", "username", "rep", "gen", "created_at", "updated_at")}, leaderboard=UserLeaderboards(legacy=legacy)
	)


async def is_authenticated(bot: BotDep, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]) -> None:
	token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()

	query = select("api_token", "t").columns("1").join("user u ON u.id = t.user_id").where("t.hash = ? AND t.removed_at IS NULL", token_hash)

	async with bot.database.connect() as conn:
		async with conn.execute(*query.build()) as cursor:
			row = await cursor.fetchone()

	if row is None:
		raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


type CurrentUserDep = Annotated[User, Depends(get_current_user)]
