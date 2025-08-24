from discord.ext import commands
from typing import TYPE_CHECKING
import logging
import discord
import config
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
			file_handler.setFormatter(config.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(config.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	@commands.command(help="Fetch information on the bot")
	async def botinfo(self, ctx: commands.Context):
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		for owner in config.BOT_CONFIG.owner_ids:
			owner_names.append(f"**<@{owner}>**")
		contributor_names = []
		for contributor in config.BOT_CONFIG.contributor_ids:
			contributor_names.append(f"**<@{contributor}>**")

		embed = discord.Embed(title=self.bot.user.name, color=config.BASE_EMBED_COLOR, description="")
		embed.set_thumbnail(url=self.bot.user.avatar.url)
		embed.description += f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({config.BOT_CONFIG.repository_link})."
		embed.description += f"\n> **Ping**: {ping_ms}ms"
		embed.description += f"\n> **Prefix**: {config.BOT_CONFIG.prefix}"
		embed.description += f"\n> **Maintainers**: {', '.join(owner_names)}"
		embed.description += f"\n> **Contributors**: {','.join(contributor_names)}"
		await ctx.reply(embed=embed)

	@commands.slash_command(name="botinfo", description="Fetch information on the bot")
	async def slash_botinfo(self, ctx: discord.ApplicationContext):
		ping_ms = round(self.bot.latency * 1000)

		owner_names = []
		for owner in config.BOT_CONFIG.owner_ids:
			owner_names.append(f"**<@{owner}>**")
		contributor_names = []
		for contributor in config.BOT_CONFIG.contributor_ids:
			contributor_names.append(f"**<@{contributor}>**")

		embed = discord.Embed(title=self.bot.user.name, color=config.BASE_EMBED_COLOR, description="")
		embed.set_thumbnail(url=self.bot.user.avatar.url)
		embed.description += f"{self.bot.user.name} is a bot made for Anicord Event Server to assist with contracts related stuff. If you would like to contribute to it's development you can do it [here]({config.BOT_CONFIG.repository_link})."
		embed.description += f"\n> **Ping**: {ping_ms}ms"
		embed.description += f"\n> **Prefix**: {config.BOT_CONFIG.prefix}"
		embed.description += f"\n> **Maintainers**: {', '.join(owner_names)}"
		embed.description += f"\n> **Contributors**: {','.join(contributor_names)}"
		await ctx.respond(embed=embed)

	@commands.command(help="Check the bot's latency", aliases=["latency"])
	async def ping(self, ctx: commands.Context):
		embed = discord.Embed(color=config.BASE_EMBED_COLOR)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.reply(embed=embed)

	@commands.slash_command(name="ping", description="Check the bot's latency")
	async def slash_ping(self, ctx: discord.ApplicationContext):
		embed = discord.Embed(color=config.BASE_EMBED_COLOR)
		embed.description = f":ping_pong: Pong! ({round(self.bot.latency * 1000)}ms)"
		await ctx.respond(embed=embed)

	@commands.command(help="Helpful information on bot related stuff")
	async def usage(self, ctx: commands.Context):
		embed = discord.Embed(color=config.BASE_EMBED_COLOR)
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
			await message.reply(None, stickers=[self.fish_sticker])
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


def setup(bot):
	bot.add_cog(Other(bot))
