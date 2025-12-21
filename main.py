from __future__ import annotations

from config import DISCORD_TOKEN, DEV_DISCORD_TOKEN
from internal.base.bot import NatsuminBot
from pathlib import Path

import argparse


def main(*, production: bool):
	logs_path = Path("logs/")
	data_path = Path("data/")

	if not logs_path.is_dir():
		logs_path.mkdir(exist_ok=True, parents=True)
	if not data_path.is_dir():
		data_path.mkdir(exist_ok=True, parents=True)

	if DISCORD_TOKEN is None:
		raise ValueError("Discord Bot Token missing!")

	is_production = production or DEV_DISCORD_TOKEN is None

	bot = NatsuminBot(is_production)

	bot.run(DISCORD_TOKEN if is_production else DEV_DISCORD_TOKEN)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--production", action="store_true")
	args = parser.parse_args()

	main(production=args.production)
