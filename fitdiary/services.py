"""Сервисы приложения, фабрика записей, наблюдатель и стратегии статистики."""

import logging
from collections import defaultdict
from dataclasses import replace
from typing import Protocol

from .domain import DiaryState, Food, MealEntry, ValidationError, Workout, day
from .storage import Repository

log = logging.getLogger(__name__)


class EventBus:
    """Паттерн Наблюдатель: уведомление только после успешного сохранения."""

    def __init__(self):
        self._listeners = []

    def subscribe(self, callback):
        """Подписать обработчик без дублирования."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def emit(self):
        """Ошибка одного наблюдателя не отменяет сохраненную операцию."""
        for callback in tuple(self._listeners):
            try:
                callback()
            except Exception:
                log.exception("observer_failed")


class EntryFactory:
    """Фабрика нормализованных записей из полей формы."""

    @staticmethod
    def meal(name, kcal, protein, fat, carbs, grams, date):
        """Создать запись питания с проверкой всех параметров."""
        return MealEntry(Food(name, kcal, protein, fat, carbs), grams, date)

    @staticmethod
    def workout(name, minutes, kcal, date):
        """Создать проверенную запись тренировки."""
        return Workout(name, minutes, kcal, date)


class AggregationStrategy(Protocol):
    """Контракт вычисления статистики для выбранного периода."""

    def calculate(self, state: DiaryState, start: str, end: str) -> list[dict]: ...


class DailyTotals:
    """Однопроходная агрегация O(n + d log d), d — число активных дней."""

    def calculate(self, state, start, end):
        """Посчитать КБЖУ и тренировки включительно между двумя датами."""
        start, end = day(start), day(end)
        if start > end:
            raise ValidationError("Начало периода позже конца")
        totals = defaultdict(lambda: [0.0] * 6)
        for meal in state.meals:
            if start <= meal.date <= end:
                row = totals[meal.date]
                for i, value in enumerate(meal.nutrients):
                    row[i] += value
        for workout in state.workouts:
            if start <= workout.date <= end:
                totals[workout.date][4] += workout.minutes
                totals[workout.date][5] += workout.kcal
        return [dict(zip(("date", "kcal", "protein", "fat", "carbs", "minutes", "burned"), (key, *totals[key]), strict=True)) for key in sorted(totals)]


class FitnessService:
    """Слой сценариев; новое состояние фиксируется после записи на диск."""

    def __init__(self, repository: Repository, events=None, strategy=None):
        self.repository = repository
        self.events = events or EventBus()
        self.strategy = strategy or DailyTotals()
        self.state = repository.load()

    def _commit(self, candidate):
        self.repository.save(candidate)
        self.state = candidate
        log.info("diary_saved meals=%d workouts=%d", len(candidate.meals), len(candidate.workouts))
        self.events.emit()

    def add_meal(self, entry):
        """Добавить порцию и уведомить интерфейс."""
        if not isinstance(entry, MealEntry):
            raise ValidationError("Требуется запись питания")
        self._check_id(entry.id)
        self._commit(replace(self.state, meals=[*self.state.meals, entry]))

    def add_workout(self, entry):
        """Добавить тренировку и уведомить интерфейс."""
        if not isinstance(entry, Workout):
            raise ValidationError("Требуется тренировка")
        self._check_id(entry.id)
        self._commit(replace(self.state, workouts=[*self.state.workouts, entry]))

    def _check_id(self, entry_id):
        if any(item.id == entry_id for item in [*self.state.meals, *self.state.workouts]):
            raise ValidationError("Запись с таким ID уже существует")

    def remove(self, entry_id):
        """Удалить запись по ID; неизвестный ID является ошибкой."""
        meals = [m for m in self.state.meals if m.id != entry_id]
        workouts = [w for w in self.state.workouts if w.id != entry_id]
        if len(meals) == len(self.state.meals) and len(workouts) == len(self.state.workouts):
            raise ValidationError("Запись не найдена")
        self._commit(replace(self.state, meals=meals, workouts=workouts))

    def update_profile(self, profile):
        """Сохранить проверенный профиль."""
        from .domain import Profile

        if not isinstance(profile, Profile):
            raise ValidationError("Требуется профиль")
        self._commit(replace(self.state, profile=profile))

    def statistics(self, start, end, snapshot=None):
        """Вычислить статистику; snapshot позволяет изолировать фоновый поток."""
        return self.strategy.calculate(snapshot if snapshot is not None else self.state, start, end)
