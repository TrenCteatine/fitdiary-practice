"""Настольный интерфейс Tkinter с фоновым вычислением статистики."""

import logging
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .domain import Profile, StorageError, ValidationError, day
from .services import EntryFactory
from .storage import JsonRepository


class FitnessApp(tk.Tk):
    """Представление MVC; все обращения к Tk выполняются в главном потоке."""

    def __init__(self, service, data_dir):
        super().__init__()
        self.service = service
        self.data_dir = Path(data_dir)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="statistics")
        self.future = None
        self.poll_id = None
        self.title("FitDiary | Питание и тренировки")
        self.geometry("1180x780")
        self.minsize(1050, 700)
        self.configure(bg="#f2f5f8")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.report_callback_exception = self.callback_error
        self._style()
        self._build()
        service.events.subscribe(self.refresh)
        self.refresh()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f5f8")
        style.configure("TLabel", background="#f2f5f8", foreground="#243448", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 16, "bold"), foreground="#117d78")
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 7))
        style.configure("TNotebook.Tab", padding=(20, 10), font=("Segoe UI", 10))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=29)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TProgressbar", background="#14978e", troughcolor="#dbe4eb")

    def _build(self):
        shell = ttk.Frame(self, padding=24)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="FitDiary", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="Дневник питания и движения • Все данные хранятся на вашем компьютере").pack(anchor="w", pady=(0, 16))
        top = ttk.Frame(shell)
        top.pack(fill="x")
        ttk.Label(top, text="Дата дневника").pack(side="left")
        self.selected_day = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(top, textvariable=self.selected_day, width=14).pack(side="left", padx=10)
        ttk.Button(top, text="Показать день", command=lambda: self.guard(self.refresh)).pack(side="left")
        ttk.Button(top, text="Резервная копия", command=lambda: self.guard(self.choose_backup)).pack(side="right")
        self.metrics = ttk.Label(shell, style="Metric.TLabel")
        self.metrics.pack(anchor="w", pady=(18, 8))
        self.progress = ttk.Progressbar(shell, maximum=100)
        self.progress.pack(fill="x")
        self.goal_text = ttk.Label(shell)
        self.goal_text.pack(anchor="w", pady=(4, 12))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True)
        self.meal_tab = ttk.Frame(self.tabs, padding=16)
        self.work_tab = ttk.Frame(self.tabs, padding=16)
        self.stats_tab = ttk.Frame(self.tabs, padding=16)
        self.profile_tab = ttk.Frame(self.tabs, padding=16)
        for tab, title in [(self.meal_tab, "Питание"), (self.work_tab, "Тренировки"), (self.stats_tab, "Статистика"), (self.profile_tab, "Профиль")]:
            self.tabs.add(tab, text=title)
        self.meal_fields = self._form(
            self.meal_tab,
            [
                ("name", "Продукт", "Овсяная каша"),
                ("grams", "Порция г", "150"),
                ("kcal", "Ккал / 100 г", "100"),
                ("protein", "Белки / 100 г", "3"),
                ("fat", "Жиры / 100 г", "2"),
                ("carbs", "Углеводы / 100 г", "16"),
            ],
        )
        ttk.Label(self.meal_tab, text="Пищевая ценность на 100 г — с упаковки продукта. Предзаполненные числа являются примером.").pack(anchor="w", pady=(4, 8))
        ttk.Button(self.meal_tab, text="Добавить продукт", command=lambda: self.guard(self.add_meal)).pack(anchor="w")
        self.meal_tree = self._table(self.meal_tab, ("Продукт", "Граммы", "Ккал", "Белки г", "Жиры г", "Углеводы г"))
        ttk.Button(self.meal_tab, text="Удалить выбранную запись", command=lambda: self.guard(lambda: self.delete(self.meal_tree))).pack(anchor="w")
        self.work_fields = self._form(self.work_tab, [("name", "Тренировка", "Ходьба"), ("minutes", "Минуты", "30"), ("kcal", "Расход ккал", "120")])
        ttk.Label(self.work_tab, text="Расход энергии вводится вручную. Он отображается отдельно от съеденных калорий.").pack(anchor="w", pady=8)
        ttk.Button(self.work_tab, text="Добавить тренировку", command=lambda: self.guard(self.add_workout)).pack(anchor="w")
        self.work_tree = self._table(self.work_tab, ("Тренировка", "Минуты", "Расход ккал"))
        ttk.Button(self.work_tab, text="Удалить выбранную запись", command=lambda: self.guard(lambda: self.delete(self.work_tree))).pack(anchor="w")
        self.stats_fields = self._form(self.stats_tab, [("start", "С даты", date.today().replace(day=1).isoformat()), ("end", "По дату", date.today().isoformat())])
        self.stats_button = ttk.Button(self.stats_tab, text="Рассчитать в фоне", command=lambda: self.guard(self.start_statistics))
        self.stats_button.pack(anchor="w", pady=8)
        self.stats_progress = ttk.Progressbar(self.stats_tab, mode="indeterminate")
        self.stats_progress.pack(fill="x")
        self.stats_tree = self._table(self.stats_tab, ("Дата", "Ккал", "Белки г", "Жиры г", "Углеводы г", "Минуты", "Расход ккал"))
        ttk.Label(self.stats_tab, text="В таблице показаны дни с записями. Питание и расход энергии не взаимозачитываются.").pack(anchor="w")
        p = self.service.state.profile
        self.profile_fields = self._form(
            self.profile_tab, [("name", "Имя", p.name), ("weight", "Масса кг", p.weight), ("height", "Рост см", p.height), ("calorie_goal", "Цель ккал", p.calorie_goal)]
        )
        self.bmi_text = ttk.Label(self.profile_tab, style="Metric.TLabel")
        self.bmi_text.pack(anchor="w", pady=16)
        ttk.Button(self.profile_tab, text="Сохранить профиль", command=lambda: self.guard(self.save_profile)).pack(anchor="w")
        ttk.Label(
            self.profile_tab,
            text="ИМТ рассчитывается по формуле масса / рост². Цель калорий вы задаете самостоятельно.\nПриложение служит для учета и не назначает рацион или программу тренировок.",
            wraplength=900,
        ).pack(anchor="w", pady=16)
        self.status = tk.StringVar(value="Готово")
        ttk.Label(shell, textvariable=self.status).pack(anchor="w", pady=(12, 0))
        self.validation_text = ttk.Label(shell)
        self.validation_text.pack(anchor="w")
        for fields in (self.meal_fields, self.work_fields, self.profile_fields):
            for variable in fields.values():
                variable.trace_add("write", self.preview)

    def preview(self, *_):
        """Проверить поля по мере ввода, не изменяя сохраненные записи."""
        try:
            tab = self.tabs.select()
            if tab == str(self.meal_tab):
                entry = EntryFactory.meal(**self.values(self.meal_fields), date=self.selected_day.get())
                label = f"Порция: {entry.nutrients[0]:.1f} ккал"
            elif tab == str(self.work_tab):
                entry = EntryFactory.workout(**self.values(self.work_fields), date=self.selected_day.get())
                label = f"Тренировка: {entry.minutes:g} мин, {entry.kcal:g} ккал"
            else:
                profile = Profile(**self.values(self.profile_fields))
                label = f"Предпросмотр ИМТ: {profile.bmi:.2f}"
            self.validation_text.configure(text=label, foreground="#117d78")
        except ValidationError as exc:
            self.validation_text.configure(text=str(exc), foreground="#b54735")

    def _form(self, parent, specs):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        fields = {}
        for col, (key, label, initial) in enumerate(specs):
            ttk.Label(frame, text=label).grid(row=0, column=col, sticky="w", padx=(0, 10))
            fields[key] = tk.StringVar(value=str(initial))
            ttk.Entry(frame, textvariable=fields[key], width=22 if key == "name" else 13).grid(row=1, column=col, sticky="ew", padx=(0, 10), pady=5)
        return fields

    def _table(self, parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=12)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=5)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=110, minwidth=65)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    @staticmethod
    def values(fields):
        return {key: value.get() for key, value in fields.items()}

    def guard(self, action):
        """Показать ожидаемую ошибку без завершения приложения."""
        try:
            action()
        except (ValidationError, StorageError) as exc:
            self.status.set(str(exc))
            messagebox.showerror("Проверьте данные", str(exc), parent=self)

    def callback_error(self, exc_type, exc, traceback):
        """Глобальный обработчик непредвиденной ошибки Tk callback."""
        logging.getLogger(__name__).error("gui_failed", exc_info=(exc_type, exc, traceback))
        messagebox.showerror("Ошибка", "Операция не выполнена. Подробности сохранены в журнале.", parent=self)

    def add_meal(self):
        self.service.add_meal(EntryFactory.meal(**self.values(self.meal_fields), date=self.selected_day.get()))

    def add_workout(self):
        self.service.add_workout(EntryFactory.workout(**self.values(self.work_fields), date=self.selected_day.get()))

    def save_profile(self):
        self.service.update_profile(Profile(**self.values(self.profile_fields)))

    def delete(self, tree):
        selected = tree.selection()
        if not selected:
            raise ValidationError("Сначала выберите запись в таблице")
        if messagebox.askyesno("Удаление", "Удалить выбранную запись?", parent=self):
            self.service.remove(selected[0])

    def refresh(self):
        """Обновить выбранный день, КБЖУ, шкалу и ИМТ после сохранения."""
        selected = day(self.selected_day.get())
        state = self.service.state
        for tree in (self.meal_tree, self.work_tree):
            tree.delete(*tree.get_children())
        # Отображение ограничено 500 строками; итоги включают все записи дня.
        meals = [m for m in state.meals if m.date == selected]
        workouts = [w for w in state.workouts if w.date == selected]
        for m in meals[:500]:
            self.meal_tree.insert("", "end", iid=m.id, values=(m.food.name, f"{m.grams:g}", *(f"{v:.1f}" for v in m.nutrients)))
        for w in workouts[:500]:
            self.work_tree.insert("", "end", iid=w.id, values=(w.name, f"{w.minutes:g}", f"{w.kcal:.1f}"))
        row = self.service.statistics(selected, selected)
        totals = row[0] if row else dict.fromkeys(("kcal", "protein", "fat", "carbs", "minutes", "burned"), 0)
        self.metrics.configure(
            text=f"{totals['kcal']:.0f} ккал     •     Б {totals['protein']:.1f} г     Ж {totals['fat']:.1f} г     У {totals['carbs']:.1f} г     •     {totals['minutes']:g} мин движения"
        )
        percent = totals["kcal"] / state.profile.calorie_goal * 100
        self.progress["value"] = min(percent, 100)
        self.goal_text.configure(text=f"{percent:.0f}% от цели {state.profile.calorie_goal:g} ккал  |  Расход тренировок: {totals['burned']:.0f} ккал")
        self.bmi_text.configure(text=f"ИМТ: {state.profile.bmi:.2f} кг/м²")
        self.status.set(f"Питание: {len(meals)} • Тренировки: {len(workouts)} • В таблицах до 500 строк • Сохранение автоматическое")

    def start_statistics(self):
        """Запустить расчет по неизменяемым записям снимка состояния."""
        start, end = (day(self.stats_fields[key].get()) for key in ("start", "end"))
        if start > end:
            raise ValidationError("Начало периода позже конца")
        if self.future is not None:
            return
        self.stats_button.configure(state="disabled")
        self.stats_progress.start(15)
        self.future = self.pool.submit(self.service.statistics, start, end, self.service.state)
        self.poll_id = self.after(50, self.poll_statistics)

    def poll_statistics(self):
        """Забрать результат в главном потоке; фон не обращается к Tk."""
        self.poll_id = None
        if not self.future.done():
            self.poll_id = self.after(50, self.poll_statistics)
            return
        try:
            rows = self.future.result()
            self.stats_tree.delete(*self.stats_tree.get_children())
            for row in rows[:500]:
                self.stats_tree.insert("", "end", values=(row["date"], *(f"{row[k]:.1f}" for k in ("kcal", "protein", "fat", "carbs", "minutes", "burned"))))
            self.status.set(f"Статистика готова: {len(rows)} дней; отображается до 500")
        except Exception as exc:
            logging.getLogger(__name__).exception("statistics_failed")
            messagebox.showerror("Статистика", str(exc), parent=self)
        finally:
            self.future = None
            self.stats_progress.stop()
            self.stats_button.configure(state="normal")

    def export_backup(self, path):
        """Сохранить резервную копию через тот же безопасный репозиторий."""
        JsonRepository(path).save(self.service.state)

    def choose_backup(self):
        """Выбрать файл для копии дневника, не меняя рабочую папку."""
        path = filedialog.asksaveasfilename(parent=self, title="Резервная копия", defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="fitdiary-backup.json")
        if path:
            self.export_backup(path)
            self.status.set("Резервная копия сохранена")

    def close(self):
        """Отменить опрос интерфейса и освободить фоновый исполнитель."""
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()
