# CLAUDE.md

Основной рабочий регламент и технический справочник для репозитория `kanatka2`.

Последнее обновление: 2026-03-15.

---

## 1. Приоритет правил

1. `AGENTS.md`
2. Этот файл (`CLAUDE.md`)
3. Живая проектная документация:
   - `docs/project/overview.md`
   - `docs/project/roadmap.md`
   - `docs/project/startup.md`
   - `docs/project/progress.md`
4. `TZ_PhotoSelector.md`
5. Код и конфиги репозитория

---

## 2. Базовые правила работы

1. Не объявлять задачи завершенными автоматически.
   - После собственных изменений использовать рабочую формулировку: изменения внесены, требуется проверка пользователя.

2. `overview.md` является главным дашбордом проекта.
   - Новые заметные направления работы, решения и хвосты сначала должны появляться там.

3. `progress.md` всегда append-only.
   - Не переписывать старые записи.
   - Каждая существенная сессия должна оставлять короткий след.
   - Если журнал дорастает примерно до 1000 строк, целиком переносить в `archive/`, а на месте создавать новый с перекрестной ссылкой.

4. `startup.md` нужен как handoff-файл для быстрого входа в следующую сессию.

5. `roadmap.md` хранит развёрнутое понимание продукта и этапов.
   - Не раздувать `overview.md` narrative-разделами.

6. Не удалять задачи из `overview.md` без явной команды пользователя.

7. Пользователь не обязан отвечать на технические вопросы.
   - Там, где возможно, принимать технические решения самостоятельно и фиксировать их в документах.

8. Ничего не удалять из проекта.
   - Устаревшие артефакты переносить в `archive/`.

---

## 3. О проекте

### Суть продукта

`kanatka2` — коммерческая программа автоматического отбора лучших фотографий с горнолыжной канатной дороги.

**Сценарий:** Камера снимает проезжающих лыжников на кресельной канатке. Программа группирует кадры в серии по времени, отбрасывает пустые кресла, выбирает лучшее фото в каждой серии, собирает печатные листы (сетка 2x4) и отправляет в типографию по локальной сети.

### Архитектурный статус на 2026-03-15

В проекте есть две конкурирующие схемы, их нельзя смешивать:

| Схема | Что означает | Статус |
|-------|--------------|--------|
| **Legacy two-app** | Основная программа у камеры, отдельный `receiver/` у принтера | Реализовано в коде, но переоценивается |
| **Новая рабочая гипотеза** | Верхний компьютер только складывает фото в сетевую папку, нижний мощный компьютер делает всю обработку и печатный workflow | Приоритетная для следующего этапа |

До явного подтверждения пользователя `receiver/` не удалять, но и не считать автоматически обязательным ядром продукта.

### Стек и зависимости

- **Язык:** Python 3.11+
- **Детекция лиц:** MediaPipe Face Landmarker (`models/face_landmarker.task`)
- **Детекция людей (fallback):** Haar upper body cascade (OpenCV, `haarcascade_upperbody.xml`)
- **Обработка изображений:** OpenCV (`opencv-contrib-python`), Pillow
- **Мониторинг папки:** watchdog
- **GUI launcher:** tkinter (stdlib)
- **Нативное окно приложения:** pywebview (WebView2/Edge на Windows)
- **Веб-интерфейс:** stdlib `http.server` + `ThreadingHTTPServer` (zero external deps)
- **Платформа:** Windows, CPU-only
- **Виртуальное окружение:** `.venv/` в корне проекта

### Ключевые числа

- Скоринг: 3 компонента — `person_present` (40), `sharpness` (35), `exposure` (25). Сумма = 100.
- При этом код уже собирает дополнительные face-метрики: `yaw/pitch/roll`, `ear`, `mouth_ratio`, локальную sharpness/brightness лица.
- Детекция: MediaPipe face → Haar upper body fallback.
- Тестовый прогон: 22/25 серий selected (88%).
- Тесты: 34 теста, 10 файлов.
- Веб-интерфейс на порту 8787.

