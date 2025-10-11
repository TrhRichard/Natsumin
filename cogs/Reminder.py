from discord.ui import View, Container, TextDisplay, Section, Thumbnail
from utils.reminder import ReminderDB, Reminder, from_utc_timestamp
from discord.ext import commands, tasks
from typing import TYPE_CHECKING
from common import config
import datetime
import logging
import discord
import utils
import re

if TYPE_CHECKING:
	from main import Natsumin

TIMESTAMP_REGEX = r"<t:(\d+):(\w+)>"


def diff_to_str(dt1: datetime.datetime, dt2: datetime.datetime) -> str:
	if dt1 > dt2:
		delta = dt1 - dt2
	else:
		delta = dt2 - dt1

	total_seconds = int(delta.total_seconds())

	years, remainder = divmod(total_seconds, 365 * 86400)
	months, remainder = divmod(remainder, 30 * 86400)
	days, remainder = divmod(remainder, 86400)
	hours, remainder = divmod(remainder, 3600)
	minutes, seconds = divmod(remainder, 60)

	parts = []
	if years > 0:
		parts.append(f"{years} year{'s' if years != 1 else ''}")
	if months > 0:
		parts.append(f"{months} month{'s' if months != 1 else ''}")
	if days > 0:
		parts.append(f"{days} day{'s' if days != 1 else ''}")
	if hours > 0:
		parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
	if minutes > 0:
		parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
	if seconds > 0:
		parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

	if not parts:
		return "0 seconds"

	return " ".join(parts)


def parse_duration_str(duration_str: str) -> datetime.timedelta:
	UNIT_CANONICAL = {"y", "M", "d", "h", "m", "s"}
	ALIASES = {
		"year": "y",
		"years": "y",
		"month": "M",
		"months": "M",
		"day": "d",
		"days": "d",
		"hour": "h",
		"hours": "h",
		"minute": "m",
		"minutes": "m",
		"second": "s",
		"seconds": "s",
	}
	pattern = r"(\d+)\s*(\w+)"
	matches = re.findall(pattern, duration_str.lower())
	if not matches:
		raise ValueError("Invalid duration format")

	total_days = 0
	hours = 0
	minutes = 0
	seconds = 0

	for value, unit_word in matches:
		unit = ALIASES.get(unit_word, unit_word)
		if unit not in UNIT_CANONICAL:
			raise ValueError(f"Unknown time unit: {unit_word}")
		v = int(value)
		if unit == "y":
			total_days += v * 365
		elif unit == "M":
			total_days += v * 30
		elif unit == "d":
			total_days += v
		elif unit == "h":
			hours += v
		elif unit == "m":
			minutes += v
		elif unit == "s":
			seconds += v

	return datetime.timedelta(days=total_days, hours=hours, minutes=minutes, seconds=seconds)


def shorten(text: str, max_len: int = 32) -> str:
	return text if len(text) <= max_len else text[: max_len - 3] + "..."


async def get_user_reminders(ctx: discord.AutocompleteContext):
	db: ReminderDB = ctx.cog.db
	if not db:
		return []
	user_reminders = await db.get_reminders(user_id=ctx.interaction.user.id)

	return [
		discord.OptionChoice(
			name=f"{shorten(reminder.message, 24)} (in {diff_to_str(datetime.datetime.now(datetime.UTC), reminder.remind_at)})", value=reminder.id
		)
		for reminder in user_reminders
	]


class RemindersList(View):
	def __init__(self, bot: "Natsumin", user: discord.User, reminders: list[Reminder], show_hidden: bool):
		super().__init__(timeout=180, disable_on_timeout=True)
		reminders = sorted(reminders, key=lambda r: r.remind_at)

		reminder_str_list: list[str] = []
		for reminder in reminders:
			if reminder.hidden and not show_hidden:
				continue
			message = shorten(reminder.message, 24)
			reminder_str_list.append(
				f"1. {f'{message} ' if message else ''}<t:{reminder.remind_timestamp()}:R> (<t:{reminder.remind_timestamp()}:f>)"
			)

		self.add_item(
			Container(
				Section(TextDisplay(f"# Reminders:\n{'\n'.join(reminder_str_list)}"), accessory=Thumbnail(user.display_avatar.url)),
				color=config.base_embed_color,
			)
		)


