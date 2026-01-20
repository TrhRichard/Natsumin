from typing import TypedDict, Literal


class BadgeData(TypedDict):
	id: str
	name: str
	description: str
	artist: str
	url: str
	type: Literal["contracts", "aria"]
	created_at: str

	author_owns_badge: int | None
	badge_count: int
