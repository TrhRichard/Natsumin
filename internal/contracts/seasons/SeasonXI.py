from __future__ import annotations

from internal.contracts.sheet import fetch_sheets, PATTERNS, Spreadsheet, SheetBlock
from internal.enums import UserStatus, UserKind, ContractStatus, ContractKind
from internal.contracts.rep import get_rep, RepName
from internal.functions import get_user_id
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import uuid4

import aiosqlite
import aiohttp
import re

if TYPE_CHECKING:
	from internal.database import NatsuDatabase

SEASON_SPREADSHEET_ID = "1AJLtpQ0KcFo7hecX2GSpv_aXGL1zKu5LbScGxxVpVGU"
FANTASY_SPREADSHEET_ID = "1LaaERlU7vlDdpdu-1XvIU1Hn0jvvmeU-hqHObbE4wHA"
SEASON_ID = "season_xi"

DASHBOARD_ROW_INDEXES: dict[str, tuple[str, str]] = {
	"D": ("Token #1", "Q"),
	"E": ("Token #2", "R"),
	"F": ("Token #3", "S"),
	"G": ("Token #4", "T"),
	"H": ("Token #5", "U"),
	"I": ("Token #6", "V"),
	"J": ("Free Spin", "W"),
	"L": ("Extreme Special", "Y"),
	"M": ("Base Buddy", "Z"),
	"N": ("Challenge Buddy", "AA"),
}
OPTIONAL_CONTRACTS: tuple[str, ...] = "Extreme Special"

WHEEL_TO_TYPE = {
	"Personal Wheel": "Personal Wheel",
	"Yuzuki (VN)": "Yuzuki Wheel",
	"Shiori (LN)": "Shiori Wheel",
	"Kimiko (Trash)": "Kimiko Wheel",
	"Kohana (Short Stories)": "Kohana Wheel",
	"Rei (Old School)": "Rei Wheel",
	"Rio (New Anime)": "Rio Anime Wheel",
	"Rio (New Manga)": "Rio Manga Wheel",
	"Sumira (Manga)": "Sumira Wheel",
	"Yume (Manhwa)": "Yume Wheel",
	"Uta (Manhua/Donghua)": "Uta Wheel",
	"Kirburger (Servers)": "Kirburger Wheel",
	"Momo (Popular)": "Momo Wheel",
	"MVR Wheel": "MVR Wheel",
	"Aria (Indie Games)": "Aria Wheel",
	"Premium (AAA Games)": "Premium Wheel",
	"Co-Op Games": "Co-Op Game Wheel",
	"Discount Games": "Discount Game Wheel",
	"Casual Games": "Casual Game Wheel",
	"Aria's Classics (Games)": "Aria Classic Wheel",
	"Nozomi (Cooking)": "Nozomi Wheel",
	"Anzu (Baking)": "Anzu Wheel",
	"Umika (Music)": "Umika Wheel",
	"Frazzle Around the World": "Frazzle Wheel",
	"Hitome (Black Market)": "Hitome Wheel",
	"Sumira's Gems (Manga)": "Sumira Gem Wheel",
}
TYPE_TO_TOKEN = {
	"Token 1": "Token #1",
	"Token 2": "Token #2",
	"Token 3": "Token #3",
	"Token 4": "Token #4",
	"Token 5": "Token #5",
	"Token 6": "Token #6",
	"Free Token": "Free Spin",
}  # fuck do i name these


