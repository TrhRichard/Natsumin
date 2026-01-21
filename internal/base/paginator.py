from __future__ import annotations

from discord.ext import pages as extpages
from discord import ui

import discord


class CustomPaginator(extpages.Paginator):
	def __init__(self, pages: list[extpages.PageGroup] | list[extpages.Page] | list[str] | list[list[discord.Embed] | discord.Embed]):
		super().__init__(
			pages,
			loop_pages=True,
			use_default_buttons=False,
			custom_buttons=[
				CustomPaginatorButton("prev", label="←", loop_label="↩", style=discord.ButtonStyle.blurple),
				CustomPaginatorButton("page_indicator", style=discord.ButtonStyle.secondary),
				CustomPaginatorButton("next", label="→", loop_label="↪", style=discord.ButtonStyle.blurple),
			],
		)

	async def on_timeout(self):
		try:
			await super().on_timeout()
		except discord.HTTPException:
			pass

	def update_buttons(self) -> dict:
		"""Updates the display state of the buttons (disabled/hidden)

		Returns
		-------
		Dict[:class:`str`, Dict[:class:`str`, Union[:class:`~PaginatorButton`, :class:`bool`]]]
			The dictionary of buttons that were updated.
		"""
		for key, button in self.buttons.items():
			if key == "first":
				if self.current_page <= 1:
					button["hidden"] = True
				elif self.current_page >= 1:
					button["hidden"] = False
			elif key == "last":
				if self.current_page >= self.page_count - 1:
					button["hidden"] = True
				if self.current_page < self.page_count - 1:
					button["hidden"] = False
			elif key == "next":
				if self.current_page == self.page_count:
					if not self.loop_pages:
						button["hidden"] = True
						button["object"].label = button["label"]
					else:
						button["object"].label = button["loop_label"]
				elif self.current_page < self.page_count:
					button["hidden"] = False
					button["object"].label = button["label"]
			elif key == "prev":
				if self.current_page <= 0:
					if not self.loop_pages:
						button["hidden"] = True
						button["object"].label = button["label"]
					else:
						button["object"].label = button["loop_label"]
				elif self.current_page >= 0:
					button["hidden"] = False
					button["object"].label = button["label"]
			elif key == "page_indicator":
				if self.page_count == 0:
					button["object"].disabled = True
		self.clear_items()
		if self.show_indicator:
			try:
				self.buttons["page_indicator"]["object"].label = f"{self.current_page + 1}/{self.page_count + 1}"
			except KeyError:
				pass
		for key, button in self.buttons.items():
			if key != "page_indicator":
				if button["hidden"]:
					button["object"].disabled = True
					if self.show_disabled:
						self.add_item(button["object"])
				else:
					if key in ("next", "prev") and (self.loop_pages and self.page_count < 1):  # changes to built in is this if statment
						button["object"].disabled = True
					else:
						button["object"].disabled = False
					self.add_item(button["object"])
			elif self.show_indicator:
				self.add_item(button["object"])

		if self.show_menu:
			self.add_menu()

		# We're done adding standard buttons and menus, so we can now add any specified custom view items below them
		# The bot developer should handle row assignments for their view before passing it to Paginator
		if self.custom_view:
			self.update_custom_view(self.custom_view)

		return self.buttons

	async def goto_page(self, page_number=0, *, interaction: discord.Interaction = None):
		try:
			await super().goto_page(page_number, interaction=interaction)
		except discord.DiscordException:
			raise
		else:
			if interaction:
				try:
					self.message = await interaction.original_response()
				except discord.NotFound:
					self.message = interaction.message


class CustomPaginatorButton(extpages.PaginatorButton):
	async def callback(self, interaction: discord.Interaction):
		"""|coro|

		The coroutine that is called when the navigation button is clicked.

		Parameters
		----------
		interaction: :class:`discord.Interaction`
		    The interaction created by clicking the navigation button.
		"""
		new_page = self.paginator.current_page
		if self.button_type == "first":
			new_page = 0
		elif self.button_type == "prev":
			if self.paginator.loop_pages and self.paginator.current_page == 0:
				new_page = self.paginator.page_count
			else:
				new_page -= 1
		elif self.button_type == "next":
			if self.paginator.loop_pages and self.paginator.current_page == self.paginator.page_count:
				new_page = 0
			else:
				new_page += 1
		elif self.button_type == "last":
			new_page = self.paginator.page_count

		if self.button_type == "page_indicator":
			await interaction.response.send_modal(PageModal(self.paginator))
		else:
			await self.paginator.goto_page(page_number=new_page, interaction=interaction)


class PageModal(ui.Modal):
	def __init__(self, paginator: CustomPaginator):
		super().__init__(title="Go to Page", timeout=60)
		self.paginator = paginator

		self.add_item(
			ui.InputText(label="Page Number", placeholder=f"Enter page number (1-{self.paginator.page_count + 1})", custom_id="page_number")
		)

	async def callback(self, interaction: discord.Interaction):
		raw_page_number: str = self.get_item("page_number").value
		if not raw_page_number.isdigit():
			return await interaction.respond("Page number must be a number.", ephemeral=True)

		page_number = int(raw_page_number) - 1

		if page_number > self.paginator.page_count or page_number < 0:
			return await interaction.respond(f"Invalid page! Page must be from 1 to {self.paginator.page_count + 1}", ephemeral=True)

		await self.paginator.goto_page(page_number, interaction=interaction)
