from discord.ext import commands


class WrongChannel(commands.CommandError): ...


class BlacklistedUser(commands.CommandError): ...
