from .contracts import *  # noqa: F403
from .rep import get_rep, RepName  # noqa: F401
from dataclasses import dataclass, fields
import aiofiles
import datetime
import asyncio
import logging
import discord
import math
import yaml


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


def get_percentage(num: float, total: float) -> int:
	return math.floor(100 * float(num) / float(total))


def is_season_ongoing() -> bool:
	current_datetime = datetime.datetime.now(datetime.UTC)
	difference = config.deadline_datetime - current_datetime
	difference_seconds = max(difference.total_seconds(), 0)
	return difference_seconds > 0


config: BotConfig = asyncio.run(BotConfig.from_file("config.yaml"))

FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