async def _sync_dashboard_sheet(dashboard_sheet: SheetBlock, conn: aiosqlite.Connection):
	for row in dashboard_sheet.rows:
		status = row.get_value("A", "")
		username = row.get_value("B", "").strip().lower()
		rep = row.get_value("C", "").strip()
		if not username:
			continue

		user_id = await get_user_id(conn, username)
		if not user_id:
			user_id = str(uuid4())
			await conn.execute("INSERT INTO user (id, username) VALUES (?, ?)", (user_id, username))

		async with conn.execute("SELECT rep FROM user WHERE id = ?", (user_id,)) as cursor:
			rep_row = await cursor.fetchone()
			user_global_rep = get_rep(rep_row["rep"]) if rep_row and rep_row["rep"] is not None else None

		user_season_rep = get_rep(rep)
		if user_global_rep is None and user_season_rep:
			await conn.execute("UPDATE user SET rep = ? WHERE id = ?", (user_season_rep.value, user_id))

		if user_season_rep is None:
			user_season_rep = RepName.UNKNOWN

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
				"INSERT INTO season_user (season_id, user_id, status, kind, rep) VALUES (?, ?, ?, ?, ?) RETURNING *",
				(SEASON_ID, user_id, user_status.value, UserKind.NORMAL.value, user_season_rep.value),
			) as cursor:
				user_row = await cursor.fetchone()
		else:
			if user_row["status"] != user_status:
				await conn.execute("UPDATE season_user SET status = ? WHERE season_id = ? AND user_id = ?", (user_status.value, SEASON_ID, user_id))
			if user_row["rep"] != user_season_rep.value:
				await conn.execute("UPDATE season_user SET rep = ? WHERE season_id = ? AND user_id = ?", (user_season_rep.value, SEASON_ID, user_id))

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

			async with conn.execute(
				"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, contract_type)
			) as cursor:
				contract_row = await cursor.fetchone()

			if not contract_row:
				contract_id = str(uuid4())
				async with conn.execute(
					"INSERT INTO season_contract (season_id, id, name, type, kind, status, contractee_id, optional) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
					(
						SEASON_ID,
						contract_id,
						contract_name,
						contract_type,
						ContractKind.NORMAL.value,
						contract_status.value,
						user_id,
						contract_type in OPTIONAL_CONTRACTS,
					),
				) as cursor:
					contract_row = await cursor.fetchone()
			else:
				contract_id: str = contract_row["id"]
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (contract_status.value, contract_id))
				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))

	await conn.commit()


async def _sync_base_sheet(base_sheet: SheetBlock, conn: aiosqlite.Connection):
	user_counts: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))

	for row in base_sheet.rows:
		username = row.get_value("B", "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		contract_name = row.get_value("E", "").strip().replace("\n", ", ")
		if not contract_name:
			continue

		status = row.get_value("A", "").strip().upper()
		contract_type = row.get_value("C", "").strip()
		contract_wheel = row.get_value("D", "").strip()
		type_wheel = WHEEL_TO_TYPE.get(contract_wheel)
		if type_wheel is None:
			continue

		match status:
			case "PASSED":
				contract_status = ContractStatus.PASSED
			case "FAILED":
				contract_status = ContractStatus.FAILED
			case "UNVERIFIED":
				contract_status = ContractStatus.UNVERIFIED
			case "LATE PASS":
				contract_status = ContractStatus.LATE_PASS
			case _:
				contract_status = ContractStatus.PENDING

		contractor = row.get_value("F", "").strip().lower().replace("\n", ", ")
		contract_progress = row.get_value("H", "").strip()
		contract_rating = row.get_value("I", "").strip()
		contract_review_url = row.get_value("J", "").strip()

		if contract_type.lower() == "bonus":
			wheels_count = user_counts[user_id]
			type_count = wheels_count[type_wheel]
			type_count += 1

			full_contract_type = f"{type_wheel} {type_count}"

			async with conn.execute(
				"SELECT 1 FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, full_contract_type)
			) as cursor:
				contract_exists = await cursor.fetchone() is not None

			wheels_count[type_wheel] = type_count
			if not contract_exists:
				query = """
					INSERT INTO season_contract 
						(season_id, id, name, type, kind, status, contractee_id, contractor, progress, rating, review_url) 
					VALUES 
						(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				"""

				await conn.execute(
					query,
					(
						SEASON_ID,
						str(uuid4()),
						contract_name,
						full_contract_type,
						ContractKind.NORMAL.value,
						contract_status,
						user_id,
						contractor,
						contract_progress,
						contract_rating,
						contract_review_url,
					),
				)
			else:
				async with conn.execute(
					"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, full_contract_type)
				) as cursor:
					contract_row = await cursor.fetchone()
					contract_id: str = contract_row["id"]

				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (contract_status.value, contract_id))
				if contract_row["contractor"] != contractor:
					await conn.execute("UPDATE season_contract SET contractor = ? WHERE id = ?", (contractor, contract_id))
				if contract_row["review_url"] != contract_review_url:
					await conn.execute("UPDATE season_contract SET review_url = ? WHERE id = ?", (contract_review_url, contract_id))
				if contract_row["progress"] != contract_progress:
					await conn.execute("UPDATE season_contract SET progress = ? WHERE id = ?", (contract_progress, contract_id))
				if contract_row["rating"] != contract_rating:
					await conn.execute("UPDATE season_contract SET rating = ? WHERE id = ?", (contract_rating, contract_id))
		else:
			token_type = TYPE_TO_TOKEN.get(contract_type)
			if token_type is None:
				continue

			async with conn.execute(
				"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, token_type)
			) as cursor:
				contract_row = await cursor.fetchone()
				contract_id: str = contract_row["id"]
				contract_type_label = f"{token_type} - {type_wheel}"

				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (contract_status.value, contract_id))
				if contract_row["contractor"] != contractor:
					await conn.execute("UPDATE season_contract SET contractor = ? WHERE id = ?", (contractor, contract_id))
				if contract_row["review_url"] != contract_review_url:
					await conn.execute("UPDATE season_contract SET review_url = ? WHERE id = ?", (contract_review_url, contract_id))
				if contract_row["progress"] != contract_progress:
					await conn.execute("UPDATE season_contract SET progress = ? WHERE id = ?", (contract_progress, contract_id))
				if contract_row["type_label"] != contract_type_label:
					await conn.execute("UPDATE season_contract SET type_label = ? WHERE id = ?", (contract_type_label, contract_id))

	await conn.commit()


