import json
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fitdiary.domain import DiaryState, Profile, StorageError
from fitdiary.services import EntryFactory, FitnessService
from fitdiary.storage import JsonRepository


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "дневник.json"
        self.repo = JsonRepository(self.path)
        self.state = DiaryState(Profile(name="Тест"), [EntryFactory.meal("Рис", 100, 3, 2, 20, 200, "2026-11-04")], [EntryFactory.workout("Ходьба", 30, 100, "2026-11-04")])

    def test_missing_file(self):
        self.assertEqual(self.repo.load(), DiaryState())

    def test_roundtrip(self):
        self.repo.save(self.state)
        self.assertEqual(self.repo.load(), self.state)
        self.assertIn("Тест", self.path.read_text(encoding="utf-8"))

    def test_corrupt_json_preserved(self):
        self.path.parent.mkdir()
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(StorageError):
            self.repo.load()
        self.assertEqual(self.path.read_text(), "{broken")

    def test_invalid_schema(self):
        self.repo.save(self.state)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["schema"] = 99
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(StorageError):
            self.repo.load()

    def test_boolean_schema_rejected(self):
        self.repo.save(self.state)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["schema"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(StorageError):
            self.repo.load()

    def test_invalid_structure(self):
        self.path.parent.mkdir()
        for payload in ("[]", "null", "{}", '{"schema":1,"profile":null}', '{"schema":1,"profile":{},"meals":[null],"workouts":[]}'):
            self.path.write_text(payload, encoding="utf-8")
            with self.subTest(payload=payload), self.assertRaises(StorageError):
                self.repo.load()

    def test_duplicate_ids_in_file(self):
        self.state.workouts = []
        self.state.meals *= 2
        self.repo.save(self.state)
        with self.assertRaises(StorageError):
            self.repo.load()

    def test_oversize(self):
        self.repo.save(self.state)
        with patch("fitdiary.storage.Path.stat") as stat:
            stat.return_value.st_size = 50_000_001
            with self.assertRaises(StorageError):
                self.repo.load()

    def test_replace_failure_preserves_original(self):
        self.repo.save(self.state)
        before = self.path.read_bytes()
        with patch("fitdiary.storage.os.replace", side_effect=PermissionError("locked")), self.assertRaises(StorageError):
            self.repo.save(DiaryState())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_parent_creation_fails(self):
        self.path.parent.parent.joinpath("nested").write_text("file")
        with self.assertRaises(StorageError):
            self.repo.save(self.state)

    def test_save_failure_before_temporary(self):
        with patch("fitdiary.storage.NamedTemporaryFile", side_effect=OSError("full")), self.assertRaises(StorageError):
            self.repo.save(self.state)

    def test_restart_integration(self):
        service = FitnessService(self.repo)
        service.add_meal(self.state.meals[0])
        service.add_workout(self.state.workouts[0])
        restarted = FitnessService(JsonRepository(self.path))
        self.assertEqual(asdict(service.state), asdict(restarted.state))
