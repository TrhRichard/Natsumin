from __future__ import annotations

from internal.contracts.sheet import sync_media_data, fetch_sheets, PATTERNS, SyncContext, Spreadsheet, SheetBlock, Row
from internal.enums import UserStatus, UserKind, ContractStatus, ContractKind
from internal.functions import get_user_id
from internal.contracts.rep import get_rep
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import uuid4

import aiosqlite
import aiohttp
import re

if TYPE_CHECKING:
	from internal.database import NatsuminDatabase
	from typing import Literal

SEASON_SPREADSHEET_ID = "1ZuhNuejQ3gTKuZPzkGg47-upLUlcgNfdW2Jrpeq8cak"
FANTASY_SPREADSHEET_ID = "1IRg3plGydWluhIIxM4uQfwzb5xdQdDF83ETVTcnUKRo"
SEASON_ID = "season_x"

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
OPTIONAL_CONTRACTS: tuple[str, ...] = ("Aria Special", "Sumira's Challenge", "Hitome's Challenge", "Sae's Challenge", "Christmas Challenge")


async def _sync_dashboard_sheet(dashboard_sheet: SheetBlock, conn: aiosqlite.Connection, ctx: SyncContext):
	async with conn.execute("SELECT id, mal_id FROM media_anilist") as cursor:
		rows = await cursor.fetchall()
		existing_anilist_ids: list[str] = [row["id"] for row in rows]
		mal_id_to_anilist: dict[str, str] = {row["mal_id"]: row["id"] for row in rows if "mal_id" in dict(row)}
	async with conn.execute("SELECT type, id FROM media_no_match") as cursor:
		rows = await cursor.fetchall()
		impossible_ids: defaultdict[str, list[str]] = defaultdict(list)
		for row in rows:
			impossible_ids[row["type"]].append(row["id"])
	async with conn.execute("SELECT id FROM media WHERE type = ?", ("steam",)) as cursor:
		rows = await cursor.fetchall()
		existing_steam_ids: list[str] = [row["id"] for row in rows]

	for row in dashboard_sheet.rows:
		status = row.get_value(0, "")
		username = row.get_value(1, "").strip().lower()

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
			contract_cell = row.get_cell(column)
			contract_name = (contract_cell.value if contract_cell else "-").strip().replace("\n", "")

			if contract_name == "-":
				continue

			match row.get_value(passed_column, "").upper().strip():
				case "PASSED" | "BADGE":
					contract_status = ContractStatus.PASSED
				case "FAILED":
					contract_status = ContractStatus.FAILED
				case "LATE PASS":
					contract_status = ContractStatus.LATE_PASS
				case _:
					contract_status = ContractStatus.PENDING

			media_type: str | None = None
			media_id: str | None = None
			if contract_cell.hyperlink is not None:
				if match := re.match(PATTERNS.ANILIST, contract_cell.hyperlink):
					media_type = "anilist"
					media_id = match.group(1)
				elif match := re.match(PATTERNS.MAL, contract_cell.hyperlink):
					media_type = "myanimelist"
					media_id = match.group(1)
				elif match := re.match(PATTERNS.STEAM, contract_cell.hyperlink):
					media_type = "steam"
					media_id = match.group(1)

			if media_type is not None:
				if media_type == "anilist":
					if media_id not in existing_anilist_ids:
						ctx.missing_anilist_ids.add(media_id)
				elif media_type == "myanimelist":
					if media_id not in mal_id_to_anilist:
						if media_id not in impossible_ids["mal"]:  # No Anilist ID found for these MAL ids
							ctx.missing_mal_ids.add(media_id)
						media_type, media_id = None, None
					else:
						media_type = "anilist"
						media_id = mal_id_to_anilist.get(media_id)
				elif media_type == "steam":
					if media_id not in existing_steam_ids:
						if media_id not in impossible_ids["steam"]:
							ctx.missing_steam_ids.add(media_id)
						else:
							media_type, media_id = None, None
				else:
					media_type, media_id = None, None

			async with conn.execute(
				"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, contract_type)
			) as cursor:
				contract_row = await cursor.fetchone()

			if not contract_row:
				contract_id = str(uuid4())
				async with conn.execute(
					"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, media_type, media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
					(
						SEASON_ID,
						contract_id,
						contract_name,
						contract_type,
						ContractKind.NORMAL.value,
						contract_status.value,
						user_id,
						media_type,
						media_id,
					),
				) as cursor:
					contract_row = await cursor.fetchone()
			else:
				contract_id: str = contract_row["id"]
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (contract_status.value, contract_id))
				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))
				if contract_row["media_type"] != media_type or contract_row["media_id"] != media_id:
					await conn.execute("UPDATE season_contract SET media_type = ?, media_id = ? WHERE id = ?", (media_type, media_id, contract_id))

	await conn.commit()