---

## 4. Структура репозитория

```
kanatka2/
├── CLAUDE.md              # Этот файл — рабочий регламент + справочник
├── AGENTS.md              # Entry point для ассистентов
├── CODEX.md               # Короткий Codex-companion к CLAUDE.md
├── README.md              # Описание проекта (GitHub)
├── TZ_PhotoSelector.md    # Техническое задание
├── requirements.txt       # Зависимости Python
├── run_gui.bat            # Запуск GUI (Windows)
│
├── src/                   # Исходный код (все модули)
│   ├── config.json        # Конфигурация (единственный файл настроек)
│   ├── main.py            # CLI entry point (argparse)
│   ├── gui.py             # Tkinter launcher
│   ├── series_browser.py  # Веб-интерфейс (HTTP-сервер, ~1500 строк)
│   ├── watcher.py         # Мониторинг папки INBOX (watchdog)
│   ├── analyzer.py        # Анализ одного фото (детекция + метрики)
│   ├── face_utils.py      # MediaPipe + Haar cascade детекция
│   ├── scorer.py          # Расчёт score (3 компонента)
│   ├── selector.py        # Выбор лучшего фото в серии
│   ├── sheet_composer.py  # Сборка печатных листов (2x4 сетка)
│   ├── badge_utils.py     # Score overlay на фото (debug)
│   ├── image_utils.py     # Чтение/запись/ресайз изображений
│   ├── export_utils.py    # ZIP-экспорт + сетевая синхронизация
│   ├── config_utils.py    # Загрузка/сохранение config.json
│   ├── metadata_utils.py  # Пути к JSON-метаданным фото
│   ├── logger_setup.py    # Настройка логирования
│   └── runtime_env.py     # Подготовка окружения (MPLCONFIGDIR)
│
├── receiver/              # Опциональный/legacy приёмник листов
│   ├── receiver_app.py
│   ├── receiver_server.py
│   ├── receiver_watcher.py
│   └── receiver_config.json
│
├── tests/                 # Юнит-тесты (unittest)
│   ├── test_app.py
│   ├── test_badge_utils.py
│   ├── test_export_utils.py
│   ├── test_presence_logic.py
│   ├── test_receiver_server.py
│   ├── test_receiver_watcher.py
│   ├── test_scorer_logic.py
│   ├── test_selector_series_fallback.py
│   ├── test_series_browser.py
│   └── test_sheet_metadata_fallback.py
│
├── models/                # ML-модели
│   ├── face_landmarker.task    # MediaPipe face landmarker
│   └── face_detector.tflite    # MediaPipe face detector
│
├── tools/                 # Утилиты разработки
│   ├── camera_simulator.py     # Симулятор камеры (подача фото с задержками)
│   └── poc_test.py             # Proof-of-concept тест
│
├── skills/                # Repo-local skills для ассистентов
│   ├── kanatka-docs-maintainer/
│   ├── kanatka-score-debug/
│   └── kanatka-pipeline-smoke/
│
├── docs/
│   ├── project/
│   │   ├── overview.md    # Короткий дашборд задач и проблем
│   │   ├── roadmap.md     # Развёрнутый продуктовый план и этапы
│   │   ├── progress.md    # Журнал сессий (append-only)
│   │   └── startup.md     # Handoff для следующей сессии
│   └── pipeline_diagram.html
│
├── build/                 # PyInstaller + Inno Setup сборка
├── installers/            # Готовые инсталляторы Windows
│
├── workdir/               # Рабочие данные (не в git)
│   ├── incoming/          # Входящие фото от камеры
│   ├── selected/          # Лучшие фото (по одному на серию)
│   ├── sheets/            # Собранные печатные листы
│   ├── discarded/         # Пустые кресла
│   ├── rejected/          # Худшие фото серии
│   ├── archive/           # Архив обработанных
│   ├── logs/              # Логи + annotated фото
│   └── temp/              # Временные файлы
│
├── INBOX/                 # Тестовые фото (исходники)
└── archive/               # Архив устаревших документов
```

