from ..classes import SeasonDB, ContractKind, ContractStatus, UserStatus, UserKind, MasterDB, Contract, SeasonDBSyncContext
from utils import get_cell, get_rep
from async_lru import alru_cache
import aiohttp
import re
import os

SPREADSHEET_ID = "1ZuhNuejQ3gTKuZPzkGg47-upLUlcgNfdW2Jrpeq8cak"
DB_PATH = "data/seasons/SeasonX.db"


async def _get_sheet_data() -> dict:
	async with aiohttp.ClientSession(headers={"Accept-Encoding": "gzip, deflate"}) as session:
		async with session.get(
			f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values:batchGet",
			params={
				"majorDimension": "ROWS",
				"valueRenderOption": "FORMATTED_VALUE",
				"ranges": [
					"Dashboard!A2:V508",
					"Base!A2:AH516",
					"Duality Special!A2:I291",
					"Veteran Special!A2:J280",
					"Epoch Special!A2:I237",
					"Honzuki Special!A2:G171",
					"Aria Special!A2:G149",
					"Arcana Special!A2:K588",
					# TODO: Implement buddy
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
	3: "Duality Special",
	4: "Epoch Special",
	5: "Honzuki Special",
	6: "Aria Special",
	7: "Arcana Special",
	8: "Base Buddy",
	9: "Challenge Buddy",
}
OPTIONAL_CONTRACTS: list[str] = ["Aria Special"]


async def _sync_dashboard_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	dashboard_rows: list[list[str]] = sheet_data["valueRanges"][0]["values"]

	for row in dashboard_rows:
		status = get_cell(row, 0, "")
		username = get_cell(row, 1, "").strip().lower()
		contract_names = row[2:11]
		contract_passed = row[13:21]

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
			if re.match(r"\d+\/\d+", contract_name):  # Ignore Arcana Souls
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
				if contract_data.name != contract_name:
					ctx.update_contract(contract_data, name=contract_name)
			else:
				ctx.create_contract(name=contract_name, type=contract_type, kind=ContractKind.NORMAL, status=contract_status, contractee=user_id)

	await ctx.commit()


async def _sync_basechallenge_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	base_challenge_rows: list[list[str]] = sheet_data["valueRanges"][1]["values"]

	for row in base_challenge_rows:
		username = get_cell(row, 3, "").strip().lower()
		contractor = get_cell(row, 5, "").strip().lower()

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
				list_url=get_url(row, 8),
				veto_used=get_cell(row, 12, "FALSE") == "TRUE",
				preferences=get_cell(row, 18, "N/A").replace("\n", ", "),
				bans=get_cell(row, 19, "N/A").replace("\n", ", "),
				accepting_manhwa=get_cell(row, 9, "N/A") == "Yes",
				accepting_ln=get_cell(row, 10, "N/A") == "Yes",
			)

		if user_id in ctx.master_users_created:
			await ctx.master_db.update_user(user_id, rep=season_user.rep)

		user_contracts = ctx.get_user_contracts(user_id, True)

		base_contract = user_contracts.get("Base Contract")

		if (
			base_contract.progress != get_cell(row, 31, "?/?").replace("\n", "")
			or base_contract.rating != get_cell(row, 28, "0/10")
			or base_contract.review_url != get_url(row, 33)
		):
			ctx.update_contract(
				base_contract,
				contractor=contractor,
				progress=get_cell(row, 31, "?/?").replace("\n", ""),
				rating=get_cell(row, 28, "0/10"),
				review_url=get_url(row, 33),
				medium=get_cell(row, 7),
				optional=False,
			)
		if challenge_contract := user_contracts.get("Challenge Contract"):
			if (
				challenge_contract.progress != get_cell(row, 32, "?/?").replace("\n", "")
				or challenge_contract.rating != get_cell(row, 30, "0/10")
				or challenge_contract.review_url != get_url(row, 34)
			):
				ctx.update_contract(
					challenge_contract,
					contractor=contractor,
					progress=get_cell(row, 32, "?/?").replace("\n", ""),
					rating=get_cell(row, 30, "0/10"),
					review_url=get_url(row, 34),
					medium=get_cell(row, 15),
					optional=False,
				)

	await ctx.commit()


async def _sync_specials_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	users_contracts: dict[int, dict[str, Contract]] = {}
	for contract in ctx.total_contracts:
		users_contracts.setdefault(contract.contractee, {})[contract.type] = contract

	# Duality Special
	rows: list[list[str]] = sheet_data["valueRanges"][2]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		duality_special = user_contracts.get("Duality Special")
		if (
			duality_special.rating != get_cell(row, 9, "0/10")
			or duality_special.progress != get_cell(row, 8, "")
			or duality_special.review_url != get_url(row, 10)
		):
			ctx.update_contract(
				duality_special,
				contractor=get_cell(row, 6, "frazzle").strip().lower(),
				progress=get_cell(row, 8, ""),
				rating=get_cell(row, 9, "0/10"),
				review_url=get_url(row, 10),
				optional=duality_special.type in OPTIONAL_CONTRACTS,
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4)),
			)

	# Veteran Special
	rows: list[list[str]] = sheet_data["valueRanges"][3]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		veteran_special = user_contracts.get("Veteran Special")
		if (
			veteran_special.progress != get_cell(row, 7, "?/?")
			or veteran_special.rating != get_cell(row, 8, "0/10")
			or veteran_special.review_url != get_url(row, 9)
		):
			ctx.update_contract(
				veteran_special,
				contractor=get_cell(row, 5).strip().lower(),
				progress=get_cell(row, 7, "?/?"),
				rating=get_cell(row, 8, "0/10"),
				review_url=get_url(row, 9),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4)),
				optional=veteran_special.type in OPTIONAL_CONTRACTS,
			)

	# Epoch Special
	rows: list[list[str]] = sheet_data["valueRanges"][4]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		epoch_special = user_contracts.get("Epoch Special")
		if (
			epoch_special.rating != get_cell(row, 9, "0/10")
			or epoch_special.progress != get_cell(row, 8, "")
			or epoch_special.review_url != get_url(row, 10)
		):
			ctx.update_contract(
				epoch_special,
				contractor=get_cell(row, 6, "").strip().lower(),
				progress=get_cell(row, 8, ""),
				rating=get_cell(row, 9, "0/10"),
				review_url=get_url(row, 10),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4)),
				optional=epoch_special.type in OPTIONAL_CONTRACTS,
			)

	# Honzuki Special
	rows: list[list[str]] = sheet_data["valueRanges"][5]["values"]
	for row in rows:
		username = get_cell(row, 3, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		honzuki_special = user_contracts.get("Honzuki Special")
		if (
			honzuki_special.rating != get_cell(row, 5, "0/10")
			or honzuki_special.progress != get_cell(row, 7, "")
			or honzuki_special.review_url != get_url(row, 8)
		):
			ctx.update_contract(
				honzuki_special,
				rating=get_cell(row, 5, "0/10"),
				progress=get_cell(row, 7, ""),
				review_url=get_url(row, 8),
				medium="LN",
				optional=epoch_special.type in OPTIONAL_CONTRACTS,
			)

	# Aria Special
	rows: list[list[str]] = sheet_data["valueRanges"][6]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		aria_special = user_contracts.get("Aria Special")
		if aria_special.rating != get_cell(row, 5, "0/10") or aria_special.review_url != get_url(row, 6):
			ctx.update_contract(
				aria_special,
				contractor=get_cell(row, 4, "").strip().lower(),
				rating=get_cell(row, 5, "0/10"),
				review_url=get_url(row, 6),
				medium="Game",
				optional=epoch_special.type in OPTIONAL_CONTRACTS,
			)

	await ctx.commit()


async def _sync_arcana_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	pass


async def _sync_aids_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	pass


async def sync_to_latest(season_db: SeasonDB):
	ctx = SeasonDBSyncContext(season_db)
	await ctx.setup()
	sheet_data = await _get_sheet_data()

	await _sync_dashboard_data(sheet_data, ctx)
	await _sync_basechallenge_data(sheet_data, ctx)
	await _sync_specials_data(sheet_data, ctx)
	await _sync_arcana_data(sheet_data, ctx)


@alru_cache
async def get_database() -> SeasonDB:
	master_db = MasterDB.get_database()
	season_db = SeasonDB("Season X", DB_PATH, master_db)
	await season_db.setup()

	return season_db
