import discord

BADGE_TYPES = ["contracts", "aria", "blitz", "event", "misc"]
BADGE_RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "limited"]

BADGE_ORDER = [
	"""
	CASE
		WHEN b.type = 'contracts' THEN 0 
		WHEN b.type = 'aria' THEN 1
		WHEN b.type = 'blitz' THEN 2
		WHEN b.type = 'event' THEN 3 
		WHEN b.type = 'misc' THEN 4
		ELSE 99
	END
	""",
	"""
	CASE
		WHEN b.rarity = 'limited' THEN 0 
		WHEN b.rarity = 'legendary' THEN 1
		WHEN b.rarity = 'epic' THEN 2 
		WHEN b.rarity = 'rare' THEN 3 
		WHEN b.rarity = 'uncommon' THEN 4 
		WHEN b.rarity = 'common' THEN 5 
		ELSE 99
	END
	""",
	"b.created_at",
	"CASE WHEN b.url = '' THEN 1 ELSE 0 END",
	"b.name",
]


class COLORS:
	DEFAULT = discord.Colour(0x434F5D)
	ERROR = discord.Colour(0xE74C3C)
