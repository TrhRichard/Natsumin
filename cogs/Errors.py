from config import FILE_LOGGING_FORMATTER, CONSOLE_LOGGING_FORMATTER
from discord.ext import commands
import logging
import discord


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

	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error: Exception):
		error_type, description = "", ""
		if isinstance(error, commands.CommandNotFound):
			return
		elif isinstance(error, commands.NotOwner):
			error_type = "Owner-only command"
			description = f"This command is restricted to {self.bot.user.name}'s owner."
		elif isinstance(error, commands.MissingPermissions):
			error_type = "Missing Permissions"
			description = f"You do not have enough permissions to use this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
		elif isinstance(error, commands.BotMissingPermissions):
			error_type = "Bot Missing Permissions"
			description = (
				f"The bot is missing the required permissions to perform this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
			)
		elif isinstance(error, commands.MissingRequiredArgument):
			error_type = "Missing Required Argument"
			description = f"You are missing required argument ``{error.param.name}``."
		elif isinstance(error, discord.HTTPException):
			error_type = "HTTP Exception"
			description = f'An HTTP error occured: "{error.text}" ({error.status})'
		elif isinstance(error, commands.CommandOnCooldown):
			error_type = "Cooldown"
			description = f"You may retry again in **{error.retry_after:.2f}** seconds."
		else:
			error_type = type(error).__name__
			description = str(error)

		embed = discord.Embed(description=error, color=discord.Color.red())
		embed.description = f"{error_type}: {description}"
		await ctx.reply(embed=embed)

		self.logger.error(f"@{ctx.author.name} -> Command error in {ctx.command}: {error_type} - {error}")

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: Exception):
		error = getattr(error, "original", error)
		error_type, description = "", ""
		if isinstance(error, commands.CommandOnCooldown):
			error_type = "Cooldown"
			description = f"You may retry again in **{error.retry_after:.2f}** seconds."
		elif isinstance(error, commands.NotOwner):
			error_type = "Owner-only command"
			description = f"This command is restricted to {self.bot.user.name}'s owner."
		elif isinstance(error, commands.MissingPermissions):
			error_type = "Missing Permissions"
			description = f"You do not have enough permissions to use this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
		elif isinstance(error, commands.BotMissingPermissions):
			error_type = "Bot Missing Permissions"
			description = (
				f"The bot is missing the required permissions to perform this command.\nMissing permissions: {', '.join(error.missing_permissions)}"
			)
		elif isinstance(error, discord.HTTPException):
			error_type = "HTTP Exception"
			description = f'An HTTP error occured: "{error.text}" ({error.status})'
		else:
			error_type = type(error).__name__
			description = str(error)

		embed = discord.Embed(color=discord.Color.red())
		embed.description = f"{error_type}: {description}"
		await ctx.respond(embed=embed)

		self.logger.error(f"@{ctx.author.name} -> Application command error in {ctx.command}: {error_type} - {error}")


def setup(bot: commands.Bot):
	bot.add_cog(Errors(bot))