async def _sync_basechallenge_sheet(base_challenge_sheet: SheetBlock, conn: aiosqlite.Connection):
	for row in base_challenge_sheet.rows:
		username = row.get_value(3, "").strip().lower()
		contractor = row.get_value(5, "").strip().lower()

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

		user_rep = get_rep(row.get_value(2, "").strip())

		if user_row["contractor_id"] != contractor_id or user_row["veto_used"] != (row.get_value(12) == "TRUE"):
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
					row.get_url(8),  # list_url
					row.get_value(12) == "TRUE",  # veto_used
					row.get_value(26, "N/A").replace("\n", ", "),  # preferences
					row.get_value(27, "N/A").replace("\n", ", "),  # bans
					row.get_value(9, "N/A") == "Yes",  # accepting_manhwa
					row.get_value(10, "N/A") == "Yes",  # accepting_ln
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
			base_contract = await cursor.fetchone()

		if (
			base_contract["progress"] != row.get_value(19, "?/?").replace("\n", "")
			or base_contract["rating"] != row.get_value(20, "0/10")
			or base_contract["review_url"] != row.get_url(24)
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
					row.get_value(19, "?/?").replace("\n", ""),  # progress
					row.get_value(20, "0/10"),  # rating
					row.get_url(24),  # review_url
					row.get_value(7),  # medium
					SEASON_ID,
					user_id,
					"Base Contract",
				),
			)

		async with conn.execute(
			"SELECT progress, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Challenge Contract"),
		) as cursor:
			challenge_contract = await cursor.fetchone()

		if challenge_contract and (
			challenge_contract["progress"] != row.get_value(22, "?/?").replace("\n", "")
			or challenge_contract["rating"] != row.get_value(23, "0/10")
			or challenge_contract["review_url"] != row.get_url(25)
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
					row.get_value(22, "?/?").replace("\n", ""),  # progress
					row.get_value(23, "0/10"),  # rating
					row.get_url(25),  # review_url
					row.get_value(15),  # medium
					SEASON_ID,
					user_id,
					"Challenge Contract",
				),
			)

	await conn.commit()


