from config import CONSOLE_LOGGING_FORMATTER, FILE_LOGGING_FORMATTER, BASE_EMBED_COLOR, BOT_CONFIG, sync_config_to_local
from discord.ext import commands
from typing import TYPE_CHECKING
import contracts
import logging
import discord
import json
import io

if TYPE_CHECKING:
	from main import Natsumin


class Owner(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.owner")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/owner.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)

			self.logger.setLevel(logging.INFO)

	@commands.command(hidden=True, aliases=["purge_cache", "clear_cache"])
	@commands.is_owner()
	async def sync_season(self, ctx: commands.Context, *, season: str = BOT_CONFIG.active_season):
		async with ctx.typing():
			try:
				duration = await contracts.sync_season_db(season)
				self.logger.info(f"{season} has been manually synced by {ctx.author.name} in {duration:.2f} seconds")
				await ctx.reply(
					embed=discord.Embed(description=f"✅ **{season}** has been synced in {duration:.2f} seconds!", color=BASE_EMBED_COLOR)
				)
			except Exception as e:
				self.logger.error(f"Failed to sync season '{season}' manually by {ctx.author.name}: {e}")
				await ctx.reply(embed=discord.Embed(description=f"❌ Failed to sync **{season}**:\n```{e}```", color=discord.Color.red()))

	@commands.command(hidden=True)
	@commands.is_owner()
	async def delete_message(self, ctx: commands.Context, message_id: int, channel_id: int = None):
		message = self.bot.get_message(message_id)
		if not message:
			if channel_id is None:
				await ctx.reply("Channel ID argument required for uncached message!", delete_after=3)
				return
			message_channel = self.bot.get_channel(channel_id)
			if not message_channel:
				message_channel = await self.bot.fetch_channel(channel_id)
			message = await message_channel.fetch_message(message_id)

		if message is None:
			await ctx.reply("Could not find the message you requested!", delete_after=3)
			return

		if message.author.id != self.bot.user.id:
			await ctx.reply("This command can only be used to delete the bot's messages!", delete_after=3)
			return

		await message.delete()
		await ctx.reply("Message deleted!", delete_after=3)

	@commands.command(hidden=True, aliases=["season_json"])
	@commands.is_owner()
	async def get_season_file(self, ctx: commands.Context, season: str = BOT_CONFIG.active_season):
		try:
			season_db = await contracts.get_season_db(season)
		except ValueError as e:
			return await ctx.reply(embed=discord.Embed(description=f"❌ {e}", color=discord.Color.red()), mention_author=False)

		all_users = await season_db.fetch_users()
		all_contracts = await season_db.fetch_contracts()

		users_json = [user.to_json() for user in all_users]
		contracts_json = [contract.to_json() for contract in all_contracts]

		discord_file = discord.File(io.BytesIO(json.dumps({"users": users_json, "contracts": contracts_json}, indent=4).encode("utf-8")))
		discord_file.filename = f"{season}.json"
		await ctx.reply(f"Here is {season} data:", file=discord_file)

	@commands.command(hidden=True, aliases=["r", "reload"])
	@commands.is_owner()
	async def reload_cogs(self, ctx: commands.Context):
		failed_cogs = []
		for cog in list(self.bot.extensions.keys()):
			try:
				self.bot.reload_extension(cog)
			except Exception as e:
				failed_cogs.append(f"{cog}: {e}")

		if failed_cogs:
			error_message = "❌ Reloaded all except the following cogs:\n" + "\n> ".join(failed_cogs)
			embed = discord.Embed(color=discord.Color.red(), description=error_message)
			await ctx.reply(embed=embed, mention_author=False)
		else:
			embed = discord.Embed(color=BASE_EMBED_COLOR, description="✅ Successfully reloaded all cogs.")
			await ctx.reply(embed=embed, mention_author=False)

	@commands.command(hidden=True, aliases=["rsc"])
	@commands.is_owner()
	async def reload_slash_command(self, ctx: commands.Context):
		await self.bot.sync_commands()
		embed = discord.Embed(color=BASE_EMBED_COLOR)
		embed.description = "✅ Successfully synced bot application commands."
		await ctx.reply(embed=embed, mention_author=False)

	@commands.command(hidden=True, aliases=["rbc"])
	@commands.is_owner()
	async def reload_bot_config(self, ctx: commands.Context):
		sync_config_to_local()
		await ctx.reply("Config has been updated to the latest version available on the system.")


def setup(bot):
	bot.add_cog(Owner(bot))
