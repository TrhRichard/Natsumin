from dotenv import load_dotenv
from ..classes import Contract, User, SeasonDB, SeasonSyncContext, ContractKind, ContractType, ContractStatus, UserStatus, UserKind
from async_lru import alru_cache
import utils
import aiohttp
import re
import os

load_dotenv()

SPREADSHEET_ID = "19aueoNx6BBU6amX7DhKGU8kHVauHWcSGiGKMzFSGkGc"
DB_PATH = "contracts/seasons/Winter2025.db"


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
					"Aid Contracts!A5:H80",
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


def get_cell(row: list[str], i: int, default="") -> str:
	if i >= len(row):
		return default
	v = row[i].strip()
	return v if v else default


def get_url(row: list[str], i: int) -> str:
	return _get_first_url(get_cell(row, i))


NAME_MEDIUM_REGEX = r"(.*) \((.*)\)"
DASHBOARD_ROW_NAMES = {
	0: ContractType.BASE_CONTRACT,
	1: ContractType.CHALLENGE_CONTRACT,
	2: ContractType.VETERAN_SPECIAL,
	3: ContractType.MOVIE_SPECIAL,
	4: ContractType.VN_SPECIAL,
	5: ContractType.INDIE_SPECIAL,
	6: ContractType.EXTREME_SPECIAL,
	7: ContractType.BASE_BUDDY,
	8: ContractType.CHALLENGE_BUDDY,
}
OPTIONAL_CONTRACTS = [ContractType.EXTREME_SPECIAL]


def is_contract_optional(contract: Contract) -> bool:
	return contract.type in OPTIONAL_CONTRACTS


async def _sync_dashboard_data(sheet_data: dict, db: SeasonDB, ctx: SeasonSyncContext):
	dashboard_rows: list[list[str]] = sheet_data["valueRanges"][0]["values"]

	for row in dashboard_rows:
		status = row[0]
		username = row[1].strip().lower()

		contract_names = row[2:11]
		contract_passed = row[12:21]

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

		if existing_user := ctx.users.get(username):
			if existing_user.status != user_status:
				await db.update_user(username, status=user_status)
		else:
			discord_id = None
			if d := await utils.find_madfigs_user(search_name=username):
				discord_id = d["user_id"]
			await db.create_user(username=username, status=user_status, kind=UserKind.NORMAL, discord_id=discord_id)
			ctx.users[username] = User(username=username, status=user_status, kind=UserKind.NORMAL, discord_id=discord_id)

		for i, contract_name in enumerate(contract_names):
			contract_type = DASHBOARD_ROW_NAMES[i]

			if contract_name == "-":
				continue

			contract_name = contract_name.strip().replace("\n", "")

			contract_status = (
				ContractStatus.PASSED
				if "PASSED" in get_cell(contract_passed, i)
				else ContractStatus.FAILED
				if "FAILED" in get_cell(contract_passed, i)
				else ContractStatus.LATE_PASS
				if "LATE PASS" in get_cell(contract_passed, i)
				else ContractStatus.PENDING
			)

			if existing_contract := ctx.contracts.get(username, {}).get(contract_type):
				if existing_contract.status != contract_status:
					await db.update_contract(existing_contract.id, status=contract_status)
			else:
				id = await db.create_contract(contract_name, contract_type, ContractKind.NORMAL, contract_status, username)
				ctx.contracts.setdefault(username, {})[contract_type] = Contract(
					id=id, name=contract_name, type=contract_type, kind=ContractKind.NORMAL, status=contract_status, contractee=username
				)


async def _sync_basechallenge_data(sheet_data: dict, db: SeasonDB, ctx: SeasonSyncContext):
	base_challenge_rows: list[list[str]] = sheet_data["valueRanges"][1]["values"]

	for row in base_challenge_rows:
		username = row[3].strip().lower()
		contractor = row[5].strip().lower()

		if username not in ctx.users:
			continue

		user = ctx.users.get(username)

		if user.contractor != contractor or user.veto_used != (get_cell(row, 10) == "TRUE"):
			await db.update_user(
				username,
				rep=get_cell(row, 2).upper(),
				contractor=contractor,
				list_url=get_url(row, 7),
				veto_used=get_cell(row, 10) == "TRUE",
				preferences=get_cell(row, 16).replace("\n", ", "),
				bans=get_cell(row, 17).replace("\n", ", "),
				accepting_manhwa=get_cell(row, 18) == "Yes",
				accepting_ln=get_cell(row, 19) == "Yes",
			)

		user_contracts = ctx.contracts[username]
		base_contract = user_contracts.get(ContractType.BASE_CONTRACT)

		if (
			base_contract.progress != get_cell(row, 29, "?/?").replace("\n", "")
			or base_contract.rating != get_cell(row, 26)
			or base_contract.review_url != get_url(row, 31)
		):
			await db.update_contract(
				base_contract.id,
				contractor=contractor,
				progress=get_cell(row, 29, "?/?").replace("\n", ""),
				rating=get_cell(row, 26),
				review_url=get_url(row, 31),
				medium=get_cell(row, 9),
				optional=is_contract_optional(base_contract),
			)
		if challenge_contract := user_contracts.get(ContractType.CHALLENGE_CONTRACT):
			if (
				challenge_contract.progress != get_cell(row, 30, "?/?").replace("\n", "")
				or challenge_contract.rating != get_cell(row, 28)
				or challenge_contract.review_url != get_url(row, 32)
			):
				await db.update_contract(
					challenge_contract.id,
					contractor=contractor,
					progress=get_cell(row, 30, "?/?").replace("\n", ""),
					rating=get_cell(row, 28),
					review_url=get_url(row, 32),
					medium=get_cell(row, 13),
					optional=is_contract_optional(challenge_contract),
				)


