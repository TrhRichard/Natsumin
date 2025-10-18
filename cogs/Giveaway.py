from discord.ui import View, Container, TextDisplay, Section, Thumbnail
from utils.other import GiveawayDB, Giveaway, from_utc_timestamp, to_utc_timestamp, TIMESTAMP_REGEX, parse_duration_str, diff_to_str
from discord.ext import commands, tasks
from typing import TYPE_CHECKING
from common import config
import discord.ui as ui
import datetime
import logging
import discord
import random
import utils
import re

if TYPE_CHECKING:
	from main import Natsumin

db = GiveawayDB("data/giveaways.db")


def shorten(text: str, max_len: int = 32) -> str:
	return text if len(text) <= max_len else text[: max_len - 3] + "..."


async def get_user_giveaways(ctx: discord.AutocompleteContext):
	if not ctx.interaction.guild_id:
		return []
	entered_giveaways = sorted(
		await db.get_user_entered_giveaways(user_id=ctx.interaction.user.id, guild_id=ctx.interaction.guild_id), key=lambda g: g.ends_at
	)

	return [
		discord.OptionChoice(
			name=f"{shorten(giveaway.reward, 24)} (in {diff_to_str(datetime.datetime.now(datetime.UTC), giveaway.ends_at)})",
			value=giveaway.message_id,
		)
		for giveaway in entered_giveaways
	]


class GiveawaysList(View):
	def __init__(self, bot: "Natsumin", user: discord.User, giveaways_entered: list[Giveaway]):
		super().__init__(timeout=180, disable_on_timeout=True)
		giveaways = sorted(giveaways_entered, key=lambda g: g.ends_at)

		giveaway_str_list: list[str] = []
		for giveaway in giveaways:
			giveaway_str_list.append(f"1. {shorten(giveaway.reward, 24)} <t:{giveaway.ends_timestamp()}:R> (<t:{giveaway.ends_timestamp()}:f>)")

		self.add_item(
			Container(
				Section(TextDisplay(f"# Giveaways entered:\n{'\n'.join(giveaway_str_list)}"), accessory=Thumbnail(user.display_avatar.url)),
				color=config.base_embed_color,
			)
		)


async def get_giveaway_embed(giveaway: Giveaway) -> discord.Embed:
	embed = discord.Embed(
		title=giveaway.reward,
		description=f"Click 🎉 button to enter!\nWinners: **{giveaway.winners}**\nEnds: <t:{giveaway.ends_timestamp()}:R>",
		color=config.base_embed_color,
	)

	role_requirements = await giveaway.get_role_requirements()
	if role_requirements:
		embed.description += (
			f"\n\nMust have the role{'s' if len(role_requirements) > 1 else ''}: {', '.join([f'<@&{role_id}>' for role_id in role_requirements])}"
		)

	return embed