---

## 5. Модули — подробное описание

### `main.py` — CLI entry point
- Команды: `process` (обработать папку), `watch` (мониторинг incoming), `sheet` (собрать листы), `gui` (запустить GUI).
- Без команды → запускает GUI.
- Флаг `--config` для альтернативного config.json.

### `gui.py` — Tkinter launcher (~318 строк)
- Класс `PhotoSelectorGUI` — окно с кнопками.
- Кнопки: обработать папку, собрать листы, просмотр серий (веб), упаковать ZIP.
- Секция настроек: автосинхронизация, сетевая папка.
- При запуске автоматически стартует веб-сервер на порту 8787, открывает браузер.
- `_kill_old_server()` — убивает старые процессы на порту через `netstat -ano` + `taskkill`.
- Заголовок: «PhotoSelector — Канатка».

### `series_browser.py` — Веб-интерфейс (~1500 строк)
**Это самый большой и сложный модуль проекта.**
- HTTP-сервер на stdlib (`http.server` + `ThreadingHTTPServer`), порт 8787.
- **Страницы:**
  - `/` — список серий (карточки с превью, бейджами, score-звёздами).
  - `/series/SERxxx` — все фото серии, кнопка «Рядом».
  - `/nearby/SERxxx` — временно́й браузер (±3 серии), batch-rescue.
  - `/settings` — страница настроек инженера (20+ параметров, ползунки, тултипы).
  - `/photo/...` — полноэкранный просмотр.
  - `/logout` — выход из сессии.
- **API:**
  - `POST /api/settings` — сохранение настроек (требует auth).
  - `POST /api/auth` — вход по паролю.
  - `POST /api/change-password` — смена пароля.
  - `POST /api/monitor` — start/stop/status мониторинга INBOX.
  - `POST /api/rescue` — «спасти» фото.
  - `POST /api/batch-rescue` — batch-rescue нескольких фото.
  - `POST /api/export-zip` — ZIP-экспорт.
- **Фичи:**
  - Авторизация: cookie `kanatka_auth`, дефолтный пароль `1234`.
  - Первый вход: подсказка о дефолтном пароле, редирект на смену пароля.
  - Пагинация: 20 серий на страницу.
  - Переключатель размера карточек (крупные/средние/мелкие), сохраняется в localStorage.
  - Мониторинг INBOX: кнопка Start/Stop, индикатор в навбаре (зелёная точка).
  - Score: 5-звёздочный рейтинг + подписи (Отлично/Хорошо/Средне/Слабо/Плохо).
- **Внутренние классы:**
  - `_MonitorState` — глобальное состояние мониторинга (observer, thread, счётчик серий).

### `watcher.py` — Мониторинг папки (~156 строк)
- `group_files_by_time()` — группировка файлов в серии по mtime.
- `process_folder()` — обработка целой папки: группировка → анализ → скоринг → выбор → сборка листов. Возвращает summary dict.
- `PendingQueue` — потокобезопасная очередь файлов с cooldown.
- `IncomingFolderHandler` — watchdog event handler (on_created, on_moved для JPG).
- `watch_incoming_folder()` — бесконечный цикл мониторинга incoming с watchdog Observer.

### `analyzer.py` — Анализ одного фото
- `analyze_photo()` — детекция лиц (MediaPipe) → fallback на Haar upper body → расчёт метрик (sharpness, brightness) → score → badge overlay.
- Возвращает `(metadata_dict, PIL.Image)`.

### `face_utils.py` — Детекция
- `MediaPipeFaceAnalyzer` — класс-обёртка:
  - `analyze_faces(image)` — MediaPipe Face Landmarker, возвращает список лиц с координатами.
  - `detect_person(image)` — Haar upper body cascade fallback для людей в шлемах/очках.
  - Landmarks: `RIGHT_EYE`, `LEFT_EYE`, `MOUTH` — индексы для анализа лица.
- Модели загружаются из `models/face_landmarker.task`.
- Haar cascade из OpenCV: `haarcascade_upperbody.xml`.

