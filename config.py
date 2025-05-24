import dataclasses
import datetime
import logging
import discord
import yaml


@dataclasses.dataclass
class Config:
	guild_ids: list[int]
	prefix: str
	owner_ids: list[int]
	contributor_ids: list[int]
	repository_link: str
	DEADLINE: str
	active_season: str
	deadline_footer: str


with open("config.yaml", "r") as file:
	BOT_CONFIG = Config(**yaml.full_load(file))

BASE_EMBED_COLOR = discord.Color.from_rgb(67, 79, 93)
FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")

dt = datetime.datetime.strptime(BOT_CONFIG.DEADLINE, "%B %d, %Y at %H:%M").replace(tzinfo=datetime.timezone.utc)
DEADLINE_TIMESTAMP_INT = int(dt.timestamp())
DEADLINE_TIMESTAMP = datetime.datetime.fromtimestamp(DEADLINE_TIMESTAMP_INT, datetime.UTC)
