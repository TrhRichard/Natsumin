from __future__ import annotations

from .functions import is_channel
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot
	from typing import Callable


def must_be_channel[T](*channel_ids: int, guild_id: int = 994071728017899600, bypass_roles: list[int] = None) -> Callable[[T], T]:
	async def predicate(ctx: commands.Context) -> bool:
		return is_channel(ctx, *channel_ids, guild_id=guild_id, raise_exception=True, bypass_roles=bypass_roles)

	return commands.check(predicate)


CAN_MODIFY_BADGES = (448318227219742720, 243880818651430912)


def can_modify_badges[T]() -> Callable[[T], T]:
	async def predicate(ctx: commands.Context) -> bool:
		bot: NatsuminBot = ctx.bot
		if await bot.is_owner(ctx.author) or ctx.author.id in CAN_MODIFY_BADGES:
			return True

		raise commands.MissingPermissions(["badge_edit"])

	return commands.check(predicate)
