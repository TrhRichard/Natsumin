from __future__ import annotations

from .queries import search_media, search_character, search_staff, Media, Character, Staff
from internal.base.context import NatsuContext, NatsuAppContext
from internal.constants import FILE_LOGGING_FORMATTER, COLORS
from internal.functions import frmt_iter
from internal.base.cog import NatsuCog
from discord.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from internal.base.bot import NatsuBot

import logging
import discord


def html_to_color(value: str) -> discord.Colour:
	return discord.Colour(int(value.lstrip("#"), 16))


class AnilistExt(NatsuCog, name="AniList"):
	"""AniList related commands"""

	def __init__(self, bot: NatsuBot):
		super().__init__(bot)
		self.logger = logging.getLogger("bot.anilist")
		self.is_syncing_enabled = True
		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/anilist.log", encoding="utf-8")
			file_handler.setFormatter(FILE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)

			self.logger.setLevel(logging.INFO)

	def create_embed_from_media(self, media: Media) -> discord.Embed:
		embed = discord.Embed(
			color=html_to_color(media.cover_image.color) if media.cover_image.color else COLORS.DEFAULT,
			description=media.description,
			url=media.site_url,
		)
		embed.set_author(name=media.title.displayed_title, url=media.site_url)
		embed.set_thumbnail(url=media.cover_image.extra_large)

		if media.genres:
			embed.add_field(name="Genres" if len(media.genres) > 1 else "Genre", value=frmt_iter(media.genres), inline=False)

		embed.add_field(name="Format", value=media.displayed_format, inline=True)
		embed.add_field(name="Source", value=media.displayed_source, inline=True)
		embed.add_field(name="Status", value=media.displayed_status, inline=True)
		if media.episodes:
			embed.add_field(name="Episodes", value=str(media.episodes), inline=True)
		if media.chapters:
			embed.add_field(name="Chapters", value=str(media.chapters), inline=True)

		embed.add_field(name="Country Of Origin", value=media.country_of_origin, inline=True)
		embed.add_field(name="Average Score", value=str(media.average_score), inline=True)

		if media.studios.nodes:
			embed.add_field(
				name="Studios" if len(media.studios.nodes) > 1 else "Studio",
				value=frmt_iter(f"[{studio.name}]({studio.site_url})" for studio in media.studios.nodes),
				inline=False,
			)

		if media.start_date is not None:
			value = media.start_date.strftime("%B %d, %Y")
			if media.end_date is not None:
				value = f"{value} to {media.end_date.strftime('%B %d, %Y')}"

			embed.add_field(name=f"{'Airing' if media.type == 'ANIME' else 'Releasing'} Date", value=value.strip(), inline=False)

		return embed

	def create_embed_from_character(self, character: Character) -> discord.Embed:
		embed = discord.Embed(color=COLORS.DEFAULT)
		embed.set_author(name=character.name.displayed_name, url=character.site_url)
		embed.set_thumbnail(url=character.image.large)

		desc_fields = []

		if character.age is not None:
			desc_fields.append(f"**Age:** {character.age}")
		if character.gender is not None:
			desc_fields.append(f"**Gender:** {character.gender}")

		desc_fields.append(character.description)
		embed.description = "\n".join(desc_fields)

		return embed

	def create_embed_from_staff(self, staff: Staff) -> discord.Embed:
		embed = discord.Embed(color=COLORS.DEFAULT, description=staff.description)
		embed.set_author(name=staff.name.displayed_name, url=staff.site_url)
		embed.set_thumbnail(url=staff.image.large)

		desc_fields = []

		if staff.age is not None:
			desc_fields.append(f"**Age:** {staff.age}")
		if staff.gender is not None:
			desc_fields.append(f"**Gender:** {staff.gender}")

		desc_fields.append(staff.description)
		embed.description = "\n".join(desc_fields)

		return embed

	anilist_group = discord.commands.SlashCommandGroup(
		"anilist",
		contexts={discord.InteractionContextType.guild, discord.InteractionContextType.bot_dm, discord.InteractionContextType.private_channel},
		integration_types={discord.IntegrationType.user_install, discord.IntegrationType.guild_install},
	)

	@anilist_group.command(name="anime", description="Get information about a anime from AniList")
	@discord.option("title", str, min_length=1, description="Name of the anime")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you, defaults to False", default=False)
	async def slash_anime(self, ctx: NatsuAppContext, title: str, hidden: bool):
		found_media = await search_media(title, "ANIME")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.respond(
					embed=discord.Embed(
						title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels."
					),
					ephemeral=hidden,
				)

			return await ctx.respond(embed=self.create_embed_from_media(found_media), ephemeral=hidden)
		else:
			return await ctx.respond(
				embed=discord.Embed(title="Not Found", description=f"Could not find a anime with the title: **{title}**", color=COLORS.ERROR),
				ephemeral=hidden,
			)

	@anilist_group.command(name="manga", description="Get information about a manga from AniList")
	@discord.option("title", str, min_length=1, description="Name of the manga")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you, defaults to False", default=False)
	async def slash_manga(self, ctx: NatsuAppContext, title: str, hidden: bool):
		found_media = await search_media(title, "MANGA")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.respond(
					embed=discord.Embed(
						title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels."
					),
					ephemeral=hidden,
				)

			return await ctx.respond(embed=self.create_embed_from_media(found_media), ephemeral=hidden)
		else:
			return await ctx.respond(
				embed=discord.Embed(title="Not Found", description=f"Could not find a manga with the title: **{title}**", color=COLORS.ERROR),
				ephemeral=hidden,
			)

	@anilist_group.command(name="lightnovel", description="Get information about a light novel from AniList")
	@discord.option("title", str, min_length=1, description="Name of the light novel")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you, defaults to False", default=False)
	async def slash_lightnovel(self, ctx: NatsuAppContext, title: str, hidden: bool):
		found_media = await search_media(title, "LIGHT_NOVEL")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.respond(
					embed=discord.Embed(
						title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels."
					),
					ephemeral=hidden,
				)

			return await ctx.respond(embed=self.create_embed_from_media(found_media), ephemeral=hidden)
		else:
			return await ctx.respond(
				embed=discord.Embed(title="Not Found", description=f"Could not find a light novel with the title: **{title}**", color=COLORS.ERROR),
				ephemeral=hidden,
			)

	@anilist_group.command(name="character", description="Get information about a character from AniList")
	@discord.option("name", str, min_length=1, description="Name of the character")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you, defaults to False", default=False)
	async def slash_character(self, ctx: NatsuAppContext, name: str, hidden: bool):
		found_character = await search_character(name)
		if found_character:
			return await ctx.respond(embed=self.create_embed_from_character(found_character), ephemeral=hidden)
		else:
			return await ctx.respond(
				embed=discord.Embed(title="Not Found", description=f"Could not find a character with the name: **{name}**", color=COLORS.ERROR),
				ephemeral=hidden,
			)

	@anilist_group.command(name="staff", description="Get information about a staff from AniList")
	@discord.option("name", str, min_length=1, description="Name of the staff")
	@discord.option("hidden", bool, description="Whether to make the response only visible to you, defaults to False", default=False)
	async def slash_staff(self, ctx: NatsuAppContext, name: str, hidden: bool):
		found_staff = await search_staff(name)
		if found_staff:
			return await ctx.respond(embed=self.create_embed_from_staff(found_staff), ephemeral=hidden)
		else:
			return await ctx.respond(
				embed=discord.Embed(title="Not Found", description=f"Could not find staff with the name: **{name}**", color=COLORS.ERROR),
				ephemeral=hidden,
			)

	@commands.command(name="anime", help="Get information about a anime from AniList")
	async def text_anime(self, ctx: NatsuContext, *, title: str):
		found_media = await search_media(title, "ANIME")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.reply(
					embed=discord.Embed(title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels.")
				)

			return await ctx.reply(embed=self.create_embed_from_media(found_media))
		else:
			return await ctx.reply(
				embed=discord.Embed(title="Not Found", description=f"Could not find a anime with the title: **{title}**", color=COLORS.ERROR)
			)

	@commands.command(name="manga", help="Get information about a manga from AniList")
	async def text_manga(self, ctx: NatsuContext, *, title: str):
		found_media = await search_media(title, "MANGA")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.reply(
					embed=discord.Embed(title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels.")
				)

			return await ctx.reply(embed=self.create_embed_from_media(found_media))
		else:
			return await ctx.reply(
				embed=discord.Embed(title="Not Found", description=f"Could not find a manga with the title: **{title}**", color=COLORS.ERROR)
			)

	@commands.command(name="lightnovel", aliases=["ln"], help="Get information about a light novel from AniList")
	async def text_lightnovel(self, ctx: NatsuContext, *, title: str):
		found_media = await search_media(title, "LIGHT_NOVEL")

		if found_media:
			if found_media.is_adult and not ctx.channel.is_nsfw():
				return await ctx.reply(
					embed=discord.Embed(title="Age-Restricted", description="Information for adult media is only allowed in Age-Restricted channels.")
				)

			return await ctx.reply(embed=self.create_embed_from_media(found_media))
		else:
			return await ctx.reply(
				embed=discord.Embed(title="Not Found", description=f"Could not find a light novel with the title: **{title}**", color=COLORS.ERROR)
			)

	@commands.command(name="character", aliases=["char"], help="Get information about a character from AniList")
	async def text_character(self, ctx: NatsuContext, *, name: str):
		found_character = await search_character(name)
		if found_character:
			return await ctx.reply(embed=self.create_embed_from_character(found_character))
		else:
			return await ctx.reply(
				embed=discord.Embed(title="Not Found", description=f"Could not find a character with the name: **{name}**", color=COLORS.ERROR)
			)

	@commands.command(name="staff", help="Get information about a staff from AniList")
	async def text_staff(self, ctx: NatsuContext, *, name: str):
		found_staff = await search_staff(name)
		if found_staff:
			return await ctx.reply(embed=self.create_embed_from_staff(found_staff))
		else:
			return await ctx.reply(
				embed=discord.Embed(title="Not Found", description=f"Could not find staff with the name: **{name}**", color=COLORS.ERROR)
			)


def setup(bot: NatsuBot):
	bot.add_cog(AnilistExt(bot))
