from __future__ import annotations

from dataclasses import dataclass, field
from config import GOOGLE_API_KEY
from typing import overload

import aiosqlite
import datetime
import aiofiles
import aiohttp
import re


class PATTERNS:
	ANILIST = r"https://anilist\.co/.+/(\d+)(?:/.*)?"
	MAL = r"https://myanimelist\.net/.+/(\d+)(?:/.*)?"
	STEAM = r"https://store\.steampowered\.com/.+/(\d+)(?:/.*)?"
	NAME_MEDIUM = r"(.*) \((.*)\)"


SHEET_DATA_FIELDS = ["sheets/properties/title", "sheets/data/rowData/values/formattedValue", "sheets/data/rowData/values/hyperlink"]


@dataclass(kw_only=True, slots=True, frozen=True)
class SyncContext:
	missing_steam_ids: set[str] = field(default_factory=set)
	missing_anilist_ids: set[str] = field(default_factory=set)
	missing_mal_ids: set[str] = field(default_factory=set)


@dataclass(kw_only=True, slots=True, frozen=True)
class Cell:
	value: str | None
	hyperlink: str | None = None


@dataclass(kw_only=True, slots=True, frozen=True)
class Row:
	cells: list[Cell | None]

	def get_cell(self, index: int) -> Cell | None:
		"""
		Get a cell at a specific index, returns None if out of range

		:param index: Index to get cell from
		:type index: int
		"""
		try:
			return self.cells[index]
		except IndexError:
			return None

	@overload
	def get_value[T](self, index: int, default: T) -> str | T: ...
	@overload
	def get_value[T](self, index: int, default: None = None) -> str | None: ...
	def get_value[T](self, index: int, default: T | None = None) -> str | T | None:
		"""
		Shortcut for `Row.get_cell(index).value`

		:param index: Index to get cell's value from
		:type index: int
		:param default: Default value if cell is missing
		:type default: T | None
		"""
		cell = self.get_cell(index)

		if cell is None:
			return default

		if cell.value is None:
			return default

		return cell.value

	def get_url(self, index: int) -> str:
		"""
		Shortcut for `Row.get_cell(index).hyperlink`,
		if hyperlink is `None` it then attempts to get a url
		from the value

		:param index: Index to get cell's url from
		:type index: int
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
class Sheet:
	name: str
	rows: list[Row]

	def get_row(self, index: int) -> Row | None:
		"""
		Get a row at a specific index, returns None if out of range

		:param index: Index to get row from
		:type index: int
		"""
		try:
			return self.rows[index]
		except IndexError:
			return None


@dataclass(kw_only=True, slots=True, frozen=True)
class Spreadsheet:
	id: str
	sheets: dict[str, Sheet]

	def get_sheet(self, sheet_name: str) -> Sheet | None:
		"""
		Get the specified sheet by name

		:param sheet_name: Name of the sheet
		:type sheet_name: str
		"""

		return self.sheets.get(sheet_name)


@overload
async def fetch_sheets(spreadsheet_id: str, range: str) -> Sheet: ...
@overload
async def fetch_sheets(spreadsheet_id: str, range: list[str]) -> Spreadsheet: ...
async def fetch_sheets(spreadsheet_id: str, range: str | list[str]) -> Sheet | Spreadsheet:
	raw_range = range
	if isinstance(raw_range, str):
		range = list(range)

	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
			params={"ranges": range, "fields": ",".join(SHEET_DATA_FIELDS), "key": GOOGLE_API_KEY},
		) as response:
			response.raise_for_status()
			spreadsheet_data: dict[str, list[dict[str]]] = await response.json()

	sheets: dict[str, Sheet] = {}

	for raw_sheet in spreadsheet_data["sheets"]:
		rows: list[Row] = []

		sheet_name = raw_sheet["properties"]["title"]
		raw_sheet_rows: list[dict[str]] = raw_sheet["data"][0]["rowData"]

		for raw_row in raw_sheet_rows:
			cells: list[Cell | None] = []

			raw_cells: list[dict[str]] = raw_row["values"]
			for raw_cell in raw_cells:
				if not raw_cell:
					cells.append(Cell(value=None))
					continue

				cells.append(Cell(value=raw_cell.get("formattedValue", ""), hyperlink=raw_cell.get("hyperlink")))

			rows.append(Row(cells=cells))

		sheets[sheet_name] = Sheet(name=sheet_name, rows=rows)

	if isinstance(raw_range, str):
		return sheets.values()[0]

	return Spreadsheet(id=spreadsheet_id, sheets=sheets)


@dataclass(kw_only=True, slots=True, frozen=True)
class AnilistMedia:
	type: str
	description: str

	id: int
	url: str
	format: str
	is_adult: bool = False
	cover_image: str | None
	cover_color: str | None
	mal_id: int | None
	start_date: str | None
	end_date: str | None

	romaji_name: str | None
	english_name: str | None
	native_name: str | None

	episodes: int | None
	chapters: int | None
	volumes: int | None


@dataclass(kw_only=True, slots=True, frozen=True)
class SteamGameData:
	type: str
	id: str
	name: str
	description: str
	developer: str
	publisher: str | None
	release_date: str | None
	header_image: str | None


async def fetch_anilist_data(*, anilist_ids: list[int] | None = None, mal_ids: list[int] | None = None) -> tuple[list[AnilistMedia], bool]:
	async with aiofiles.open("assets/queries/anilist_media_query.graphql", "r") as f:
		query = await f.read()

	variables = {}
	variables["page"] = 1
	if anilist_ids:
		variables["idIn"] = list(anilist_ids)
	elif mal_ids:
		variables["idMalIn"] = list(mal_ids)

	if not variables:
		raise ValueError("Expected anilist_ids OR mal_ids")

	medias: list[AnilistMedia] = []

	rate_limited: bool = False
	try:
		async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
			while True:
				async with session.post("https://graphql.anilist.co", json={"query": query, "variables": variables}) as response:
					response.raise_for_status()
					json_page_data: dict[str] = (await response.json())["data"]["Page"]

				medias_on_page: list[dict[str]] = json_page_data["media"]
				for m_data in medias_on_page:
					raw_start_date = m_data["startDate"]
					if raw_start_date["year"] and raw_start_date["month"] and raw_start_date["day"]:
						start_date = f"{raw_start_date['year']:04}-{raw_start_date['month']:02}-{raw_start_date['day']:02}"
					else:
						start_date = None

					raw_end_date = m_data["endDate"]
					if raw_end_date["year"] and raw_end_date["month"] and raw_end_date["day"]:
						end_date = f"{raw_end_date['year']:04}-{raw_end_date['month']:02}-{raw_end_date['day']:02}"
					else:
						end_date = None

					medias.append(
						AnilistMedia(
							type=m_data["type"],
							description=m_data["description"],
							id=m_data["id"],
							url=m_data["siteUrl"],
							format=str(m_data["format"]).replace("_", " ").upper(),
							is_adult=m_data["isAdult"],
							cover_image=m_data["coverImage"]["extraLarge"],
							cover_color=m_data["coverImage"]["color"],
							mal_id=m_data["idMal"],
							start_date=start_date,
							end_date=end_date,
							romaji_name=m_data["title"]["romaji"],
							english_name=m_data["title"]["english"],
							native_name=m_data["title"]["native"],
							episodes=m_data["episodes"],
							chapters=m_data["chapters"],
							volumes=m_data["volumes"],
						)
					)

				page_info: dict[str] = json_page_data["pageInfo"]
				if not page_info["hasNextPage"]:
					break

				variables["page"] += 1

	except aiohttp.ClientResponseError as err:
		rate_limited = err.status == 429
		if not medias:
			raise

	return medias, rate_limited


async def fetch_steam_data(ids: list[int]) -> tuple[list[SteamGameData], bool]:
	if not ids:
		return

	games: list[SteamGameData] = []
	rate_limited = False

	try:
		async with aiohttp.ClientSession() as session:
			for appid in ids:
				async with session.get(f"https://store.steampowered.com/api/appdetails?appids={appid}") as response:
					response.raise_for_status()
					json_data = await response.json()
					if not json_data[str(appid)]["success"]:
						continue
					game_json_data: dict[str] = (await response.json())[str(appid)]["data"]
					games.append(
						SteamGameData(
							type=game_json_data["type"],
							name=game_json_data["name"],
							description=game_json_data.get("short_description", game_json_data.get("description", "")),
							id=game_json_data["steam_appid"],
							developer=", ".join(game_json_data["developers"]),
							publisher=", ".join(game_json_data["publishers"]) if "publishers" in game_json_data else None,
							release_date=game_json_data["release_date"]["date"] if "release_date" in game_json_data else None,
							header_image=game_json_data.get("header_image"),
						)
					)

	except aiohttp.ClientResponseError:
		if not games:
			raise

	return games, rate_limited


async def sync_media_data(conn: aiosqlite.Connection, ctx: SyncContext):
	if ctx.missing_steam_ids:
		steam_games: list[SteamGameData] = []
		rate_limited = False
		try:
			games_found, rate_limited = await fetch_steam_data(ctx.missing_steam_ids)
			steam_games.extend(games_found)
		except aiohttp.ClientResponseError as err:
			if err.status == 429:
				rate_limited = True

		if steam_games:
			for game in steam_games:
				if str(game.id) in ctx.missing_steam_ids:
					ctx.missing_steam_ids.remove(str(game.id))

				await conn.execute(
					"INSERT OR IGNORE INTO media (type, id, name, description, medium, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
					("steam", game.id, game.name, game.description, game.type.upper(), str(datetime.datetime.now(datetime.UTC))),
				)

				query = """
					INSERT OR IGNORE INTO media_steam (
						id, url, developer, publisher,
						release_date, header_image
					) VALUES (?, ?, ?, ?, ?, ?)
				"""
				await conn.execute(
					query,
					(game.id, f"https://store.steampowered.com/app/{game.id}/", game.developer, game.publisher, game.release_date, game.header_image),
				)

		if ctx.missing_steam_ids and not rate_limited:
			await conn.executemany(
				"INSERT OR IGNORE INTO media_no_match (type, id) VALUES (?, ?)", [("steam", steam_id) for steam_id in ctx.missing_steam_ids]
			)

		await conn.commit()

	if ctx.missing_anilist_ids or ctx.missing_mal_ids:
		was_rate_limited = False
		try:
			total_medias: list[AnilistMedia] = []

			if ctx.missing_anilist_ids:
				anilist_medias, rate_limited = await fetch_anilist_data(anilist_ids=[int(ani_id) for ani_id in ctx.missing_anilist_ids])
				total_medias.extend(anilist_medias)
				was_rate_limited = rate_limited
			if ctx.missing_mal_ids:
				mal_medias, rate_limited = await fetch_anilist_data(mal_ids=[int(mal_id) for mal_id in ctx.missing_mal_ids])
				total_medias.extend(mal_medias)
				was_rate_limited = rate_limited
		except aiohttp.ClientResponseError as err:  # Do not stop syncing if fetching metadata starts to fail
			if err.status == 429:
				was_rate_limited = True

		if total_medias:
			for media in total_medias:
				name_to_use = media.english_name or media.romaji_name or media.native_name

				if media.mal_id and str(media.mal_id) in ctx.missing_mal_ids:
					ctx.missing_mal_ids.remove(str(media.mal_id))

				await conn.execute(
					"INSERT OR IGNORE INTO media (type, id, name, description, medium, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
					("anilist", media.id, name_to_use, media.description, media.type, str(datetime.datetime.now(datetime.UTC))),
				)

				query = """
						INSERT OR IGNORE INTO media_anilist (
							id, url, format, is_adult,
							cover_image, cover_color, mal_id,
							start_date, end_date,
							romaji_name, english_name, native_name,
							episodes, chapters, volumes
						) VALUES (
							?, ?, ?, ?,
							?, ?, ?,
							?, ?,
							?, ?, ?,
							?, ?, ?
						)
					"""
				await conn.execute(
					query,
					(
						media.id,
						media.url,
						media.format,
						media.is_adult,
						media.cover_image,
						media.cover_color,
						media.mal_id,
						media.start_date,
						media.end_date,
						media.romaji_name,
						media.english_name,
						media.native_name,
						media.episodes,
						media.chapters,
						media.volumes,
					),
				)

		if ctx.missing_mal_ids and not was_rate_limited:
			await conn.executemany(
				"INSERT OR IGNORE INTO media_no_match (type, id) VALUES (?, ?)", [("mal", mal_id) for mal_id in ctx.missing_mal_ids]
			)

		await conn.commit()
