from __future__ import annotations
from dataclasses import dataclass, fields
import datetime
import aiofiles
import discord
import yaml

__all__ = ["config"]


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


with open("config.yaml") as f:
	config: BotConfig = BotConfig(**yaml.safe_load(f))


def get_master_db():
	from contracts import MasterDB

	return MasterDB.get_database()
