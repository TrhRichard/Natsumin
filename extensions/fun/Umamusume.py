from __future__ import annotations

from internal.base.cog import NatsuminCog
from discord.ext import commands

import discord


class Umamusume(NatsuminCog):
	@commands.group("umamusume", help="uma uma uma uma uma", aliases=["uma"], hidden=True, invoke_without_command=True)
	async def uma_group(self, ctx: commands.Context):
		pass

	@uma_group.command("doto", aliases=["meishodoto"])
	async def doto(self, ctx: commands.Context):
		gallery = discord.ui.MediaGallery()
		gallery.add_item("https://files.catbox.moe/5fqu0o.mp4", description="a video")
		await ctx.reply(view=discord.ui.DesignerView(discord.ui.Container(gallery), store=False))

	@uma_group.command("chiyono", aliases=["sakurachiyonoo", "chiyo"])
	async def chiyono(self, ctx: commands.Context):
		gallery = discord.ui.MediaGallery()
		gallery.add_item("https://files.catbox.moe/kigu0t.mp4", description="a video")
		await ctx.reply(view=discord.ui.DesignerView(discord.ui.Container(gallery), store=False))

	@uma_group.command("mambo", aliases=["omatsurimambo", "machitan"])
	async def mambo(self, ctx: commands.Context):
		gallery = discord.ui.MediaGallery()
		gallery.add_item("https://files.catbox.moe/x8jgrk.mp4", description="a video")
		await ctx.reply(view=discord.ui.DesignerView(discord.ui.Container(gallery), store=False))

	@uma_group.command("kita", aliases=["kitasanblack", "kitasan", "kita-chan"])
	async def kita(self, ctx: commands.Context):
		gallery = discord.ui.MediaGallery()
		gallery.add_item("https://files.catbox.moe/racrfl.mov", description="a video")
		await ctx.reply(view=discord.ui.DesignerView(discord.ui.Container(gallery), store=False))
