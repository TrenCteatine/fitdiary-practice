"""Структурированный журнал JSON Lines с ротацией."""

import json
import logging
from logging.handlers import RotatingFileHandler


class JsonFormatter(logging.Formatter):
    """Формат без содержимого дневника и параметров профиля."""

    def format(self, record):
        data = {"time": self.formatTime(record), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def configure_logging(directory):
    """Открыть журнал 1 МБ, две резервные копии."""
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "fitdiary.jsonl", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("fitdiary")
    logger.setLevel(logging.INFO)
    for previous in logger.handlers[:]:
        previous.close()
        logger.removeHandler(previous)
    logger.addHandler(handler)
