from internal.base.bot import NatsuBot
from fastapi import Request, Depends
from typing import Annotated


def get_bot(request: Request) -> NatsuBot:
	return request.app.state.bot


type BotDep = Annotated[NatsuBot, Depends(get_bot)]
