"""Сценарий для пошаговой проверки КБЖУ с python -m pdb."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fitdiary.services import EntryFactory

entry = EntryFactory.meal("Проверочный продукт", 100, 10, 5, 20, 250, "2026-11-04")
totals = entry.nutrients
assert totals == (250.0, 25.0, 12.5, 50.0)
print("Расчет порции проверен:", totals)
