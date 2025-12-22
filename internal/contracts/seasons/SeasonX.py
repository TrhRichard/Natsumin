from __future__ import annotations

from internal.enums import UserStatus, UserKind, ContractStatus, ContractKind
from internal.functions import get_cell, get_url as _get_url, get_user_id
from internal.contracts.rep import get_rep
from config import GOOGLE_API_KEY
from typing import TYPE_CHECKING
from uuid import uuid4

import aiosqlite
import aiohttp
import re

if TYPE_CHECKING:
	from internal.database import NatsuminDatabase
	from typing import Literal

SPREADSHEET_ID = "1ZuhNuejQ3gTKuZPzkGg47-upLUlcgNfdW2Jrpeq8cak"
SEASON_ID = "season_x"


async def _get_sheet_data() -> dict:
	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values:batchGet",
			params={
				"majorDimension": "ROWS",
				"valueRenderOption": "FORMATTED_VALUE",
				"ranges": [
					"Dashboard!A2:AB508",
					"Base!A2:AI516",
					"Duality Special!A2:K291",
					"Veteran Special!A2:J280",
					"Epoch Special!A2:K237",
					"Honzuki Special!A2:I171",
					"Aria Special!A2:G149",
					"Arcana Special!A2:N1539",
					"Buddying!A2:N100",
					"Sumira's Challenge!A2:F508",
					"Hitome's Challenge!A2:F508",
					"Sae's Challenge!A2:F508",
				],
				"key": GOOGLE_API_KEY,
			},
		) as response:
			response.raise_for_status()
			sheet_data = await response.json()
			return sheet_data


def get_url(row: list[str], i: int) -> str:
	return _get_url(get_cell(row, i, "", str))


NAME_MEDIUM_REGEX = r"(.*) \((.*)\)"
DASHBOARD_ROW_INDEXES: dict[int, tuple[str, int]] = {
	2: ("Base Contract", 15),
	3: ("Challenge Contract", 16),
	4: ("Veteran Special", 17),
	5: ("Duality Special", 18),
	6: ("Epoch Special", 19),
	7: ("Honzuki Special", 20),
	8: ("Aria Special", 21),
	10: ("Base Buddy", 22),
	11: ("Challenge Buddy", 23),
	12: ("Sumira's Challenge", 24),
	13: ("Hitome's Challenge", 25),
	14: ("Sae's Challenge", 27),
}
OPTIONAL_CONTRACTS: tuple[str, ...] = ("Aria Special",)


async def _sync_dashboard_data(sheet_data: dict, conn: aiosqlite.Connection):
	dashboard_rows: list[list[str]] = sheet_data["valueRanges"][0]["values"]

	for row in dashboard_rows:
		status = get_cell(row, 0, "")
		username = get_cell(row, 1, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			user_id = str(uuid4())
			await conn.execute("INSERT INTO user (id, username) VALUES (?, ?)", (user_id, username))

		match status:
			case "P":
				user_status = UserStatus.PASSED
			case "F":
				user_status = UserStatus.FAILED
			case "INC":
				user_status = UserStatus.INCOMPLETE
			case "LP":
				user_status = UserStatus.LATE_PASS
			case _:
				user_status = UserStatus.PENDING

		async with conn.execute("SELECT * FROM season_user WHERE season_id = ? AND user_id = ?", (SEASON_ID, user_id)) as cursor:
			user_row = await cursor.fetchone()

		if not user_row:
			async with conn.execute(
				"INSERT INTO season_user (season_id, user_id, status, kind) VALUES (?, ?, ?, ?) RETURNING *",
				(SEASON_ID, user_id, user_status.value, UserKind.NORMAL.value),
			) as cursor:
				user_row = await cursor.fetchone()
		else:
			if user_row["status"] != user_status:
				await conn.execute("UPDATE season_user SET status = ? WHERE season_id = ? AND user_id = ?", (user_status.value, SEASON_ID, user_id))

		for column, (contract_type, passed_column) in DASHBOARD_ROW_INDEXES.items():
			contract_name = get_cell(row, column, "-").strip().replace("\n", "")

			if contract_name == "-":
				continue

			match get_cell(row, passed_column, "").upper().strip():
				case "PASSED" | "BADGE":
					contract_status = ContractStatus.PASSED
				case "FAILED":
					contract_status = ContractStatus.FAILED
				case "LATE PASS":
					contract_status = ContractStatus.LATE_PASS
				case _:
					contract_status = ContractStatus.PENDING

			async with conn.execute(
				"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, contract_type)
			) as cursor:
				contract_row = await cursor.fetchone()

			if not contract_row:
				contract_id = str(uuid4())
				async with conn.execute(
					"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
					(SEASON_ID, contract_id, contract_name, contract_type, ContractKind.NORMAL.value, contract_status.value, user_id),
				) as cursor:
					contract_row = await cursor.fetchone()
			else:
				contract_id: str = contract_row["id"]
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (user_status.value, contract_id))
				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))

	await conn.commit()


