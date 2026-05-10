from __future__ import annotations

from internal.contracts.sheet import sync_media_data, fetch_sheets, PATTERNS, SyncContext, Spreadsheet, SheetBlock, Row
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
	from internal.database import NatsuminDatabase
	from typing import Literal

SEASON_SPREADSHEET_ID = ""
FANTASY_SPREADSHEET_ID = "1LaaERlU7vlDdpdu-1XvIU1Hn0jvvmeU-hqHObbE4wHA"
SEASON_ID = "season_xi"

OPTIONAL_CONTRACTS: tuple[str, ...] = tuple()


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


async def sync_season(database: NatsuminDatabase):
	async with database.connect() as conn:
		try:
			fantasy_sheet = await fetch_sheets(FANTASY_SPREADSHEET_ID, "Draft Picks!A1:M500")
			await _sync_fantasy_sheet(fantasy_sheet, conn)
		except aiohttp.ClientResponseError:
			pass  # Ignore response errors for fantasy sheet
