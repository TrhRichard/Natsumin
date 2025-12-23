from __future__ import annotations

from internal.exceptions import WrongChannel, BlacklistedUser
from internal.base.cog import NatsuminCog
from internal.functions import frmt_iter
from internal.constants import COLORS
from discord.ext import commands

import aiosqlite
import datetime
import sqlite3
import discord


class Errors(NatsuminCog):
	def get_error_info(self, error: Exception) -> tuple[str, str, bool]:
		err_type, err_details, should_log = "", "", False
		if isinstance(error, commands.NotOwner):
			err_type = "Owner-only command"
			err_details = f"This command is restricted to {self.bot.user.name}'s owner."
		elif isinstance(error, commands.MissingPermissions):
			err_type = "Missing Permissions"
			err_details = f"You do not have enough permissions to use this command.\nMissing permissions: {frmt_iter(error.missing_permissions)}"
		elif isinstance(error, commands.BotMissingPermissions):
			err_type = "Bot Missing Permissions"
			err_details = (
				f"The bot is missing the required permissions to perform this command.\nMissing permissions: {frmt_iter(error.missing_permissions)}"
			)
		elif isinstance(error, commands.MissingRequiredArgument):
			err_type = "Missing Required Argument"
			err_details = f"You are missing required argument ``{error.param.name}``."
		elif isinstance(error, discord.HTTPException):
			err_type = "HTTP Exception"
			err_details = f'An HTTP error occured: "{error.text}" ({error.status})'
			should_log = True
		elif isinstance(error, commands.CommandOnCooldown):
			err_type = "Cooldown"
			err_details = f"You may retry again in **{error.retry_after:.2f}** seconds."
		elif isinstance(error, WrongChannel):
			err_details = str(error)
			should_log = False
		elif isinstance(error, BlacklistedUser):
			err_details = "no"
			should_log = False
		elif isinstance(error, (aiosqlite.Error, sqlite3.Error)):
			err_type = "SQLite Exception"
			err_details = "Encountered a SQLite error, for more info check the console."
			should_log = True
		else:
			err_type = type(error).__name__
			err_details = str(error)
			should_log = True

		return err_type, err_details, should_log

	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error: Exception):
		error = getattr(error, "original", error)

		if isinstance(error, commands.CommandNotFound):
			return

		err_type, err_details, should_log = self.get_error_info(error)

		if should_log:
			self.bot.logger.error(f"Command error from @{ctx.author.name} in {ctx.clean_prefix}{ctx.command}", exc_info=error)

		if ctx.channel.guild:
			channel_perms = ctx.channel.permissions_for(ctx.channel.guild.me)
			if not channel_perms.send_messages:
				return

		embed = discord.Embed(
			title=err_type if err_type else None, description=err_details, timestamp=datetime.datetime.now(datetime.UTC), color=COLORS.ERROR
		)
		try:
			await ctx.reply(embed=embed)
		except discord.NotFound:
			pass

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception):
		error = getattr(error, "original", error)
		err_type, err_details, should_log = self.get_error_info(error)
		if err_type is None and err_details is None:
			return

		if should_log:
			self.bot.logger.error(f"Application command error from @{ctx.author.name} in /{ctx.command}", exc_info=error)

		embed = discord.Embed(
			title=err_type if err_type else None, description=err_details, timestamp=datetime.datetime.now(datetime.UTC), color=COLORS.ERROR
		)
		try:
			await ctx.respond(embed=embed, ephemeral=True)
		except discord.NotFound:
			pass
