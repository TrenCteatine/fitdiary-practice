"""Показать исходные результаты проверок для снимка экрана в отчете."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

root = tk.Tk()
root.title("FitDiary | Результаты проверок")
root.geometry("1120x760")
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)
folder = Path(__file__).resolve().parents[1] / "evidence"
for title, filename in [("Тесты и покрытие", "coverage.txt"), ("Профилирование CPU и памяти", "profiling_summary.txt"), ("Список тестов", "tests.txt")]:
    frame = ttk.Frame(notebook)
    notebook.add(frame, text=title)
    box = tk.Text(frame, font=("Consolas", 12), wrap="none", padx=18, pady=18, background="#f4f7fa", foreground="#20334b")
    box.pack(fill="both", expand=True)
    content = (folder / filename).read_text(encoding="utf-8")
    if filename == "coverage.txt":
        content = (
            "FITDIARY — ПРОВЕРКА КАЧЕСТВА\n\n"
            + (folder / "tests.txt").read_text(encoding="utf-8").split("----------------------------------------------------------------------")[-1]
            + "\n"
            + content
            + "\n"
            + (folder / "static_analysis.txt").read_text(encoding="utf-8")
        )
    box.insert("1.0", content)
    box.configure(state="disabled")
root.mainloop()
