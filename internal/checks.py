from __future__ import annotations

from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot
	from typing import Callable


CAN_MODIFY_BADGES = (448318227219742720, 243880818651430912)


def can_modify_badges[T]() -> Callable[[T], T]:
	async def predicate(ctx: commands.Context) -> bool:
		bot: NatsuminBot = ctx.bot
		if await bot.is_owner(ctx.author) or ctx.author.id in CAN_MODIFY_BADGES:
			return True

		raise commands.MissingPermissions(["badge_edit"])

	return commands.check(predicate)


def whitelist_channel_only[T]() -> Callable[[T], T]:
	async def predicate(ctx: commands.Context[NatsuminBot]) -> bool:
		is_blacklisted, _ = await ctx.bot.is_blacklisted(ctx, raise_exception=True, ignore_channel=False)
		return not is_blacklisted

	return commands.check(predicate)
