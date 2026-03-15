# Startup

Обновлено: 2026-03-15

## Quick Context

- Проект `kanatka2` — коммерческая программа отбора фото с горнолыжной канатки. Продукт на продажу.
- Пользователь — **не программист**. Готовит инженера к поездке на горнолыжный курорт.
- **Два EXE-файла** собраны: PhotoSelector (192 МБ) + KanatkaReceiver (40 МБ).
- Актуальный рабочий регламент: `CLAUDE.md` (полный справочник, обновлён 2026-03-15).
- Дашборд и журнал:
  - `docs/project/overview.md` — задачи, приоритеты, статусы.
  - `docs/project/progress.md` — журнал сессий.

## What Exists Right Now

### Основная программа (PhotoSelector):
- Пайплайн: `watcher.py` → `analyzer.py` → `scorer.py` → `selector.py` → `sheet_composer.py`.
- **UI: pywebview** (нативное окно WebView2/Edge) → HTTP-сервер на localhost:8787.
- Точка входа: `src/app.py` (pywebview). Fallback: `src/gui.py` (tkinter).
- **Веб-интерфейс (`series_browser.py`, ~1500 строк) — основной UI:**
  - Серии: карточки, бейджи, score-звёзды, пагинация (20/стр), переключатель размера.
  - Временной браузер: показ соседних серий, batch-rescue.
  - Настройки инженера: 20+ параметров, ползунки, тултипы, пароль (дефолт 1234).
  - Мониторинг INBOX: Start/Stop кнопка, зелёный индикатор.
  - Авторизация: cookie-сессия, смена пароля, first-login подсказка.
- Экспорт: ZIP с фильтрацией по дате, автосинхронизация в сетевую папку.
- Скоринг: `person_present` (40) + `sharpness` (35) + `exposure` (25) = 100.
- Детекция: MediaPipe face → Haar upper body cascade fallback. 22/25 = 88%.

### Программа-приёмник (KanatkaReceiver):
- `receiver/receiver_app.py` — pywebview, порт 8788.
- Следит за папкой (watchdog), показывает листы в сетке с автообновлением.
- При первом запуске: диалог выбора папки, сохранение в `receiver_config.json`.
- Без ML-зависимостей — только Pillow + watchdog.

### Сборка (PyInstaller):
- `build/build.py` — скрипт сборки (`--main`, `--receiver`, `--all`).
- `build/kanatka.spec`, `build/receiver.spec` — спецификации.
- Результат: `dist/PhotoSelector/`, `dist/KanatkaReceiver/`.

### Тесты:
- 34 теста, все проходят через `.venv/Scripts/python.exe`.

## Что осталось

**Приоритет 2 — тестирование и документация:**
- KAN-032: Улучшить симулятор камеры для E2E тестирования.
- KAN-033: Deployment README для инженера.
- KAN-034: Гайд по настройкам.

**Приоритет 3 — backlog:**
- KAN-016: Системный трей.
- KAN-023: Архитектура LAN-связи.
- KAN-007: Оптимизация под SSD.
- KAN-027: Play/Stop кнопки.

## First Files To Read

1. `CLAUDE.md` — полный справочник (структура, модули, конфигурация, ловушки)
2. `docs/project/overview.md` — дашборд задач с приоритетами
3. `docs/project/progress.md` (последняя запись)
4. `src/config.json` — все настройки
5. `src/app.py` — pywebview launcher (главная точка входа)
6. `src/series_browser.py` — главный веб-модуль (~1500 строк)
7. `receiver/receiver_app.py` — приёмник

## Known Pitfalls

- Порт 8787: убивать старые процессы перед перезапуском.
- Порт 8788: приёмник на отдельном порту.
- Тесты: только через `.venv/Scripts/python.exe`, не через системный Python.
- В bash: `cd C:/Users/user/Projects/kanatka2 && .venv/Scripts/python.exe ...`.
- `run_gui.bat` НЕ должен переопределять `HOME`/`USERPROFILE`.
- `.venv` была создана для `kanatka`, pip может ставить пакеты не туда — использовать `--target`.
- EXE-размер: PhotoSelector ~192 МБ, KanatkaReceiver ~40 МБ — это нормально.