### `scorer.py` — Скоринг
- `compute_overall_score(metrics, weights, thresholds)` — расчёт итогового score (0-100).
- 3 компонента: `person_present` (40), `sharpness` (35), `exposure` (25).
- Утилиты: `clamp()`, `normalize_range()`, `centered_score()`.

### `selector.py` — Выбор лучшего в серии
- `process_series()` — обрабатывает серию фото:
  - Анализирует каждый кадр через `analyze_photo()`.
  - Выбирает кадр с максимальным score → `selected/`.
  - Остальные → `rejected/`.
  - Пустые серии (нет людей) → `discarded/`.
  - Генерирует `ser*_report.json`.

### `sheet_composer.py` — Сборка листов
- `compose_sheet()` — собирает одну страницу из N фото (сетка 2x4).
- `compose_pending_sheets()` — берёт фото из `selected/`, собирает листы, перемещает использованные фото в `archive/`.
- Параметры листа в `config.json` → `sheet`.

### `badge_utils.py` — Score overlay (~274 строк)
- `add_score_badge()` — рисует таблицу score поверх фото.
- 3 колонки: Человек, Резкость, Свет.
- Авто-масштаб шрифтов через `fit_table_fonts()` (binary search).
- `DEBUG_COLUMNS` — определение колонок.

### `image_utils.py` — Утилиты изображений
- `read_image()` — чтение через `np.fromfile` + `cv2.imdecode` (поддержка Unicode путей).
- `save_image()` — сохранение.
- `resize_longest_side()` — ресайз с сохранением пропорций.
- `compute_sharpness()` — Laplacian variance.
- `compute_brightness()` — средняя яркость.
- `list_jpeg_files()` — список JPG файлов в папке.
- `crop_image()` — обрезка по координатам.

### `export_utils.py` — Экспорт
- `create_results_zip()` — ZIP с selected + sheets на рабочий стол, фильтр по дате.
- `sync_sheets_to_network()` — копирование новых листов в сетевую папку.

### `config_utils.py` — Конфигурация
- `load_config()` — загрузка `config.json`, резолвинг относительных путей через `PROJECT_ROOT`.
- `save_config()` — сохранение обратно (конвертирует абсолютные пути в относительные).
- `ensure_runtime_directories()` — создание рабочих директорий.
- `get_project_root()` — надёжный корень проекта.
- `save_json()` — утилита записи JSON.

### `metadata_utils.py` — Метаданные фото
- `photo_metadata_enabled()` — проверка, включен ли sidecar JSON.
- `build_photo_metadata_path()` — путь к JSON-метаданным (SHA1-хеш в имени).
- По умолчанию sidecar выключен (`write_photo_metadata_json: false`).

### `logger_setup.py` — Логирование
- `build_logger()` — создаёт logger с файловым + консольным handler.
- Лог: `workdir/logs/photo_selector.log`.

### `runtime_env.py` — Окружение
- `prepare_runtime_environment()` — устанавливает `MPLCONFIGDIR`, возвращает `project_root`.

---

## 6. Инструменты разработки (`tools/`)

### `camera_simulator.py` — Симулятор камеры
- Берёт фото из INBOX, разбивает на серии случайного размера.
- Копирует в `incoming/` с реалистичными задержками.
- Параметры: `--frame-delay` (0.2с), `--series-delay-min/max` (12-20с), `--min-series/max-series` (5-7).
- Запуск: `.venv/Scripts/python.exe tools/camera_simulator.py`.

---

## 7. Конфигурация (`src/config.json`)

