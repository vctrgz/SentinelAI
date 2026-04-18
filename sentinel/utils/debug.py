from utils.logger import logger
import json


def debug_dump(title, data):
    logger.debug(f"[DEBUG] {title}")
    logger.debug(json.dumps(data, indent=2))