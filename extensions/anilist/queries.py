from dataclasses import dataclass
from typing import Literal

import datetime
import aiohttp
import re

ANILIST_LINK_PATTERN = re.compile(r"anilist\.co\/\w+\/(\d+)")

MEDIA_SEARCH_QUERY = """
query MediaSearch($search: String, $type: MediaType, $media_id: Int, $format: MediaFormat, $format_not: MediaFormat) {
  Media(search: $search, type: $type, id: $media_id, format: $format, format_not: $format_not) {
    title {
      romaji
      native
      english
    }
    id
    type
    description
    startDate {
      day
      month
      year
    }
    endDate {
      day
      month
      year
    }
    studios(isMain: true) {
      nodes {
        name
        siteUrl
      }
    }
    format
    isAdult
    coverImage {
      color
      extraLarge
    }
    genres
    status(version: 2)
    countryOfOrigin
    averageScore
    source(version: 3)
    siteUrl
    chapters
    episodes
  }
}
"""


CHARACTER_SEARCH_QUERY = """
query CharacterSearch($search: String, $character_id: Int)  {
  Character(search: $search, id: $character_id) {
    name {
      full
      first
      last
      native
    }
    id
    description
    image {
      large
    }
    gender
    age
    siteUrl
  }
}
"""

type MediaType = Literal["ANIME", "MANGA"]
type MediaFormat = Literal["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC", "MANGA", "NOVEL", "ONE_SHOT"]
type MediaStatus = Literal["FINISHED", "RELEASING", "NOT_YET_RELEASED", "CANCELLED", "HIATUS"]
type MediaSource = Literal[
	"ORIGINAL",
	"MANGA",
	"LIGHT_NOVEL",
	"VISUAL_NOVEL",
	"VIDEO_GAME",
	"OTHER",
	"NOVEL",
	"DOUJINSHI",
	"ANIME",
	"WEB_NOVEL",
	"LIVE_ACTION",
	"GAME",
	"COMIC",
	"MULTIMEDIA_PROJECT",
	"PICTURE_BOOK",
]

MEDIA_FORMAT_DISPLAYED: dict[MediaFormat, str] = {
	"TV_SHORT": "TV Short",
	"MOVIE": "Movie",
	"SPECIAL": "Special",
	"MUSIC": "Music",
	"MANGA": "Manga",
	"NOVEL": "Novel",
	"ONE_SHOT": "One Shot",
}


@dataclass(slots=True, frozen=True, kw_only=True)
class MediaTitle:
	romaji: str
	native: str
	english: str | None

	@staticmethod
	def from_dict(data: dict):
		return MediaTitle(romaji=data["romaji"], native=data["native"], english=data["english"])

	@property
	def displayed_title(self):
		return self.english if self.english else (self.romaji if self.romaji else self.native)


@dataclass(slots=True, frozen=True, kw_only=True)
class Studio:
	name: str
	site_url: str

	@staticmethod
	def from_dict(data: dict):
		return Studio(name=data["name"], site_url=data["siteUrl"])


@dataclass(slots=True, frozen=True, kw_only=True)
class StudioConnection:
	nodes: list[Studio]

	@staticmethod
	def from_dict(data: dict):
		return StudioConnection(nodes=[Studio.from_dict(d) for d in data["nodes"]])


@dataclass(slots=True, frozen=True, kw_only=True)
class MediaCoverImage:
	color: str | None
	extra_large: str

	@staticmethod
	def from_dict(data: dict):
		return MediaCoverImage(color=data["color"], extra_large=data["extraLarge"])


