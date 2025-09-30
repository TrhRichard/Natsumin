# Natsumin

The Discord bot for the Anicord Event Server, held together by hopes and dreams.

Maintained by [Richard](https://github.com/TrhRichard).

## Setup

1. Clone this project
1. Install the packages from requirements.txt in a new virtual enviroment.
1. Activate newly made enviroment if you haven't already.
1. Create a `.env` file and add this in it:

```env
DISCORD_TOKEN = "DISCORD-TOKEN-HERE"
GOOGLE_API_KEY = "GOOGLE-API-KEY-HERE" # Required for fetching data from the sheet, only needs google sheets api
```

5. Run `py -m scripts.setup_masterdb` in the terminal to setup the master database.

You should now be ready to start the bot if you did everything right.
If for whatever reason it's not working either figure it out yourself
or contact me on Discord.

## License

Natsumin is licensed under [GNU GPLv3](./LICENSE).
