from ..classes import SeasonDB, ContractKind, ContractStatus, UserStatus, UserKind, MasterDB, Contract, SeasonDBSyncContext
from utils import get_cell, get_rep
from async_lru import alru_cache
from typing import Literal
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
					"Dashboard!A2:Y508",
					"Base!A2:AI516",
					"Duality Special!A2:K291",
					"Veteran Special!A2:J280",
					"Epoch Special!A2:K237",
					"Honzuki Special!A2:I171",
					"Aria Special!A2:G149",
					"Arcana Special!A2:N1400",
					"Buddying!A2:N100",
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
DASHBOARD_ROW_INDEXES: dict[int, tuple[str, int]] = {
	2: ("Base Contract", 14),
	3: ("Challenge Contract", 15),
	4: ("Veteran Special", 16),
	5: ("Duality Special", 17),
	6: ("Epoch Special", 18),
	7: ("Honzuki Special", 19),
	8: ("Aria Special", 20),
	10: ("Base Buddy", 21),
	11: ("Challenge Buddy", 22),
	12: ("Sumira's Challenge", 23),
}
OPTIONAL_CONTRACTS: list[str] = ["Aria Special"]


async def _sync_dashboard_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	dashboard_rows: list[list[str]] = sheet_data["valueRanges"][0]["values"]

	for row in dashboard_rows:
		status = get_cell(row, 0, "")
		username = get_cell(row, 1, "").strip().lower()

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

		for column, (contract_type, passed_column) in DASHBOARD_ROW_INDEXES.items():
			contract_name = get_cell(row, column, "-").strip().replace("\n", "")

			if contract_name == "-":
				continue

			contract_status = (
				ContractStatus.PASSED
				if "PASSED" in get_cell(row, passed_column, "", str)
				else ContractStatus.FAILED
				if "FAILED" in get_cell(row, passed_column, "", str)
				else ContractStatus.LATE_PASS
				if "LATE PASS" in get_cell(row, passed_column, "", str)
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

		if season_user.contractor != contractor or season_user.veto_used != (get_cell(row, 12) == "TRUE"):
			ctx.update_user(
				season_user,
				contractor=contractor,
				rep=get_rep(get_cell(row, 2, "")),
				list_url=get_url(row, 8),
				veto_used=get_cell(row, 12, "FALSE") == "TRUE",
				preferences=get_cell(row, 26, "N/A").replace("\n", ", "),
				bans=get_cell(row, 27, "N/A").replace("\n", ", "),
				accepting_manhwa=get_cell(row, 9, "N/A") == "Yes",
				accepting_ln=get_cell(row, 10, "N/A") == "Yes",
			)

		if user_id in ctx.master_users_created:
			await ctx.master_db.update_user(user_id, rep=season_user.rep)

		user_contracts = ctx.get_user_contracts(user_id, True)

		base_contract = user_contracts.get("Base Contract")

		if (
			base_contract.progress != get_cell(row, 19, "?/?").replace("\n", "")
			or base_contract.rating != get_cell(row, 20, "0/10")
			or base_contract.review_url != get_url(row, 24)
		):
			ctx.update_contract(
				base_contract,
				contractor=contractor,
				progress=get_cell(row, 19, "?/?").replace("\n", ""),
				rating=get_cell(row, 20, "0/10"),
				review_url=get_url(row, 24),
				medium=get_cell(row, 7),
				optional=False,
			)
		if challenge_contract := user_contracts.get("Challenge Contract"):
			if (
				challenge_contract.progress != get_cell(row, 22, "?/?").replace("\n", "")
				or challenge_contract.rating != get_cell(row, 23, "0/10")
				or challenge_contract.review_url != get_url(row, 25)
			):
				ctx.update_contract(
					challenge_contract,
					contractor=contractor,
					progress=get_cell(row, 22, "?/?").replace("\n", ""),
					rating=get_cell(row, 23, "0/10"),
					review_url=get_url(row, 25),
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
			or duality_special.progress != get_cell(row, 8, "").replace("\n", "")
			or duality_special.review_url != get_url(row, 10)
		):
			ctx.update_contract(
				duality_special,
				contractor=get_cell(row, 6, "frazzle").strip().lower(),
				progress=get_cell(row, 8, "").replace("\n", ""),
				rating=get_cell(row, 9, "0/10"),
				review_url=get_url(row, 10),
				optional=duality_special.type in OPTIONAL_CONTRACTS,
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),
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
			veteran_special.progress != get_cell(row, 7, "?/?").replace("\n", "")
			or veteran_special.rating != get_cell(row, 8, "0/10")
			or veteran_special.review_url != get_url(row, 9)
		):
			ctx.update_contract(
				veteran_special,
				contractor=get_cell(row, 5).strip().lower(),
				progress=get_cell(row, 7, "?/?").replace("\n", ""),
				rating=get_cell(row, 8, "0/10"),
				review_url=get_url(row, 9),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),
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
			or epoch_special.progress != get_cell(row, 8, "").replace("\n", "")
			or epoch_special.review_url != get_url(row, 10)
		):
			ctx.update_contract(
				epoch_special,
				contractor=get_cell(row, 6, "").strip().lower(),
				progress=get_cell(row, 8, "").replace("\n", ""),
				rating=get_cell(row, 9, "0/10"),
				review_url=get_url(row, 10),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 4, "")),
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
			or honzuki_special.progress != get_cell(row, 7, "").replace("\n", "")
			or honzuki_special.review_url != get_url(row, 8)
		):
			ctx.update_contract(
				honzuki_special,
				rating=get_cell(row, 5, "0/10"),
				progress=get_cell(row, 7, "").replace("\n", ""),
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
				optional=aria_special.type in OPTIONAL_CONTRACTS,
			)

	await ctx.commit()


