from discord.ext import commands, tasks
from typing import Mapping, Optional, overload, Literal
from dotenv import load_dotenv
from common import config, get_master_db
from async_lru import alru_cache
import contracts
import discord
import os
import re

load_dotenv()


class Natsumin(commands.Bot):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.sync_databases.start()
		self.anicord: discord.Guild = None
		self.master_db = get_master_db()

	async def on_ready(self):
		os.system("cls" if os.name == "nt" else "clear")
		print(f"Logged in as {self.user.name}#{self.user.discriminator}!")

		self.anicord = self.get_guild(994071728017899600)

	async def on_user_update(self, old: discord.User, new: discord.User):
		if old.name == new.name:
			return  # Username change

		master_user = await self.get_master_user(old)
		if not master_user:
			return

		await self.master_db.update_user(master_user.id, username=new.name)
		await self.master_db.add_user_alias(master_user.id, old.name)

	@alru_cache(ttl=contracts.CACHE_DURATION)
	async def get_master_user(self, user: discord.Member | discord.User) -> contracts.MasterUser | None:
		return await self.master_db.fetch_user(discord_id=user.id, username=user.name)

	@alru_cache(ttl=contracts.CACHE_DURATION)
	async def get_season_user(self, user: discord.Member | discord.User, season: str = None) -> contracts.SeasonUser | None:
		if season is None:
			season = config.active_season

		master_user = await self.get_master_user(user)
		if not master_user:
			return None

		season_db = await contracts.get_season_db(season)
		season_user = await season_db.fetch_user(master_user.id)

		return season_user

	@overload
	async def get_targeted_user(
		self, username: str | discord.User, *, season: str = ..., return_as_master: Literal[True]
	) -> tuple[discord.User | None, contracts.MasterUser | None]: ...
	@overload
	async def get_targeted_user(
		self, username: str | discord.User, *, season: str = ..., return_as_master: Literal[False] = ...
	) -> tuple[discord.User | None, contracts.SeasonUser | None]: ...
	async def get_targeted_user(self, username: str | discord.User, *, season: str = None, return_as_master: bool = False) -> tuple:
		if season is None:
			season = config.active_season

		discord_user: discord.Member = None

		if isinstance(username, str):
			if match := re.match(r"<@!?(\d+)>", username):
				discord_id = int(match.group(1))
				if self.anicord:
					discord_user = self.anicord.get_member(discord_id)
					if not discord_user:
						discord_user = await self.anicord.fetch_member(discord_id)
				else:
					discord_user = await self.get_or_fetch_user(discord_id)

				if not discord_user:
					return None, None

				username = discord_user.name
		elif isinstance(username, (discord.User, discord.Member)):
			discord_user = username
			username = discord_user.name

		master_user = await self.master_db.fetch_user_fuzzy(username)
		if master_user is None:
			return None, None

		if discord_user is None:
			if master_user.discord_id and self.anicord:
				discord_user = self.anicord.get_member(master_user.discord_id)
				if not discord_user:
					discord_user = await self.anicord.fetch_member(master_user.discord_id)

			if not discord_user and master_user.discord_id:
				discord_user = await self.get_or_fetch_user(master_user.discord_id)

		if return_as_master:
			return discord_user, master_user
		else:
			season_db = await contracts.get_season_db(season)
			season_user = await season_db.fetch_user(master_user.id)
			return discord_user, season_user

	@tasks.loop(minutes=10)
	async def sync_databases(self):
		await contracts.sync_season_db()

	@sync_databases.before_loop
	async def before_sync(self):
		await self.wait_until_ready()


bot = Natsumin(
	command_prefix=commands.when_mentioned_or(config.prefix),
	status=discord.Status.online,
	intents=discord.Intents.all(),
	case_insensitive=True,
	allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False, replied_user=False),
)


class Help(commands.HelpCommand):
	def get_command_signature(self, command: commands.Command):
		return "**%s%s**%s" % (self.context.clean_prefix, command.qualified_name, (f" {command.signature}" if command.signature else ""))

	async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]):
		embed = discord.Embed(color=config.base_embed_color, description="")

		for cog, cog_commands in mapping.items():
			filtered: list[commands.Command] = await self.filter_commands(cog_commands, sort=True)
			command_signatures = [f"{self.get_command_signature(c)}\n  - {c.help}" for c in filtered]

			if command_signatures:
				embed.description += "".join([f"\n- {s}" for s in command_signatures])

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_command_help(self, command: commands.Command):
		embed = discord.Embed(color=config.base_embed_color)

		embed.description = f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"
		if len(command.aliases) > 0:
			embed.description += f"\n> **Aliases**: {', '.join(command.aliases)}"

		if command.help:
			embed.description += f"\n\n{command.help}"

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_cog_help(self, cog: commands.Cog):
		embed = discord.Embed(color=config.base_embed_color)

		filtered: list[commands.Command] = await self.filter_commands(cog.get_commands(), sort=True)
		command_signatures = [self.get_command_signature(c) for c in filtered]

		if command_signatures:
			cog_name = getattr(cog, "qualified_name", "No Category")
			embed.add_field(name=cog_name, value="\n".join([f"> {s}" for s in command_signatures]), inline=False)

		channel = self.get_destination()
		await channel.send(embed=embed)


bot.help_command = Help()
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)
bot.load_extension("cogs", recursive=True)
bot.run(os.getenv("DISCORD_TOKEN"))