async def _sync_basechallenge_data(sheet_data: dict, conn: aiosqlite.Connection):
	base_challenge_rows: list[list[str]] = sheet_data["valueRanges"][1]["values"]

	for row in base_challenge_rows:
		username = get_cell(row, 3, "").strip().lower()
		contractor = get_cell(row, 5, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT u.rep as global_rep, su.contractor_id, su.veto_used FROM season_user su INNER JOIN user u ON su.user_id = u.id WHERE su.season_id = ? AND su.user_id = ?",
			(SEASON_ID, user_id),
		) as cursor:
			user_row = await cursor.fetchone()

		if not user_row:
			continue

		contractor_id = await get_user_id(conn, contractor)

		user_rep = get_rep(get_cell(row, 2, "").strip())

		if user_row["contractor_id"] != contractor_id or user_row["veto_used"] != (get_cell(row, 12) == "TRUE"):
			await conn.execute(
				"""
				UPDATE season_user SET 
					contractor_id = ?, 
					rep = ?, 
					list_url = ?, 
					veto_used = ?, 
					preferences = ?, 
					bans = ?,
					accepting_manhwa = ?,
					accepting_ln = ?
				WHERE season_id = ? AND user_id = ?
				""",
				(
					contractor_id,
					user_rep.value,  # rep
					get_url(row, 8),  # list_url
					get_cell(row, 12, "FALSE") == "TRUE",  # veto_used
					get_cell(row, 26, "N/A").replace("\n", ", "),  # preferences
					get_cell(row, 27, "N/A").replace("\n", ", "),  # bans
					get_cell(row, 9, "N/A") == "Yes",  # accepting_manhwa
					get_cell(row, 10, "N/A") == "Yes",  # accepting_ln
					SEASON_ID,
					user_id,
				),
			)

		if user_row["global_rep"] != user_rep:
			await conn.execute("UPDATE user SET rep = ? WHERE id = ?", (user_rep.value, user_id))

		async with conn.execute(
			"SELECT progress, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Base Contract"),
		) as cursor:
			base_row = await cursor.fetchone()

		if (
			base_row["progress"] != get_cell(row, 19, "?/?").replace("\n", "")
			or base_row["rating"] != get_cell(row, 20, "0/10")
			or base_row["review_url"] != get_url(row, 24)
		):
			await conn.execute(
				"""
				UPDATE season_contract SET
					contractor = ?,
					progress = ?,
					rating = ?,
					review_url = ?,
					medium = ?
				WHERE season_id = ? AND contractee_id = ? AND type = ?
			""",
				(
					contractor,
					get_cell(row, 19, "?/?").replace("\n", ""),  # progress
					get_cell(row, 20, "0/10"),  # rating
					get_url(row, 24),  # review_url
					get_cell(row, 7),  # medium
					SEASON_ID,
					user_id,
					"Base Contract",
				),
			)

		async with conn.execute(
			"SELECT progress, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Challenge Contract"),
		) as cursor:
			challenge_row = await cursor.fetchone()

		if challenge_row and (
			challenge_row["progress"] != get_cell(row, 22, "?/?").replace("\n", "")
			or challenge_row["rating"] != get_cell(row, 23, "0/10")
			or challenge_row["review_url"] != get_url(row, 25)
		):
			await conn.execute(
				"""
				UPDATE season_contract SET
					contractor = ?,
					progress = ?,
					rating = ?,
					review_url = ?,
					medium = ?
				WHERE season_id = ? AND contractee_id = ? AND type = ?
			""",
				(
					contractor,
					get_cell(row, 22, "?/?").replace("\n", ""),  # progress
					get_cell(row, 23, "0/10"),  # rating
					get_url(row, 25),  # review_url
					get_cell(row, 15),  # medium
					SEASON_ID,
					user_id,
					"Challenge Contract",
				),
			)

	await conn.commit()