async def _sync_specials_data(sheet_data: dict, db: SeasonDB, ctx: SeasonSyncContext):
	rows: list[list[str]] = sheet_data["valueRanges"][2]["values"]

	# Veteran Special
	for row in rows:
		username = row[2].strip().lower()

		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		veteran_special = user_contracts.get(ContractType.VETERAN_SPECIAL)
		if (
			veteran_special.progress != get_cell(row, 6, "?/?")
			or veteran_special.rating != get_cell(row, 7)
			or veteran_special.review_url != get_url(row, 8)
		):
			await db.update_contract(
				veteran_special.id,
				contractor=get_cell(row, 4).strip().lower(),
				progress=get_cell(row, 6, "?/?"),
				rating=get_cell(row, 7),
				review_url=get_url(row, 8),
				medium=re.sub(NAME_MEDIUM_REGEX, r"\2", get_cell(row, 3)),
				optional=is_contract_optional(veteran_special),
			)

	# VN Special
	rows: list[list[str]] = sheet_data["valueRanges"][3]["values"]
	for row in rows:
		username = row[2].strip().lower()

		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		vn_special = user_contracts.get(ContractType.VN_SPECIAL)
		if vn_special.rating != get_cell(row, 5) or vn_special.review_url != get_url(row, 6):
			await db.update_contract(
				vn_special.id,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if vn_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="VN",
				optional=is_contract_optional(vn_special),
			)

	# Movie Special
	rows: list[list[str]] = sheet_data["valueRanges"][4]["values"]
	for row in rows:
		username = row[2].strip().lower()
		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		movie_special = user_contracts.get(ContractType.MOVIE_SPECIAL)
		if movie_special.rating != get_cell(row, 5) or movie_special.review_url != get_url(row, 6):
			await db.update_contract(
				movie_special.id,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if movie_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="Movie",
				optional=is_contract_optional(movie_special),
			)

	# Indie Special
	rows: list[list[str]] = sheet_data["valueRanges"][5]["values"]
	for row in rows:
		username = row[2].strip().lower()
		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		indie_special = user_contracts.get(ContractType.INDIE_SPECIAL)
		if indie_special.progress != get_cell(row, 5) or indie_special.rating != get_cell(row, 6) or indie_special.review_url != get_url(row, 7):
			await db.update_contract(
				indie_special.id,
				contractor=get_cell(row, 4).strip().lower(),
				progress=get_cell(row, 5),
				rating=get_cell(row, 6),
				review_url=get_url(row, 7),
				medium="Game",
				optional=is_contract_optional(indie_special),
			)

	# Extreme Special
	rows: list[list[str]] = sheet_data["valueRanges"][6]["values"]
	for row in rows:
		username = row[2].strip().lower()
		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		extreme_special = user_contracts.get(ContractType.EXTREME_SPECIAL)
		if extreme_special.rating != get_cell(row, 5) or extreme_special.review_url != get_url(row, 6):
			await db.update_contract(
				extreme_special.id,
				contractor=get_cell(row, 4).strip().lower(),
				progress="Completed" if extreme_special.status in [ContractStatus.PASSED, ContractStatus.LATE_PASS] else "Not Completed",
				rating=get_cell(row, 5),
				review_url=get_url(row, 6),
				medium="Movie",
				optional=is_contract_optional(extreme_special),
			)

	# Buddying
	rows: list[list[str]] = sheet_data["valueRanges"][7]["values"]
	for row in rows:
		username = row[2].strip().lower()
		if username not in ctx.users:
			continue

		user_contracts = ctx.contracts.get(username)
		if base_buddy := user_contracts.get(ContractType.BASE_BUDDY):
			if base_buddy.progress != get_cell(row, 8, "?/?") or base_buddy.rating != get_cell(row, 10) or base_buddy.review_url != get_url(row, 12):
				await db.update_contract(
					base_buddy.id,
					contractor=get_cell(row, 4).strip().lower(),
					progress=get_cell(row, 8, "?/?"),
					rating=get_cell(row, 10),
					review_url=get_url(row, 12),
					medium="Anime / Manga",
					optional=is_contract_optional(base_buddy),
				)
		if challenge_buddy := user_contracts.get(ContractType.CHALLENGE_BUDDY):
			if (
				challenge_buddy.progress != get_cell(row, 9, "?/?")
				or challenge_buddy.rating != get_cell(row, 11)
				or challenge_buddy.review_url != get_url(row, 13)
			):
				await db.update_contract(
					challenge_buddy.id,
					contractor=get_cell(row, 6).strip().lower(),
					progress=get_cell(row, 9, "?/?"),
					rating=get_cell(row, 11),
					review_url=get_url(row, 13),
					medium="Anime / Manga",
					optional=is_contract_optional(challenge_buddy),
				)


