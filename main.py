from __future__ import annotations

from config import DISCORD_TOKEN
from internal.base.bot import NatsuBot
from pathlib import Path


def main():
	logs_path = Path("logs/")
	data_path = Path("data/")

	logs_path.mkdir(exist_ok=True, parents=True)
	data_path.mkdir(exist_ok=True, parents=True)

	bot = NatsuBot()

	bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
	main()
