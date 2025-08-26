# This script will run a barebones version of the bot in order to populate the Master database.
# This file is esential for the bot to function, without Master.db
# If there is already a Master.db in data/ it will be erased.

from discord.ext import commands
from dotenv import load_dotenv
from async_lru import alru_cache
from typing import TypeVar
import aiosqlite
import aiohttp
import asyncio
import discord
import config
import json
import os

load_dotenv()


def rows_to_columns(rows: list[list]) -> list[list]:
	max_len = max(len(row) for row in rows)  # fix the size issue cause GOOGLE
	padded_rows = [row + [None] * (max_len - len(row)) for row in rows]

	return list(map(list, zip(*padded_rows)))


R = TypeVar("R")


def get_cell(row: list, index: int, default: R = None) -> R:
	try:
		value = row[index]
		if value is None:
			return default
		return value
	except IndexError:
		return default


@alru_cache(ttl=60)
async def fetch_sheet_data() -> dict:
	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{config.BOT_CONFIG.mastersheet_spreadsheet_id}/values:batchGet",
			params={
				"majorDimension": "ROWS",
				"valueRenderOption": "FORMATTED_VALUE",
				"ranges": [
					"Legacy!A2:E830",
					"Contracts Badges (WIP)!D1:AM3",
					"Contracts Badges (WIP)!A4:AM410",
					"Aria's Den Badges!B1:F3",
					"Aria's Den Badges!A4:F55",
				],
				"key": os.getenv("GOOGLE_API_KEY"),
			},
		) as response:
			response.raise_for_status()
			sheet_data = await response.json()
			return sheet_data


bot = commands.Bot(
	command_prefix=commands.when_mentioned,
	status=discord.Status.do_not_disturb,
	intents=discord.Intents.all(),
	case_insensitive=True,
	allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
)


@bot.event
async def on_ready():
	os.system("cls" if os.name == "nt" else "clear")
	print(f"Logged in as {bot.user.name}#{bot.user.discriminator}!")

	try:
		_anicord = bot.get_guild(994071728017899600) or await bot.fetch_guild(994071728017899600)
	except discord.HTTPException:
		print("Could not get AES guild, script ending.")
		return await bot.close()

	# guild_members = await anicord.fetch_members(limit=None).flatten()


async def setup_database(delete_if_exists: bool = False):
	if delete_if_exists:
		if os.path.exists("data/master.db"):
			os.remove("data/master.db")

	async with aiosqlite.connect("data/master.db") as c:
		with open("contracts/Master.sql", "r") as sql_file:
			sql_script = sql_file.read()
		await c.executescript(sql_script)
		await c.commit()


async def main():
	await setup_database(True)

	sheet_data = await fetch_sheet_data()

	value_ranges: list[dict] = sheet_data["valueRanges"]

	badges_to_add: list[dict[str]] = []

	badges_sheet = value_ranges[1]
	aria_badges_sheet = value_ranges[3]

	for column in rows_to_columns(badges_sheet.get("values")):
		split_name = get_cell(column, 0, "").split("\n", 1)
		badges_to_add.append(
			{
				"name": split_name[0].removesuffix("*").strip(),
				"description": split_name[1].strip(),
				"artist": get_cell(column, 2, "").strip(),
				"url": "",
				"type": "contracts",
			}
		)

	for column in rows_to_columns(aria_badges_sheet.get("values")):
		badges_to_add.append(
			{"name": get_cell(column, 0, "").strip(), "description": "", "artist": get_cell(column, 2, "").strip(), "url": "", "type": "aria"}
		)

	async with aiosqlite.connect("data/master.db") as c:
		await c.executemany(
			"INSERT INTO badges (name, description, artist, url, type) VALUES (?, ?, ?, ?, ?);",
			[(badge["name"], badge["description"], badge["artist"], badge["url"], badge["type"]) for badge in badges_to_add],
		)
		await c.commit()

	return  # disable bot for now

	try:
		await bot.start(os.getenv("DISCORD_TOKEN"))
	except KeyboardInterrupt:
		await bot.close()


asyncio.run(main())