async def _sync_special_sheets(spreadsheet: Spreadsheet, conn: aiosqlite.Connection):
	# Duality Special
	for row in spreadsheet.get_sheet("Duality Special", block=0).rows:
		username = row.get_value(3, "").strip().lower()

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
			contract_row["rating"] != row.get_value(9, "0/10")
			or contract_row["progress"] != row.get_value(8, "").replace("\n", "")
			or contract_row["review_url"] != row.get_url(10)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(6, "frazzle_dazzle").strip().lower(),  # contractor
					row.get_value(8, "").replace("\n", ""),  # progress
					row.get_value(9, "0/10"),  # rating
					row.get_url(10),  # review_url
					"Duality Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Veteran Special
	for row in spreadsheet.get_sheet("Veteran Special", block=0).rows:
		username = row.get_value(3, "").strip().lower()

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
			contract_row["rating"] != row.get_value(8, "0/10")
			or contract_row["progress"] != row.get_value(7, "").replace("\n", "")
			or contract_row["review_url"] != row.get_url(9)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(5, "").strip().lower(),  # contractor
					row.get_value(7, "").replace("\n", ""),  # progress
					row.get_value(8, "0/10"),  # rating
					row.get_url(9),  # review_url
					"Veteran Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Epoch Special
	for row in spreadsheet.get_sheet("Epoch Special", block=0).rows:
		username = row.get_value(3, "").strip().lower()

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
			contract_row["rating"] != row.get_value(9, "0/10")
			or contract_row["progress"] != row.get_value(8, "").replace("\n", "")
			or contract_row["review_url"] != row.get_url(10)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(6, "frazzle_dazzle").strip().lower(),  # contractor
					row.get_value(8, "").replace("\n", ""),  # progress
					row.get_value(9, "0/10"),  # rating
					row.get_url(10),  # review_url
					"Epoch Special" in OPTIONAL_CONTRACTS,  # optional
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(4, "")),  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Honzuki Special
	for row in spreadsheet.get_sheet("Honzuki Special", block=0).rows:
		username = row.get_value(3, "").strip().lower()

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
			contract_row["rating"] != row.get_value(7, "0/10")
			or contract_row["progress"] != row.get_value(6, "").replace("\n", "")
			or contract_row["review_url"] != row.get_url(8)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle_dazzle",  # contractor
					row.get_value(6, "").replace("\n", ""),  # progress
					row.get_value(7, "0/10"),  # rating
					row.get_url(8),  # review_url
					"Honzuki Special" in OPTIONAL_CONTRACTS,  # optional
					"LN",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Aria Special
	for row in spreadsheet.get_sheet("Aria Special", block=0).rows:
		username = row.get_value(2, "").strip().lower()

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

		if contract_row["rating"] != row.get_value(5, "0/10") or contract_row["review_url"] != row.get_url(6):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(4, "").strip().lower(),  # contractor
					row.get_value(5, "0/10"),  # rating
					row.get_url(6),  # review_url
					"Aria Special" in OPTIONAL_CONTRACTS,  # optional
					"Game",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Sumira's Challenge
	for row in spreadsheet.get_sheet("Sumira's Challenge", block=0).rows:
		username = row.get_value(2, "").strip().lower()

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

		if contract_row["rating"] != row.get_value(4, "0/10") or contract_row["review_url"] != row.get_url(5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle_dazzle",  # contractor
					row.get_value(4, "0/10"),  # rating
					row.get_url(5),  # review_url
					"Sumira's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Manga",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Hitome's Challenge
	for row in spreadsheet.get_sheet("Hitome's Challenge", block=0).rows:
		username = row.get_value(2, "").strip().lower()

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

		if contract_row["rating"] != row.get_value(4, "0/10") or contract_row["review_url"] != row.get_url(5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle_dazzle",  # contractor
					row.get_value(4, "0/10"),  # rating
					row.get_url(5),  # review_url
					"Hitome's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Movie",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Sae's Challenge
	for row in spreadsheet.get_sheet("Sae's Challenge", block=0).rows:
		username = row.get_value(2, "").strip().lower()

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

		if contract_row["rating"] != row.get_value(4, "0/10") or contract_row["review_url"] != row.get_url(5):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle_dazzle",  # contractor
					row.get_value(4, "0/10"),  # rating
					row.get_url(5),  # review_url
					"Sae's Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Cooking",  # medium,
					SEASON_ID,
					contract_row["id"],
				),
			)

	# Christmas Challenge
	for row in spreadsheet.get_sheet("Christmas Challenge", block=0).rows:
		username = row.get_value(2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		match row.get_value(0, "").upper().strip():
			case "PASSED" | "BADGE":
				contract_status = ContractStatus.PASSED
			case "FAILED":
				contract_status = ContractStatus.FAILED
			case "LATE PASS":
				contract_status = ContractStatus.LATE_PASS
			case _:
				contract_status = ContractStatus.PENDING

		async with conn.execute(
			"SELECT id, rating, status, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Christmas Challenge"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			await conn.execute(
				"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, optional, rating, review_url, medium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
				(
					SEASON_ID,
					str(uuid4()),
					"Tokyo Godfathers",  # name
					"Christmas Challenge",  # type
					ContractKind.NORMAL.value,  # kind
					contract_status.value,  # status,
					user_id,  # contractee_id
					"frazzle_dazzle",  # contractor
					"Christmas Challenge" in OPTIONAL_CONTRACTS,  # optional
					row.get_value(3, "0/10"),  # rating
					row.get_url(4),  # review_url
					"Movie",  # medium
				),
			)
		elif (
			contract_row["status"] != contract_status.value
			or contract_row["rating"] != row.get_value(3, "0/10")
			or contract_row["review_url"] != row.get_url(4)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, optional = ?, medium = ?, status = ? WHERE season_id = ? AND id = ?",
				(
					"frazzle_dazzle",  # contractor
					row.get_value(3, "0/10"),  # rating
					row.get_url(4),  # review_url
					"Christmas Challenge" in OPTIONAL_CONTRACTS,  # optional
					"Movie",  # medium
					contract_status.value,  # status
					SEASON_ID,
					contract_row["id"],
				),
			)

	await conn.commit()


async def _sync_buddies_sheet(buddy_sheet: SheetBlock, conn: aiosqlite.Connection):
	for row in buddy_sheet.rows:
		username = row.get_value(2, "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Base Buddy"),
		) as cursor:
			base_buddy_row = await cursor.fetchone()

		if base_buddy_row and (
			base_buddy_row["rating"] != row.get_value(10, "0/10")
			or base_buddy_row["progress"] != row.get_value(8, "").replace("\n", "")
			or base_buddy_row["review_url"] != row.get_url(12)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(4, "").strip().lower(),  # contractor
					row.get_value(8, "").replace("\n", ""),  # progress
					row.get_value(10, "0/10"),  # rating
					row.get_url(12),  # review_url
					"Base Buddy" in OPTIONAL_CONTRACTS,  # optional
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(5, "")),  # medium,
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
			challenge_buddy_row["rating"] != row.get_value(11, "0/10")
			or challenge_buddy_row["progress"] != row.get_value(9, "").replace("\n", "")
			or challenge_buddy_row["review_url"] != row.get_url(13)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, optional = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value(6, "").strip().lower(),  # contractor
					row.get_value(9, "").replace("\n", ""),  # progress
					row.get_value(11, "0/10"),  # rating
					row.get_url(13),  # review_url
					"Challenge Buddy" in OPTIONAL_CONTRACTS,  # optional
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(7, "")),  # medium,
					SEASON_ID,
					challenge_buddy_row["id"],
				),
			)

	await conn.commit()


