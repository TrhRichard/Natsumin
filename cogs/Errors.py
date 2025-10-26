from utils import FILE_LOGGING_FORMATTER, CONSOLE_LOGGING_FORMATTER
from discord.ext import commands
from discord import ui
import aiosqlite
import logging
import discord
import utils


class ErrorView(ui.DesignerView):
	def __init__(self, err_type: str, err_details: str):
		super().__init__(store=False)

		if err_type:
			error_display = ui.TextDisplay(f"### {err_type}\n-# {err_details}")
		else:
			error_display = ui.TextDisplay(f"-# {err_details}")

		self.add_item(
			ui.Container(
				ui.TextDisplay("-# **ERROR**"),
				error_display,
				ui.Separator(),
				ui.TextDisplay("-# If this error keeps happening, tell Richard."),
				color=discord.Color.red(),
			)
		)


class Errors(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.logger = logging.getLogger("bot.errors")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/errors.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)

			self.logger.setLevel(logging.ERROR)

	def get_error_info(self, error: Exception) -> tuple[str, str, bool]:
		err_type, err_details, should_log = "", "", True
		if isinstance(error, commands.NotOwner):
			err_type = "Owner-only command"
			err_details = f"This command is restricted to {self.bot.user.name}'s owner."
		elif isinstance(error, commands.MissingPermissions):
			err_type = "Missing Permissions"
			err_details = f"You do not have enough permissions to use this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
		elif isinstance(error, commands.BotMissingPermissions):
			err_type = "Bot Missing Permissions"
			err_details = (
				f"The bot is missing the required permissions to perform this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
			)
		elif isinstance(error, commands.MissingRequiredArgument):
			err_type = "Missing Required Argument"
			err_details = f"You are missing required argument ``{error.param.name}``."
		elif isinstance(error, discord.HTTPException):
			err_type = "HTTP Exception"
			err_details = f'An HTTP error occured: "{error.text}" ({error.status})'
		elif isinstance(error, commands.CommandOnCooldown):
			err_type = "Cooldown"
			err_details = f"You may retry again in **{error.retry_after:.2f}** seconds."
		elif isinstance(error, utils.WrongChannel):
			err_details = str(error)
			should_log = False  # This will probably happen a lot so instead of spamming logs I decided to just disable logging for it
		elif isinstance(error, aiosqlite.Error):
			err_type = "SQLite Exception"
			err_details = "Encountered a SQLite error, for more info check the console."
		else:
			err_type = type(error).__name__
			err_details = str(error)

		return err_type, err_details, should_log

	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error: Exception):
		error = getattr(error, "original", error)

		if isinstance(error, commands.CommandNotFound):
			return

		err_type, err_details, should_log = self.get_error_info(error)

		if should_log:
			self.logger.error(f"@{ctx.author.name} -> Command error in {ctx.command}", exc_info=error)

		if ctx.channel.guild:
			channel_perms = ctx.channel.permissions_for(ctx.channel.guild.me)
			if not channel_perms.send_messages:
				return

		await ctx.reply(view=ErrorView(err_type, err_details))

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception):
		error = getattr(error, "original", error)
		err_type, err_details, should_log = self.get_error_info(error)
		if err_type is None and err_details is None:
			return

		if should_log:
			self.logger.error(f"@{ctx.author.name} -> Application command error in {ctx.command}", exc_info=error)

		is_ephemeral = False
		if ctx.channel.guild:
			channel_perms = ctx.channel.permissions_for(ctx.channel.guild.me)
			is_ephemeral = not channel_perms.send_messages

		await ctx.respond(view=ErrorView(err_type, err_details), ephemeral=is_ephemeral)


def setup(bot: commands.Bot):
	bot.add_cog(Errors(bot))
