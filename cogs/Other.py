from utils import FILE_LOGGING_FORMATTER, config
from discord.ext import commands
from typing import TYPE_CHECKING
import logging
import discord

if TYPE_CHECKING:
	from main import Natsumin


class Other(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.other")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/other.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.setLevel(logging.INFO)

	def get_bot_info_container(self) -> discord.ui.Container:
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		for owner in config.owner_ids:
			owner_names.append(f"**<@{owner}>**")
		contributor_names = []
		for contributor in config.contributor_ids:
			contributor_names.append(f"**<@{contributor}>**")

		container = discord.ui.Container(color=config.base_embed_color)
		container.add_section(
			discord.ui.TextDisplay(
				f"## {self.bot.user.name}\n"
				f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({config.repository_link})."
			),
			accessory=discord.ui.Thumbnail(url=self.bot.user.avatar.url),
		)
		container.add_separator()
		container.add_text(
			f"**Ping**: {ping_ms}ms\n"
			f"**Prefix**: `{config.prefix}`\n"
			f"**Maintainers**: {','.join(owner_names)}\n"
			f"**Contributors**: {','.join(contributor_names)}\n"
		)
		container.add_item(discord.ui.ActionRow(discord.ui.Button(label="Repository", url=config.repository_link)))
		return container

	@commands.command(help="Fetch information on the bot")
	async def botinfo(self, ctx: commands.Context):
		await ctx.reply(view=discord.ui.DesignerView(self.get_bot_info_container(), store=False))

	@commands.slash_command(name="botinfo", description="Fetch information on the bot")
	async def slash_botinfo(self, ctx: discord.ApplicationContext):
		await ctx.respond(view=discord.ui.DesignerView(self.get_bot_info_container(), store=False))

	@commands.command(help="Check the bot's latency", aliases=["latency"])
	async def ping(self, ctx: commands.Context):
		embed = discord.Embed(color=config.base_embed_color)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.reply(embed=embed)

	@commands.slash_command(name="ping", description="Check the bot's latency")
	async def slash_ping(self, ctx: discord.ApplicationContext):
		embed = discord.Embed(color=config.base_embed_color)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.respond(embed=embed)

	@commands.command("richardpoggers", hidden=True, help="why", aliases=["richardpog"])
	async def richard_poggers(self, ctx: commands.Context):
		try:
			sticker = self.bot.get_sticker(1336790955281485845) or await self.bot.fetch_sticker(1336790955281485845)
			await ctx.reply(None, stickers=[sticker])
		except discord.Forbidden:
			await ctx.reply("poggers")


def setup(bot):
	bot.add_cog(Other(bot))
