from discord.ext import commands
from typing import TYPE_CHECKING
from common import config
import logging
import discord
import utils
import random

if TYPE_CHECKING:
	from main import Natsumin

FISH_STICKER_ID = 1073965395595235358


class Other(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.other")

		self.fish_sticker: discord.GuildSticker = self.bot.get_sticker(FISH_STICKER_ID)
		self.fish_messages_since_last: int = 0
		self.fish_event_forced = False

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/other.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
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
		container.add_item(discord.ui.Button(label="Repository", url=config.repository_link))
		return container

	@commands.command(help="Fetch information on the bot")
	async def botinfo(self, ctx: commands.Context):
		await ctx.reply(view=discord.ui.View(self.get_bot_info_container()))

	@commands.slash_command(name="botinfo", description="Fetch information on the bot")
	async def slash_botinfo(self, ctx: discord.ApplicationContext):
		await ctx.respond(view=discord.ui.View(self.get_bot_info_container()))

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

	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		if not message.guild or message.guild.id != 994071728017899600:
			return
		if message.author.id != 551441930773331978:
			return

		self.fish_messages_since_last += 1

		bot_perms_in_channel = message.channel.permissions_for(message.guild.me)
		if not bot_perms_in_channel.send_messages:
			return

		if not self.fish_sticker:
			self.fish_sticker = await self.bot.fetch_sticker(FISH_STICKER_ID)

		if not self.fish_event_forced:
			if self.fish_messages_since_last >= 1000:
				if random.randint(1, 100) != 15:
					return
			else:
				if random.randint(1, 10000) != 15:
					return

		self.logger.info(f"A fish event has been triggered in #{message.channel.name} after {self.fish_messages_since_last} messages")
		self.fish_messages_since_last = 0
		self.fish_event_forced = False
		try:
			await message.reply(
				None,
				stickers=[self.fish_sticker],
				allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False, replied_user=True),
			)
		except (discord.HTTPException, discord.Forbidden) as e:
			self.logger.error(f"Could not send a fish event: {e}")

	@commands.command(hidden=True)
	async def fish_count(self, ctx: commands.Context):
		await ctx.reply(f"Current fish messages count since bot startup and last chisato: {self.fish_messages_since_last}")

	@commands.command(hidden=True)
	@commands.is_owner()
	async def force_fish(self, ctx: commands.Context):
		self.fish_event_forced = True
		await ctx.reply("Next fish message will forcefully be a fish event.")

	@commands.command("richardpoggers", hidden=True, help="why", aliases=["richardpog"])
	async def richard_poggers(self, ctx: commands.Context):
		sticker = self.bot.get_sticker(1336790955281485845) or await self.bot.fetch_sticker(1336790955281485845)
		await ctx.reply(None, stickers=[sticker])


def setup(bot):
	bot.add_cog(Other(bot))
