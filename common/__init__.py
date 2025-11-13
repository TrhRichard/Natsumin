from __future__ import annotations
from dataclasses import dataclass, fields
import datetime
import aiofiles
import discord
import yaml
import re

__all__ = ["config", "STRINGS"]

CHOICE_PATTERN = r"%<\((?P<var_to_check>\w+):(?P<is_true>.*?)\|(?P<is_false>.*?)\)>"


@dataclass
class BotConfig:
	guild_ids: list[int]
	prefix: str
	owner_ids: list[int]
	contributor_ids: list[int]
	repository_link: str
	deadline_timestamp: int
	active_season: str
	deadline_footer: str
	mastersheet_spreadsheet_id: int
	embed_color: list[int]
	syncing_enabled: bool

	@property
	def deadline_datetime(self) -> datetime.datetime:
		return datetime.datetime.fromtimestamp(self.deadline_timestamp, tz=datetime.UTC)

	@property
	def base_embed_color(self) -> discord.Colour:
		return discord.Colour.from_rgb(self.embed_color[0], self.embed_color[1], self.embed_color[2])

	async def update_from_file(self, path: str = "config.yaml"):
		async with aiofiles.open(path, "r", encoding="utf-8") as f:
			content = await f.read()

		data: dict[str] = yaml.safe_load(content)

		for f in fields(self):
			if f.name in data:
				setattr(self, f.name, data[f.name])

	@classmethod
	async def from_file(cls, path: str = "config.yaml"):
		async with aiofiles.open(path, "r", encoding="utf-8") as f:
			content = await f.read()

		data: dict[str] = yaml.safe_load(content)
		return cls(**data)


@dataclass
class BotStrings:
	data: dict[str]

	def get(self, path: str, **kwargs) -> str:
		level: dict[str] = self.data
		for part in (part.strip() for part in path.split(".") if part.strip()):
			value = level.get(part)
			if value is None:
				raise ValueError(f"Could not find string at {path}")
			elif isinstance(value, dict):
				level = value
				continue
			elif isinstance(value, str):
				return self._format_string(value, **kwargs)

	async def update_from_file(self, path: str = "strings.yml"):
		async with aiofiles.open(path, "r", encoding="utf-8") as f:
			content = await f.read()

		self.data = yaml.safe_load(content)

	@classmethod
	async def from_file(cls, path: str = "strings.yml"):
		async with aiofiles.open(path, "r", encoding="utf-8") as f:
			content = await f.read()

		data: dict[str] = yaml.safe_load(content)
		return cls(data=data)

	def _format_string(self, string: str, **kwargs) -> str:
		def replacer(match: re.Match) -> str:
			var_to_check: str = match.group("var_to_check")
			is_true: str = match.group("is_true")
			is_false: str = match.group("is_false")

			if var_to_check in kwargs:
				return is_true if kwargs[var_to_check] else is_false
			else:
				return match.group(0).replace("{", "{{").replace("}", "}}")

		choiced_string = re.sub(CHOICE_PATTERN, replacer, string)

		formatted_string = choiced_string
		try:
			formatted_string = choiced_string.format(**kwargs)
		except KeyError:
			pass

		return formatted_string

	def __call__(self, path: str, **kwargs) -> str:
		return self.get(path, **kwargs)


with open("strings.yml", "r", encoding="utf-8") as f:
	STRINGS: BotStrings = BotStrings(data=yaml.safe_load(f))

with open("config.yml", "r", encoding="utf-8") as f:
	config: BotConfig = BotConfig(**yaml.safe_load(f))


def get_master_db():
	from contracts import MasterDB

	return MasterDB.get_database()
