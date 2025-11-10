from utils.time import parse_duration_str, from_utc_timestamp, to_utc_timestamp
from utils import FILE_LOGGING_FORMATTER, config, shorten
from discord.ext import commands, tasks
from typing import TYPE_CHECKING
import discord.ui as ui
import datetime
import logging
import discord
import re

if TYPE_CHECKING:
	from main import Natsumin

TIMESTAMP_PATTERN = r"<t:(\d+):(\w+)>"


class GiveawayCog(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.giveaway")
		self.giveaway_loop.start()

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/giveaway.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.setLevel(logging.INFO)

	giveaway_group = discord.SlashCommandGroup("giveaway", "Giveaway commands", guild_ids=config.guild_ids)

	@giveaway_group.command(description="Create a new giveaway", contexts=[discord.InteractionContextType.guild])
	@commands.has_permissions(manage_guild=True)
	@discord.option("duration", str, required=True, description="Valid durations: 1d24h60m or 1 day 24 hours 60 minutes, UTC timestamp")
	@discord.option("prize", str, required=True, description="The prize of the giveaway")
	@discord.option("winners", int, default=1, description="Amount of winners, defaults to 1")
	@discord.option("host", str, default=None, description="Host of the giveaway, defaults to giveaway creator's username")
	@discord.option("channel", discord.TextChannel, default=None, description="Channel in which the giveaway is in, defaults to current channel")
	@discord.option("role_required", discord.Role, default=None, description="Role required to enter the giveaway, defaults to None")
	@discord.option("roles_required", str, default="", description="Roles required to enter the giveaway, separated by a comma")
	@discord.option("tags", str, default="", description="Tags for this giveaway, separated by a comma")
	async def create(
		self,
		ctx: discord.ApplicationContext,
		duration: str,
		prize: str,
		winners: int,
		host: str,
		channel: discord.TextChannel | None,
		role_required: discord.Role | None,
		roles_required: str,
		tags: str,
	):
		if winners < 1:
			return await ctx.respond("Winners count cannot be lower than 1.", ephemeral=True)

		if host is None:
			host = ctx.author.name
		if channel is None:
			channel = ctx.channel

		giveaway_role_ids: list[int] = []
		if role_required is not None:
			giveaway_role_ids.append(role_required.id)
		if roles_required:
			total_ids = 1 if role_required else 0
			invalid_ids: list[str] = []
			for role_id in roles_required.split(","):
				total_ids += 1
				role_id = role_id.strip()
				if not role_id.isdigit():
					invalid_ids.append(role_id)
					continue
				role_found = await ctx.guild.get_or_fetch(discord.Role, int(role_id))
				if role_found is None:
					invalid_ids.append(role_id)
					continue
				giveaway_role_ids.append(role_found.id)

			if invalid_ids:
				return await ctx.respond(f"Found **{len(invalid_ids)}** invalid ids out of {total_ids}. ({', '.join(invalid_ids)})", ephemeral=True)

		giveaway_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
		giveaway_ends_at: datetime.datetime = None
		duration = duration.strip()

		if (timestamp_match := re.search(TIMESTAMP_PATTERN, duration)) or (duration.isdigit() and len(duration) > 4):
			if timestamp_match is not None:
				timestamp = int(timestamp_match.group(1))
			else:
				timestamp = int(duration)

			try:
				giveaway_ends_at = from_utc_timestamp(timestamp)
			except OSError:
				return await ctx.respond("Invalid timestamp, timestamp seems to be way too much in the future", ephemeral=True)

			current_datetime = datetime.datetime.now(datetime.UTC)
			if giveaway_ends_at <= current_datetime:
				return await ctx.respond("Invalid timestamp, timestamp must be in the future not the past", ephemeral=True)
		else:
			current_datetime = datetime.datetime.now(datetime.UTC)

			try:
				delta = parse_duration_str(duration)
			except ValueError:
				return await ctx.respond(
					"Invalid duration format, please use something like: `1d24h60m` or `1 day 24 hours 60 minutes`, alternatively use a UTC timestamp",
					ephemeral=True,
				)

			giveaway_ends_at = datetime.datetime.now(datetime.UTC) + delta

		await ctx.respond(
			f"wip\ngiveaway_ends_at=<t:{to_utc_timestamp(giveaway_ends_at)}:F> {prize=} {winners=} {host=} {channel=} {giveaway_role_ids=} {giveaway_tags=}",
			ephemeral=True,
		)

	@giveaway_group.command(description="End a active giveaway", contexts=[discord.InteractionContextType.guild])
	@commands.has_permissions(manage_guild=True)
	@discord.option("message_id", int, required=True, description="The Message Id for what giveaway to end")
	async def end(self, ctx: discord.ApplicationContext, message_id: int):
		await ctx.respond(f"wip {message_id=}", ephemeral=True)

	@commands.message_command(name="End giveaway", guilds_ids=config.guild_ids)
	async def message_end(self, ctx: discord.ApplicationContext, target: discord.Message):
		await ctx.respond(f"wip {target=}", ephemeral=True)

	@commands.message_command(name="Leave giveaway", guilds_ids=config.guild_ids)
	async def message_leave(self, ctx: discord.ApplicationContext, target: discord.Message):
		await ctx.respond(f"wip {target=}", ephemeral=True)

	@giveaway_group.command(description="Get a list of all the giveaways in the server", contexts=[discord.InteractionContextType.guild])
	@discord.option("prize", str, default=None, description="Filter by prize, checks if provided string is in the title of the giveaway")
	@discord.option("winners", int, default=None, description="Filter by amount of winners")
	@discord.option("host", str, default=None, description="Filter by host")
	@discord.option("role_required", discord.Role, default=None, description="Filter by role required to enter, for more roles use roles_required")
	@discord.option("roles_required", str, default="", description="Filter by roles required to enter, each id separated by a comma")
	@discord.option("tags", str, default="", description="Filter by giveaway tags, each tagseparated by a comma")
	async def list(
		self,
		ctx: discord.ApplicationContext,
		prize: str | None,
		winners: int | None,
		host: str | None,
		role_required: discord.Role | None,
		roles_required: str,
		tags: str,
	):
		giveaway_role_ids: list[int] = []
		if role_required is not None:
			giveaway_role_ids.append(role_required.id)
		if roles_required:
			total_ids = 1 if role_required else 0
			invalid_ids: list[str] = []
			for role_id in roles_required.split(","):
				total_ids += 1
				role_id = role_id.strip()
				if not role_id.isdigit():
					invalid_ids.append(role_id)
					continue
				role_found = await ctx.guild.get_or_fetch(discord.Role, int(role_id))
				if role_found is None:
					invalid_ids.append(role_id)
					continue
				giveaway_role_ids.append(role_found.id)

			if invalid_ids:
				return await ctx.respond(f"Found **{len(invalid_ids)}** invalid ids out of {total_ids}. ({', '.join(invalid_ids)})", ephemeral=True)

		giveaway_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
		await ctx.respond(f"wip\n{prize=} {winners=} {host=} {giveaway_role_ids=} {giveaway_tags=}", ephemeral=False)

	@giveaway_group.command(
		description="Get a list of all the giveaways you've entered in the server", contexts=[discord.InteractionContextType.guild]
	)
	@discord.option("prize", str, default=None, description="Filter by prize, checks if provided string is in the title of the giveaway")
	@discord.option("winners", int, default=None, description="Filter by amount of winners")
	@discord.option("host", str, default=None, description="Filter by host")
	@discord.option("role_required", discord.Role, default=None, description="Filter by role required to enter, for more roles use roles_required")
	@discord.option("roles_required", str, default="", description="Filter by roles required to enter, each id separated by a comma")
	@discord.option("tags", str, default="", description="Filter by giveaway tags, each tagseparated by a comma")
	async def entered(
		self,
		ctx: discord.ApplicationContext,
		prize: str | None,
		winners: int | None,
		host: str | None,
		role_required: discord.Role | None,
		roles_required: str,
		tags: str,
	):
		giveaway_role_ids: list[int] = []
		if role_required is not None:
			giveaway_role_ids.append(role_required.id)
		if roles_required:
			total_ids = 1 if role_required else 0
			invalid_ids: list[str] = []
			for role_id in roles_required.split(","):
				total_ids += 1
				role_id = role_id.strip()
				if not role_id.isdigit():
					invalid_ids.append(role_id)
					continue
				role_found = await ctx.guild.get_or_fetch(discord.Role, int(role_id))
				if role_found is None:
					invalid_ids.append(role_id)
					continue
				giveaway_role_ids.append(role_found.id)

			if invalid_ids:
				return await ctx.respond(f"Found **{len(invalid_ids)}** invalid ids out of {total_ids}. ({', '.join(invalid_ids)})", ephemeral=True)

		giveaway_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
		await ctx.respond(f"wip\n{prize=} {winners=} {host=} {giveaway_role_ids=} {giveaway_tags=}", ephemeral=False)

	@commands.group(name="giveaway", aliases=["ga", "g"], invoke_without_command=True, help="Giveaway related commands")
	@commands.guild_only()
	async def giveaway_textgroup(self, ctx: commands.Context):
		await ctx.reply(f"Please specify a valid subcommand. Use `{ctx.clean_prefix}help {ctx.invoked_with}` for a full list.")

	@giveaway_textgroup.command("reroll", aliases=["rr"], help="Reroll a giveaway that has already ended")
	@commands.has_permissions(manage_guild=True)
	@commands.guild_only()
	async def text_reroll(self, ctx: commands.Context, message_id: int, winner_index: int = 1):
		await ctx.reply(f"wip {message_id=} {winner_index=}")

	@tasks.loop(seconds=5)
	async def giveaway_loop(self):
		pass

	@giveaway_loop.before_loop
	async def before_loop(self):
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(GiveawayCog(bot))
