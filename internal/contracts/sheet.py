from __future__ import annotations

from dataclasses import dataclass
from config import GOOGLE_API_KEY
from typing import overload

import aiohttp
import re


class PATTERNS:
	ANILIST = r"https://anilist\.co/.+/(\d+)(?:/.*)?"
	MAL = r"https://myanimelist\.net/.+/(\d+)(?:/.*)?"
	STEAM = r"https://store\.steampowered\.com/.+/(\d+)(?:/.*)?"
	NAME_MEDIUM = r"(.*) \((.*)\)"


SHEET_DATA_FIELDS = ["sheets/properties/title", "sheets/data/rowData/values/formattedValue", "sheets/data/rowData/values/hyperlink"]


def column_to_index(col: str) -> int:
	col = col.upper()
	result = 0

	for char in col:
		result = result * 26 + (ord(char) - ord("A") + 1)

	return result - 1


def cell_to_indices(cell: str) -> tuple[int, int]:
	match = re.match(r"([A-Za-z]+)(\d+)", cell)
	col, row = match.groups()

	col_index = column_to_index(col)
	row_index = int(row) - 1

	return row_index, col_index


@dataclass(kw_only=True, slots=True, frozen=True)
class Cell:
	value: str | None
	hyperlink: str | None = None


@dataclass(kw_only=True, slots=True, frozen=True)
class Row:
	cells: list[Cell | None]

	def get_cell(self, index: int | str) -> Cell | None:
		"""
		Get a cell at a specific index, returns None if out of range

		:param index: Index to get cell from
		:type index: int | str
		"""
		try:
			if isinstance(index, str):
				index = column_to_index(index)

			return self.cells[index]
		except IndexError:
			return None

	@overload
	def get_value[T](self, index: int | str, default: T) -> str | T: ...
	@overload
	def get_value[T](self, index: int | str, default: None = None) -> str | None: ...
	def get_value[T](self, index: int | str, default: T | None = None) -> str | T | None:
		"""
		Shortcut for `Row.get_cell(index).value`

		:param index: Index to get cell's value from
		:type index: int | str
		:param default: Default value if cell is missing
		:type default: T | None
		"""
		cell = self.get_cell(index)

		if cell is None:
			return default

		if cell.value is None:
			return default

		return cell.value

	def get_url(self, index: int | str) -> str:
		"""
		Shortcut for `Row.get_cell(index).hyperlink`,
		if hyperlink is `None` it then attempts to get a url
		from the value

		:param index: Index to get cell's url from
		:type index: int | str
		:return: URL found, empty string if nothing is found.
		:rtype: str
		"""

		cell = self.get_cell(index)

		if cell is None:
			return ""

		if cell.hyperlink:
			return cell.hyperlink

		if cell.value is None:
			return ""

		match = re.search(r"(https?:\/\/[^\s]+)", cell.value)
		return match.group(0) if match else ""


@dataclass(kw_only=True, slots=True, frozen=True)
class SheetBlock:
	name: str
	rows: list[Row]

	def get_row(self, index: int) -> Row | None:
		"""
		Get a row at a specific index, returns `None` if out of range

		:param index: Index to get row from
		:type index: int
		"""
		try:
			return self.rows[index]
		except IndexError:
			return None

	def get_cell(self, cell: str) -> Cell | None:
		"""
		Get a cell at a specific position <br>
		Keep in mind that
		something like `A2` in a sheet of range `A2:B4` would actually be
		`A1`

		:param cell: Position of the cell
		:type cell: str
		"""
		row_idx, col_idx = cell_to_indices(cell)

		row = self.get_row(row_idx)
		if not row:
			return None

		column = row.get_cell(col_idx)
		return column


@dataclass(kw_only=True, slots=True, frozen=True)
class Sheet:
	name: str
	blocks: list[SheetBlock]

	def get_row(self, index: int, *, block: int = 0) -> Row | None:
		"""
		Shortcut for `Sheet.blocks[0].get_row()`
		"""
		return self.blocks[block].get_row(index)

	def get_cell(self, cell: str, *, block: int = 0) -> Cell | None:
		"""
		Shortcut for `Sheet.blocks[0].get_cell()`
		"""
		return self.blocks[block].get_cell(cell)


@dataclass(kw_only=True, slots=True, frozen=True)
class Spreadsheet:
	id: str
	sheets: dict[str, Sheet]

	@overload
	def get_sheet(self, sheet_name: str, *, block: int | None = ...) -> SheetBlock | None: ...
	def get_sheet(self, sheet_name: str, *, block: int | None = None) -> Sheet | None:
		"""
		Get the specified sheet by name

		:param sheet_name: Name of the sheet
		:type sheet_name: str
		"""

		if block is not None:
			sheet = self.sheets.get(sheet_name)
			if sheet:
				return sheet.blocks[block]
		else:
			return self.sheets.get(sheet_name)


@overload
async def fetch_sheets(spreadsheet_id: str, range: str) -> SheetBlock: ...
@overload
async def fetch_sheets(spreadsheet_id: str, range: list[str]) -> Spreadsheet: ...
async def fetch_sheets(spreadsheet_id: str, range: str | list[str]) -> SheetBlock | Spreadsheet:
	raw_range = range
	if isinstance(raw_range, str):
		range = [raw_range]

	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
			params={"ranges": range, "fields": ",".join(SHEET_DATA_FIELDS), "key": GOOGLE_API_KEY},
		) as response:
			response.raise_for_status()
			spreadsheet_data: dict[str, list[dict[str]]] = await response.json()

	sheets: dict[str, Sheet] = {}

	for raw_sheet in spreadsheet_data["sheets"]:
		blocks: list[SheetBlock] = []

		sheet_name = raw_sheet["properties"]["title"]

		for block in raw_sheet["data"]:
			rows: list[Row] = []
			block_rows: list[dict[str]] = block["rowData"]

			for raw_row in block_rows:
				cells: list[Cell] = []

				if len(raw_row) != 0:
					raw_cells: list[dict[str]] = raw_row["values"]
					for raw_cell in raw_cells:
						if not raw_cell:
							cells.append(Cell(value=None))
							continue

						cells.append(Cell(value=raw_cell.get("formattedValue", ""), hyperlink=raw_cell.get("hyperlink")))

				rows.append(Row(cells=cells))

			blocks.append(SheetBlock(name=sheet_name, rows=rows))

		sheets[sheet_name] = Sheet(name=sheet_name, blocks=blocks)

	if isinstance(raw_range, str):
		sheet: Sheet = tuple(sheets.values())[0]
		return sheet.blocks[0]

	return Spreadsheet(id=spreadsheet_id, sheets=sheets)
