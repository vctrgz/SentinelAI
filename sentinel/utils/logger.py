import logging
import os

def setup_logger():
    logger = logging.getLogger("SentinelAI")

    if logger.handlers:
        return logger  # evita duplicados

    logger.setLevel(logging.DEBUG)

    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger