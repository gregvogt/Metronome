import logging
import sys

class ConsoleFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR

class StderrFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.ERROR

def setup_logging(logfile=None, level=logging.INFO):
    formatter = logging.Formatter(
        fmt="[%(asctime)s]: %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger = logging.getLogger()
    logger.setLevel(level)
    logger.handlers.clear()

    # Stdout handler for INFO and below
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.addFilter(ConsoleFilter())
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # Stderr handler for ERROR and above
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Optional file handler
    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

# Example usage:
# setup_logging("mylogfile.log", logging.DEBUG)
# logging.info("This is an info message")
# logging.error("This is an error message")