async def _sync_buddies_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	users_contracts: dict[int, dict[str, Contract]] = {}
	for contract in ctx.total_contracts:
		users_contracts.setdefault(contract.contractee, {})[contract.type] = contract

	rows: list[list[str]] = sheet_data["valueRanges"][8]["values"]
	for row in rows:
		username = get_cell(row, 2, "").strip().lower()

		user_id = ctx.get_user_id(username)
		if not user_id:
			continue

		season_user = ctx.get_user(user_id)
		if not season_user:
			continue

		user_contracts = users_contracts.get(user_id)
		base_buddy = user_contracts.get("Base Buddy")
		if base_buddy and (
			base_buddy.rating != get_cell(row, 10, "0/10")
			or base_buddy.progress != get_cell(row, 8, "").replace("\n", "")
			or base_buddy.review_url != get_url(row, 12)
		):
			ctx.update_contract(
				base_buddy,
				contractor=get_cell(row, 4, "").strip().lower(),
				rating=get_cell(row, 10, "0/10"),
				progress=get_cell(row, 8, "").replace("\n", ""),
				review_url=get_url(row, 12),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 5, "")),
				optional=base_buddy.type in OPTIONAL_CONTRACTS,
			)
		challenge_buddy = user_contracts.get("Challenge Buddy")
		if challenge_buddy and (
			challenge_buddy.rating != get_cell(row, 11, "0/10")
			or challenge_buddy.progress != get_cell(row, 9, "").replace("\n", "")
			or challenge_buddy.review_url != get_url(row, 13)
		):
			ctx.update_contract(
				challenge_buddy,
				contractor=get_cell(row, 6, "").strip().lower(),
				rating=get_cell(row, 11, "0/10"),
				progress=get_cell(row, 9, "").replace("\n", ""),
				review_url=get_url(row, 13),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 7, "")),
				optional=challenge_buddy.type in OPTIONAL_CONTRACTS,
			)

	await ctx.commit()


arcana_special_columns = {"rating": 12, "review_url": 13}