async def _sync_specials_data(sheet_data: dict, conn: aiosqlite.Connection):
	# Duality Special
	rows: list[list[str]] = sheet_data["valueRanges"][2]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Duality Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if (
			contract_row["rating"] != get_cell(row, 9, "0/10")
			or contract_row["progress"] != get_cell(row, 8, "").replace("\n", "")
			or contract_row["review_url"] != get_url(row, 10)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 6, "frazzle").strip().lower(),  # contractor
					get_cell(row, 8, "").replace("\n", ""),  # progress
					get_cell(row, 9, "0/10"),  # rating
					get_url(row, 10),  # review_url
					"Duality Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Veteran Special
	rows: list[list[str]] = sheet_data["valueRanges"][3]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Veteran Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if (
			contract_row["rating"] != get_cell(row, 8, "0/10")
			or contract_row["progress"] != get_cell(row, 7, "").replace("\n", "")
			or contract_row["review_url"] != get_url(row, 9)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 5, "").strip().lower(),  # contractor
					get_cell(row, 7, "").replace("\n", ""),  # progress
					get_cell(row, 8, "0/10"),  # rating
					get_url(row, 9),  # review_url
					"Veteran Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Epoch Special
	rows: list[list[str]] = sheet_data["valueRanges"][4]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Epoch Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if (
			contract_row["rating"] != get_cell(row, 9, "0/10")
			or contract_row["progress"] != get_cell(row, 8, "").replace("\n", "")
			or contract_row["review_url"] != get_url(row, 10)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 6, "frazzle").strip().lower(),  # contractor
					get_cell(row, 8, "").replace("\n", ""),  # progress
					get_cell(row, 9, "0/10"),  # rating
					get_url(row, 10),  # review_url
					"Epoch Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Honzuki Special
	rows: list[list[str]] = sheet_data["valueRanges"][5]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Honzuki Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if (
			contract_row["rating"] != get_cell(row, 7, "0/10")
			or contract_row["progress"] != get_cell(row, 6, "").replace("\n", "")
			or contract_row["review_url"] != get_url(row, 8)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle",  # contractor
					get_cell(row, 6, "").replace("\n", ""),  # progress
					get_cell(row, 7, "0/10"),  # rating
					get_url(row, 8),  # review_url
					"Honzuki Special" in OPTIONAL_CONTRACTS,  # optional
					"LN",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Aria Special
	rows: list[list[str]] = sheet_data["valueRanges"][6]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Aria Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if contract_row["rating"] != get_cell(row, 5, "0/10") or contract_row["review_url"] != get_url(row, 6):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 4, "").strip().lower(),  # contractor
					get_cell(row, 5, "0/10"),  # rating
					get_url(row, 6),  # review_url
					"Aria Special" in OPTIONAL_CONTRACTS,  # optional
					"Game",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Sumira's Challenge
	rows: list[list[str]] = sheet_data["valueRanges"][9]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Sumira's Challenge"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if contract_row["rating"] != get_cell(row, 4, "0/10") or contract_row["review_url"] != get_url(row, 5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle",  # contractor
					get_cell(row, 4, "0/10"),  # rating
					get_url(row, 5),  # review_url
					"Sumira's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Manga",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Hitome's Challenge
	rows: list[list[str]] = sheet_data["valueRanges"][10]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Hitome's Challenge"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if contract_row["rating"] != get_cell(row, 4, "0/10") or contract_row["review_url"] != get_url(row, 5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle",  # contractor
					get_cell(row, 4, "0/10"),  # rating
					get_url(row, 5),  # review_url
					"Hitome's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Movie",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Sae's Challenge
	rows: list[list[str]] = sheet_data["valueRanges"][11]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Sae's Challenge"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if contract_row["rating"] != get_cell(row, 4, "0/10") or contract_row["review_url"] != get_url(row, 5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle",  # contractor
					get_cell(row, 4, "0/10"),  # rating
					get_url(row, 5),  # review_url
					"Sae's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Cooking",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	await conn.commit()


