import logging
import time

FILE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
FILE_LOGGING_FORMATTER.converter = time.gmtime
CONSOLE_LOGGING_FORMATTER = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S")
CONSOLE_LOGGING_FORMATTER.converter = time.gmtime


def setup_logger(name: str, *, file: str | None = None) -> logging.Logger:
	logger = logging.getLogger(name)
	logger.handlers.clear()
	logger.propagate = False

	if file:
		file_handler = logging.FileHandler(file, encoding="utf-8")
		file_handler.setFormatter(FILE_LOGGING_FORMATTER)
		logger.addHandler(file_handler)

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(CONSOLE_LOGGING_FORMATTER)
	logger.addHandler(console_handler)

	logger.setLevel(logging.INFO)
	return logger
