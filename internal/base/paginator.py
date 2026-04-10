from __future__ import annotations

from discord.ext import commands, pages as extpages
from typing import Literal
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


type V2PaginatorButtonType = Literal["previous_page", "page_indicator", "next_page"]


class V2PaginatorButton(ui.Button):
	def __init__(self, button_type: V2PaginatorButtonType):
		super().__init__(custom_id=button_type)

		self.button_type: V2PaginatorButtonType = button_type
		self.paginator: V2Paginator | None = None

	def _update_button(self):
		assert self.paginator is not None

		match self.button_type:
			case "previous_page":
				self.label = "↩" if self.paginator.current_page - 1 < 0 else "←"
				self.disabled = len(self.paginator.pages) == 1
				self.style = discord.ButtonStyle.secondary
			case "next_page":
				self.label = "↪" if self.paginator.current_page + 1 > self.paginator.last_page else "→"
				self.disabled = len(self.paginator.pages) == 1
				self.style = discord.ButtonStyle.secondary
			case "page_indicator":
				self.label = f"{self.paginator.current_page + 1}/{len(self.paginator.pages)}"
				self.disabled = len(self.paginator.pages) == 1
				self.style = discord.ButtonStyle.primary

	async def callback(self, interaction):
		if self.paginator.author_check and interaction.user != self.paginator.user:
			return await interaction.respond("You did not trigger this command!", ephemeral=True)

		new_page = self.paginator.current_page
		match interaction.custom_id:
			case "previous_page":
				if self.paginator.current_page == 0:
					new_page = self.paginator.last_page
				else:
					new_page -= 1
			case "next_page":
				if self.paginator.current_page == self.paginator.last_page:
					new_page = 0
				else:
					new_page += 1
			case "page_indicator":
				await interaction.response.send_modal(ChangePageModal(self.paginator))
				return

		await self.paginator.goto_page(new_page, interaction=interaction)


class V2Page:
	def __init__(self, items: list[ui.ViewItem], *, extra_buttons: list[ui.Button] | None = None, custom_view: ui.DesignerView | None = None):
		self.items = items
		self.extra_buttons = extra_buttons
		if custom_view:
			for item in custom_view.children:
				self.items.append(item)


class V2Paginator:
	def __init__(
		self,
		pages: list[ui.ViewItem | list[ui.ViewItem] | V2Page],
		*,
		timeout: float | None = 180,
		disable_on_timeout: bool = True,
		store: bool = True,
		add_default_buttons: bool = True,
		author_check: bool = True,
	):
		self.current_page = 0
		self.pages: list[ui.ViewItem | list[ui.ViewItem] | V2Page] = []
		self.user: discord.abc.User | None = None
		self.message: discord.Message | discord.WebhookMessage | None = None
		self.author_check = author_check

		self._view = ui.DesignerView(timeout=timeout, disable_on_timeout=disable_on_timeout, store=store)
		self._button_row = ui.ActionRow()

		for page in pages:
			self.pages.append(page)

		if add_default_buttons:
			self._add_default_buttons()

	@property
	def last_page(self):
		return len(self.pages) - 1

	def add_button(self, button: V2PaginatorButton):
		button.paginator = self
		self._button_row.add_item(button)

	@staticmethod
	def get_page_content(page_content: ui.ViewItem | list[ui.ViewItem] | ui.DesignerView) -> V2Page:
		if isinstance(page_content, ui.ViewItem):
			return V2Page([page_content])
		elif isinstance(page_content, list):
			return V2Page(page_content)
		elif isinstance(page_content, ui.DesignerView):
			return V2Page([], custom_view=page_content)
		else:
			return page_content

	async def respond(self, interaction: discord.Interaction, ephemeral: bool = False):
		if not isinstance(interaction, discord.Interaction):
			raise TypeError(f"expected Interaction not {interaction.__class__!r}")

		if ephemeral and (self._view.timeout is None or self._view.timeout >= 900):
			raise ValueError("paginator responses cannot be ephemeral if the paginator timeout is 15 minutes or greater")

		self._update_content()

		self.user = interaction.user

		if interaction.response.is_done():
			msg: discord.WebhookMessage = await interaction.followup.send(view=self._view, ephemeral=ephemeral)

			if not ephemeral and not msg.flags.ephemeral:
				msg = await msg.channel.fetch_message(msg.id)
		else:
			msg = await interaction.response.send_message(view=self._view, ephemeral=ephemeral)

		if isinstance(msg, (discord.Message, discord.WebhookMessage)):
			self.message = msg
		elif isinstance(msg, discord.Interaction):
			self.message = await msg.original_response()

		return self.message

	async def send(self, ctx: commands.Context) -> discord.Message:
		if not isinstance(ctx, commands.Context):
			raise TypeError(f"expected Context not {ctx.__class__!r}")

		self._update_content()

		self.user = ctx.author
		self.message = await ctx.send(view=self._view)

		return self.message

	async def reply(self, ctx: commands.Context) -> discord.Message:
		if not isinstance(ctx, commands.Context):
			raise TypeError(f"expected Context not {ctx.__class__!r}")

		self._update_content()

		self.user = ctx.author
		self.message = await ctx.reply(view=self._view)

		return self.message

	async def goto_page(self, page_number: int = 0, *, interaction: discord.Interaction | None = None) -> discord.Message:
		old_page = self.current_page
		self.current_page = page_number
		self._update_content()

		try:
			if interaction:
				await interaction.response.defer()
				await interaction.followup.edit_message(self.message.id, view=self._view)
			else:
				await self.message.edit(view=self._view)
		except discord.DiscordException:
			self.current_page = old_page
			self._update_content()
			raise

	def _update_content(self):
		self._view.clear_items()

		page = self.get_page_content(self.pages[self.current_page])

		for item in page.items:
			self._view.add_item(item)

		self._add_default_buttons()
		if page.extra_buttons is not None:
			for button in page.extra_buttons:
				self._button_row.add_item(button)

		self._view.add_item(self._button_row)

		for button in self._button_row.children:
			if isinstance(button, V2PaginatorButton):
				button._update_button()

	def _add_default_buttons(self):
		self._button_row = ui.ActionRow()

		default_buttons = (V2PaginatorButton("previous_page"), V2PaginatorButton("page_indicator"), V2PaginatorButton("next_page"))
		for button in default_buttons:
			self.add_button(button)


class ChangePageModal(ui.Modal):
	def __init__(self, paginator: V2Paginator):
		super().__init__(title="Go to Page", timeout=60)
		self.paginator = paginator

		self.add_item(ui.InputText(label="Page Number", placeholder=f"Enter page number (1-{self.paginator.last_page + 1})", custom_id="page_number"))

	async def callback(self, interaction: discord.Interaction):
		raw_page_number: str = self.get_item("page_number").value
		if not raw_page_number.isdigit():
			return await interaction.respond("Page number must be a number.", ephemeral=True)

		page_number = int(raw_page_number) - 1

		if page_number > self.paginator.last_page or page_number < 0:
			return await interaction.respond(f"Invalid page! Page must be from 1 to {self.paginator.last_page + 1}", ephemeral=True)

		await self.paginator.goto_page(page_number, interaction=interaction)