async def _sync_aids_data(sheet_data: dict, db: SeasonDB, ctx: SeasonSyncContext):
	rows: list[list[str]] = sheet_data["valueRanges"][9]["values"]

	aids_user_count: dict[str, int] = {}
	for row in rows:
		username = get_cell(row, 1).lower()

		if username == "":
			continue
		elif username not in ctx.users:  # Either user didnt get cached properly or user wasn't in season, create it then
			if not await db.has_user(username):
				discord_id = None
				if d := await utils.find_madfigs_user(search_name=username):
					discord_id = d["user_id"]
				await db.create_user(
					username=username,
					status=UserStatus.PENDING,
					kind=UserKind.AID,
					rep="AIDS",
					discord_id=discord_id,
					contractor="Cow Lord",
					list_url="https://discord.com/channels/994071728017899600/1008810171876773978/1374143929787613375",
					veto_used=False,
					accepting_manhwa=False,
					accepting_ln=False,
					preferences="Unknown",
					bans="Unknown",
				)
				ctx.users[username] = User(
					username=username,
					status=UserStatus.PENDING,
					kind=UserKind.AID,
					rep="AIDS",
					discord_id=discord_id,
					contractor="Cow Lord",
					list_url="https://discord.com/channels/994071728017899600/1008810171876773978/1374143929787613375",
					veto_used=False,
					accepting_manhwa=False,
					accepting_ln=False,
					preferences="Unknown",
					bans="Unknown",
				)

		user_contracts = ctx.contracts.setdefault(username, {})

		if username not in aids_user_count:
			aids_user_count[username] = 0
		aids_user_count[username] += 1
		contract_type = ContractType(f"Aid Contract {aids_user_count[username]}")

		aid_name = get_cell(row, 4).replace("\n", "")

		contract_status: ContractStatus
		if get_cell(row, 0) == "PASSED":
			contract_status = ContractStatus.PASSED
		elif get_cell(row, 0) == "FAILED":
			contract_status = ContractStatus.FAILED
		else:
			contract_status = ContractStatus.PENDING

		if existing_contract := user_contracts.get(contract_type):
			if (
				existing_contract.name != aid_name
				or existing_contract.progress != get_cell(row, 5)
				or existing_contract.contractor != get_cell(row, 3).lower()
				or existing_contract.rating != get_cell(row, 6)
				or existing_contract.review_url != get_url(row, 7)
			):
				await db.update_contract(
					existing_contract.id,
					name=aid_name,
					status=contract_status,
					progress=get_cell(row, 5),
					rating=get_cell(row, 6),
					review_url=get_url(row, 7),
					contractor=get_cell(row, 3).lower(),
				)
		else:
			id = await db.create_contract(
				name=aid_name,
				type=contract_type,
				kind=ContractKind.AID,
				status=contract_status,
				contractee=username,
				progress=get_cell(row, 5),
				rating=get_cell(row, 6),
				review_url=get_cell(row, 7),
				contractor=get_cell(row, 3).lower(),
				optional=False,
			)
			ctx.contracts[username][contract_type] = Contract(
				id=id,
				name=aid_name,
				type=contract_type,
				kind=ContractKind.AID,
				status=contract_status,
				contractee=username,
				progress=get_cell(row, 5),
				rating=get_cell(row, 6),
				review_url=get_cell(row, 7),
				contractor=get_cell(row, 3).lower(),
				optional=False,
			)


async def sync_to_latest(db: SeasonDB):
	ctx = SeasonSyncContext()
	await ctx.load(db)
	sheet_data = await _get_sheet_data()

	await _sync_dashboard_data(sheet_data, db, ctx)
	await _sync_basechallenge_data(sheet_data, db, ctx)
	await _sync_specials_data(sheet_data, db, ctx)
	await _sync_aids_data(sheet_data, db, ctx)


@alru_cache
async def get_database() -> SeasonDB:
	season_db = SeasonDB("Winter 2025", "data/seasons/Winter2025.db")
	await season_db.setup()

	return season_db
