from utils.time import parse_duration_str, from_utc_timestamp, to_utc_timestamp
from utils import FILE_LOGGING_FORMATTER, config, shorten
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal
from discord.ext import commands, tasks
from dataclasses import dataclass
import discord.ui as ui
import aiosqlite
import aiofiles
import datetime
import asyncio
import logging
import discord
import random
import re

if TYPE_CHECKING:
	from main import Natsumin

TIMESTAMP_PATTERN = r"<t:(\d+):(\w+)>"


@dataclass(slots=True, kw_only=True)
class GiveawayEvent:
	update_type: Literal["user_joined", "user_left", "ended", "winner_rerolled"]
	giveaway_id: int


@dataclass(slots=True, kw_only=True)
class GiveawayUserJoinedEvent(GiveawayEvent):
	update_type: Literal["user_joined"] = "user_joined"
	user_id: int


@dataclass(slots=True, kw_only=True)
class GiveawayUserLeftEvent(GiveawayEvent):
	update_type: Literal["user_left"] = "user_left"
	user_id: int


@dataclass(slots=True, kw_only=True)
class GiveawayEndedEvent(GiveawayEvent):
	update_type: Literal["ended"] = "ended"
	users_entered: list[int]
	winners: list[int]


@dataclass(slots=True, kw_only=True)
class GiveawayWinnerRerolledEvent(GiveawayEvent):
	update_type: Literal["winner_rerolled"] = "winner_rerolled"
	user_id: int
	index_rerolled: int


def get_giveaway_embed(
	prize: str,
	winners_amount: int,
	ends_at_timestamp: int,
	tags: list[str] = None,
	role_requirements: list[int] = None,
	has_ended: bool = False,
	winners: list[int] = None,
) -> discord.Embed:
	if role_requirements is None:
		role_requirements = []
	if winners is None:
		winners = []
	if tags is None:
		tags = []

	embed = discord.Embed(title=prize, description="", color=config.base_embed_color)
	if not has_ended:
		embed.description = f"""Click 🎉 button to enter!
Winners: **{winners_amount}**
Ends: <t:{ends_at_timestamp}:R>
"""
		if role_requirements:
			embed.description += (
				f"\n\nMust have the role{'s' if len(role_requirements) > 1 else ''}: {', '.join(f'<@&{role_id}>' for role_id in role_requirements)}"
			)
	else:
		if winners:
			embed.description = f"Winner{'s' if len(winners) > 1 else ''}: {', '.join(f'<@&{user_id}>' for user_id in winners)}"
		else:
			embed.description = "No winner."

	if tags:
		embed.set_footer(text=shorten(", ".join(tags), 128))  # in what world will this reach more than 128 characters

	return embed


class GiveawayCog(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.giveaway")

		self.giveaway_ending_check.before_loop = self.before_loops
		self.giveaway_message_updates.before_loop = self.before_loops

		self.giveaway_ending_check.start()
		self.giveaway_message_updates.start()

		self.giveaway_events: asyncio.Queue[GiveawayEvent] = asyncio.Queue()

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/giveaway.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.setLevel(logging.INFO)

	@asynccontextmanager
	async def connect(self):  # experimenting with NOT making a class for each db
		async with aiosqlite.connect("data/giveaway.db") as conn:
			conn.row_factory = aiosqlite.Row
			try:
				yield conn
			except aiosqlite.Error as err:
				self.logger.error(err, exc_info=err)
			finally:
				pass

	giveaway_group = discord.SlashCommandGroup("giveaway", "Giveaway commands", guild_ids=config.guild_ids)

	@giveaway_group.command(description="Create a new giveaway", contexts=[discord.InteractionContextType.guild])
	@commands.has_permissions(manage_guild=True)
	@discord.option("duration", str, required=True, description="Valid durations: 1d24h60m or 1 day 24 hours 60 minutes, UTC timestamp")
	@discord.option("prize", str, min_length=1, required=True, description="The prize of the giveaway")
	@discord.option("winners", int, min_value=1, default=1, description="Amount of winners, defaults to 1")
	@discord.option("host", str, min_length=3, default=None, description="Host of the giveaway, defaults to giveaway creator's username")
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
		async with self.connect() as conn:
			async with conn.execute("SELECT * FROM giveaways WHERE message_id = ? AND ended = FALSE", (message_id,)) as cursor:
				row = await cursor.fetchone()
				if not row:
					return await ctx.respond("Could not find a active giveaway with that id", ephemeral=False)

		await ctx.respond(f"wip {message_id=}", ephemeral=True)

	@commands.message_command(name="End giveaway", guilds_ids=config.guild_ids)
	async def message_end(self, ctx: discord.ApplicationContext, target: discord.Message):
		async with self.connect() as conn:
			async with conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (target.id,)) as cursor:
				pass

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
	@discord.option("tags", str, default="", description="Filter by giveaway tags, each tag separated by a comma")
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
	@discord.option("tags", str, default="", description="Filter by giveaway tags, each tag separated by a comma")
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

	@commands.Cog.listener()
	async def on_ready(self):
		async with aiofiles.open("assets/schemas/Giveaway.sql") as f:
			script = await f.read()

		async with self.connect() as conn:
			await conn.executescript(script)
			await conn.commit()

	@commands.Cog.listener()
	async def on_message_delete(self, message: discord.Message):
		async with self.connect() as conn:
			async with conn.execute("DELETE FROM giveaways WHERE message_id = ? RETURNING author_id, host", (message.id,)) as cursor:
				row = await cursor.fetchone()
				if not row:
					return  # No giveaway
			await conn.commit()

		giveaway_author = await self.bot.get_or_fetch(discord.User, row["host"])

		self.logger.info(f"Giveaway {message.id} by {giveaway_author.id if giveaway_author else row['host']} has been deleted")

	async def get_message_from_row(self, guild_id: int, channel_id: int, message_id: int) -> discord.Message | None:
		giveaway_guild = await self.bot.get_or_fetch(discord.Guild, guild_id)
		if not giveaway_guild:
			return None
		giveaway_channel = await giveaway_guild.get_or_fetch(discord.TextChannel, channel_id)
		if not giveaway_channel:
			return None

		try:
			giveaway_message = self.bot.get_message(message_id)
			if not giveaway_message:
				giveaway_message = await giveaway_channel.fetch_message(message_id)

			return giveaway_message
		except (discord.HTTPException, discord.Forbidden, discord.NotFound):
			return None

	@tasks.loop(seconds=5)
	async def giveaway_ending_check(self):
		async with self.connect() as conn:
			async with conn.execute("UPDATE giveaways SET ended = TRUE WHERE ends_at > created_at AND ended = FALSE RETURNING *") as cursor:
				rows = await cursor.fetchall()
				await conn.commit()

				for row in rows:
					giveaway_message = await self.get_message_from_row(row["guild_id"], row["channel_id"], row["message_id"])
					if not giveaway_message:
						self.logger.error(f"Could not process the ending of giveaway {row['message_id']}: Message not found")
						return

					users_entered: list[int] = None
					async with conn.execute("SELECT user_id FROM users_entered WHERE giveaway_id = ?", (row["message_id"],)) as cursor:
						user_rows = await cursor.fetchall()
						users_entered = [user_row["user_id"] for user_row in user_rows]

					valid_users_entered: list[int] = []

					for user_id in users_entered:
						discord_user = await self.bot.get_or_fetch(discord.User, user_id)
						if discord_user:
							valid_users_entered.append(discord_user.id)

					if valid_users_entered:
						valid_winners = random.sample(valid_users_entered, min(row["winners"], len(valid_users_entered)))

						winner_inserts = [(row["message_id"], index + 1, user_id) for index, user_id in enumerate(valid_winners)]
						await conn.executemany("INSERT INTO winners (giveaway_id, winner_index, user_id) VALUES (?, ?, ?)", winner_inserts)
						await conn.commit()
					else:
						valid_winners = []

					self.giveaway_events.put(
						GiveawayEndedEvent(
							update_type="ended", giveaway_id=row["message_id"], users_entered=valid_users_entered, winners=valid_winners
						)
					)

	@tasks.loop(seconds=5)
	async def giveaway_message_updates(self):
		try:
			while True:
				event = self.giveaway_events.get_nowait()

				async with self.connect() as conn:
					async with conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (event.giveaway_id,)) as cursor:
						row = await cursor.fetchone()
						if not row:  # ?
							continue

					async with conn.execute("SELECT role_id FROM role_requirements WHERE giveaway_id = ?", (event.giveaway_id,)) as cursor:
						role_requirements: list[int] = [r["role_id"] for r in await cursor.fetchall()]

					async with conn.execute("SELECT tag FROM tags WHERE giveaway_id = ?", (event.giveaway_id,)) as cursor:
						giveaway_tags: list[int] = [t["tag"] for t in await cursor.fetchall()]

				giveaway_message = await self.get_message_from_row(row["guild_id"], row["channel_id"], row["message_id"])
				if not giveaway_message:
					self.logger.warning(f"Could not update giveaway {event.giveaway_id}: Message not found")
					continue

				if isinstance(event, GiveawayEndedEvent):
					await giveaway_message.edit(
						embed=get_giveaway_embed(row["prize"], row["winners"], row["ends_at"], giveaway_tags, role_requirements, True, event.winners),
						view=None,
					)
					await giveaway_message.reply(
						f"Congratulations! ok winners since this isnt done: {', '.join(f'<@{user_id}>' for user_id in event.winners)}"
					)
				else:
					self.logger.warning(f"Unhandled event type: {event.update_type}")

		except asyncio.QueueEmpty:
			pass

	async def before_loops(self):
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(GiveawayCog(bot))
