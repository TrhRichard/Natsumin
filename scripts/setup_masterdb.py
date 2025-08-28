# This script will run a barebones version of the bot in order to create the initial version of the Master database.
# The bot itself will update the master database every now and then but it cannot create it for my sanity since python stinks.
# If there is already a Master.db in data/ it will be erased.

# this entire script sucks ass ngl but it works kinda? so im not bothered to fix it

from typing import TypeVar, Callable
from discord.ext import commands
from dotenv import load_dotenv
from async_lru import alru_cache
from utils.rep import get_rep
from thefuzz import process
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
	print(f"Bot online: {bot.user.name}#{bot.user.discriminator}")
	try:
		anicord = bot.get_guild(994071728017899600) or await bot.fetch_guild(994071728017899600)
	except discord.HTTPException:
		print("It seems the bot is not in Anicord, cannot continue to set the discord id on users.")
		return await bot.close()  ## appears to not be a good idea to close it here for some reason whatever

	print("Now requesting all guild members from anicord, this may take a while...")
	guild_members = await anicord.fetch_members(limit=None).flatten()
	print(f"Received {len(guild_members)} members!")
	name_members: dict[str, discord.Member] = {m.name: m for m in guild_members}
	member_names: dict[discord.Member, str] = {m: m.name for m in guild_members}  # let me cook

	async with aiosqlite.connect("data/master.db") as db:
		db.row_factory = aiosqlite.Row
		async with db.execute("SELECT * FROM users WHERE discord_id IS NULL") as cursor:
			users = await cursor.fetchall()
			for user in users:
				username: str = user["username"]
				if member := name_members.get(username):
					await db.execute("UPDATE OR IGNORE users SET discord_id = ? WHERE id = ?", (member.id, user["id"]))
				else:
					fuzzy_results: list[tuple[str, int, discord.Member]] = process.extract(username, member_names, limit=1)
					if not fuzzy_results:
						print(f"Could not find a discord id for {username}, skipping...")
						continue

					_, confidence, member = fuzzy_results[0]
					if confidence >= 90:
						if username == member.name:
							await db.execute("UPDATE OR IGNORE users SET discord_id = ? WHERE id = ?", (member.id, user["id"]))
						else:
							print(f"It appears that {username}'s actual name is {member.name}, updating that as well")
							await db.execute(
								"UPDATE OR IGNORE users SET discord_id = ?, username = ? WHERE id = ?", (member.id, member.name, user["id"])
							)

		await db.commit()

	print("master.db Setup complete!")
	await bot.close()


async def setup_database(delete_if_exists: bool = False):
	if delete_if_exists:
		if os.path.exists("data/master.db"):
			os.remove("data/master.db")

	async with aiosqlite.connect("data/master.db") as c:
		with open("contracts/Master.sql", "r") as sql_file:
			sql_script = sql_file.read()
		await c.executescript(sql_script)
		await c.commit()


def fuzzy_search_user(user_list: list[dict[str]], name: str) -> dict[str] | None:
	username_list = [u.get("username") for u in user_list]
	fuzzy_results: list[tuple[str, int]] = process.extract(name.lower(), username_list, limit=1)
	if fuzzy_results:
		username_found, confidence = fuzzy_results[0]
		if confidence >= 90:
			return user_list[username_list.index(username_found)]
	return None


async def main():
	await setup_database(True)

	sheet_data = await fetch_sheet_data()

	value_ranges: list[dict] = sheet_data["valueRanges"]

	badges_to_add: list[dict[str]] = []

	badges_sheet = value_ranges[1]
	aria_badges_sheet = value_ranges[3]

	print("Adding badges...")

	for index, column in enumerate(rows_to_columns(badges_sheet.get("values"))):
		split_name = get_cell(column, 0, "").split("\n", 1)
		badge_data = {
			"name": split_name[0].removesuffix("*").strip(),
			"description": split_name[1].strip(),
			"artist": get_cell(column, 2, "").strip(),
			"url": "",
			"type": "contracts",
			"id": None,
			"_index": index,
		}
		badges_to_add.append(badge_data)

	for index, column in enumerate(rows_to_columns(aria_badges_sheet.get("values"))):
		badge_data = {
			"name": get_cell(column, 0, "").strip(),
			"description": "",
			"artist": get_cell(column, 2, "").strip(),
			"url": "",
			"type": "aria",
			"id": None,
			"_index": index,
		}
		badges_to_add.append(badge_data)

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
	usernames_found: set[str] = set()

	print("Adding users...")

	legacy_sheet = value_ranges[0]
	for row in legacy_sheet.get("values"):
		name: str = get_cell(row, 3, None)
		if name is None or name.strip().lower() in usernames_found:
			continue
		usernames_found.add(name.strip().lower())
		users_to_add.append(
			{
				"username": name.strip().lower(),
				"discord_id": None,
				"rep": get_rep(get_cell(row, 0, None)),
				"gen": get_cell(row, 1, None, int),
				"exp": get_cell(row, 4, 0, int),
				"id": None,
			}
		)

	users_dict: dict[str, dict[str]] = {}
	async with aiosqlite.connect("data/master.db") as db:
		for user in users_to_add:
			async with db.execute(
				"INSERT OR IGNORE INTO users (username, rep, gen) VALUES (?, ?, ?)", (user["username"], user["rep"], user["gen"])
			) as cursor:
				if cursor.lastrowid:
					user_id = cursor.lastrowid
					user["id"] = user_id
					users_dict[user["username"]] = user
					await db.execute("INSERT OR IGNORE INTO legacy_leaderboard (user_id, exp) VALUES (?, ?)", (user_id, user["exp"]))

		await db.commit()

	print("Adding badges to users...")

	user_badges_sheet = value_ranges[2]
	aria_user_badges_sheet = value_ranges[4]

	async with aiosqlite.connect("data/master.db") as db:
		# CONTRACTS BADGES
		for row in user_badges_sheet.get("values"):
			name = get_cell(row, 1, None, str).strip().lower()
			user = users_dict.get(name)
			user_id: int = None
			if user is None:
				user = fuzzy_search_user(users_to_add, name)
				if user is None:
					continue

			user_id = user["id"]

			badges_status: list[str] = row[3:]
			for badge in badges_to_add:
				if badge["type"] != "contracts":
					continue
				status = get_cell(badges_status, badge["_index"], "")
				if status.strip() == "COMPLETE":
					await db.execute("INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)", (user_id, badge["id"]))

		# ARIA BADGES
		for row in aria_user_badges_sheet.get("values"):
			name = get_cell(row, 0, None, str).strip().lower()
			user = users_dict.get(name)
			user_id: int = None
			if user is None:
				user = fuzzy_search_user(users_to_add, name)
				if user is None:
					async with db.execute("INSERT INTO users (username) VALUES (?)", (name,)) as cursor:
						user_id = cursor.lastrowid
						# print(f"Couldn't find user with name {name}, now created with id {user_id}")

			if user_id is None:
				user_id = user["id"]

			badges_status: list[str] = row[1:]
			for badge in badges_to_add:
				if badge["type"] != "aria":
					continue
				status = get_cell(badges_status, badge["_index"], "")
				if status.strip() in ["COMPLETE", "100%"]:
					await db.execute("INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)", (user_id, badge["id"]))

		await db.commit()

	print("Finished the botless setup, starting discord bot...")


if __name__ == "__main__":
	asyncio.run(main())
	bot.run(os.getenv("DISCORD_TOKEN"))
