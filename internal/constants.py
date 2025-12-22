import discord
import logging
import time

FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
FILE_LOGGING_FORMATTER.converter = time.gmtime
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
CONSOLE_LOGGING_FORMATTER.converter = time.gmtime


class COLORS:
	DEFAULT = discord.Colour(0x434F5D)
	ERROR = discord.Colour(0xC91A0E)
