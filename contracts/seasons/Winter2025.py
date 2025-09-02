from ..classes import SeasonDB, ContractKind, ContractStatus, UserStatus, UserKind, MasterDB, Contract, SeasonDBSyncContext
from utils import get_cell, get_rep
from async_lru import alru_cache
import aiohttp
import re
import os

SPREADSHEET_ID = "19aueoNx6BBU6amX7DhKGU8kHVauHWcSGiGKMzFSGkGc"
DB_PATH = "data/seasons/Winter2025.db"


async def _get_sheet_data() -> dict:
	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values:batchGet",
			params={
				"majorDimension": "ROWS",
				"valueRenderOption": "FORMATTED_VALUE",
				"ranges": [
					"Dashboard!A2:U394",
					"Base!A2:AG394",
					"Veteran Special!A2:I167",
					"VN Special!A2:G126",
					"Movie Special!A2:H243",
					"Indie Special!A2:H136",
					"Extreme Special!A2:G95",
					"Buddying!A2:N68",
					"Odds!A1:B49",
					"Aid Contracts!A5:H90",
				],
				"key": os.getenv("GOOGLE_API_KEY"),
			},
		) as response:
			response.raise_for_status()
			sheet_data = await response.json()
			return sheet_data


def _get_first_url(text: str) -> str:
	match = re.search(r"(https?:\/\/[^\s]+)", text)
	if match:
		return match.group(0)
	return ""


def get_url(row: list[str], i: int) -> str:
	return _get_first_url(get_cell(row, i, "", str))


NAME_MEDIUM_REGEX = r"(.*) \((.*)\)"
DASHBOARD_ROW_NAMES = {
	0: "Base Contract",
	1: "Challenge Contract",
	2: "Veteran Special",
	3: "Movie Special",
	4: "VN Special",
	5: "Indie Special",
	6: "Extreme Special",
	7: "Base Buddy",
	8: "Challenge Buddy",
}
OPTIONAL_CONTRACTS = ["Extreme Special"]


async def _sync_dashboard_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	dashboard_rows: list[list[str]] = sheet_data["valueRanges"][0]["values"]

	for row in dashboard_rows:
		status = row[0]
		username = row[1].strip().lower()
		contract_names = row[2:11]
		contract_passed = row[12:21]

		user_id = ctx.get_user_id(username)
		if not user_id:
			user_id = await ctx.create_master_user(username)

		user_status: UserStatus
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

		season_user, existed_already = ctx.get_or_create_user(user_id, kind=UserKind.NORMAL, status=user_status)

		if existed_already:
			if season_user.status != user_status:
				ctx.update_user(season_user, status=user_status)

		user_contracts = ctx.get_user_contracts(user_id, True)

		for i, contract_name in enumerate(contract_names):
			contract_type = DASHBOARD_ROW_NAMES[i]

			if contract_name == "-":
				continue

			contract_name = contract_name.strip().replace("\n", "")

			contract_status = (
				ContractStatus.PASSED
				if "PASSED" in get_cell(contract_passed, i, "", str)
				else ContractStatus.FAILED
				if "FAILED" in get_cell(contract_passed, i, "", str)
				else ContractStatus.LATE_PASS
				if "LATE PASS" in get_cell(contract_passed, i, "", str)
				else ContractStatus.PENDING
			)

			if contract_data := user_contracts.get(contract_type):
				if contract_data.status != contract_status:
					ctx.update_contract(contract_data, status=contract_status)
			else:
				ctx.create_contract(name=contract_name, type=contract_type, kind=ContractKind.NORMAL, status=contract_status, contractee=user_id)

	await ctx.commit()


