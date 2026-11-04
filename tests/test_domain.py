import math
import unittest

from fitdiary.domain import Food, MealEntry, Profile, ValidationError, Workout, day, number, text
from fitdiary.services import EntryFactory


class DomainTests(unittest.TestCase):
    def test_decimal_comma(self):
        self.assertEqual(number("12,5", "масса"), 12.5)

    def test_number_invalid(self):
        for value in (True, "abc", None, "nan", math.inf, -1, 100001):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                number(value, "число")

    def test_number_boundaries(self):
        self.assertEqual(number(0, "x"), 0)
        self.assertEqual(number(100000, "x"), 100000)

    def test_text_trim(self):
        self.assertEqual(text("  Ходьба ", "x"), "Ходьба")

    def test_text_invalid(self):
        for value in ("  ", "x" * 121, None, 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                text(value, "x")

    def test_date_leap_year(self):
        self.assertEqual(day("2024-02-29"), "2024-02-29")

    def test_invalid_date(self):
        for value in ("2026-02-29", "04.11.2026", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                day(value)

    def test_bmi(self):
        self.assertAlmostEqual(Profile(weight=80, height=200).bmi, 20)

    def test_invalid_profile(self):
        for args in ({"weight": 0}, {"height": 0}, {"calorie_goal": 0}, {"name": ""}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                Profile(**args)

    def test_food_values(self):
        food = Food(" Рис ", "130", "2,7", 0.3, 28)
        self.assertEqual(food.name, "Рис")
        self.assertEqual(food.protein, 2.7)

    def test_invalid_food(self):
        with self.assertRaises(ValidationError):
            Food("A", 1001, 1, 0, 1)
        with self.assertRaises(ValidationError):
            Food("A", 100, 101, 0, 1)

    def test_portion_nutrients(self):
        portion = EntryFactory.meal("A", 100, 10, 5, 20, 250, "2026-11-04")
        self.assertEqual(portion.nutrients, (250, 25, 12.5, 50))

    def test_invalid_portion(self):
        with self.assertRaises(ValidationError):
            MealEntry("invalid", 10, "2026-11-04")
        with self.assertRaises(ValidationError):
            EntryFactory.meal("A", 100, 1, 0, 1, 0, "2026-11-04")

    def test_workout(self):
        workout = EntryFactory.workout(" Бег ", "20,5", 0, "2026-11-04")
        self.assertEqual((workout.name, workout.minutes, workout.kcal), ("Бег", 20.5, 0))

    def test_invalid_workout(self):
        for args in [("A", 0, 0, "2026-11-04"), ("A", 1441, 0, "2026-11-04"), ("A", 1, -1, "2026-11-04")]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                Workout(*args)

    def test_unique_id_and_immutable_records(self):
        first = Workout("A", 1, 1, "2026-11-04")
        second = Workout("A", 1, 1, "2026-11-04")
        self.assertNotEqual(first.id, second.id)
        with self.assertRaises(AttributeError):
            first.kcal = 20