| Секция | Назначение | Ключевые параметры |
|--------|------------|-------------------|
| `paths` | Все рабочие папки | `test_photos_folder`, `input_folder`, `output_*`, `log_dir` |
| `series_detection` | Группировка в серии | `max_gap_seconds` (3.0), `cooldown_seconds` (8.0) |
| `haar_cascade` | Параметры Haar fallback | `scale_factor` (1.05), `min_neighbors` (3), `min_size` (60) |
| `processing` | Обработка | `resize_longest_side` (1920) |
| `output` | Выходные файлы | `show_score_badge`, `write_photo_metadata_json` |
| `scoring_weights` | Веса скоринга | `person_present` (40), `sharpness` (35), `exposure` (25) |
| `thresholds` | Пороги детекции | `min_face_confidence`, `min_person_confidence`, sharpness/brightness пороги |
| `network` | Сетевая папка | `output_path`, `auto_sync_sheets` |
| `auth` | Авторизация | `settings_password` (дефолт: `1234`) |
| `sheet` | Параметры листа | `grid_columns` (2), `grid_rows` (4), размеры, качество |

---

## 8. Тесты

- **Фреймворк:** unittest (pytest не установлен в .venv).
- **Запуск:** `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`.
- **24 теста, 7 файлов**, все проходят.
- **Важно:** системный Python не видит cv2 — тесты обязательно через `.venv`.

---

## 9. Документооборот

- `docs/project/overview.md` — дашборд задач, текущие направления.
- `docs/project/roadmap.md` — развёрнутая продуктовая картина и этапы.
- `docs/project/progress.md` — журнал сессий (append-only).
- `docs/project/startup.md` — быстрый handoff для следующей сессии.

---

## 10. Документирование фидбэка (КРИТИЧЕСКИ ВАЖНО)

Каждый фидбэк пользователя, каждое решение, каждое открытие — НЕМЕДЛЕННО фиксировать:
1. Новые задачи и пожелания → добавить строку в dashboard в `overview.md`.
2. Решения и открытия → записать в `progress.md`.
3. Изменения в архитектуре или длинные продуктовые пояснения → обновить `docs/project/roadmap.md`.
4. Новые задачи и нерешённые проблемы → держать в `overview.md`.

**НЕ ОТКЛАДЫВАТЬ.** Не «потом запишу». Не «это я помню». Записать СРАЗУ.

Перед ответом пользователю — перечитать `overview.md` и проверить, что он актуален.

---

## 11. Правила разработки

1. Сначала минимальное решение, потом расширение.
2. Изменения по скорингу сопровождать проверкой на реальных фото.
3. Крупные решения сначала фиксировать в `progress.md`.
4. Тесты запускать через `.venv`: `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`.
5. Перед запуском сервера убивать старые процессы на порту 8787.
6. Рабочая директория: `C:\Users\user\Projects\kanatka2`.
7. В bash использовать: `cd C:/Users/user/Projects/kanatka2 && .venv/Scripts/python.exe ...`.

---

## 12. Известные ограничения и ловушки

1. **Порт 8787:** старые серверные процессы не умирают сами — обязательно убивать перед перезапуском (`_kill_old_server()`).
2. **MediaPipe + экипировка:** люди в полной маске + очки + шлем могут не распознаваться MediaPipe → Haar upper body cascade ловит ~88%.
3. **Unicode пути:** `cv2.imread()` не работает с кириллицей — используем `np.fromfile()` + `cv2.imdecode()`.
4. **Батники:** `run_gui.bat` и `run_demo.bat` НЕ должны переопределять `HOME`/`USERPROFILE` — это ломает Windows file dialog.
5. **pytest:** не установлен, используем `unittest discover`.
6. **Размер EXE:** ожидается ~200-400 МБ из-за MediaPipe + OpenCV.

---

## 13. Что не делать

- Не оставлять критичные решения только в чате.
- Не объявлять "все готово" без проверки пользователя.
- Не удалять существующие артефакты.
- Не сокращать `progress.md` без переноса в `archive/`.

---

## 14. Быстрые ссылки

- `AGENTS.md`
- `docs/project/overview.md`
- `docs/project/startup.md`
- `docs/project/progress.md`
- `TZ_PhotoSelector.md`
- `src/config.json`
- `src/series_browser.py` — главный веб-модуль
- `src/watcher.py` — мониторинг INBOX
- `tools/camera_simulator.py` — симулятор камеры
