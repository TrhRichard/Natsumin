from __future__ import annotations

from config import OWNER_IDS, CONTRIBUTOR_IDS, BOT_PREFIX, DEV_BOT_PREFIX, REPOSITORY_URL
from internal.constants import FILE_LOGGING_FORMATTER, COLORS
from internal.base.cog import NatsuminCog
from discord.ext import commands
from typing import TYPE_CHECKING

import discord
import logging

if TYPE_CHECKING:
	from internal.base.bot import NatsuminBot


class OtherExt(NatsuminCog, name="Other"):
	"""Other commands that don't fit in a category"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.other")
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/other.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

	def get_bot_info_container(self) -> discord.ui.Container:
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		contributor_names = []
		for owner in OWNER_IDS:
			owner_names.append(f"**<@{owner}>**")
		for contributor in CONTRIBUTOR_IDS:
			contributor_names.append(f"**<@{contributor}>**")

		container = discord.ui.Container(color=COLORS.DEFAULT)
		container.add_section(
			discord.ui.TextDisplay(
				f"## {self.bot.user.name}\n"
				f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({REPOSITORY_URL})."
			),
			accessory=discord.ui.Thumbnail(url=self.bot.user.avatar.url),
		)
		container.add_separator()
		container.add_text(
			(f"**Maintainers**: {','.join(owner_names)}\n" if owner_names else "")
			+ (f"**Contributors**: {','.join(contributor_names)}\n" if contributor_names else "")
			+ f"**Ping**: {ping_ms}ms\n"
			+ f"**Prefix**: `{BOT_PREFIX if self.bot.is_production else DEV_BOT_PREFIX}`\n"
		)
		container.add_item(discord.ui.ActionRow(discord.ui.Button(label="Repository", url=REPOSITORY_URL)))
		return container

	@commands.command(help="Get information on the bot")
	async def botinfo(self, ctx: commands.Context):
		await ctx.reply(view=discord.ui.DesignerView(self.get_bot_info_container(), store=False))

	@commands.slash_command(name="botinfo", description="Get information on the bot")
	async def slash_botinfo(self, ctx: discord.ApplicationContext):
		await ctx.respond(view=discord.ui.DesignerView(self.get_bot_info_container(), store=False))

	@commands.command(help="Check the bot's latency", aliases=["latency"])
	async def ping(self, ctx: commands.Context):
		embed = discord.Embed(color=COLORS.DEFAULT)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.reply(embed=embed)

	@commands.slash_command(name="ping", description="Check the bot's latency")
	async def slash_ping(self, ctx: discord.ApplicationContext):
		embed = discord.Embed(color=COLORS.DEFAULT)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.respond(embed=embed)

	@commands.command(help="Get the time when the bot started")
	async def uptime(self, ctx: commands.Context):
		await ctx.reply(f"Bot started at {discord.utils.format_dt(self.bot.started_at)}!")

	@commands.command(hidden=True, help="why", aliases=["richardpog"])
	async def richardpoggers(self, ctx: commands.Context):
		try:
			sticker = self.bot.get_sticker(1336790955281485845) or await self.bot.fetch_sticker(1336790955281485845)
			await ctx.reply(None, stickers=[sticker])
		except (discord.Forbidden, discord.NotFound):
			await ctx.reply("poggers")


def setup(bot: NatsuminBot):
	bot.add_cog(OtherExt(bot))
