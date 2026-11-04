import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fitdiary.__main__ import main
from fitdiary.storage import JsonRepository


class StartupTests(unittest.TestCase):
    def test_demo_and_existing_data(self):
        with TemporaryDirectory() as folder:
            with patch("sys.argv", ["fitdiary", "--data-dir", folder, "--demo"]), patch("fitdiary.__main__.FitnessApp") as app, patch("fitdiary.__main__.configure_logging"):
                main()
                main()
            state = JsonRepository(Path(folder) / "diary.json").load()
            self.assertEqual(len(state.meals), 4)
            self.assertEqual(len(state.workouts), 2)
            self.assertEqual(app.return_value.mainloop.call_count, 2)

    def test_empty_start(self):
        with TemporaryDirectory() as folder:
            with patch("sys.argv", ["fitdiary", "--data-dir", folder]), patch("fitdiary.__main__.FitnessApp"), patch("fitdiary.__main__.configure_logging"):
                main()
            self.assertFalse((Path(folder) / "diary.json").exists())

    def test_corrupt_start_stops(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "diary.json"
            file.write_text(json.dumps({"schema": 99}), encoding="utf-8")
            with (
                patch("sys.argv", ["fitdiary", "--data-dir", folder]),
                patch("fitdiary.__main__.messagebox.showerror") as dialog,
                patch("fitdiary.__main__.configure_logging"),
                self.assertLogs("fitdiary.__main__", level="ERROR"),self.assertRaises(SystemExit) as error
            ):
                main()
            self.assertEqual(error.exception.code, 1)
            dialog.assert_called_once()
            self.assertEqual(json.loads(file.read_text())["schema"], 99)