async def _sync_specials_sheet(spreadsheet: Spreadsheet, conn: aiosqlite.Connection):
	# Extreme Special
	for row in spreadsheet.get_sheet("Extreme Special", block=0).rows:
		username = row.get_value("C", "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Extreme Special"),
		) as cursor:
			contract_row = await cursor.fetchone()

		if not contract_row:
			continue

		if contract_row["rating"] != row.get_value("F", "0/10") or contract_row["review_url"] != row.get_url("G"):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, rating = ?, review_url = ?, medium = ? WHERE id = ?",
				(
					row.get_value("E", "frazzle_dazzle").strip().lower(),  # contractor
					row.get_value("F", "0/10"),  # rating
					row.get_url("G"),  # review_url
					"Game",  # medium,
					contract_row["id"],
				),
			)

	await conn.commit()


async def _sync_buddies_sheet(buddy_sheet: SheetBlock, conn: aiosqlite.Connection):
	for row in buddy_sheet.rows:
		username = row.get_value("C", "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		async with conn.execute(
			"SELECT id, rating, progress, review_url FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?",
			(SEASON_ID, user_id, "Base Buddy"),
		) as cursor:
			base_buddy_row = await cursor.fetchone()

		if base_buddy_row and (
			base_buddy_row["rating"] != row.get_value("M", "0/10")
			or base_buddy_row["progress"] != row.get_value("K", "").replace("\n", "")
			or base_buddy_row["review_url"] != row.get_url("O")
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value("G", "").strip().lower(),  # contractor
					row.get_value("K", "").replace("\n", ""),  # progress
					row.get_value("M", "0/10"),  # rating
					row.get_url("O"),  # review_url
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value("H", "")),  # medium,
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
			challenge_buddy_row["rating"] != row.get_value("N", "0/10")
			or challenge_buddy_row["progress"] != row.get_value("L", "").replace("\n", "")
			or challenge_buddy_row["review_url"] != row.get_url("P")
		):
			await conn.execute(
				"UPDATE season_contract SET contractor = ?, progress = ?, rating = ?, review_url = ?, medium = ? WHERE season_id = ? AND id = ?",
				(
					row.get_value("I", "").strip().lower(),  # contractor
					row.get_value("L", "").replace("\n", ""),  # progress
					row.get_value("N", "0/10"),  # rating
					row.get_url("P"),  # review_url
					re.sub(PATTERNS.NAME_MEDIUM, r"\2", row.get_value("J", "")),  # medium,
					SEASON_ID,
					challenge_buddy_row["id"],
				),
			)

	await conn.commit()