async def _sync_buddies_data(sheet_data: dict, conn: aiosqlite.Connection):
	rows: list[list[str]] = sheet_data["valueRanges"][8]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Base Buddy"),
		) as cursor:
			base_buddy_row = await cursor.fetchone()

		if base_buddy_row and (
			base_buddy_row["rating"] != get_cell(row, 10, "0/10")
			or base_buddy_row["progress"] != get_cell(row, 8, "").replace("\n", "")
			or base_buddy_row["review_url"] != get_url(row, 12)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 4, "").strip().lower(),  # contractor
					get_cell(row, 8, "").replace("\n", ""),  # progress
					get_cell(row, 10, "0/10"),  # rating
					get_url(row, 12),  # review_url
					"Base Buddy" in OPTIONAL_CONTRACTS,  # optional
					re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 5, "")),  # medium,
					SEASON_ID,
					base_buddy_row["id"],
				),
			)

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Challenge Buddy"),
		) as cursor:
			challenge_buddy_row = await cursor.fetchone()

		if challenge_buddy_row and (
			challenge_buddy_row["rating"] != get_cell(row, 11, "0/10")
			or challenge_buddy_row["progress"] != get_cell(row, 9, "").replace("\n", "")
			or challenge_buddy_row["review_url"] != get_url(row, 13)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					get_cell(row, 6, "").strip().lower(),  # contractor
					get_cell(row, 9, "").replace("\n", ""),  # progress
					get_cell(row, 11, "0/10"),  # rating
					get_url(row, 13),  # review_url
					"Challenge Buddy" in OPTIONAL_CONTRACTS,  # optional
					re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 7, "")),  # medium,
					SEASON_ID,
					challenge_buddy_row["id"],
				),
			)

	await conn.commit()


arcana_special_columns = {"status": 0, "user": 3, "quests": 4, "soul_quota": 5, "minimum_quest": 7, "rating": 12, "review_url": 13}