class GiveawayMessageView(View):
	def __init__(self, entered_users: int = 0, has_ended: bool = False):
		super().__init__(timeout=None)

		enter_button = ui.Button(
			style=discord.ButtonStyle.primary, label=str(entered_users), emoji="🎉", disabled=has_ended, custom_id="natsumin:enter_giveaway"
		)
		participants_button = ui.Button(style=discord.ButtonStyle.secondary, label="Participants", emoji="👤", custom_id="natsumin:get_participants")

		enter_button.callback = self.enter_callback
		participants_button.callback = self.participants_callback

		self.add_item(enter_button)
		self.add_item(participants_button)

	async def enter_callback(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)
		giveaway = await db.get_giveaway(interaction.message.id)
		if not giveaway:
			return await interaction.respond("Could not find a giveaway in the database for this message.", ephemeral=True)

		interaction_message = await interaction.original_response()

		entered_users = await giveaway.get_users_entered()

		if giveaway.ended or datetime.datetime.now(datetime.UTC) > giveaway.ends_at:
			return await interaction.respond(f"Giveaway **{giveaway.reward}** has already ended with {len(entered_users)} entries!", ephemeral=True)

		if interaction.user.id in entered_users:
			return await interaction.respond("todo leaving", ephemeral=True)

		roles_required = await giveaway.get_role_requirements()
		if roles_required:
			missing_roles: list[int] = []
			for role_id in roles_required:
				if not interaction.user.get_role(role_id):
					missing_roles.append(role_id)

			if missing_roles:
				return await interaction.respond(f"Missing roles: {', '.join([f'<@&{role_id}>' for role_id in missing_roles])}", ephemeral=True)

		success = await db.add_user_to_giveaway(interaction.message.id, interaction.user.id)
		if success:
			embed = discord.Embed(
				title="Entry confirmed!",
				description=f"Your entry for the giveaway of [{giveaway.reward}]({interaction_message.jump_url}) is confirmed!",
				color=config.base_embed_color,
			)
			await interaction.message.edit(embed=await get_giveaway_embed(giveaway), view=GiveawayMessageView(len(entered_users) + 1, giveaway.ended))
		else:
			embed = discord.Embed(
				title="Entry error", description="Something went wrong while trying to add you to the giveaway.", color=config.base_embed_color
			)
		await interaction.respond(embed=embed, ephemeral=True)

	async def participants_callback(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)
		giveaway = await db.get_giveaway(interaction.message.id)
		if not giveaway:
			return await interaction.respond("Could not find a giveaway in the database for this message.", ephemeral=True)

		await interaction.respond(
			f"todo participant list\ntemp: {', '.join([f'<@{user_id}>' for user_id in await giveaway.get_users_entered()])}", ephemeral=True
		)


