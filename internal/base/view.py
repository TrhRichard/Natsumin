from __future__ import annotations

from internal.schemas import BadgeData
from internal.constants import COLORS
from discord import ui

import discord


class BadgeDisplay(ui.DesignerView):
	def __init__(self, invoker: discord.abc.User, badges: list[BadgeData]):
		super().__init__(disable_on_timeout=True)

		self.invoker = invoker
		self.badges = badges
		self.current_badge_selected = 0

		self.add_item(self.get_badge_container(badges[self.current_badge_selected]))

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass

	async def button_callback(self, interaction: discord.Interaction):
		match interaction.custom_id:
			case "previous":
				self.current_badge_selected = (self.current_badge_selected - 1) % len(self.badges)
			case "next":
				self.current_badge_selected = (self.current_badge_selected + 1) % len(self.badges)
			case _:
				return

		self.clear_items()
		self.add_item(self.get_badge_container(self.badges[self.current_badge_selected]))
		await interaction.edit(view=self)

	def get_badge_container(self, badge: BadgeData) -> ui.Container:
		badge_artist = ui.TextDisplay(f"-# Artist: {badge['artist']}" if badge["artist"] else "-# No artist")
		if badge["url"]:
			badge_art = ui.MediaGallery()
			badge_art.add_item(badge["url"], description=badge["artist"])
		else:
			badge_art = ui.TextDisplay("No image available.")

		page_buttons = ui.ActionRow(
			ui.Button(style=discord.ButtonStyle.secondary, label="<--", disabled=False, custom_id="previous"),
			ui.Button(
				style=discord.ButtonStyle.primary,
				label=f"{self.current_badge_selected + 1}/{len(self.badges)}",
				disabled=True,  # len(self.badges) == 1,
				custom_id="change_page",
			),
			ui.Button(style=discord.ButtonStyle.secondary, label="-->", disabled=False, custom_id="next"),
		)

		for button in page_buttons.children:
			button.callback = self.button_callback

		return ui.Container(
			ui.TextDisplay(f"## {badge['name']}\n{badge['description']}"),
			ui.TextDisplay(f"-# Type: {badge['type']}"),
			ui.Separator(),
			badge_art,
			badge_artist,
			ui.Separator(),
			page_buttons,
			color=COLORS.DEFAULT,
		)