async def _sync_arcana_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	users_contracts: dict[int, dict[str, Contract]] = {}
	for contract in ctx.total_contracts:
		users_contracts.setdefault(contract.contractee, {})[contract.type] = contract

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
			username = get_cell(row, 3, "").strip().lower()
			if not username:
				i += 1
				continue

			user_id = ctx.get_user_id(username)
			if not user_id:
				i += 1
				continue

			season_user = ctx.get_user(user_id)
			if not season_user:
				i += 1
				continue

			user_contracts = users_contracts.get(user_id)
			arcana_count = 0
			i += 1
			while i < len(rows) and get_row_type(rows[i]) == "contract":
				contract_row = rows[i]
				contract_name = get_cell(contract_row, 4, "").strip().replace("\n", ", ")
				contract_soul_quota = get_cell(contract_row, 7, "N/A").strip()

				if not contract_name or contract_soul_quota == "N/A":
					i += 1
					continue

				contract_review = get_url(contract_row, arcana_special_columns["review_url"])
				contract_rating = get_cell(contract_row, arcana_special_columns["rating"], "0/10")
				raw_contract_status = get_cell(contract_row, 0, "").strip()
				match raw_contract_status:
					case "PASSED" | "PURIFIED" | "ENLIGHTENMENT":
						contract_status = ContractStatus.PASSED
					case "DEATH":
						contract_status = ContractStatus.FAILED
					case _:
						contract_status = ContractStatus.PENDING

				existing_contract: Contract | None = None
				for contract in user_contracts.values():
					if contract.type.startswith("Arcana Special") and contract.name == contract_name:
						existing_contract = contract
						break

				medium_match = re.search(NAME_MEDIUM_REGEX, contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1
				if existing_contract is None:
					ctx.create_contract(
						name=contract_name,
						type=f"Arcana Special {arcana_count}",
						kind=ContractKind.NORMAL,
						status=contract_status,
						contractee=user_id,
						contractor="?",
						rating=contract_rating,
						review_url=contract_review,
						medium=contract_medium,
					)
				elif (
					existing_contract.status != contract_status
					or existing_contract.rating != contract_rating
					or existing_contract.review_url != contract_review
				):
					ctx.update_contract(status=contract_status, rating=contract_rating, review_url=contract_review, medium=contract_medium)

				i += 1

			if arcana_count == 0:  # This should only happen if the user won 0 quests in the raffle
				min_contract_name = get_cell(row, 6, "").strip().replace("\n", ", ")
				if not min_contract_name:  # If it's empty just continue don't bother
					continue

				min_contract_review = get_url(row, arcana_special_columns["review_url"])
				min_contract_rating = get_cell(row, arcana_special_columns["rating"], "0/10")

				raw_contract_status = get_cell(contract_row, 0, "").strip()
				match raw_contract_status:
					case "PASSED" | "PURIFIED" | "ENLIGHTENMENT":
						min_contract_status = ContractStatus.PASSED
					case "DEATH":
						min_contract_status = ContractStatus.FAILED
					case _:
						min_contract_status = ContractStatus.PENDING

				existing_contract: Contract | None = None
				for contract in user_contracts.values():
					if contract.type.startswith("Arcana Special") and contract.name == min_contract_name:
						existing_contract = contract
						break

				medium_match = re.search(NAME_MEDIUM_REGEX, min_contract_name)
				contract_medium = medium_match.group(2) if medium_match else ""
				arcana_count += 1
				if existing_contract is None:
					ctx.create_contract(
						name=min_contract_name,
						type=f"Arcana Special {arcana_count}",
						kind=ContractKind.NORMAL,
						status=min_contract_status,
						contractee=user_id,
						contractor="?",
						rating=min_contract_rating,
						review_url=min_contract_review,
						medium=contract_medium,
					)
				elif (
					existing_contract.status != min_contract_status
					or existing_contract.rating != min_contract_rating
					or existing_contract.review_url != min_contract_review
				):
					ctx.update_contract(status=min_contract_status, rating=min_contract_rating, review_url=min_contract_review)

			continue
		elif row_type == "empty":
			break

		i += 1

	await ctx.commit()


async def _sync_aids_data(sheet_data: dict, ctx: SeasonDBSyncContext):
	pass


async def sync_to_latest(season_db: SeasonDB):
	ctx = SeasonDBSyncContext(season_db)
	await ctx.setup()
	sheet_data = await _get_sheet_data()

	await _sync_dashboard_data(sheet_data, ctx)
	await _sync_basechallenge_data(sheet_data, ctx)
	await _sync_specials_data(sheet_data, ctx)
	await _sync_buddies_data(sheet_data, ctx)
	await _sync_arcana_data(sheet_data, ctx)


@alru_cache
async def get_database() -> SeasonDB:
	master_db = MasterDB.get_database()
	season_db = SeasonDB("Season X", DB_PATH, master_db)
	await season_db.setup()

	return season_db
