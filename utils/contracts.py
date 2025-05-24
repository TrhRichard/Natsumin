from typing import TYPE_CHECKING

from async_lru import alru_cache
import aiosqlite
import datetime
import discord
import config
import contracts
import re
import os

if TYPE_CHECKING:
	from main import Natsumin


@alru_cache
async def get_usernames(season_db: contracts.SeasonDB, query: str = "", limit: int = None) -> list[str]:
	sql_query = "SELECT username FROM users WHERE lower(username) LIKE ?"
	if limit:
		sql_query += f" LIMIT {limit}"
	async with season_db.connect() as db:
		async with db.execute(sql_query, (f"%{query.lower()}%",)) as cursor:
			return [row[0] for row in await cursor.fetchall()]


@alru_cache
async def get_reps(season_db: contracts.SeasonDB, query: str = "", limit: int = None) -> list[str]:
	sql_query = "SELECT DISTINCT rep FROM users WHERE upper(rep) LIKE ?"
	if limit:
		sql_query += f" LIMIT {limit}"
	async with season_db.connect() as db:
		async with db.execute(sql_query, (f"%{query.lower()}%",)) as cursor:
			return [row[0] for row in await cursor.fetchall() if row[0] != "AIDS"]


async def get_slash_usernames(ctx: discord.AutocompleteContext):
	season_db = await contracts.get_season_db()
	return await get_usernames(season_db, query=ctx.value.strip(), limit=25)


async def get_slash_reps(ctx: discord.AutocompleteContext):
	season_db = await contracts.get_season_db()
	return await get_reps(season_db, query=ctx.value.strip(), limit=25)


async def _get_contract_user(season_db: contracts.SeasonDB, username: str) -> contracts.User:
	user: contracts.User = await season_db.fetch_user(username=username)
	if not user:
		if d := await find_madfigs_user(search_name=username):
			return await season_db.fetch_user(username=(*[s.strip().lower() for s in d["previous_names"].split(",")],))
	else:
		return user


async def get_target(
	bot: "Natsumin", ctx_user: discord.Member, username: str | None = None, season: str = config.BOT_CONFIG.active_season
) -> tuple[discord.User | discord.Member | None, str | None]:
	season_db = await contracts.get_season_db(season)
	if not username:
		if user := await _get_contract_user(season_db, ctx_user.name):
			return ctx_user, user.username
		return ctx_user, ctx_user.name

	user_id: int = None
	match = re.match(r"<@!?(\d+)>", username.lower())
	if match:
		user_id = int(match.group(1))
		member = await bot.get_contract_user(id=user_id)
		if user := await _get_contract_user(season_db, member.name):
			return member, user.username
		return member, member.name if member else None

	match username:
		case "[contractee]":
			if contractee := await season_db.fetch_user(contractor=ctx_user.name):
				username = contractee.username
				user_id = contractee.discord_id
		case "[contractor]":
			user = await season_db.fetch_user(username=ctx_user.name)
			if contractor := await season_db.fetch_user(username=user.contractor):
				username = contractor.username
				user_id = contractor.discord_id
		case match if match := re.match(r"(\S*)\[(\S*)]", username):
			check_username, check_type = match.groups()
			check_user = await _get_contract_user(season_db, check_username)
			if check_user:
				match check_type:
					case "contractee":
						if contractee := await season_db.fetch_user(contractor=check_user.username):
							username = contractee.username
							user_id = contractee.discord_id
					case "contractor":
						if contractor := await season_db.fetch_user(username=check_user.contractor):
							username = contractor.username
							user_id = contractor.discord_id
		case _:
			if user := await _get_contract_user(season_db, username):
				user_id = user.discord_id
				username = user.username

	member = await bot.get_contract_user(id=user_id, username=username)
	return member, username


def get_common_embed(
	user: contracts.User | None = None, member: discord.Member | None = None, season: str = config.BOT_CONFIG.active_season
) -> discord.Embed:
	embed = discord.Embed(color=config.BASE_EMBED_COLOR, description="")
	if user:
		symbol = ""
		match user.status:
			case contracts.UserStatus.FAILED:
				symbol = "❌"
			case contracts.UserStatus.PASSED:
				symbol = "✅"
			case contracts.UserStatus.LATE_PASS:
				symbol = "⌛☑️"
			case contracts.UserStatus.INCOMPLETE:
				symbol = "⛔"

		if season != config.BOT_CONFIG.active_season:
			symbol += f" ({season})" if symbol != "" else f"{(season)}"

		embed.set_author(
			name=f"{user.username} {symbol}",
			url=user.list_url if user.list_url != "" else None,
			icon_url=member.display_avatar.url if member else None,
		)

	if season == config.BOT_CONFIG.active_season:
		current_datetime = datetime.datetime.now(datetime.UTC)
		difference = config.DEADLINE_TIMESTAMP - current_datetime
		difference_seconds = max(difference.total_seconds(), 0)

		if difference_seconds > 0:
			days, remainder = divmod(difference_seconds, 86400)
			hours, remainder = divmod(remainder, 3600)
			minutes, _ = divmod(remainder, 60)
			embed.set_footer(
				text=config.BOT_CONFIG.deadline_footer.format(days=int(days), hours=int(hours), minutes=int(minutes)),
				icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096",
			)
		else:
			embed.set_footer(text="This season has ended.", icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096")
	else:
		embed.set_footer(text=f"Data from {season}", icon_url="https://cdn.discordapp.com/emojis/998705274074435584.webp?size=4096")
	return embed


@alru_cache  # NOTE: Could probably make all madfigs sheet related stuff better but works for now
async def find_madfigs_user(user_id: int = None, search_name: str = None) -> dict | None:
	if not os.path.isfile("data/madfigs.db"):
		return None

	if not user_id and not search_name:
		raise ValueError("You must provide at least one of user_id, search_name.")

	query = "SELECT * FROM users WHERE "
	params = []
	conditions = []

	if user_id:
		conditions.append("user_id = ?")
		params.append(user_id)
	if search_name:
		conditions.append("username = ?")
		params.append(search_name)

	query += " OR ".join(conditions)

	async with aiosqlite.connect("data/madfigs.db") as db:
		async with db.execute(query, params) as cursor:
			row = await cursor.fetchone()
			if row:
				return {"user_id": row[0], "username": row[1], "previous_names": row[2]}

		async with db.execute("SELECT * from users WHERE previous_names != ''") as cursor:
			rows = await cursor.fetchall()
			for user_id, username, prev_names in rows:
				for prev in prev_names.split():
					prev = prev.strip().lower()
					if search_name == prev:
						return {"user_id": user_id, "username": username, "previous_names": prev_names}

	return None