async def _sync_basechallenge_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	base_challenge_rows: list[list[str]] = sheet_data["valueRanges"][1]["values"]

	for row in base_challenge_rows:
		username = row[3].strip().lower()
		contractor = row[5].strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		if season_user.contractor != contractor or season_user.veto_used != (get_cell(row, 10) == "TRUE"):
			ctx.update_user(
				season_user,
				contractor=contractor,
				rep=get_rep(get_cell(row, 2, "")),
				list_url=get_url(row, 7),
				veto_used=get_cell(row, 10) == "TRUE",
				preferences=get_cell(row, 16).replace("\n", ", "),
				bans=get_cell(row, 17).replace("\n", ", "),
				accepting_manhwa=get_cell(row, 18) == "Yes",
				accepting_ln=get_cell(row, 19) == "Yes",
			)

		user_contracts = ctx.get_user_contracts(user_id, True)

		base_contract = user_contracts.get("Base Contract")

		if (
			base_contract.progress != get_cell(row, 29, "?/?").replace("\n", "")
			or base_contract.rating != get_cell(row, 26, "")
			or base_contract.review_url != get_url(row, 31)
		):
			ctx.update_contract(
				base_contract,
				contractor=contractor,
				progress=get_cell(row, 29, "?/?").replace("\n", ""),
				rating=get_cell(row, 26),
				review_url=get_url(row, 31),
				medium=get_cell(row, 9),
				optional=False,
			)
		if challenge_contract := user_contracts.get("Challenge Contract"):
			if (
				challenge_contract.progress != get_cell(row, 30, "?/?").replace("\n", "")
				or challenge_contract.rating != get_cell(row, 28, "")
				or challenge_contract.review_url != get_url(row, 32)
			):
				ctx.update_contract(
					challenge_contract,
					contractor=contractor,
					progress=get_cell(row, 30, "?/?").replace("\n", ""),
					rating=get_cell(row, 28),
					review_url=get_url(row, 32),
					medium=get_cell(row, 13),
					optional=False,
				)

	await ctx.commit()


async def _sync_specials_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	rows: list[list[str]] = sheet_data["valueRanges"][2]["values"]

	users_contracts: dict[int, dict[str, Contract]] = {}
	for contract in ctx.total_contracts:
		users_contracts.setdefault(contract.contractee, {})[contract.type] = contract

	# Veteran Special
	for row in rows:
		username = row[2].strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		veteran_special = user_contracts.get("Veteran Special")
		if (
			veteran_special.progress != get_cell(row, 6, "?/?")
			or veteran_special.rating != get_cell(row, 7)
			or veteran_special.review_url != get_url(row, 8)
		):
			ctx.update_contract(
				veteran_special,
				contractor=get_cell(row, 4).strip().lower(),
				progress=get_cell(row, 6, "?/?"),
				rating=get_cell(row, 7),
				review_url=get_url(row, 8),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 3)),
				optional=veteran_special.type in OPTIONAL_CONTRACTS,
			)

	# VN Special
	rows: list[list[str]] = sheet_data["valueRanges"][3]["values"]
	for row in rows:
		username = row[2].strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		vn_special = user_contracts.get("VN Special")
		if vn_special.rating != get_cell(row, 5) or vn_special.review_url != get_url(row, 6):
			ctx.update_contract(
				vn_special,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if vn_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="VN",
				optional=vn_special.type in OPTIONAL_CONTRACTS,
			)

	# Movie Special
	rows: list[list[str]] = sheet_data["valueRanges"][4]["values"]
	for row in rows:
		username = row[2].strip().lower()
		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		movie_special = user_contracts.get("Movie Special")
		if movie_special.rating != get_cell(row, 5) or movie_special.review_url != get_url(row, 6):
			ctx.update_contract(
				movie_special,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if movie_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="Movie",
				optional=movie_special.type in OPTIONAL_CONTRACTS,
			)

	# Indie Special
	rows: list[list[str]] = sheet_data["valueRanges"][5]["values"]
	for row in rows:
		username = row[2].strip().lower()
		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		indie_special = user_contracts.get("Indie Special")
		if indie_special.progress != get_cell(row, 5) or indie_special.rating != get_cell(row, 6) or indie_special.review_url != get_url(row, 7):
			ctx.update_contract(
				indie_special,
				contractor=get_cell(row, 4).strip().lower(),
				progress=get_cell(row, 5),
				rating=get_cell(row, 6),
				review_url=get_url(row, 7),
				medium="Game",
				optional=indie_special in OPTIONAL_CONTRACTS,
			)

	# Extreme Special
	rows: list[list[str]] = sheet_data["valueRanges"][6]["values"]
	for row in rows:
		username = row[2].strip().lower()
		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		extreme_special = user_contracts.get("Extreme Special")
		if extreme_special.rating != get_cell(row, 5) or extreme_special.review_url != get_url(row, 6):
			ctx.update_contract(
				extreme_special,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if extreme_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="Movie",
				optional=extreme_special.type in OPTIONAL_CONTRACTS,
			)

	# Buddying
	rows: list[list[str]] = sheet_data["valueRanges"][7]["values"]
	for row in rows:
		username = row[2].strip().lower()
		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		if base_buddy := user_contracts.get("Base Buddy"):
			if base_buddy.progress != get_cell(row, 8, "?/?") or base_buddy.rating != get_cell(row, 10) or base_buddy.review_url != get_url(row, 12):
				ctx.update_contract(
					base_buddy,
					contractor=get_cell(row, 4).strip().lower(),
					progress=get_cell(row, 8, "?/?"),
					rating=get_cell(row, 10),
					review_url=get_url(row, 12),
					medium="Anime / Manga",
					optional=base_buddy.type in OPTIONAL_CONTRACTS,
				)
		if challenge_buddy := user_contracts.get("Challenge Buddy"):
			if (
				challenge_buddy.progress != get_cell(row, 9, "?/?")
				or challenge_buddy.rating != get_cell(row, 11)
				or challenge_buddy.review_url != get_url(row, 13)
			):
				ctx.update_contract(
					challenge_buddy,
					contractor=get_cell(row, 6).strip().lower(),
					progress=get_cell(row, 9, "?/?"),
					rating=get_cell(row, 11),
					review_url=get_url(row, 13),
					medium="Anime / Manga",
					optional=challenge_buddy.type in OPTIONAL_CONTRACTS,
				)

	await ctx.commit()


