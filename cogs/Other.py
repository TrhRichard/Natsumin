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
FISH_EMOTE_ID = 1101799865098457088


class Other(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.other")

		self.fish_emote = self.bot.get_emoji(FISH_EMOTE_ID)
		self.fish_sticker: discord.GuildSticker = self.bot.get_sticker(FISH_STICKER_ID)
		self.fish_messages_since_last: int = 0

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/other.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	@commands.command(help="Fetch information on the bot")
	async def botinfo(self, ctx: commands.Context):
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		for owner in config.owner_ids:
			owner_names.append(f"**<@{owner}>**")
		contributor_names = []
		for contributor in config.contributor_ids:
			contributor_names.append(f"**<@{contributor}>**")

		embed = discord.Embed(title=self.bot.user.name, color=config.base_embed_color, description="")
		embed.set_thumbnail(url=self.bot.user.avatar.url)
		embed.description += f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({config.repository_link})."
		embed.description += f"\n> **Ping**: {ping_ms}ms"
		embed.description += f"\n> **Prefix**: {config.prefix}"
		embed.description += f"\n> **Maintainers**: {', '.join(owner_names)}"
		embed.description += f"\n> **Contributors**: {','.join(contributor_names)}"
		await ctx.reply(embed=embed)

	@commands.slash_command(name="botinfo", description="Fetch information on the bot")
	async def slash_botinfo(self, ctx: discord.ApplicationContext):
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		for owner in config.owner_ids:
			owner_names.append(f"**<@{owner}>**")
		contributor_names = []
		for contributor in config.contributor_ids:
			contributor_names.append(f"**<@{contributor}>**")

		embed = discord.Embed(title=self.bot.user.name, color=config.base_embed_color, description="")
		embed.set_thumbnail(url=self.bot.user.avatar.url)
		embed.description += f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({config.repository_link})."
		embed.description += f"\n> **Ping**: {ping_ms}ms"
		embed.description += f"\n> **Prefix**: {config.prefix}"
		embed.description += f"\n> **Maintainers**: {', '.join(owner_names)}"
		embed.description += f"\n> **Contributors**: {','.join(contributor_names)}"
		await ctx.respond(embed=embed)

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

	@commands.command(help="Helpful information on bot related stuff")
	async def usage(self, ctx: commands.Context):
		embed = discord.Embed(color=config.base_embed_color)
		embed.description = """
- Meanings of each emoji next to a username:
  - ❌: Failed
  - ✅: Passed
  - ⌛☑️: Late Pass
  - ⛔: Incomplete (Partial Fail)
- For commands that take a username as an argument you can do the following:
  - `[contractee]`: Your contractee in the season
  - `[contractor]`: Your contractor in the season
    - For each of the options above you can add a username before to check for that user, for example: ``frazzle_dazzle[contractee]``
"""
		await ctx.reply(embed=embed)

	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		if not message.guild or message.guild.id != 994071728017899600:
			return
		if message.author.id != 551441930773331978:
			return

		self.fish_messages_since_last += 1

		bot_perms_in_channel = message.channel.permissions_for(message.guild.me)
		if not bot_perms_in_channel.send_messages or not bot_perms_in_channel.add_reactions:
			return

		if not self.fish_sticker:
			self.fish_sticker = await self.bot.fetch_sticker(FISH_STICKER_ID)

		if random.randint(1, 10000) != 15:
			return

		self.logger.info(f"A fish event has been triggered in #{message.channel.name} after {self.fish_messages_since_last} messages")
		self.fish_messages_since_last = 0

		match random.randint(1, 2):
			case 1:  # Reaction
				await message.add_reaction(self.fish_emote)
			case 2:  # Sticker
				await message.reply(None, stickers=[self.fish_sticker])

	@commands.command(hidden=True)
	async def fish_count(self, ctx: commands.Context):
		await ctx.reply(f"Current fish messages count since bot startup and last chisato: {self.fish_messages_since_last}")


def setup(bot):
	bot.add_cog(Other(bot))
