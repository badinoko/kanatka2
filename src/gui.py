from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config_utils import ensure_runtime_directories, get_project_root, load_config, save_config
from export_utils import create_results_zip, sync_sheets_to_network
from logger_setup import build_logger
from series_browser import start_browser
from sheet_composer import compose_pending_sheets
from watcher import process_folder


class TextWidgetHandler(logging.Handler):
    def __init__(self, widget: tk.Text) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)

        def append() -> None:
            self.widget.configure(state="normal")
            self.widget.insert("end", message + "\n")
            self.widget.see("end")
            self.widget.configure(state="disabled")

        self.widget.after(0, append)


class PhotoSelectorGUI:
    def __init__(self, config_path: str | None = None) -> None:
        self.config = load_config(config_path)
        ensure_runtime_directories(self.config)
        self.logger = build_logger(self.config["paths"]["log_dir"])
        self._browser_thread: threading.Thread | None = None

        self.root = tk.Tk()
        self.root.title("PhotoSelector — Канатка")
        self.root.geometry("920x700")
        self.root.minsize(780, 580)

        self.source_var = tk.StringVar(value=self.config["paths"]["test_photos_folder"])
        self.status_var = tk.StringVar(value="Готово к запуску")
        self.show_score_badge_var = tk.BooleanVar(
            value=self.config.get("output", {}).get("show_score_badge", True)
        )
        self.network_path_var = tk.StringVar(
            value=self.config.get("network", {}).get("output_path", "")
        )
        self.auto_sync_var = tk.BooleanVar(
            value=self.config.get("network", {}).get("auto_sync_sheets", False)
        )

        self._build_ui()
        self._attach_log_handler()
        # Auto-start web server on launch
        self.root.after(500, self._auto_start_browser)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        # --- Source folder ---
        ttk.Label(frame, text="Папка с фото").grid(row=0, column=0, sticky="w")
        source_entry = ttk.Entry(frame, textvariable=self.source_var)
        source_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Выбрать", command=self._pick_folder).grid(row=1, column=1, sticky="ew")

        # --- Main buttons ---
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        ttk.Button(button_frame, text="Обработать папку", command=self._process_folder).pack(side="left")
        ttk.Button(button_frame, text="Собрать листы", command=self._compose_sheets).pack(side="left", padx=(8, 0))
        ttk.Separator(button_frame, orient="vertical").pack(side="left", padx=(12, 12), fill="y")
        ttk.Button(button_frame, text="Просмотр серий", command=self._open_browser).pack(side="left")
        ttk.Button(button_frame, text="Упаковать ZIP", command=self._export_zip).pack(side="left", padx=(8, 0))

        # --- Options ---
        options_frame = ttk.LabelFrame(frame, text="Настройки", padding=8)
        options_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 6))

        ttk.Checkbutton(
            options_frame,
            text="Показывать таблицу score",
            variable=self.show_score_badge_var,
            command=self._toggle_score_badge,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Checkbutton(
            options_frame,
            text="Автосинхронизация листов в сетевую папку",
            variable=self.auto_sync_var,
            command=self._toggle_auto_sync,
        ).grid(row=1, column=0, columnspan=3, sticky="w")

        ttk.Label(options_frame, text="Сетевая папка:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        net_entry = ttk.Entry(options_frame, textvariable=self.network_path_var, width=50)
        net_entry.grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(4, 0))
        ttk.Button(options_frame, text="Обзор", command=self._pick_network_folder).grid(row=2, column=2, pady=(4, 0))
        options_frame.columnconfigure(1, weight=1)

        # --- Status ---
        ttk.Label(frame, textvariable=self.status_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 4))

        # --- Log ---
        self.log_widget = tk.Text(frame, wrap="word", state="disabled")
        self.log_widget.grid(row=5, column=0, columnspan=2, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_widget.yview)
        scrollbar.grid(row=5, column=2, sticky="ns")
        self.log_widget.configure(yscrollcommand=scrollbar.set)

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

    def _attach_log_handler(self) -> None:
        handler = TextWidgetHandler(self.log_widget)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
        self.logger.addHandler(handler)

    def _pick_folder(self) -> None:
        current = Path(self.source_var.get())
        # Resolve relative paths (e.g. "INBOX") against PROJECT_ROOT
        if not current.is_absolute():
            current = get_project_root() / current
        if not current.exists():
            current = get_project_root()
        selected = filedialog.askdirectory(initialdir=str(current))
        if selected:
            self.source_var.set(selected)

    def _pick_network_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.network_path_var.get() or str(Path.cwd()))
        if selected:
            self.network_path_var.set(selected)
            self._save_network_config()

    def _toggle_score_badge(self) -> None:
        enabled = self.show_score_badge_var.get()
        self.config.setdefault("output", {})["show_score_badge"] = enabled
        self.config.setdefault("sheet", {})["show_score_badge"] = enabled
        save_config(self.config)
        mode_text = "включен" if enabled else "выключен"
        self.status_var.set(f"Показ таблицы score {mode_text}")
        self.logger.info("Показ таблицы score %s", mode_text)

    def _toggle_auto_sync(self) -> None:
        enabled = self.auto_sync_var.get()
        self._save_network_config()
        mode_text = "включена" if enabled else "выключена"
        self.status_var.set(f"Автосинхронизация {mode_text}")
        self.logger.info("Автосинхронизация листов %s", mode_text)

    def _save_network_config(self) -> None:
        self.config.setdefault("network", {})["output_path"] = self.network_path_var.get()
        self.config["network"]["auto_sync_sheets"] = self.auto_sync_var.get()
        save_config(self.config)

    def _process_folder(self) -> None:
        source_folder = Path(self.source_var.get())
        if not source_folder.is_absolute():
            source_folder = get_project_root() / source_folder
        if not source_folder.exists():
            messagebox.showerror("Ошибка", "Папка с фото не найдена")
            return

        self.status_var.set("Идёт обработка...")

        def worker() -> None:
            try:
                summary = process_folder(
                    source_folder,
                    self.config,
                    self.logger,
                    remove_source_files=False,
                    save_annotations=True,
                )
                self.status_var.set(
                    f"Готово: серий={summary['series_total']}, выбрано={summary['selected_total']}, листов={summary['sheets_total']}"
                )
                # Auto-sync sheets if enabled
                synced = sync_sheets_to_network(self.config, self.logger)
                if synced:
                    self.logger.info("Синхронизировано листов в сетевую папку: %s", synced)
            except Exception as error:  # pragma: no cover
                self.status_var.set("Ошибка")
                self.logger.exception("Ошибка обработки: %s", error)
                messagebox.showerror("Ошибка", str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _compose_sheets(self) -> None:
        try:
            selected_dir = Path(self.config["paths"]["output_selected"])
            selected_before = len(list(selected_dir.glob("*.jpg")))
            generated = compose_pending_sheets(self.config, self.logger)
            if generated:
                self.status_var.set(f"Собрано листов: {len(generated)}")
                # Auto-sync
                synced = sync_sheets_to_network(self.config, self.logger)
                if synced:
                    self.logger.info("Синхронизировано листов в сетевую папку: %s", synced)
            else:
                minimum = self.config["sheet"].get("min_photos_to_compose", self.config["sheet"]["photos_per_sheet"])
                self.status_var.set(
                    f"Листов не собрано: выбрано {selected_before}, нужно минимум {minimum}"
                )
        except Exception as error:  # pragma: no cover
            self.logger.exception("Ошибка сборки листов: %s", error)
            messagebox.showerror("Ошибка", str(error))

    def _open_browser(self) -> None:
        """Open the web series browser. Start server if needed, otherwise just open a tab."""
        import webbrowser
        if self._browser_thread is None or not self._browser_thread.is_alive():
            try:
                self._browser_thread = start_browser(self.config)
                self.status_var.set("Веб-интерфейс запущен: http://127.0.0.1:8787")
                self.logger.info("Веб-интерфейс запущен на http://127.0.0.1:8787")
            except OSError as exc:
                if "address already in use" in str(exc).lower() or "10048" in str(exc):
                    webbrowser.open("http://127.0.0.1:8787")
                    self.status_var.set("Веб-интерфейс открыт в браузере")
                else:
                    self.logger.exception("Ошибка запуска веб-интерфейса: %s", exc)
                    messagebox.showerror("Ошибка", str(exc))
        else:
            webbrowser.open("http://127.0.0.1:8787")
            self.status_var.set("Веб-интерфейс открыт в браузере")

    def _export_zip(self) -> None:
        """Show date filter dialog and pack results into a ZIP file."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Упаковка ZIP")
        dlg.geometry("380x260")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="Период для упаковки:", font=("", 11, "bold")).pack(pady=(16, 8))

        preset_var = tk.StringVar(value="all")
        presets = ttk.Frame(dlg)
        presets.pack(fill="x", padx=20)
        ttk.Radiobutton(presets, text="Всё", variable=preset_var, value="all").pack(anchor="w")
        ttk.Radiobutton(presets, text="Сегодня", variable=preset_var, value="today").pack(anchor="w")
        ttk.Radiobutton(presets, text="Эта неделя", variable=preset_var, value="week").pack(anchor="w")
        ttk.Radiobutton(presets, text="Свой диапазон", variable=preset_var, value="custom").pack(anchor="w")

        custom_frame = ttk.Frame(dlg)
        custom_frame.pack(fill="x", padx=20, pady=(4, 0))
        ttk.Label(custom_frame, text="С:").pack(side="left")
        date_from_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        date_from_entry = ttk.Entry(custom_frame, textvariable=date_from_var, width=12)
        date_from_entry.pack(side="left", padx=(4, 12))
        ttk.Label(custom_frame, text="По:").pack(side="left")
        date_to_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        date_to_entry = ttk.Entry(custom_frame, textvariable=date_to_var, width=12)
        date_to_entry.pack(side="left", padx=(4, 0))

        def do_export() -> None:
            preset = preset_var.get()
            d_from = None
            d_to = None
            today = date.today()
            if preset == "today":
                d_from = today.strftime("%Y-%m-%d")
                d_to = d_from
            elif preset == "week":
                week_start = today - timedelta(days=today.weekday())
                d_from = week_start.strftime("%Y-%m-%d")
                d_to = today.strftime("%Y-%m-%d")
            elif preset == "custom":
                d_from = date_from_var.get().strip() or None
                d_to = date_to_var.get().strip() or None

            dlg.destroy()
            try:
                zip_path = create_results_zip(self.config, date_from=d_from, date_to=d_to)
                self.status_var.set(f"ZIP создан: {zip_path.name}")
                self.logger.info("Результаты упакованы: %s", zip_path)
                messagebox.showinfo("Готово", f"ZIP-архив сохранён на рабочий стол:\n{zip_path}")
            except ValueError as exc:
                messagebox.showwarning("Нет файлов", str(exc))
            except Exception as exc:  # pragma: no cover
                self.logger.exception("Ошибка упаковки: %s", exc)
                messagebox.showerror("Ошибка", str(exc))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill="x", padx=20, pady=(16, 12))
        ttk.Button(btn_frame, text="Упаковать", command=do_export).pack(side="right")
        ttk.Button(btn_frame, text="Отмена", command=dlg.destroy).pack(side="right", padx=(0, 8))

    def _auto_start_browser(self) -> None:
        """Auto-start the web series browser on GUI launch."""
        try:
            self._browser_thread = start_browser(self.config)
            self.status_var.set("Веб-интерфейс запущен: http://127.0.0.1:8787")
            self.logger.info("Веб-интерфейс автоматически запущен на http://127.0.0.1:8787")
        except OSError as exc:
            if "address already in use" in str(exc).lower() or "10048" in str(exc):
                self.status_var.set("Веб-интерфейс уже запущен: http://127.0.0.1:8787")
            else:
                self.logger.warning("Не удалось запустить веб-интерфейс: %s", exc)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(config_path: str | None = None) -> None:
    app = PhotoSelectorGUI(config_path)
    app.run()
