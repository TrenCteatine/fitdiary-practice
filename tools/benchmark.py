"""Нагрузочные измерения на синтетических данных; не данные пользователя."""

import cProfile
import gc
import io
import json
import platform
import pstats
import statistics
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fitdiary.domain import DiaryState, Food, MealEntry, Workout
from fitdiary.services import DailyTotals
from fitdiary.storage import JsonRepository

ROOT = Path(__file__).resolve().parents[1]


def dataset(size):
    food = Food("Синтетический продукт", 100, 5, 3, 12)
    days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(365)]
    return DiaryState(
        meals=[MealEntry(food, 100, days[i % 365], f"m{i}") for i in range(size)], workouts=[Workout("Тестовая ходьба", 30, 100, days[i % 365], f"w{i}") for i in range(size // 10)]
    )


def naive(state):
    """Сравнительный вариант: повторное сканирование всех записей для каждого дня."""
    result = []
    for current in sorted({m.date for m in state.meals} | {w.date for w in state.workouts}):
        one = DiaryState(state.profile, [m for m in state.meals if m.date == current], [w for w in state.workouts if w.date == current])
        result.extend(DailyTotals().calculate(one, current, current))
    return result


def main():
    target = ROOT / "evidence"
    target.mkdir(exist_ok=True)
    strategy = DailyTotals()
    calculate = lambda state: strategy.calculate(state, "2026-01-01", "2026-12-31")
    rows = []
    for size in (1000, 10000, 50000):
        state = dataset(size)
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            calculate(state)
            durations.append(time.perf_counter() - start)
        with TemporaryDirectory() as folder:
            repo = JsonRepository(Path(folder) / "diary.json")
            start = time.perf_counter()
            repo.save(state)
            save_time = time.perf_counter() - start
            start = time.perf_counter()
            loaded = repo.load()
            load_time = time.perf_counter() - start
            assert loaded == state
            file_size = repo.path.stat().st_size
        rows.append(
            {"meals": size, "workouts": size // 10, "median_seconds": statistics.median(durations), "save_seconds": save_time, "load_seconds": load_time, "json_bytes": file_size}
        )
    state = dataset(10000)
    start = time.perf_counter()
    baseline = naive(state)
    naive_seconds = time.perf_counter() - start
    start = time.perf_counter()
    optimized = calculate(state)
    optimized_seconds = time.perf_counter() - start
    assert baseline == optimized
    profiler = cProfile.Profile()
    profiler.runcall(calculate, state)
    profiler.dump_stats(str(target / "cpu.prof"))
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(18)
    (target / "cpu_profile.txt").write_text(stream.getvalue(), encoding="utf-8")
    tracemalloc.start()
    calculate(state)
    gc.collect()
    before, _ = tracemalloc.get_traced_memory()
    for _ in range(10):
        calculate(state)
    gc.collect()
    after, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # Настоящий главный цикл Tk продолжает получать heartbeat во время расчета.
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    gaps = []
    large = dataset(50000)
    last = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(calculate, large)

        def heartbeat():
            nonlocal last
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
            if future.done():
                root.quit()
            else:
                root.after(5, heartbeat)

        root.after(5, heartbeat)
        root.mainloop()
        future.result()
    root.destroy()
    result = {
        "environment": platform.platform(),
        "python": platform.python_version(),
        "rows": rows,
        "comparison": {"naive_seconds": naive_seconds, "optimized_seconds": optimized_seconds, "speedup": naive_seconds / optimized_seconds, "equal_results": True},
        "memory": {"before_bytes": before, "after_bytes": after, "growth_bytes": after - before, "peak_bytes": peak, "iterations": 10},
        "ui_heartbeat": {"samples": len(gaps), "max_gap_seconds": max(gaps)},
    }
    (target / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "profiling_summary.txt").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n\n" + stream.getvalue(), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