class ReminderCog(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.reminder")
		self.db = ReminderDB("data/reminders.db")
		self.reminder_loop.start()

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/reminder.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	async def create_reminder(self, user: discord.User, channel: discord.TextChannel, remind_in: str, message: str, hidden: bool) -> tuple[str, bool]:
		if match := re.match(TIMESTAMP_REGEX, remind_in):
			try:
				timestamp = int(match.group(1))
			except ValueError:
				return "Invalid timestamp.", True

			remind_at = from_utc_timestamp(timestamp)
			current_datetime = datetime.datetime.now(datetime.UTC)
			if remind_at <= current_datetime:
				return "Invalid timestamp, timestamp must be in the future not the past.", True
		else:
			try:
				delta = parse_duration_str(remind_in)
			except ValueError:
				return "Invalid duration format, please use something like: `1d24h60m` or `1 day 24 hours 60 minutes`", True

			remind_at = datetime.datetime.now(datetime.UTC) + delta

		new_reminder = await self.db.create_reminder(user.id, channel.id, remind_at, message, hidden)

		time_diff_str = diff_to_str(new_reminder.created_at, new_reminder.remind_at)
		response = f"Done! Reminding in {time_diff_str}: `{new_reminder.message}`"
		if not new_reminder.message.strip():
			response = f"Done! Reminding in {time_diff_str}"

		self.logger.info(f"@{user.name} created reminder id={new_reminder.id} message={new_reminder.message}, due in {time_diff_str}.")
		return response, hidden

	async def delete_reminder(self, user: discord.User, id: int, hidden: bool) -> tuple[str, bool]:
		user_reminders = await self.db.get_reminders(user_id=user.id)

		has_reminder_with_id = any([reminder.id == id for reminder in user_reminders])

		if not has_reminder_with_id:
			return f"Could not find any reminder with id {id}", True

		deleted_reminder = [r for r in user_reminders if r.id == id][0]
		await self.db.delete_reminder(id)

		time_diff_str = diff_to_str(datetime.datetime.now(datetime.UTC), deleted_reminder.remind_at)

		self.logger.info(f"@{user.name} deleted reminder id={deleted_reminder.id} message={deleted_reminder.message}, due in {time_diff_str}")

		if deleted_reminder.message:
			return f"Deleted reminder `{deleted_reminder.message}` that's due in {time_diff_str}", hidden
		else:
			return f"Deleted reminder that's due in {time_diff_str}", hidden

	async def list_reminders(self, user: discord.User, hidden: bool, show_hidden: bool) -> tuple[str | RemindersList, bool]:
		user_reminders = await self.db.get_reminders(user_id=user.id)
		hidden_reminders = [r for r in user_reminders if r.hidden]
		channel_reminders = [r for r in user_reminders if not r.hidden]
		show_hidden = show_hidden if not hidden else hidden

		if show_hidden and (len(channel_reminders) == 0 and len(hidden_reminders) == 0):
			return "No reminders set!", hidden
		elif len(channel_reminders) == 0:
			return "No reminders set!", hidden

		return RemindersList(self.bot, user, user_reminders, show_hidden), hidden

	@commands.Cog.listener()
	async def on_ready(self):
		await self.db.setup()

	reminder_group = discord.SlashCommandGroup("reminder", "Reminder commands", guild_ids=config.guild_ids)

	@reminder_group.command(description="Create a new reminder.")
	@discord.option("when", str, required=True, parameter_name="remind_in", description="Example: 1d24h60m or 1 day 24 hours 60 minutes")
	@discord.option("message", str, default="", description="Optionally include a message to display when the reminder is due")
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def create(self, ctx: discord.ApplicationContext, remind_in: str, message: str, hidden: bool):
		response, ephemeral = await self.create_reminder(ctx.user, ctx.channel, remind_in, message, hidden)
		await ctx.respond(response, ephemeral=ephemeral)

	@reminder_group.command(description="Delete a reminder.")
	@discord.option(
		"id", int, required=True, autocomplete=get_user_reminders, description="ID of the reminder, should get autocompleted if not skill issue"
	)
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def delete(self, ctx: discord.ApplicationContext, id: int, hidden: bool):
		response, ephemeral = await self.delete_reminder(ctx.user, id, hidden)
		await ctx.respond(response, ephemeral=ephemeral)

	@reminder_group.command(description="See all the currently set reminders and their reminding date")
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	@discord.option("show_hidden", bool, description="Show hidden (DM) reminders, hidden argument takes priority over this.", default=False)
	async def list(self, ctx: discord.ApplicationContext, hidden: bool = False, show_hidden: bool = False):
		response, ephemeral = await self.list_reminders(ctx.user, hidden, show_hidden)
		if isinstance(response, RemindersList):
			await ctx.respond(view=response, ephemeral=ephemeral)
		else:
			await ctx.response(response, ephemeral=ephemeral)

	@commands.group(name="reminder", help="Reminder commands", aliases=["remind"], hidden=True, invoke_without_command=True)
	async def reminder_textgroup(self, ctx: commands.Context):
		await ctx.reply("Please specify a valid subcommand.")

	@reminder_textgroup.command("create", help="Create a new reminder", aliases=["new", "add"])
	async def text_create(self, ctx: commands.Context, remind_in: str, *, message: str):
		response, _ = await self.create_reminder(ctx.author, ctx.channel, remind_in, message, False)
		await ctx.reply(response)

	@reminder_textgroup.command("delete", help="Delete a reminder", aliases=["remove"])
	async def text_delete(self, ctx: commands.Context, id: int):
		response, _ = await self.delete_reminder(ctx.author, id)
		await ctx.reply(response)

	@reminder_textgroup.command("list", help="List all of your reminders")
	async def text_list(self, ctx: commands.Context, show_hidden: bool = False):
		response, _ = await self.list_reminders(ctx.author, False, show_hidden)
		if isinstance(response, RemindersList):
			await ctx.reply(view=response)
		else:
			await ctx.reply(response)

	@tasks.loop(seconds=15)
	async def reminder_loop(self):
		due_reminders = await self.db.get_due_reminders()

		for reminder in due_reminders:
			try:
				user = await self.bot.get_or_fetch_user(reminder.user_id)
				if not user:
					continue

				channel = self.bot.get_channel(reminder.channel_id)
				if not channel:
					channel = await self.bot.fetch_channel(reminder.channel_id)

				channelless_response = (
					f"Reminder from <t:{reminder.created_timestamp()}:R>{f': `{reminder.message}`' if reminder.message.strip() else ''}"
				)

				if (not channel) or reminder.hidden:
					await user.send(
						channelless_response, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)
					)
					continue

				bot_perms_in_channel = channel.permissions_for(channel.guild.me)
				if not bot_perms_in_channel.send_messages:
					await user.send(
						channelless_response, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)
					)
					continue

				await channel.send(
					f"<@{user.id}>, reminder from <t:{reminder.created_timestamp()}:R>{f': `{reminder.message}`' if reminder.message.strip() else ''}",
					allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
				)
			except Exception as e:
				self.logger.error(f"Could not emit reminder {reminder.id} to user {reminder.user_id}: {e}")

	@reminder_loop.before_loop
	async def before_loop(self):
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(ReminderCog(bot))
