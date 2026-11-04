"""Версионированный JSON и атомарная замена файла при сохранении."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from .domain import DiaryState, Food, MealEntry, Profile, StorageError, Workout


class Repository(Protocol):
    """Контракт хранилища для подмены в тестах и смены способа хранения."""

    def load(self) -> DiaryState: ...

    def save(self, state: DiaryState) -> None: ...


class JsonRepository:
    """UTF-8 JSON schema 1; ошибки не заменяют исходные данные пустым файлом."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        """Загрузить полностью проверенные данные или вернуть новый дневник."""
        if not self.path.exists():
            return DiaryState()
        try:
            if self.path.stat().st_size > 50_000_000:
                raise ValueError("Файл превышает 50 МБ")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if type(data["schema"]) is not int or data["schema"] != 1:
                raise ValueError("Неизвестная версия формата")
            state = DiaryState(Profile(**data["profile"]))
            state.meals = [MealEntry(food=Food(**row["food"]), **{k: v for k, v in row.items() if k != "food"}) for row in data["meals"]]
            state.workouts = [Workout(**row) for row in data["workouts"]]
            ids = [item.id for item in [*state.meals, *state.workouts]]
            if len(set(ids)) != len(ids):
                raise ValueError("Повторяющиеся ID записей")
            return state
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise StorageError(f"Не удалось прочитать {self.path.name}: {exc}") from exc

    def save(self, state):
        """Сохранить через временный файл, fsync и os.replace в том же каталоге."""
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": 1, **asdict(state)}
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError(f"Не удалось сохранить {self.path.name}: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