async def _sync_midseason_sheet(midseason_sheet: SheetBlock, conn: aiosqlite.Connection):
	for row in midseason_sheet.rows:
		username = row.get_value("B", "").strip().lower()

		user_id = await get_user_id(conn, username)
		if not user_id:
			continue

		contract_name = row.get_value("E", "").strip().replace("\n", ", ")
		if not contract_name:
			continue

		status = row.get_value("A", "").strip().upper()
		contract_type = row.get_value("C", "").strip()
		contract_name = row.get_value("D", "").strip()

		match status:
			case "PASSED":
				contract_status = ContractStatus.PASSED
			case "FAILED":
				contract_status = ContractStatus.FAILED
			case "UNVERIFIED":
				contract_status = ContractStatus.UNVERIFIED
			case "LATE PASS":
				contract_status = ContractStatus.LATE_PASS
			case _:
				contract_status = ContractStatus.PENDING

		contract_rating = row.get_value("E", "").strip()
		contract_review_url = row.get_value("F", "").strip()

		async with conn.execute(
			"SELECT 1 FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, contract_type)
		) as cursor:
			contract_exists = await cursor.fetchone() is not None

		if not contract_exists:
			query = """
				INSERT INTO season_contract 
					(season_id, id, name, type, kind, status, contractee_id, rating, review_url) 
				VALUES 
					(?, ?, ?, ?, ?, ?, ?, ?, ?)
			"""
			await conn.execute(
				query,
				(
					SEASON_ID,
					str(uuid4()),
					contract_name,
					contract_type,
					ContractKind.NORMAL.value,
					contract_status,
					user_id,
					contract_rating,
					contract_review_url,
				),
			)
		else:
			async with conn.execute(
				"SELECT * FROM season_contract WHERE season_id = ? AND contractee_id = ? AND type = ?", (SEASON_ID, user_id, contract_type)
			) as cursor:
				contract_row = await cursor.fetchone()
				contract_id: str = contract_row["id"]

				if contract_row["name"] != contract_name:
					await conn.execute("UPDATE season_contract SET name = ? WHERE id = ?", (contract_name, contract_id))
				if contract_row["status"] != contract_status:
					await conn.execute("UPDATE season_contract SET status = ? WHERE id = ?", (contract_status.value, contract_id))
				if contract_row["review_url"] != contract_review_url:
					await conn.execute("UPDATE season_contract SET review_url = ? WHERE id = ?", (contract_review_url, contract_id))
				if contract_row["rating"] != contract_rating:
					await conn.execute("UPDATE season_contract SET rating = ? WHERE id = ?", (contract_rating, contract_id))

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
						raise RuntimeError(f"No ID found for {rows[i].get_value(2)}")

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


async def sync_season(database: NatsuDatabase):
	spreadsheet = await fetch_sheets(
		SEASON_SPREADSHEET_ID, ["Dashboard!A2:AA330", "Base!A2:J2857", "Extreme Special!A2:G84", "Buddying!A2:P329", "Mid-Season Drops!A2:F350"]
	)

	async with database.connect() as conn:
		await _sync_dashboard_sheet(spreadsheet.get_sheet("Dashboard", block=0), conn)
		await _sync_base_sheet(spreadsheet.get_sheet("Base", block=0), conn)
		await _sync_specials_sheet(spreadsheet, conn)
		await _sync_buddies_sheet(spreadsheet.get_sheet("Buddying", block=0), conn)
		await _sync_midseason_sheet(spreadsheet.get_sheet("Mid-Season Drops", block=0), conn)

		try:
			fantasy_sheet = await fetch_sheets(FANTASY_SPREADSHEET_ID, "Draft Picks!A1:M500")
			await _sync_fantasy_sheet(fantasy_sheet, conn)
		except aiohttp.ClientResponseError:
			pass  # Ignore response errors for fantasy sheet