arcana_special_columns = {"status": 0, "user": 3, "quests": 4, "soul_quota": 5, "minimum_quest": 7, "rating": 12, "review_url": 13}


async def _sync_arcana_sheet(sheet: SheetBlock, conn: aiosqlite.Connection):
	rows = sheet.rows

	def get_row_type(row: Row) -> Literal["user", "contract", "empty"]:
		binding_cell = row.get_value(1, "").strip()
		user_cell = row.get_value(arcana_special_columns["user"], "").strip().lower()
		contract_cell = row.get_value(arcana_special_columns["quests"], "").strip()
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
			username = row.get_value(arcana_special_columns["user"], "").strip().lower()
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

			user_soul_quota = int(row.get_value(arcana_special_columns["soul_quota"], 0))
			if match := re.match(r"(\d+)\/(\d+)", row.get_value(arcana_special_columns["quests"], "0/14")):
				user_quest_count = int(match.group(1))
			else:
				user_quest_count = 0

			arcana_count = 0
			if user_quest_count < user_soul_quota:
				min_contract_name = row.get_value(arcana_special_columns["minimum_quest"], "PLEASE SELECT").strip().replace("\n", ", ")
				if not min_contract_name:
					min_contract_name = "PLEASE SELECT"
				min_contract_review = row.get_url(arcana_special_columns["review_url"])
				min_contract_rating = row.get_value(arcana_special_columns["rating"], "0/10")

				raw_contract_status = row.get_value(arcana_special_columns["status"], "").strip()
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
					db_row = await cursor.fetchone()

				medium_match = re.search(PATTERNS.NAME_MEDIUM, min_contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1

				if db_row is None:
					await conn.execute(
						"INSERT OR IGNORE INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, rating, review_url, medium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
						(
							SEASON_ID,
							str(uuid4()),
							min_contract_name,
							f"Arcana Special {arcana_count}",
							ContractKind.NORMAL.value,
							min_contract_status.value,
							user_id,
							"frazzle_dazzle",
							min_contract_rating,
							min_contract_review,
							contract_medium,
						),
					)
				elif (
					db_row["status"] != min_contract_status.value
					or db_row["name"] != min_contract_name
					or db_row["rating"] != min_contract_rating
					or db_row["review_url"] != min_contract_review
				):
					await conn.execute(
						"UPDATE season_contract SET name = ?, status = ?, rating = ?, review_url = ? WHERE season_id = ? AND id = ?",
						(min_contract_name, min_contract_status.value, min_contract_rating, min_contract_review, SEASON_ID, db_row["id"]),
					)

			i += 1
			while i < len(rows) and get_row_type(rows[i]) == "contract":
				contract_row = rows[i]
				contract_name = contract_row.get_value(arcana_special_columns["quests"], "").strip().replace("\n", ", ")
				contract_soul_quota = contract_row.get_value(arcana_special_columns["soul_quota"], "N/A").strip()

				if not contract_name or contract_soul_quota == "N/A":
					i += 1
					continue

				contract_review = contract_row.get_url(arcana_special_columns["review_url"])
				contract_rating = contract_row.get_value(arcana_special_columns["rating"], "0/10")
				raw_contract_status = contract_row.get_value(arcana_special_columns["status"], "").strip()
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
					db_row = await cursor.fetchone()

				medium_match = re.search(PATTERNS.NAME_MEDIUM, contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1
				if db_row is None:
					await conn.execute(
						"INSERT OR IGNORE INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, rating, review_url, medium) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
						(
							SEASON_ID,
							str(uuid4()),
							contract_name,
							f"Arcana Special {arcana_count}",
							ContractKind.NORMAL.value,
							contract_status.value,
							user_id,
							"frazzle_dazzle",
							contract_rating,
							contract_review,
							contract_medium,
						),
					)
				elif db_row["status"] != contract_status.value or db_row["rating"] != contract_rating or db_row["review_url"] != contract_review:
					await conn.execute(
						"UPDATE season_contract SET name = ?, status = ?, rating = ?, review_url = ? WHERE season_id = ? AND id = ?",
						(contract_name, contract_status.value, contract_rating, contract_review, SEASON_ID, db_row["id"]),
					)

				i += 1

			continue
		elif row_type == "empty":
			break

		i += 1

	await conn.commit()


async def _sync_fantasy_sheet(fantasy_sheet: SheetBlock, conn: aiosqlite.Connection):
	rows = fantasy_sheet.rows

	i = 0
	while i < len(rows):
		row = rows[i]
		if row.get_value(1, "") == "Player:":
			username = row.get_value(2, "")
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

			async with conn.execute("SELECT * FROM season_user_fantasy WHERE season_id = ? AND user_id = ?", (SEASON_ID, user_id)) as cursor:
				fantasy_row = await cursor.fetchone()

			i += 1
			if fantasy_row:
				update_list = []
				update_params = []

				for m_i in range(5):
					i += 1
					update_list.append(f"member{m_i + 1}_score = ?")
					update_params.append(int(rows[i].get_value(4, 0)))

				i += 2

				update_list.append("total_score = ?")
				update_params.append(int(rows[i].get_value(2, 0)))

				if fantasy_row["total_score"] != int(rows[i].get_value(2, 0)) or any(
					fantasy_row[f"member{index}_score"] != member_score for index, member_score in enumerate(update_params[:1], start=1)
				):
					await conn.execute(
						f"UPDATE season_user_fantasy SET {','.join(update_list)} WHERE season_id = ? AND user_id = ?",
						(*update_params, SEASON_ID, user_id),
					)

				i += 1
			else:
				member_ids: list[tuple[str, int]] = []

				for m_i in range(5):
					i += 1
					member_id = await get_user_id(conn, rows[i].get_value(2))
					if not member_id:
						print(f"{rows[i].get_value(2)} NO ID")
						raise

					member_ids.append((member_id, int(rows[i].get_value(4, 0))))

				i += 2

				total_score = int(rows[i].get_value(2, 0))

				query = """
					INSERT INTO season_user_fantasy
						(
							season_id, user_id, total_score, 
							member1_id, member1_score, member2_id, member2_score,
							member3_id, member3_score, member4_id, member4_score,
							member5_id, member5_score
						)
					VALUES
						(
							?, ?, ?,
							?, ?, ?, ?,
							?, ?, ?, ?,
							?, ?
						)
					RETURNING *
				"""
				flat_members = []
				for m in member_ids:
					flat_members.extend(m)

				async with conn.execute(query, (SEASON_ID, user_id, total_score, *flat_members)) as cursor:
					fantasy_row = await cursor.fetchone()

				i += 1
		else:
			i += 1
			continue

	await conn.commit()


async def _sync_aids_sheet(aids_sheet: SheetBlock, conn: aiosqlite.Connection, ctx: SyncContext):
	async with conn.execute("SELECT id, mal_id FROM media_anilist") as cursor:
		rows = await cursor.fetchall()
		existing_anilist_ids: list[str] = [row["id"] for row in rows]
		mal_id_to_anilist: dict[str, str] = {row["mal_id"]: row["id"] for row in rows if "mal_id" in dict(row)}
	async with conn.execute("SELECT type, id FROM media_no_match") as cursor:
		rows = await cursor.fetchall()
		impossible_ids: defaultdict[str, list[str]] = defaultdict(list)
		for row in rows:
			impossible_ids[row["type"]].append(row["id"])
	async with conn.execute("SELECT id FROM media WHERE type = ?", ("steam",)) as cursor:
		rows = await cursor.fetchall()
		existing_steam_ids: list[str] = [row["id"] for row in rows]

	user_id_occurances: defaultdict[str, int] = defaultdict(int)
	aid_user_passed: defaultdict[str, int] = defaultdict(int)
	aid_user_total: defaultdict[str, int] = defaultdict(int)

	for row in aids_sheet.rows:
		username = row.get_value(1, "").strip().lower()

		if not username:
			continue

		user_id = await get_user_id(conn, username)
		if not user_id:
			print(f"User id not found for {username}, currently creation of users is not available!")
			continue

		async with conn.execute("SELECT kind, status FROM season_user WHERE season_id = ? AND user_id = ?", (SEASON_ID, user_id)) as cursor:
			user_row = await cursor.fetchone()
			if not user_row:
				async with conn.execute(
					"INSERT INTO season_user (season_id, user_id, status, kind) VALUES (?, ?, ?, ?) RETURNING kind, status",
					(SEASON_ID, user_id, UserStatus.PENDING.value, UserKind.AID.value),
				) as cursor:
					user_row = await cursor.fetchone()

		user_id_occurances[user_id] += 1
		aid_number = user_id_occurances.get(user_id)

		async with conn.execute(
			"SELECT id, rating, progress, review_url, name, media_type, media_id FROM season_contract WHERE season_id = ? AND contractee_id = ? AND kind = ? AND type = ?",
			(SEASON_ID, user_id, ContractKind.AID.value, f"Aid Contract {aid_number}"),
		) as cursor:
			aid_contract_row = await cursor.fetchone()

		match row.get_value(0, "").strip().upper():
			case "PASSED":
				contract_status = ContractStatus.PASSED
			case "FAILED":
				contract_status = ContractStatus.FAILED
			case _:
				contract_status = ContractStatus.PENDING

		if user_row["kind"] == UserKind.AID.value and user_row["status"] != UserStatus.PASSED.value:
			aid_user_total[user_id] += 1
			if contract_status == ContractStatus.PASSED:
				aid_user_passed[user_id] += 1

		media_type: str | None = None
		media_id: str | None = None
		if name_hyperlink := row.get_url(6):
			if match := re.match(PATTERNS.ANILIST, name_hyperlink):
				media_type = "anilist"
				media_id = match.group(1)
			elif match := re.match(PATTERNS.MAL, name_hyperlink):
				media_type = "myanimelist"
				media_id = match.group(1)
			elif match := re.match(PATTERNS.STEAM, name_hyperlink):
				media_type = "steam"
				media_id = match.group(1)

		if media_type is not None:
			if media_type == "anilist":
				if media_id not in existing_anilist_ids:
					ctx.missing_anilist_ids.add(media_id)
			elif media_type == "myanimelist":
				if media_id not in mal_id_to_anilist:
					if media_id not in impossible_ids["mal"]:  # No Anilist ID found for these MAL ids
						ctx.missing_mal_ids.add(media_id)
					media_type, media_id = None, None
				else:
					media_type = "anilist"
					media_id = mal_id_to_anilist.get(media_id)
			elif media_type == "steam":
				if media_id not in existing_steam_ids:
					if media_id not in impossible_ids["steam"]:
						ctx.missing_steam_ids.add(media_id)
					else:
						media_type, media_id = None, None
			else:
				media_type, media_id = None, None

		contract_name = row.get_value(6, "").strip().replace("\n", ", ")
		contract_progress = row.get_value(5, "").replace("\n", "")
		contract_review_url = row.get_url(7)
		contract_rating = row.get_value(4, "0/10")
		contract_medium = re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value(6, ""))
		contract_contractor = row.get_value(3, "").strip().lower()

		if aid_contract_row and (
			aid_contract_row["rating"] != contract_rating
			or aid_contract_row["progress"] != contract_progress
			or aid_contract_row["review_url"] != contract_review_url
			or aid_contract_row["name"] != contract_name
			or (aid_contract_row["media_type"] != media_type or aid_contract_row["media_id"] != media_id)
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, medium = ?, status = ?, name = ?, media_type = ?, media_id = ? WHERE season_id = ? AND id = ?",
				(
					contract_contractor,
					contract_progress,
					contract_rating,
					contract_review_url,
					contract_medium,
					contract_status.value,
					contract_name,
					media_type,
					media_id,
					SEASON_ID,
					aid_contract_row["id"],
				),
			)
		elif not aid_contract_row:
			contract_id = str(uuid4())
			await conn.execute(
				"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, contractor, progress, rating, review_url, medium, media_type, media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
				(
					SEASON_ID,
					contract_id,
					contract_name,
					f"Aid Contract {aid_number}",
					ContractKind.AID.value,
					contract_status.value,
					user_id,
					contract_contractor,
					contract_progress,
					contract_rating,
					contract_review_url,
					contract_medium,
					media_type,
					media_id,
				),
			)

	for user_id, total in aid_user_total.items():
		passed = aid_user_passed[user_id]

		if passed >= total:
			await conn.execute("UPDATE season_user SET status = ? WHERE season_id = ? AND user_id = ?", (UserStatus.PASSED, SEASON_ID, user_id))

	await conn.commit()


async def sync_season(database: NatsuminDatabase):
	spreadsheet = await fetch_sheets(
		SEASON_SPREADSHEET_ID,
		[
			"Dashboard!A2:AC508",
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
			"Christmas Challenge!A2:E36",
			"Aid Parade!A4:H106",
		],
	)

	ctx = SyncContext()

	async with database.connect() as conn:
		await _sync_dashboard_sheet(spreadsheet.get_sheet("Dashboard", block=0), conn, ctx)
		await _sync_basechallenge_sheet(spreadsheet.get_sheet("Base", block=0), conn)
		await _sync_special_sheets(spreadsheet, conn)
		await _sync_buddies_sheet(spreadsheet.get_sheet("Buddying", block=0), conn)
		await _sync_arcana_sheet(spreadsheet.get_sheet("Arcana Special", block=0), conn)
		await _sync_aids_sheet(spreadsheet.get_sheet("Aid Parade", block=0), conn, ctx)

		try:
			fantasy_sheet = await fetch_sheets(FANTASY_SPREADSHEET_ID, "Draft Picks!A1:L312")
			await _sync_fantasy_sheet(fantasy_sheet, conn)
		except aiohttp.ClientResponseError:
			pass  # Ignore response errors for fantasy sheet

		await sync_media_data(conn, ctx)  # In case of missing media ids sync at the end
