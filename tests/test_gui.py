import json
import logging
import unittest
from concurrent.futures import Future
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fitdiary.domain import ValidationError
from fitdiary.gui import FitnessApp
from fitdiary.logging_setup import JsonFormatter, configure_logging
from fitdiary.services import FitnessService
from fitdiary.storage import JsonRepository


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.service = FitnessService(JsonRepository(self.directory / "diary.json"))
        self.app = FitnessApp(self.service, self.directory)
        self.app.withdraw()
        self.addCleanup(self.app.close)
        self.app.update()

    def test_add_meal_and_refresh(self):
        self.app.add_meal()
        self.assertEqual(len(self.app.meal_tree.get_children()), 1)
        self.assertIn("150", self.app.metrics["text"])

    def test_add_workout(self):
        self.app.add_workout()
        self.assertEqual(len(self.app.work_tree.get_children()), 1)

    def test_save_profile(self):
        self.app.profile_fields["weight"].set("80")
        self.app.profile_fields["height"].set("200")
        self.app.save_profile()
        self.assertIn("20.00", self.app.bmi_text["text"])

    def test_live_validation_meal(self):
        self.app.meal_fields["grams"].set("0")
        self.assertIn("допустимо", self.app.validation_text["text"])
        self.app.meal_fields["grams"].set("200")
        self.assertIn("200.0", self.app.validation_text["text"])

    def test_live_validation_workout(self):
        self.app.tabs.select(self.app.work_tab)
        self.app.work_fields["minutes"].set("40")
        self.assertIn("40", self.app.validation_text["text"])

    def test_live_profile(self):
        self.app.tabs.select(self.app.profile_tab)
        self.app.profile_fields["weight"].set("90")
        self.assertIn("ИМТ", self.app.validation_text["text"])

    def test_guard_expected_error(self):
        with patch("fitdiary.gui.messagebox.showerror") as dialog:
            self.app.guard(Mock(side_effect=ValidationError("ошибка")))
        dialog.assert_called_once()
        self.assertEqual(self.app.status.get(), "ошибка")

    def test_global_error(self):
        with patch("fitdiary.gui.messagebox.showerror") as dialog, self.assertLogs("fitdiary.gui", level="ERROR"):
            self.app.callback_error(RuntimeError, RuntimeError("test"), None)
        dialog.assert_called_once()

    def test_delete_selected(self):
        self.app.add_meal()
        self.app.meal_tree.selection_set(self.app.meal_tree.get_children()[0])
        with patch("fitdiary.gui.messagebox.askyesno", return_value=True):
            self.app.delete(self.app.meal_tree)
        self.assertEqual(self.service.state.meals, [])

    def test_delete_cancelled(self):
        self.app.add_workout()
        self.app.work_tree.selection_set(self.app.work_tree.get_children()[0])
        with patch("fitdiary.gui.messagebox.askyesno", return_value=False):
            self.app.delete(self.app.work_tree)
        self.assertEqual(len(self.service.state.workouts), 1)

    def test_delete_nothing(self):
        with self.assertRaises(ValidationError):
            self.app.delete(self.app.meal_tree)

    def test_backup(self):
        destination = self.directory / "backup.json"
        with patch("fitdiary.gui.filedialog.asksaveasfilename", return_value=str(destination)):
            self.app.choose_backup()
        self.assertEqual(JsonRepository(destination).load(), self.service.state)
        with patch("fitdiary.gui.filedialog.asksaveasfilename", return_value=""):
            self.app.choose_backup()

    def test_async_statistics(self):
        self.app.add_meal()
        today = date.today().isoformat()
        self.app.stats_fields["start"].set(today)
        self.app.stats_fields["end"].set(today)
        self.app.start_statistics()
        future = self.app.future
        future.result(timeout=5)
        self.app.after_cancel(self.app.poll_id)
        self.app.poll_statistics()
        self.assertIsNone(self.app.future)
        self.assertEqual(len(self.app.stats_tree.get_children()), 1)

    def test_async_reversed_dates(self):
        self.app.stats_fields["start"].set("2026-12-31")
        self.app.stats_fields["end"].set("2026-01-01")
        with self.assertRaises(ValidationError):
            self.app.start_statistics()

    def test_async_pending_and_duplicate(self):
        self.app.future = Future()
        self.app.start_statistics()
        self.app.poll_statistics()
        self.assertIsNotNone(self.app.poll_id)
        self.app.future.cancel()

    def test_async_failure(self):
        future = Future()
        future.set_exception(RuntimeError("ошибка расчета"))
        self.app.future = future
        with patch("fitdiary.gui.messagebox.showerror") as dialog, self.assertLogs("fitdiary.gui", level="ERROR"):
            self.app.poll_statistics()
        self.assertIsNone(self.app.future)
        self.assertEqual(str(self.app.stats_button["state"]), "normal")
        dialog.assert_called_once()


class LoggingTests(unittest.TestCase):
    def test_json_format(self):
        record = logging.LogRecord("test", logging.INFO, "", 1, "saved %d", (2,), None)
        self.assertEqual(json.loads(JsonFormatter().format(record))["message"], "saved 2")

    def test_logging_rotation_configuration(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            configure_logging(folder)
            configure_logging(folder)
            logger = logging.getLogger("fitdiary")
            logger.info("test")
            try:
                raise ValueError("bad")
            except ValueError:
                logger.exception("caught")
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
            rows = (folder / "fitdiary.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 2)
            self.assertIn("exception", json.loads(rows[-1]))
