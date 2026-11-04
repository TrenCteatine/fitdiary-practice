"""Точка входа: python -m fitdiary [--data-dir ПАПКА] [--demo]."""

import argparse
import logging
import os
from datetime import date
from pathlib import Path
from tkinter import messagebox

from .domain import StorageError
from .gui import FitnessApp
from .logging_setup import configure_logging
from .services import EntryFactory, FitnessService
from .storage import JsonRepository


def main():
    parser = argparse.ArgumentParser(description="FitDiary — питание и тренировки")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FitDiary")
    parser.add_argument("--demo", action="store_true", help="Заполнить пустой дневник демонстрационными данными")
    args = parser.parse_args()
    try:
        configure_logging(args.data_dir / "logs")
        service = FitnessService(JsonRepository(args.data_dir / "diary.json"))
        if args.demo and not service.state.meals and not service.state.workouts:
            today = date.today().isoformat()
            for fields in [
                ("Овсяная каша", 100, 3, 2, 16, 200),
                ("Куриная грудка", 165, 31, 3.6, 0, 180),
                ("Рис отварной", 130, 2.7, 0.3, 28, 150),
                ("Яблоко", 52, 0.3, 0.2, 14, 160),
            ]:
                service.add_meal(EntryFactory.meal(*fields, today))
            service.add_workout(EntryFactory.workout("Ходьба", 40, 160, today))
            service.add_workout(EntryFactory.workout("Растяжка", 15, 35, today))
        app = FitnessApp(service, args.data_dir)
        app.mainloop()
    except (StorageError, OSError) as exc:
        logging.getLogger(__name__).exception("startup_failed")
        messagebox.showerror("Не удалось открыть дневник", f"{exc}\nИсходный файл не заменен. Проверьте папку данных.")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
