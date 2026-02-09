from discord.ext import commands


class BlacklistedUser(commands.CommandError):
	def __init__(self, reason: str | None, *args):
		self.reason = reason

		super().__init__(f"User blacklisted{f', reason: {reason}' if reason else ''}", *args)


class NotWhitelistedChannel(commands.CommandError):
	def __init__(self, valid_channel_ids: list[int], *args):
		self.valid_channel_ids = valid_channel_ids

		super().__init__(f"Channel not whitelisted, whitelisted channels: {', '.join(str(c) for c in valid_channel_ids)}", *args)
