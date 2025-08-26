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
	mastersheet_spreadsheet_id: int


BOT_CONFIG: Config = None
DEADLINE_TIMESTAMP_INT: int = None
DEADLINE_TIMESTAMP: datetime.datetime = None


def sync_config_to_local():
	global BOT_CONFIG, DEADLINE_TIMESTAMP_INT, DEADLINE_TIMESTAMP  # these are constant case but like its my code so cry about it if u dont like it
	"""Sync's the in-memory config to the current one in disk"""
	with open("config.yaml", "r") as file:
		BOT_CONFIG = Config(**yaml.full_load(file))

	dt = datetime.datetime.strptime(BOT_CONFIG.DEADLINE, "%B %d, %Y at %H:%M").replace(tzinfo=datetime.timezone.utc)
	DEADLINE_TIMESTAMP_INT = int(dt.timestamp())
	DEADLINE_TIMESTAMP = datetime.datetime.fromtimestamp(DEADLINE_TIMESTAMP_INT, datetime.UTC)


BASE_EMBED_COLOR = discord.Color.from_rgb(67, 79, 93)
FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")


sync_config_to_local()
