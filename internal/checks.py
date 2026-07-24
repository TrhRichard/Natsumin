from __future__ import annotations

from internal.base.context import NatsuContext
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from collections.abc import Callable


def whitelist_channel_only[T]() -> Callable[[T], T]:
	async def predicate(ctx: NatsuContext) -> bool:
		is_blacklisted, _ = await ctx.bot.is_blacklisted(ctx, raise_exception=True, ignore_channel=False)
		return not is_blacklisted

	return commands.check(predicate)
