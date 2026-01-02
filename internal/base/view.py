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

		for item in self.get_badge_page(self.badges[self.current_badge_selected]):
			self.add_item(item)

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except (discord.Forbidden, discord.NotFound):
			pass

	def update_ui(self):
		self.clear_items()
		for item in self.get_badge_page(self.badges[self.current_badge_selected]):
			self.add_item(item)

	async def button_callback(self, interaction: discord.Interaction):
		if interaction.user.id != self.invoker.id:
			return await interaction.respond("You did not trigger this command!", ephemeral=True)

		match interaction.custom_id:
			case "previous":
				self.current_badge_selected = (self.current_badge_selected - 1) % len(self.badges)
			case "next":
				self.current_badge_selected = (self.current_badge_selected + 1) % len(self.badges)
			case "page_indicator":
				return await interaction.response.send_modal(BadgeDisplayPageModal(self))
			case _:
				return

		self.update_ui()

		await interaction.edit(view=self)

	def get_badge_page(self, badge: BadgeData) -> tuple[ui.Container, ui.ActionRow]:
		if badge["url"]:
			badge_art = ui.MediaGallery()
			badge_art.add_item(badge["url"], description=badge["artist"])
		else:
			badge_art = ui.TextDisplay("No image available.")

		badge_details: tuple[str, ...] = (
			f"Artist: {badge['artist'] if badge['artist'] else 'None'}",
			f"Type: {badge['type']}",
			f"Owned: {'Yes' if 'author_owns_badge' in badge and badge['author_owns_badge'] else 'No'}",
		)

		page_buttons = ui.ActionRow(
			ui.Button(
				style=discord.ButtonStyle.secondary,
				label="↩" if self.current_badge_selected - 1 < 0 else "←",
				disabled=len(self.badges) == 1,
				custom_id="previous",
			),
			ui.Button(
				style=discord.ButtonStyle.primary,
				label=f"{self.current_badge_selected + 1}/{len(self.badges)}",
				disabled=len(self.badges) == 1,
				custom_id="page_indicator",
			),
			ui.Button(
				style=discord.ButtonStyle.secondary,
				label="↪" if self.current_badge_selected + 1 >= len(self.badges) else "→",
				disabled=len(self.badges) == 1,
				custom_id="next",
			),
		)

		for button in page_buttons.children:
			button.callback = self.button_callback

		return (
			ui.Container(
				ui.TextDisplay(f"## {badge['name']}\n{badge['description']}"),
				ui.TextDisplay("\n".join(badge_details)),
				ui.Separator(),
				badge_art,
				# ui.TextDisplay(f"-# ID: {badge['id']}"),
				color=COLORS.DEFAULT,
			),
			page_buttons,
		)


class BadgeDisplayPageModal(ui.Modal):
	def __init__(self, badge_display: BadgeDisplay):
		super().__init__(title="Go to Page", timeout=60)
		self.badge_display = badge_display

		self.add_item(
			ui.InputText(label="Page Number", placeholder=f"Enter page number (1-{len(self.badge_display.badges)})", custom_id="page_number")
		)

	async def callback(self, interaction: discord.Interaction):
		raw_page_number: str = self.get_item("page_number").value
		if not raw_page_number.isdigit():
			return await interaction.respond("Page number must be a number.", ephemeral=True)

		try:
			page_number = int(raw_page_number)
		except ValueError:
			page_number = 1

		self.badge_display.current_badge_selected = (page_number - 1) % len(self.badge_display.badges)
		self.badge_display.update_ui()
		await interaction.edit(view=self.badge_display)
