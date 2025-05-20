from typing import Mapping, Optional
from config import BOT_CONFIG, BASE_EMBED_COLOR
from discord.ext import commands, tasks
from dotenv import load_dotenv
import utils
import contracts
import discord
import os

load_dotenv()


class Natsumin(commands.Bot):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.sync_to_sheet.start()
		self.anicord: discord.Guild

	async def on_ready(self):
		os.system("cls" if os.name == "nt" else "clear")
		print(f"Logged in as {self.user.name}#{self.user.discriminator}!")
		self.anicord = self.get_guild(994071728017899600)

	async def get_contract_user(self, *, id: int = None, username: str = None, season: str = BOT_CONFIG.active_season) -> discord.User | None:
		if id:
			discord_user = (self.anicord.get_member(id) or await self.anicord.fetch_member(id)) if self.anicord else await self.get_or_fetch_user(id)
			return discord_user
		elif username:
			season_db = await contracts.get_season_db(season)
			if u := await season_db.fetch_user(username=username):
				id = u.discord_id if u.discord_id else None
			elif d := await utils.find_madfigs_user(search_name=username):
				id = d["user_id"]
			if id:
				return (self.anicord.get_member(id) or await self.anicord.fetch_member(id)) if self.anicord else await self.get_or_fetch_user(id)

			for member in self.get_all_members():
				if member.name == username:
					return member
		return None

	@tasks.loop(minutes=10)
	async def sync_to_sheet(self):
		await contracts.sync_season_db()

	@sync_to_sheet.before_loop
	async def before_sync(self):
		await self.wait_until_ready()


bot = Natsumin(
	command_prefix=commands.when_mentioned_or(BOT_CONFIG.prefix),
	status=discord.Status.online,
	intents=discord.Intents.all(),
	case_insensitive=True,
	allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
)


def recursive_load_cogs(path: str):
	for root, _, files in os.walk(path):
		for file in files:
			if file.endswith(".py"):
				relative_path = os.path.relpath(root, path).replace(os.sep, ".")
				cog_name = f"{relative_path}.{file[:-3]}" if relative_path != "." else file[:-3]
				bot.load_extension(f"{path}.{cog_name}")


class Help(commands.HelpCommand):
	def get_command_signature(self, command: commands.Command):
		return "**%s%s**%s%s" % (
			self.context.clean_prefix,
			command.qualified_name,
			(f" {command.signature}" if command.signature else ""),
			(": " + command.help) if command.help else "",
		)

	async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]):
		embed = discord.Embed(color=BASE_EMBED_COLOR)

		for cog, cog_commands in mapping.items():
			filtered: list[commands.Command] = await self.filter_commands(cog_commands, sort=True)
			command_signatures = [self.get_command_signature(c) for c in filtered]

			if command_signatures:
				cog_name = getattr(cog, "qualified_name", "No Category")
				embed.add_field(name=cog_name, value="\n".join([f"> {s}" for s in command_signatures]), inline=False)

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_command_help(self, command: commands.Command):
		embed = discord.Embed(color=BASE_EMBED_COLOR)

		embed.description = f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"
		if len(command.aliases) > 0:
			embed.description += f"\n> **Aliases**: {', '.join(command.aliases)}"

		if command.help:
			embed.description += f"\n\n{command.help}"

		channel = self.get_destination()
		await channel.send(embed=embed)

	async def send_cog_help(self, cog: commands.Cog):
		embed = discord.Embed(color=BASE_EMBED_COLOR)

		filtered: list[commands.Command] = await self.filter_commands(cog.get_commands(), sort=True)
		command_signatures = [self.get_command_signature(c) for c in filtered]

		if command_signatures:
			cog_name = getattr(cog, "qualified_name", "No Category")
			embed.add_field(name=cog_name, value="\n".join([f"> {s}" for s in command_signatures]), inline=False)

		channel = self.get_destination()
		await channel.send(embed=embed)


bot.help_command = Help()

recursive_load_cogs("cogs")
bot.run(os.getenv("DEV_DISCORD_TOKEN"))
