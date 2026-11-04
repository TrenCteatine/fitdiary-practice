import unittest
from dataclasses import replace
from unittest.mock import Mock

from fitdiary.domain import DiaryState, Profile, StorageError, ValidationError
from fitdiary.services import DailyTotals, EntryFactory, EventBus, FitnessService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.load.return_value = DiaryState()
        self.service = FitnessService(self.repo)
        self.meal = EntryFactory.meal("Рис", 130, 2.7, 0.3, 28, 100, "2026-11-04")
        self.workout = EntryFactory.workout("Ходьба", 30, 100, "2026-11-04")

    def test_load_on_start(self):
        self.repo.load.assert_called_once_with()

    def test_save_and_observe_after_success(self):
        callback = Mock()
        self.service.events.subscribe(callback)
        self.service.add_meal(self.meal)
        self.repo.save.assert_called_once_with(self.service.state)
        callback.assert_called_once_with()

    def test_failed_save_rolls_back(self):
        callback = Mock()
        self.service.events.subscribe(callback)
        self.repo.save.side_effect = StorageError("disk full")
        before = self.service.state
        with self.assertRaises(StorageError):
            self.service.add_meal(self.meal)
        self.assertIs(self.service.state, before)
        self.assertEqual(self.service.state.meals, [])
        callback.assert_not_called()

    def test_add_workout(self):
        self.service.add_workout(self.workout)
        self.assertEqual(self.service.state.workouts, [self.workout])

    def test_duplicate_ids(self):
        self.service.add_meal(self.meal)
        with self.assertRaises(ValidationError):
            self.service.add_meal(self.meal)
        with self.assertRaises(ValidationError):
            self.service.add_workout(replace(self.workout, id=self.meal.id))

    def test_wrong_types(self):
        for action in (self.service.add_meal, self.service.add_workout, self.service.update_profile):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                action("invalid")

    def test_remove_meal(self):
        self.service.add_meal(self.meal)
        self.service.remove(self.meal.id)
        self.assertEqual(self.service.state.meals, [])

    def test_remove_workout(self):
        self.service.add_workout(self.workout)
        self.service.remove(self.workout.id)
        self.assertEqual(self.service.state.workouts, [])

    def test_remove_missing(self):
        with self.assertRaises(ValidationError):
            self.service.remove("unknown")
        self.repo.save.assert_not_called()

    def test_update_profile(self):
        profile = Profile(name="Тест", weight=80, height=200)
        self.service.update_profile(profile)
        self.assertEqual(self.service.state.profile, profile)

    def test_empty_stats(self):
        self.assertEqual(self.service.statistics("2026-11-01", "2026-11-30"), [])

    def test_stats_inclusive(self):
        self.service.add_meal(self.meal)
        self.service.add_meal(replace(self.meal, id="2", date="2026-11-05"))
        self.service.add_workout(self.workout)
        rows = self.service.statistics("2026-11-04", "2026-11-04")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kcal"], 130)
        self.assertEqual(rows[0]["burned"], 100)

    def test_stats_sorted(self):
        self.service.add_meal(replace(self.meal, date="2026-11-05"))
        self.service.add_workout(replace(self.workout, date="2026-11-03"))
        rows = self.service.statistics("2026-11-01", "2026-11-30")
        self.assertEqual([r["date"] for r in rows], ["2026-11-03", "2026-11-05"])
        self.assertEqual(rows[0]["kcal"], 0)

    def test_stats_repeated_meals(self):
        self.service.add_meal(self.meal)
        self.service.add_meal(replace(self.meal, id="another"))
        self.assertEqual(self.service.statistics("2026-11-04", "2026-11-04")[0]["kcal"], 260)

    def test_reversed_period(self):
        with self.assertRaises(ValidationError):
            DailyTotals().calculate(DiaryState(), "2026-11-05", "2026-11-01")

    def test_strategy_injection(self):
        strategy = Mock()
        strategy.calculate.return_value = [{"custom": 1}]
        service = FitnessService(self.repo, strategy=strategy)
        self.assertEqual(service.statistics("2026-11-01", "2026-11-30"), [{"custom": 1}])

    def test_snapshot_isolated_from_later_add(self):
        snapshot = self.service.state
        self.service.add_meal(self.meal)
        self.assertEqual(self.service.statistics("2026-11-04", "2026-11-04", snapshot), [])

    def test_observer_failure_isolated(self):
        events = EventBus()
        bad = Mock(side_effect=RuntimeError("observer"))
        good = Mock()
        events.subscribe(bad)
        events.subscribe(good)
        events.subscribe(good)
        with self.assertLogs("fitdiary.services", level="ERROR"):
            events.emit()
        good.assert_called_once()
