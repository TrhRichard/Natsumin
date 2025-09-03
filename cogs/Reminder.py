from utils.reminder import ReminderDB
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

	@commands.Cog.listener()
	async def on_ready(self):
		await self.db.setup()

	reminder_group = discord.SlashCommandGroup("reminder", "Reminder commands", guild_ids=config.guild_ids)

	@reminder_group.command(description="Create a new reminder.")
	@discord.option("when", str, required=True, parameter_name="remind_in", description="Example: 1d24h60m or 1 day 24 hours 60 minutes")
	@discord.option("message", str, default="", description="Optionally include a message to display when the reminder is due")
	@discord.option("hidden", bool, description="Optionally make the response only visible to you", default=False)
	async def create(self, ctx: discord.ApplicationContext, remind_in: str, message: str, hidden: bool):
		try:
			delta = parse_duration_str(remind_in)
		except ValueError:
			return await ctx.respond("Invalid duration format, please use something like: `1d24h60m` or `1 day 24 hours 60 minutes`", ephemeral=True)

		remind_at = datetime.datetime.now(datetime.UTC) + delta

		new_reminder = await self.db.create_reminder(ctx.user.id, ctx.channel.id, remind_at, message, hidden)

		time_diff_str = diff_to_str(new_reminder.created_at, new_reminder.remind_at)
		response = f"Done! Reminding in {time_diff_str}: `{new_reminder.message}`"
		if not new_reminder.message.strip():
			response = f"Done! Reminding in {time_diff_str}"

		self.logger.info(f"@{ctx.user.name} created reminder id={new_reminder.id} message={new_reminder.message}, due in {time_diff_str}.")

		await ctx.respond(response, ephemeral=hidden)

	@reminder_group.command(description="Delete a reminder.")
	@discord.option(
		"id", int, required=True, autocomplete=get_user_reminders, description="ID of the reminder, should get autocompleted if not skill issue"
	)
	@discord.option("hidden", bool, description="Optionally make the response visible to you", default=False)
	async def delete(self, ctx: discord.ApplicationContext, id: int, hidden: bool):
		user_reminders = await self.db.get_reminders(user_id=ctx.user.id)

		has_reminder_with_id = any([reminder.id == id for reminder in user_reminders])

		if not has_reminder_with_id:
			return await ctx.respond(f"Could not find any reminder with id {id}", ephemeral=True)

		deleted_reminder = [r for r in user_reminders if r.id == id][0]
		await self.db.delete_reminder(id)

		time_diff_str = diff_to_str(datetime.datetime.now(datetime.UTC), deleted_reminder.remind_at)
		if deleted_reminder.message:
			await ctx.respond(f"Deleted reminder `{deleted_reminder.message}` that's due in {time_diff_str}", ephemeral=hidden)
		else:
			await ctx.respond(f"Deleted reminder that's due in {time_diff_str}", ephemeral=hidden)

		self.logger.info(f"@{ctx.user.name} deleted reminder id={deleted_reminder.id} message={deleted_reminder.message}, due in {time_diff_str}")

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
					await user.send(channelless_response)
					continue

				bot_perms_in_channel = channel.permissions_for(channel.guild.me)
				if not bot_perms_in_channel.send_messages:
					await user.send(channelless_response)
					continue

				await channel.send(
					f"<@{user.id}>, reminder from <t:{reminder.created_timestamp()}:R>{f': `{reminder.message}`' if reminder.message.strip() else ''}"
				)
			except Exception as e:
				self.logger.error(f"Could not emit reminder {reminder.id} to user {reminder.user_id}: {e}")

	@reminder_loop.before_loop
	async def before_loop(self):
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(ReminderCog(bot))
