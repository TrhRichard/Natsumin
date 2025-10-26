from discord.ext import commands
from typing import TYPE_CHECKING
import logging
import discord
import utils

if TYPE_CHECKING:
	from main import Natsumin


class Umamusume(commands.Cog):
	def __init__(self, bot: "Natsumin"):
		self.bot = bot
		self.logger = logging.getLogger("bot.other")

		if not self.logger.handlers:
			file_handler = logging.FileHandler("logs/other.log", encoding="utf-8")
			file_handler.setFormatter(utils.FILE_LOGGING_FORMATTER)
			console_handler = logging.StreamHandler()
			console_handler.setFormatter(utils.CONSOLE_LOGGING_FORMATTER)
			self.logger.addHandler(file_handler)
			self.logger.addHandler(console_handler)
			self.logger.setLevel(logging.INFO)

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


def setup(bot):
	bot.add_cog(Umamusume(bot))