async def _sync_arcana_data(sheet_data: dict, conn: aiosqlite.Connection):
	rows: list[list[str]] = sheet_data["valueRanges"][7]["values"]

	def get_row_type(row: list[str]) -> Literal["user", "contract", "empty"]:
		binding_cell = get_cell(row, 1, "").strip()
		user_cell = get_cell(row, 3, "").strip().lower()
		contract_cell = get_cell(row, 4, "").strip()
		if not binding_cell and contract_cell:
			return "contract"
		elif binding_cell and user_cell:
			return "user"
		return "empty"

	i = 0
	while i < len(rows):
		row = rows[i]
		row_type = get_row_type(row)

		if row_type == "user":
			username = get_cell(row, arcana_special_columns["user"], "").strip().lower()
			if not username:
				i += 1
				continue

			user_id = await get_user_id(conn, username)
			if not user_id:
				i += 1
				continue

			async with conn.execute("SELECT 1 FROM season_user WHERE season_id = ? AND user_id = ?", (SEASON_ID, user_id)) as cursor:
				does_user_exist = await cursor.fetchone()

			if not does_user_exist:
				i += 1
				continue

			user_soul_quota = get_cell(row, arcana_special_columns["soul_quota"], 0, int)
			if match := re.match(r"(\d+)\/(\d+)", get_cell(row, arcana_special_columns["quests"], "0/14")):
				user_quest_count = int(match.group(1))
			else:
				user_quest_count = 0

			arcana_count = 0
			if user_quest_count < user_soul_quota:
				min_contract_name = get_cell(row, arcana_special_columns["minimum_quest"], "PLEASE SELECT").strip().replace("\n", ", ")
				if not min_contract_name:
					min_contract_name = "PLEASE SELECT"
				min_contract_review = get_url(row, arcana_special_columns["review_url"])
				min_contract_rating = get_cell(row, arcana_special_columns["rating"], "0/10")

				raw_contract_status = get_cell(row, arcana_special_columns["status"], "").strip()
				match raw_contract_status:
					case "PASSED" | "PURIFIED" | "ENLIGHTENMENT":
						min_contract_status = ContractStatus.PASSED
					case "DEATH":
						min_contract_status = ContractStatus.FAILED
					case "UNVERIFIED":
						min_contract_status = ContractStatus.UNVERIFIED
					case _:
						min_contract_status = ContractStatus.PENDING

				async with conn.execute(
					"""
					SELECT id, status, name, rating, review_url FROM season_contract 
					WHERE season_id = ?
						AND contractee_id = ?
						AND type LIKE "Arcana Special%"
						AND (name = ? OR name = "PLEASE SELECT")
					ORDER BY type DESC
					LIMIT 1
					""",
					(SEASON_ID, user_id, min_contract_name),
				) as cursor:
					contract_row = await cursor.fetchone()

				medium_match = re.search(NAME_MEDIUM_REGEX, min_contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1

				if contract_row is None:
					await conn.execute(
						"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, rating, review_url, medium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
						(
							SEASON_ID,
							str(uuid4()),
							min_contract_name,
							f"Arcana Special {arcana_count}",
							ContractKind.NORMAL.value,
							min_contract_status.value,
							user_id,
							"frazzle",
							min_contract_rating,
							min_contract_review,
							contract_medium,
						),
					)
				elif (
					contract_row["status"] != min_contract_status.value
					or contract_row["name"] != min_contract_name
					or contract_row["rating"] != min_contract_rating
					or contract_row["review_url"] != min_contract_review
				):
					await conn.execute(
						"UPDATE season_contract SET name = ?, status = ?, rating = ?, review_url = ? WHERE season_id = ? AND id = ?",
						(min_contract_name, min_contract_status.value, min_contract_rating, min_contract_review, SEASON_ID, contract_row["id"]),
					)

			i += 1
			while i < len(rows) and get_row_type(rows[i]) == "contract":
				contract_row = rows[i]
				contract_name = get_cell(contract_row, arcana_special_columns["quests"], "").strip().replace("\n", ", ")
				contract_soul_quota = get_cell(contract_row, arcana_special_columns["soul_quota"], "N/A").strip()

				if not contract_name or contract_soul_quota == "N/A":
					i += 1
					continue

				contract_review = get_url(contract_row, arcana_special_columns["review_url"])
				contract_rating = get_cell(contract_row, arcana_special_columns["rating"], "0/10")
				raw_contract_status = get_cell(contract_row, arcana_special_columns["status"], "").strip()
				match raw_contract_status:
					case "PASSED" | "PURIFIED" | "ENLIGHTENMENT":
						contract_status = ContractStatus.PASSED
					case "DEATH":
						contract_status = ContractStatus.FAILED
					case "UNVERIFIED":
						contract_status = ContractStatus.UNVERIFIED
					case _:
						contract_status = ContractStatus.PENDING

				async with conn.execute(
					"""
					SELECT id, status, rating, review_url FROM season_contract 
					WHERE season_id = ?
						AND contractee_id = ?
						AND type LIKE "Arcana Special%"
						AND name = ?
					ORDER BY type DESC
					LIMIT 1
					""",
					(SEASON_ID, user_id, contract_name),
				) as cursor:
					contract_row = await cursor.fetchone()

				medium_match = re.search(NAME_MEDIUM_REGEX, contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1
				if contract_row is None:
					await conn.execute(
						"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, rating, review_url, medium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
						(
							SEASON_ID,
							str(uuid4()),
							contract_name,
							f"Arcana Special {arcana_count}",
							ContractKind.NORMAL.value,
							contract_status.value,
							user_id,
							"frazzle",
							contract_rating,
							contract_review,
							contract_medium,
						),
					)
				elif (
					contract_row["status"] != contract_status.value
					or contract_row["rating"] != contract_rating
					or contract_row["review_url"] != contract_review
				):
					await conn.execute(
						"UPDATE season_contract SET name = ?, status = ?, rating = ?, review_url = ? WHERE season_id = ? AND id = ?",
						(contract_name, contract_status.value, contract_rating, contract_review, SEASON_ID, contract_row["id"]),
					)

				i += 1

			continue
		elif row_type == "empty":
			break

		i += 1

	await conn.commit()


async def sync_season(database: NatsuminDatabase):
	sheet_data = await _get_sheet_data()

	async with database.connect() as conn:
		await _sync_dashboard_data(sheet_data, conn)
		await _sync_basechallenge_data(sheet_data, conn)
		await _sync_specials_data(sheet_data, conn)
		await _sync_buddies_data(sheet_data, conn)
		await _sync_arcana_data(sheet_data, conn)
