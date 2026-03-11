from typing import TypedDict, Literal


class BadgeData(TypedDict):
	id: str
	name: str
	description: str
	artist: str
	url: str
	type: Literal["contracts", "aria", "event", "misc"]
	created_at: str
	rarity: Literal["common", "uncommon", "rare", "epic", "legendary", "limited"]

	author_owns_badge: int | None
	badge_count: int