async def _sync_aids_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	rows: list[list[str]] = sheet_data["valueRanges"][9]["values"]

	aids_user_count: dict[int, int] = {}
	for row in rows:
		username = get_cell(row, 1, "").strip().lower()
		contractor = get_cell(row, 3, "").strip().lower()

		if not username:
			continue

		user_id = ctx.get_user_id(username)
		if not user_id:
			user_id = await ctx.create_master_user(username)

		_, _ = ctx.get_or_create_user(user_id, kind=UserKind.AID, status=UserStatus.PENDING)

		user_contracts = ctx.get_user_contracts(user_id, True)

		if user_id not in aids_user_count:
			aids_user_count[user_id] = 0
		aids_user_count[user_id] += 1
		contract_type = f"Aid Contract {aids_user_count[user_id]}"

		aid_name = get_cell(row, 6).replace("\n", "")

		contract_status: ContractStatus
		if get_cell(row, 0) == "PASSED":
			contract_status = ContractStatus.PASSED
		elif get_cell(row, 0) == "FAILED":
			contract_status = ContractStatus.FAILED
		else:
			contract_status = ContractStatus.PENDING

		if e_contract := user_contracts.get(contract_type):
			if (
				e_contract.name != aid_name
				or e_contract.progress != get_cell(row, 5)
				or e_contract.contractor != contractor
				or e_contract.rating != get_cell(row, 4)
				or e_contract.review_url != get_url(row, 7)
			):
				ctx.update_contract(
					e_contract,
					name=aid_name,
					status=contract_status,
					progress=get_cell(row, 5),
					rating=get_cell(row, 4),
					review_url=get_url(row, 7),
					contractor=contractor,
				)
		else:
			ctx.create_contract(
				name=aid_name,
				type=contract_type,
				kind=ContractKind.AID,
				status=contract_status,
				contractee=user_id,
				progress=get_cell(row, 5),
				rating=get_cell(row, 4),
				review_url=get_url(row, 7),
				contractor=contractor,
				optional=False,
			)

	await ctx.commit()


async def sync_to_latest(season_db: SeasonDB):
	ctx = SeasonDBSyncContext(season_db)
	await ctx.setup()
	sheet_data = await _get_sheet_data()

	await _sync_dashboard_data(sheet_data, ctx)
	await _sync_basechallenge_data(sheet_data, ctx)
	await _sync_specials_data(sheet_data, ctx)
	await _sync_aids_data(sheet_data, ctx)


@alru_cache
async def get_database() -> SeasonDB:
	master_db = MasterDB.get_database()
	season_db = SeasonDB("Winter 2025", DB_PATH, master_db)
	await season_db.setup()

	return season_db
