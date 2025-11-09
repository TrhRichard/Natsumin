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


class GiveawayFilterFlags(commands.FlagConverter, delimiter=" ", prefix="-"):
	prize: str | None = commands.Flag(name="prize", aliases=["p"], default=None, positional=True)
	winners: int | None = commands.flag(name="winners", aliases=["w"], default=None)
	host: str | None = commands.Flag(name="host", aliases=["h"], default=None)
	role_required: list[int] = commands.flag(name="role_required", aliases=["role", "r"], default=lambda _: list())
	tags: list[str] = commands.flag(name="tags", aliases=["tag", "t"], default=lambda _: list())


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

	@giveaway_group.command(description="Create a new giveaway.")
	@discord.option("duration", str, required=True, description="Valid durations: 1d24h60m or 1 day 24 hours 60 minutes, UTC timestamp")
	@discord.option("prize", str, required=True, description="The prize of the giveaway")
	@discord.option("winners", int, default=1, description="Amount of winners, defaults to 1")
	@discord.option("host", str, default=None, description="Host of the giveaway, defaults to giveaway creator's username")
	@discord.option("channel", discord.TextChannel, default=None, description="Channel in which the giveaway is in, defaults to current channel")
	@discord.option("role_required", discord.Role, default=None, description="Role required to enter the giveaway, defaults to None")
	@discord.option(
		"roles_required", str, default="", description="Roles required to enter the giveaway, separted by a comma (includes role_required if set)"
	)
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
			f"wip\ngiveaway_ends_at=<t:{to_utc_timestamp(giveaway_ends_at)}:F> {prize=} {winners=} {host=} {channel=} {role_required=} {roles_required=} {tags=}",
			ephemeral=True,
		)

	@commands.group(name="giveaway", aliases=["ga"], invoke_without_command=True, help="Giveaway related commands")
	async def giveaway_textgroup(self, ctx: commands.Context):
		await ctx.reply(f"Please specify a valid subcommand. Use `{ctx.clean_prefix}help {ctx.invoked_with}` for a full list.")

	@giveaway_textgroup.command("list", aliases=["total"], help="Get a list of all giveaways in the server")
	async def text_list(self, ctx: commands.Context, *, flags: GiveawayFilterFlags):
		await ctx.reply(f"wip {flags}")

	@giveaway_textgroup.command("entered", aliases=["mine", "me"], help="Get a list of all giveaways you've entered in the server")
	async def text_entered(self, ctx: commands.Context, *, flags: GiveawayFilterFlags):
		await ctx.reply(f"wip {flags}")

	@tasks.loop(seconds=5)
	async def giveaway_loop(self):
		pass

	@giveaway_loop.before_loop
	async def before_loop(self):
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(GiveawayCog(bot))
