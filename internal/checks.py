from __future__ import annotations

from internal.exceptions import UnauthorizedUser
from internal.base.context import NatsuContext
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from typing import Callable


DATABASE_EDIT_PERM = (546659584727580692, 448318227219742720, 243880818651430912, 133087204980424704)


def can_modify_database[T]() -> Callable[[T], T]:
	async def predicate(ctx: NatsuContext) -> bool:
		if ctx.author.id in DATABASE_EDIT_PERM or await ctx.bot.is_owner(ctx.author):
			return True

		raise UnauthorizedUser()

	return commands.check(predicate)


def whitelist_channel_only[T]() -> Callable[[T], T]:
	async def predicate(ctx: NatsuContext) -> bool:
		is_blacklisted, _ = await ctx.bot.is_blacklisted(ctx, raise_exception=True, ignore_channel=False)
		return not is_blacklisted

	return commands.check(predicate)
