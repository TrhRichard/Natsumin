from __future__ import annotations

from internal.constants import FILE_LOGGING_FORMATTER, COLORS
from internal.functions import shorten, diff_to_str
from internal.base.cog import NatsuminCog
from discord.ext import commands, tasks
from typing import TYPE_CHECKING
from discord import ui

import parsedatetime
import datetime
import discord
import logging
import re

if TYPE_CHECKING:
	from internal.database.Reminder import ReminderDatabase, Reminder
	from internal.base.bot import NatsuminBot


TIMESTAMP_PATTERN = r"<t:(\d+):(\w+)>"


async def get_user_reminders(ctx: discord.AutocompleteContext):
	db: ReminderDatabase = ctx.cog.db
	if not db:
		return []
	user_reminders: list[Reminder] = sorted(await db.get_reminders(user_id=ctx.interaction.user.id), key=lambda r: r.remind_at)

	return [
		discord.OptionChoice(
			name=f"{shorten(reminder.message, 24)} ({diff_to_str(reminder.remind_at, datetime.datetime.now(datetime.UTC))})", value=reminder.id
		)
		for reminder in user_reminders
	]


class RemindersList(ui.DesignerView):
	def __init__(self, bot: NatsuminBot, invoker: discord.User, reminders: list[Reminder], show_hidden: bool):
		super().__init__(store=False)
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
			ui.Container(
				ui.Section(ui.TextDisplay(f"# Reminders:\n{'\n'.join(reminder_str_list)}"), accessory=ui.Thumbnail(invoker.display_avatar.url)),
				color=COLORS.DEFAULT,
			)
		)


class ReminderExt(NatsuminCog, name="Reminder"):
	"""Reminder commands"""

	def __init__(self, bot: NatsuminBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.reminder")
		self.db = bot.reminders
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/reminder.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

		self.reminder_loop.start()

	async def create_reminder(
		self, user: discord.User, channel: discord.TextChannel, remind_in: str, message: str, hidden: bool = False
	) -> tuple[str, bool]:
		current_datetime = datetime.datetime.now(datetime.UTC)
		if match := re.match(TIMESTAMP_PATTERN, remind_in):
			try:
				timestamp = int(match.group(1))
			except ValueError:
				return "Invalid timestamp.", True

			remind_at = datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
		else:
			calender = parsedatetime.Calendar()

			remind_at, parse_result = calender.parseDT(remind_in, sourceTime=current_datetime, tzinfo=datetime.UTC)

			if parse_result == 0:
				return (
					"Invalid duration format, please use something like: `1d24h60m` or `1 day 24 hours 60 minutes`, alternatively use a UTC timestamp",
					True,
				)

		if remind_at <= current_datetime:
			return "Invalid timestamp, it seems that you've attempted to set the reminder to end in the past.", True

		new_reminder = await self.db.create_reminder(user.id, channel.id, remind_at, message, hidden)

		time_diff_str = diff_to_str(new_reminder.remind_at, new_reminder.created_at)
		response = f"Done! Reminding in {time_diff_str}: `{new_reminder.message}`"
		if not new_reminder.message.strip():
			response = f"Done! Reminding in {time_diff_str}"

		self.logger.info(f"@{user.name} created reminder id={new_reminder.id} message={new_reminder.message}, due in {time_diff_str}.")
		return response, hidden

	async def delete_reminder(self, user: discord.User, id: int, hidden: bool = False) -> tuple[str, bool]:
		user_reminders = await self.db.get_reminders(user_id=user.id)

		has_reminder_with_id = any([reminder.id == id for reminder in user_reminders])

		if not has_reminder_with_id:
			return f"Could not find any reminder with id {id}", True

		deleted_reminder = [r for r in user_reminders if r.id == id][0]
		await self.db.delete_reminder(id)

		time_diff_str = diff_to_str(deleted_reminder.remind_at, datetime.datetime.now(datetime.UTC))

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

	reminder_group = discord.SlashCommandGroup("reminder", "Reminder commands")

	@reminder_group.command(description="Create a new reminder.")
	@discord.option("when", str, required=True, parameter_name="remind_in", description="Example: 1d24h60m or 1 day 24 hours 60 minutes")
	@discord.option("message", str, default="", description="Optionally include a message to display when the reminder is due")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=False)
	async def create(self, ctx: discord.ApplicationContext, remind_in: str, message: str, hidden: bool):
		response, ephemeral = await self.create_reminder(ctx.user, ctx.channel, remind_in, message, hidden)
		await ctx.respond(response, ephemeral=ephemeral)

	@reminder_group.command(description="Delete a reminder.")
	@discord.option(
		"id", int, required=True, autocomplete=get_user_reminders, description="ID of the reminder, should get autocompleted if not skill issue"
	)
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=False)
	async def delete(self, ctx: discord.ApplicationContext, id: int, hidden: bool):
		response, ephemeral = await self.delete_reminder(ctx.user, id, hidden)
		await ctx.respond(response, ephemeral=ephemeral)

	@reminder_group.command(description="See all the currently set reminders and their reminding date")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you", default=False)
	@discord.option("show_hidden", bool, description="Show hidden (DM) reminders, hidden argument takes priority over this.", default=False)
	async def list(self, ctx: discord.ApplicationContext, hidden: bool = False, show_hidden: bool = False):
		response, ephemeral = await self.list_reminders(ctx.user, hidden, show_hidden)
		if isinstance(response, RemindersList):
			await ctx.respond(view=response, ephemeral=ephemeral)
		else:
			await ctx.respond(response, ephemeral=ephemeral)

	@commands.group(name="reminder", aliases=["remind", "reminders"], invoke_without_command=True, help="Reminder related commands")
	async def reminder_textgroup(self, ctx: commands.Context):
		await ctx.reply(f"Please specify a valid subcommand. Use `{ctx.clean_prefix}help {ctx.invoked_with}` for a full list.")

	@reminder_textgroup.command(
		"create",
		aliases=["new", "add"],
		help="Create a new reminder",
		description="Create a new reminder. In order to specify a time like `1 hour 15 minutes` you must put it in quotation marks.\nAdditionally you can use a discord timestamp as the time, for example `<t:1894658400:f>` (which would turn into <t:1894658400:f>)",
	)
	async def text_create(self, ctx: commands.Context, remind_in: str, *, message: str = ""):
		response, _ = await self.create_reminder(ctx.author, ctx.channel, remind_in, message, False)
		await ctx.reply(response)

	@reminder_textgroup.command(
		"delete",
		aliases=["remove"],
		help="Delete a reminder",
		description="Delete a reminder, grab the id from the list subcommand otherwise guess it if u can lol",
	)
	async def text_delete(self, ctx: commands.Context, id: int):
		response, _ = await self.delete_reminder(ctx.author, id)
		await ctx.reply(response)

	@reminder_textgroup.command(
		"list",
		aliases=["all"],
		help="List all of your reminders",
		description="List all of your reminders, by default ones made hidden will not be listed",
	)
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
				user = await self.bot.get_or_fetch(discord.User, reminder.user_id)
				if not user:
					continue

				channel = await self.bot.get_or_fetch(discord.TextChannel, reminder.channel_id)

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
		await self.bot.reminders.wait_until_ready()


def setup(bot: NatsuminBot):
	bot.add_cog(ReminderExt(bot))
