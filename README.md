# Natsumin

A Discord bot for the Anicord Event Server, held together by hopes and dreams.

Maintained by [Richard](https://github.com/TrhRichard).

## Installation

1. **Clone the repository:**

```bash
git clone https://github.com/TrhRichard/Natsumin
cd Natsumin
```

2. **Install Dependencies:**

```bash
uv sync
```

3. **Initialize Master Database**:

```bash
uv run -m scripts.setup_masterdb
```

### Dependencies

-   [uv](https://docs.astral.sh/uv/): An extremely fast Python package and project manager, written in Rust.

## Configuration

Before being able to run the bot or any script you will need to create a `.env` file with the following content:

```toml
DISCORD_TOKEN = "DISCORD-TOKEN-HERE"
GOOGLE_API_KEY = "GOOGLE-API-KEY-HERE" # Required for accessing Google Sheets data
```

## License

Natsumin is licensed under [GNU GPLv3](./LICENSE).
