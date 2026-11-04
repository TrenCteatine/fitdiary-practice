"""Модели и проверка данных без зависимости от интерфейса и файлов."""

import math
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4


class ValidationError(ValueError):
    """Некорректное значение пользовательского поля."""


class StorageError(Exception):
    """Ошибка чтения или безопасного сохранения дневника."""


def number(value, label, minimum=0, maximum=100000):
    """Проверить конечное число, принимая запятую как десятичный знак."""
    if isinstance(value, bool):
        raise ValidationError(f"{label}: требуется число")
    try:
        result = float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        raise ValidationError(f"{label}: требуется число") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValidationError(f"{label}: допустимо от {minimum:g} до {maximum:g}")
    return result


def text(value, label, maximum=120):
    """Нормализовать обязательную текстовую строку."""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValidationError(f"{label}: от 1 до {maximum} символов")
    return value.strip()


def day(value):
    """Проверить и вернуть дату в формате ГГГГ-ММ-ДД."""
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise ValidationError("Дата: используйте ГГГГ-ММ-ДД") from None


@dataclass(frozen=True)
class Profile:
    """Параметры пользователя; цель калорий задается самим пользователем."""

    name: str = "Пользователь"
    weight: float = 70.0
    height: float = 175.0
    calorie_goal: float = 2000.0

    def __post_init__(self):
        object.__setattr__(self, "name", text(self.name, "Имя"))
        for key, lo, hi in [("weight", 1, 600), ("height", 30, 300), ("calorie_goal", 1, 20000)]:
            object.__setattr__(self, key, number(getattr(self, key), key, lo, hi))

    @property
    def bmi(self):
        """ИМТ = масса в кг / квадрат роста в метрах, без медицинской оценки."""
        return self.weight / (self.height / 100) ** 2


@dataclass(frozen=True)
class Food:
    """Пищевая ценность продукта на 100 граммов."""

    name: str
    kcal: float
    protein: float
    fat: float
    carbs: float

    def __post_init__(self):
        object.__setattr__(self, "name", text(self.name, "Продукт"))
        for key in ("kcal", "protein", "fat", "carbs"):
            object.__setattr__(self, key, number(getattr(self, key), key, 0, 1000 if key == "kcal" else 100))


@dataclass(frozen=True)
class MealEntry:
    """Порция продукта в определенный день; ID стабилен при сохранении."""

    food: Food
    grams: float
    date: str
    id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self):
        if not isinstance(self.food, Food):
            raise ValidationError("Требуется продукт Food")
        object.__setattr__(self, "grams", number(self.grams, "Масса порции", 0.1, 10000))
        object.__setattr__(self, "date", day(self.date))
        object.__setattr__(self, "id", text(self.id, "ID"))

    @property
    def nutrients(self):
        """Вернуть КБЖУ порции без промежуточного округления."""
        return tuple(getattr(self.food, key) * self.grams / 100 for key in ("kcal", "protein", "fat", "carbs"))


@dataclass(frozen=True)
class Workout:
    """Запись тренировки; затраты энергии вводятся вручную."""

    name: str
    minutes: float
    kcal: float
    date: str
    id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self):
        object.__setattr__(self, "name", text(self.name, "Тренировка"))
        object.__setattr__(self, "minutes", number(self.minutes, "Минуты", 0.1, 1440))
        object.__setattr__(self, "kcal", number(self.kcal, "Расход ккал", 0, 20000))
        object.__setattr__(self, "date", day(self.date))
        object.__setattr__(self, "id", text(self.id, "ID"))


@dataclass
class DiaryState:
    """Корневое состояние дневника для репозитория и сервисов."""

    profile: Profile = field(default_factory=Profile)
    meals: list[MealEntry] = field(default_factory=list)
    workouts: list[Workout] = field(default_factory=list)
