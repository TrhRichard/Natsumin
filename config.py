from dotenv import load_dotenv

import json
import os

load_dotenv(".env")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
BOT_PREFIX = os.getenv("DISCORD_PREFIX", "%")
IS_PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LOGGING_CHANNEL_ID = int(os.getenv("LOGGING_CHANNEL_ID", -1))

EDITOR_IDS: list[int] = json.loads(os.getenv("EDITOR_IDS", "[]"))
GUILD_IDS: list[int] = json.loads(os.getenv("GUILD_IDS", "[]"))
OWNER_IDS: list[int] = json.loads(os.getenv("OWNER_IDS", "[]"))
CONTRIBUTOR_IDS: list[int] = json.loads(os.getenv("CONTRIBUTOR_IDS", "[]"))
REPOSITORY_URL = "https://github.com/TrhRichard/Natsumin"

DISABLED_EXTENSIONS = ()
