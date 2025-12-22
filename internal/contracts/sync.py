from thefuzz import process

import aiosqlite


async def get_user_id(conn: aiosqlite.Connection, username: str) -> str | None:
	if username == "":
		return None

	async with conn.execute(
		"""
		SELECT id FROM user WHERE username = ?1 
		UNION ALL 
		SELECT user_id as id FROM user_alias WHERE username = ?1
		""",
		(username,),
	) as cursor:
		row = await cursor.fetchone()
		if row:
			return row["id"]

	async with conn.execute("""
		SELECT id, username FROM user 
		UNION ALL 
		SELECT user_id as id, username FROM user_alias
		""") as cursor:
		id_username = {row["id"]: row["username"] for row in await cursor.fetchall()}

		fuzzy_result = process.extractOne(username, id_username, score_cutoff=91)
		if fuzzy_result:
			return fuzzy_result[2]
		else:
			return None
