from dataclasses import dataclass, field
from typing import TypedDict, Literal
from datetime import datetime


class BadgeData(TypedDict):
	id: str
	name: str
	description: str
	artist: str
	url: str
	type: Literal["contracts", "aria", "event", "misc"]
	created_at: str
	updated_at: str | None
	rarity: Literal["common", "uncommon", "rare", "epic", "legendary", "limited"]

	author_owns_badge: int | None
	badge_count: int


@dataclass(slots=True, kw_only=True)
class UserConfig:
	badge_display_type: Literal["one", "list"]
	track_username_history: bool
	updated_at: datetime | None = None

	def __post_init__(self):
		self.track_username_history = bool(self.track_username_history)
		if self.updated_at is not None:
			self.updated_at = datetime.fromisoformat(self.updated_at)