@dataclass(slots=True, frozen=True, kw_only=True)
class Media:
	title: MediaTitle
	id: int
	type: MediaType
	description: str
	start_date: datetime.date | None
	end_date: datetime.date | None
	studios: StudioConnection
	format: MediaFormat
	is_adult: bool
	cover_image: MediaCoverImage
	genres: list[str]
	status: MediaStatus
	country_of_origin: str
	average_score: int
	source: MediaSource
	site_url: str
	chapters: int | None
	episodes: int | None

	@staticmethod
	def from_dict(data: dict):
		return Media(
			title=MediaTitle.from_dict(data["title"]),
			id=data["id"],
			type=data["type"],
			description=sanitize_description(data["description"]),
			start_date=datetime.date(data["startDate"]["year"], data["startDate"]["month"], data["startDate"]["day"])
			if data["startDate"]["year"] is not None
			else None,
			end_date=datetime.date(data["endDate"]["year"], data["endDate"]["month"], data["endDate"]["day"])
			if data["endDate"]["year"] is not None
			else None,
			studios=StudioConnection.from_dict(data["studios"]),
			format=data["format"],
			is_adult=data["isAdult"],
			cover_image=MediaCoverImage.from_dict(data["coverImage"]),
			genres=data["genres"],
			status=data["status"],
			country_of_origin=data["countryOfOrigin"],
			average_score=data["averageScore"],
			source=data["source"],
			site_url=data["siteUrl"],
			chapters=data["chapters"],
			episodes=data["episodes"],
		)

	@property
	def displayed_format(self):
		return MEDIA_FORMAT_DISPLAYED.get(self.format, self.format)

	@property
	def displayed_status(self):
		return format_media_thing(self.status)

	@property
	def displayed_source(self):
		return format_media_thing(self.source)

	@property
	def displayed_type(self):
		return format_media_thing(self.type)


@dataclass(slots=True, frozen=True, kw_only=True)
class CharacterName:
	full: str
	first: str
	last: str | None
	native: str

	@staticmethod
	def from_dict(data: dict):
		return CharacterName(full=data["full"], first=data["first"], last=data["last"], native=data["native"])

	@property
	def displayed_name(self):
		return (f"{self.last if self.last else ''} {self.first if self.first else ''}".strip() or self.full) or self.native


@dataclass(slots=True, frozen=True, kw_only=True)
class CharacterImage:
	large: str

	@staticmethod
	def from_dict(data: dict):
		return CharacterImage(large=data["large"])


@dataclass(slots=True, frozen=True, kw_only=True)
class Character:
	name: CharacterName
	id: int
	description: str
	image: CharacterImage
	gender: str
	age: str
	site_url: str

	@staticmethod
	def from_dict(data: dict):
		return Character(
			name=CharacterName.from_dict(data["name"]),
			id=data["id"],
			description=sanitize_description(data["description"]),
			image=CharacterImage.from_dict(data["image"]),
			gender=data["gender"],
			age=data["age"],
			site_url=data["siteUrl"],
		)


def sanitize_description(description: str) -> str:
	return (
		description.replace("<br>", "")
		.replace("\\n", "\n")
		.replace("</i>", "*")
		.replace("<i>", "*")
		.replace("</b>", "**")
		.replace("<b>", "**")
		.replace("&mdash;", "—")
	)


def format_media_thing(thing: MediaType | MediaFormat | MediaSource | MediaStatus) -> str:
	return thing.replace("_", " ").title()


async def search_media(search: str | int, media_type: Literal["ANIME", "MANGA", "LIGHT_NOVEL"] = "ANIME") -> Media:
	link_match: re.Match[str] | None = ANILIST_LINK_PATTERN.search(search)
	if link_match is not None:
		print(link_match, search)
		search = int(link_match.group(1))
	elif search.lower().startswith("id") and search.lower().removeprefix("id").isnumeric():
		search = int(search.lower().removeprefix("id"))

	variables = {"search": search, "type": media_type}
	if media_type == "LIGHT_NOVEL":
		variables["type"] = "MANGA"
		variables["format"] = "NOVEL"
	elif media_type == "MANGA":
		variables["format_not"] = "NOVEL"

	if isinstance(search, int):
		variables.pop("search")
		variables["media_id"] = search

	async with aiohttp.ClientSession() as session:
		async with session.post("https://graphql.anilist.co", json={"query": MEDIA_SEARCH_QUERY, "variables": variables}) as resp:
			if not resp.ok:
				return None
			if resp.status != 200:
				return None

			json_body = await resp.json()
			return Media.from_dict(json_body["data"]["Media"])


async def search_character(search: str | int) -> Character:
	link_match: re.Match[str] | None = ANILIST_LINK_PATTERN.search(search)
	if link_match is not None:
		search = int(link_match.group(1))
	elif search.lower().startswith("id") and search.lower().removeprefix("id").isnumeric():
		search = int(search.lower().removeprefix("id"))

	variables = {"search": search}

	if isinstance(search, int):
		variables.pop("search")
		variables["character_id"] = search

	async with aiohttp.ClientSession() as session:
		async with session.post("https://graphql.anilist.co", json={"query": CHARACTER_SEARCH_QUERY, "variables": variables}) as resp:
			if not resp.ok:
				return None
			if resp.status != 200:
				return None

			json_body = await resp.json()
			return Character.from_dict(json_body["data"]["Character"])
