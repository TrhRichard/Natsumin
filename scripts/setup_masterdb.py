# This script will run a barebones version of the bot in order to create the initial version of the Master database.
# The bot itself will update the master database every now and then but it cannot create it for my sanity since python stinks.
# If there is already a Master.db in data/ it will be erased.

# this entire script sucks ass ngl but it works kinda? so im not bothered to fix it

from typing import TypeVar, Callable
from discord.ext import commands
from dotenv import load_dotenv
from async_lru import alru_cache
import aiosqlite
import aiohttp
import asyncio
import discord
import config
import os

load_dotenv()


def rows_to_columns(rows: list[list]) -> list[list]:
	max_len = max(len(row) for row in rows)  # fix the size issue cause GOOGLE
	padded_rows = [row + [None] * (max_len - len(row)) for row in rows]

	return list(map(list, zip(*padded_rows)))


T = TypeVar("T")


def get_cell(row: list, index: int, default: T = None, return_type: Callable[[any], T] = None) -> T:
	try:
		value = row[index]
		if value is None:
			return default
		if return_type is not None:
			try:
				return return_type(value)
			except (ValueError, TypeError):
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
		anicord = bot.get_guild(994071728017899600) or await bot.fetch_guild(994071728017899600)
	except discord.HTTPException:
		print("Could not get AES guild, script ending.")
		return await bot.close()

	guild_members = await anicord.fetch_members(limit=None).flatten()
	name_members: dict[str, discord.Member] = {m.name: m for m in guild_members}

	async with aiosqlite.connect("data/master.db") as db:
		db.row_factory = aiosqlite.Row
		async with db.execute("SELECT * FROM users") as cursor:
			users = await cursor.fetchall()
			for user in users:
				if member := name_members.get(user["username"]):
					print(member)
					await db.execute("UPDATE users SET discord_id = ? WHERE username = ?", (member.id, user["username"]))

		await db.commit()


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
	contracts_badges: list[dict[str]] = []
	aria_badges: list[dict[str]] = []

	badges_sheet = value_ranges[1]
	aria_badges_sheet = value_ranges[3]

	for column in rows_to_columns(badges_sheet.get("values")):
		split_name = get_cell(column, 0, "").split("\n", 1)
		badge_data = {
			"name": split_name[0].removesuffix("*").strip(),
			"description": split_name[1].strip(),
			"artist": get_cell(column, 2, "").strip(),
			"url": "",
			"type": "contracts",
			"id": None,
		}
		badges_to_add.append(badge_data)
		contracts_badges.append(badge_data)

	for column in rows_to_columns(aria_badges_sheet.get("values")):
		badge_data = {
			"name": get_cell(column, 0, "").strip(),
			"description": "",
			"artist": get_cell(column, 2, "").strip(),
			"url": "",
			"type": "aria",
		}
		badges_to_add.append(badge_data)
		aria_badges.append(badge_data)

	async with aiosqlite.connect("data/master.db") as db:
		for badge in badges_to_add:
			async with db.execute(
				"INSERT INTO badges (name, description, artist, url, type) VALUES (?, ?, ?, ?, ?);",
				(badge["name"], badge["description"], badge["artist"], badge["url"], badge["type"]),
			) as cursor:
				badge_id = cursor.lastrowid
				badge["id"] = badge_id
		await db.commit()

	users_to_add: list[dict[str]] = []

	legacy_sheet = value_ranges[0]
	for row in legacy_sheet.get("values"):
		name: str = get_cell(row, 3, None)
		if name is None:
			continue
		users_to_add.append(
			{
				"username": name.strip().lower(),
				"discord_id": None,
				"rep": get_cell(row, 0, "UNKNOWN REP"),
				"gen": get_cell(row, 1, -1, int),
				"exp": get_cell(row, 4, 0, int),
				"id": None,
			}
		)

	users_dict: dict[str, dict[str]] = {}

	async with aiosqlite.connect("data/master.db") as db:
		for user in users_to_add:
			async with db.execute("INSERT INTO users (username, rep, gen) VALUES (?, ?, ?);", (user["username"], user["rep"], user["gen"])) as cursor:
				user_id = cursor.lastrowid
				user["id"] = user_id
				users_dict[user["username"]] = user
				await db.execute("INSERT INTO legacy_leaderboard (user_id, exp) VALUES (?, ?)", (user_id, user["exp"]))

		await db.commit()

	user_badges_sheet = value_ranges[2]
	aria_user_badges_sheet = value_ranges[4]

	async with aiosqlite.connect("data/master.db") as db:
		for row in user_badges_sheet.get("values"):
			name = get_cell(row, 1, None, str).strip().lower()
			user = users_dict.get(name)
			user_id: int = None
			if not user:
				continue
			else:
				user_id = user["id"]

			badges_status: list[str] = row[3:]
			i = -1
			for badge in contracts_badges:
				i += 1
				status = get_cell(badges_status, i, "")
				if status.strip() == "COMPLETE":
					await db.execute("INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)", (user_id, badge["id"]))

		for row in aria_user_badges_sheet.get("values"):
			name = get_cell(row, 0, None, str).strip().lower()
			user = users_dict.get(name)
			user_id: int = None
			if not user:
				async with db.execute("INSERT INTO users (username) VALUES (?)", (name,)) as cursor:
					user_id = cursor.lastrowid
			else:
				user_id = user["id"]

			badges_status: list[str] = row[1:]
			i = -1
			for badge in aria_badges:
				i += 1
				status = get_cell(badges_status, i, "")
				if status.strip() in ["COMPLETE", "100%"]:
					await db.execute("INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)", (user_id, badge["id"]))

		await db.commit()

	return

	try:
		await bot.start(os.getenv("DEV_DISCORD_TOKEN"))
	except KeyboardInterrupt:
		await bot.close()


asyncio.run(main())
