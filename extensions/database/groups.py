from config import GUILD_IDS

import discord

database_group = discord.SlashCommandGroup("database", description="Various database related commands", guild_ids=GUILD_IDS)
badge_subgroup = database_group.create_subgroup("badge", "Badge related database commands")