class GiveawayCog(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.giveaway")
		self.giveaway_loop.start()

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/giveaway.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

	@commands.Cog.listener()
	async def on_ready(self):
		await db.setup()
		if "giveaway_message_view" not in self.bot.added_persistent_views:
			self.bot.added_persistent_views.append("giveaway_message_view")
			self.bot.add_view(GiveawayMessageView())

	giveaway_group = discord.SlashCommandGroup("giveaway", "Giveaway commands", guild_ids=config.guild_ids)

	@giveaway_group.command(description="Create a new giveaway")
	@discord.option("duration", str, parameter_name="ends_at", description="The duration for this giveaway")
	@discord.option("winners", int, default=1, description="The number of winners for this giveaway")
	@discord.option("reward", str, description="The reward for this giveaway")
	@discord.option("channel", discord.TextChannel, default=None, description="The channel this giveaway will be created in")
	@discord.option(
		"required-role",
		discord.Role,
		parameter_name="required_role",
		default=None,
		description="The role required for this giveaway, can be used together with required_roles",
	)
	@discord.option(
		"required-roles",
		str,
		parameter_name="required_roles",
		default="",
		description="The ids of each role required for this giveaway, separated by ,",
	)
	async def create(
		self,
		ctx: discord.ApplicationContext,
		ends_at: str,
		reward: str,
		winners: int,
		channel: discord.TextChannel | None,
		required_role: discord.Role | None,
		required_roles: str,
	):
		if match := re.match(TIMESTAMP_REGEX, ends_at):
			try:
				timestamp = int(match.group(1))
			except ValueError:
				return ctx.respond("Invalid timestamp.", ephemeral=True)

			ends_at_datetime = from_utc_timestamp(timestamp)
			current_datetime = datetime.datetime.now(datetime.UTC)
			if ends_at_datetime <= current_datetime:
				return ctx.respond("Invalid timestamp, timestamp must be in the future not the past.", ephemeral=True)
		else:
			try:
				delta = parse_duration_str(ends_at)
			except ValueError:
				await ctx.respond("Invalid duration format, please use something like: `1d24h60m` or `1 day 24 hours 60 minutes`", ephemeral=True)

			ends_at_datetime = datetime.datetime.now(datetime.UTC) + delta

		await ctx.defer(ephemeral=True)

		giveaway_channel = channel or ctx.channel

		invalid_role_ids: list[str] = []

		roles_needed: list[int] = []
		if required_roles:
			roles_required_list = required_roles.split(",")
			for str_role_id in roles_required_list:
				str_role_id = str_role_id.strip()
				if str_role_id.isdigit():
					role_id = int(str_role_id)
					role_found = await discord.utils.get_or_fetch(giveaway_channel.guild, "role", role_id, default=None)
					if not role_found:
						invalid_role_ids.append(str_role_id)

					if role_id not in roles_needed:
						roles_needed.append(role_id)
				else:
					invalid_role_ids.append(str_role_id)

		if required_role and required_role.id not in roles_needed:
			roles_needed.append(required_role.id)

		embed = discord.Embed(
			title=reward,
			description=f"Click 🎉 button to enter!\nWinners: **{winners}**\nEnds: <t:{to_utc_timestamp(ends_at_datetime)}:R>",
			color=config.base_embed_color,
		)
		if roles_needed:
			embed.description += (
				f"\n\nMust have the role{'s' if len(roles_needed) > 1 else ''}: {', '.join([f'<@&{role_id}>' for role_id in roles_needed])}"
			)

		giveaway_message = await giveaway_channel.send(embed=embed, view=GiveawayMessageView(0, False))

		await db.create_giveaway(
			giveaway_message.id, giveaway_channel.id, giveaway_channel.guild.id, ctx.user.id, reward, ends_at_datetime, winners, roles_needed
		)
		await ctx.respond(f"Giveaway started! You can find it [here]({giveaway_message.jump_url})", ephemeral=True)

	@tasks.loop(seconds=10)
	async def giveaway_loop(self):
		due_giveaways = await db.get_due_giveaways()

		for giveaway in due_giveaways:
			try:
				message = self.bot.get_message(giveaway.message_id)
				if not message:
					channel: discord.TextChannel = await discord.utils.get_or_fetch(self.bot, "channel", giveaway.channel_id)
					message = await channel.fetch_message(giveaway.message_id)

				users_entered = await giveaway.get_users_entered()
				valid_entries: list[discord.User] = []
				for user_id in users_entered:
					if user := await self.bot.get_or_fetch_user(user_id):
						valid_entries.append(user)

				winners: list[discord.User] = random.sample(valid_entries, min(len(valid_entries), giveaway.winners))

				if not winners:
					embed = discord.Embed(title=giveaway.reward, description="No winner.", color=config.base_embed_color)
				else:
					embed = discord.Embed(
						title=giveaway.reward,
						description=f"Winner{'s' if len(winners) > 1 else ''}: {', '.join([user.mention for user in winners])}",
						color=config.base_embed_color,
					)

				await message.edit("GIVEAWAY ENDED", embed=embed, view=GiveawayMessageView(len(users_entered), True))

				if not winners:
					continue

				async with db.connect() as conn:
					await conn.executemany(
						"INSERT OR IGNORE INTO winners (giveaway_id, winner_index, user_id) VALUES (?, ?, ?)",
						[(giveaway.message_id, index, user.id) for index, user in enumerate(winners, start=1)],
					)
					await conn.commit()

				embed = discord.Embed(
					description=(
						f"{' & '.join([user.mention for user in winners])} won the giveaway of **{giveaway.reward}**!\n\n"
						+ f"- Reroll command: `{config.prefix}reroll {giveaway.message_id}`"
					),
					color=config.base_embed_color,
				)

				await message.reply(
					"Congratulations! 🎉",
					embed=embed,
					view=View(ui.Button(style=discord.ButtonStyle.link, label="Giveaway Message", url=message.jump_url), timeout=None),
				)

			except Exception as e:
				self.logger.error(e)

	@giveaway_loop.before_loop
	async def before_loop(self):
		await db.setup()
		await self.bot.wait_until_ready()


def setup(bot):
	bot.add_cog(GiveawayCog(bot))
