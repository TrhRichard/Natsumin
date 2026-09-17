# Natsumin

A Discord bot for the Anicord Event Server, held together by hopes and dreams.

## Configuration

Before being able to run the bot or any of the scripts you will need to create a `.env` file with the following content:

```toml
DISCORD_TOKEN = "DISCORD-TOKEN-HERE"
DISCORD_PREFIX = "%"
PRODUCTION = true # or false
LOGGING_CHANNEL_ID = -1 # channel id where errors can go into

EDITOR_IDS = [] # List of discord user ids that basically can access database modifying commands
GUILD_IDS = [] # List of discord server ids where most slash commands sync into
OWNER_IDS = []
CONTRIBUTOR_IDS = []

GOOGLE_API_KEY = "GOOGLE-API-KEY-HERE" # Required for Google Sheets API
```

## License

Natsumin is licensed under [GNU GPLv3](./LICENSE).
