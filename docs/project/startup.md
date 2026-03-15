# Startup

Обновлено: 2026-03-15

## Quick Context

- Проект `kanatka2` — коммерческая программа отбора фото с горнолыжной канатки. Продукт на продажу.
- Пользователь — **не программист**. Готовит инженера к поездке на горнолыжный курорт.
- **Два инсталлятора Windows** собраны: PhotoSelector_Setup.exe (53 МБ) + KanatkaReceiver_Setup.exe (15 МБ).
- Актуальный рабочий регламент: `CLAUDE.md` (полный справочник, обновлён 2026-03-15).
- Новый `CODEX.md` создан как короткий companion для Codex-сессий.
- Дашборд и журнал:
  - `docs/project/overview.md` — задачи, приоритеты, статусы.
  - `docs/project/progress.md` — журнал сессий.
- Главная новая неопределённость уже сузилась: компьютеров два физически, но по свежему пояснению автора проекта нижний компьютер у принтера делает всю обработку, а верхний малый компьютер у камеры в основном передаёт фото по сети.
- Для внешнего согласования подготовлен документ: `docs/project/author-review-2026-03-15.md`.
- Для быстрой переписки с автором подготовлен короткий вопросник: `docs/project/author-checklist-2026-03-15.md`.
- По трём спорным местам подготовлен decision-note: `docs/project/decision-note-2026-03-15-queue-print-cleanup.md`.
- Для следующего шага по качеству отбора подготовлен design brief: `docs/project/kan-038-score-design-brief.md`.
- Для нового окна чата подготовлен copy-paste prompt: `docs/project/new-chat-prompt-2026-03-15.md`.
- Ответы автора уже получены; ими подтверждены архитектура, базовая философия score и необязательность `receiver/`.

## What Exists Right Now

### Текущая рекомендуемая топология
- Верхний малый ПК у камеры: только capture/transfer node.
- Общая сетевая папка: мост между узлами.
- Нижний ПК у принтера: главный processing/printing node.
- Практический вывод: в следующей сессии смотреть на `src/config.json -> paths.input_folder` как на будущую сетевую входящую папку нижнего ПК.

### Основная программа (PhotoSelector):
- Пайплайн: `watcher.py` → `analyzer.py` → `scorer.py` → `selector.py` → `sheet_composer.py`.
- **UI: pywebview** (нативное окно WebView2/Edge) → HTTP-сервер на localhost:8787.
- Точка входа: `src/app.py` (pywebview). Fallback: `src/gui.py` (tkinter).
- **Веб-интерфейс (`series_browser.py`, ~1500 строк) — основной UI:**
  - Серии: карточки, бейджи, score-звёзды, пагинация (20/стр), переключатель размера.
  - Временной браузер: показ соседних серий, batch-rescue.
  - Настройки инженера: 20+ параметров, ползунки, тултипы, пароль (дефолт 1234).
  - Мониторинг INBOX: Start/Stop кнопка, зелёный индикатор.
  - Авторизация: HTML form POST + 302 redirect (pywebview-совместимо), cookie-сессия.
- Экспорт: ZIP с фильтрацией по дате, автосинхронизация в сетевую папку.
- Скоринг: `person_present` (40) + `sharpness` (35) + `exposure` (25) = 100.
- Детекция: MediaPipe face → Haar upper body cascade fallback. 22/25 = 88%.
- Важно: код уже собирает `yaw/pitch/roll`, `ear`, `mouth_ratio`, но итоговый `score` их не использует.

### Программа-приёмник (KanatkaReceiver):
- `receiver/receiver_app.py` — pywebview, порт 8788.
- Следит за папкой (watchdog), показывает листы в сетке с автообновлением.
- При первом запуске: диалог выбора папки, сохранение в `receiver_config.json`.
- Без ML-зависимостей — только Pillow + watchdog.
- Статус на 2026-03-15: реализовано, но продуктовая необходимость переоценивается.

### Сборка и инсталляторы:
- `build/build.py` — полный скрипт сборки (`--main`, `--receiver`, `--installers`, `--all`).
- PyInstaller: `build/kanatka.spec`, `build/receiver.spec`.
- Inno Setup: `build/photoselector.iss`, `build/receiver.iss`.
- Результат: `installers/PhotoSelector_Setup.exe`, `installers/KanatkaReceiver_Setup.exe`.

### E2E тестирование:
- `tools/e2e_test.py` — запуск обеих программ на одном компьютере с симулятором камеры.
- `tools/camera_simulator.py` — подача фото из INBOX с реалистичными задержками.
- Режимы: `--fast`, `--headless`, `--duration`.

### Тесты:
- 34 теста, все проходят через `.venv/Scripts/python.exe`.

## Что осталось

**Приоритет 1 — сначала убрать архитектурную путаницу:**
- KAN-037: Зафиксировать целевую схему компьютеров и понять, нужен ли `receiver/` в продукте.
- KAN-038: Пересобрать score-модель поверх уже существующих face-метрик.
- KAN-039: Решить судьбу ambiguous-series и порога близких score.

Практическая трактовка KAN-037 на сейчас:
- основной app живёт на нижнем ПК;
- верхний ПК не рассматривается как место основной логики отбора;
- `receiver/` пока не удалять, но и не считать обязательным для поставки.
- nearby/rescue считать штатной частью основной программы.
- Следующий реальный шаг до нового кода: получить ответы автора на checklist.
  Обновление: ответы уже есть; следующий шаг теперь не сбор мнений, а проектирование score и operator-flow.
- По score уже подготовлен отдельный implementation-oriented brief; это главный документ следующего этапа.
- Уже можно начинать KAN-038 без ожидания новых ответов автора; для этого есть отдельный new-chat prompt.

Открытые вопросы после ответов автора:
- как не блокировать очередь, если оператору показывается “Фото рядом”;
- как именно включать/выключать автопечать;
- нужен ли cleanup как отдельный процесс ради изоляции ошибок.

**Приоритет 2 — документация для инженера:**
- KAN-033: Deployment README для инженера.
- KAN-034: Гайд по настройкам.
- KAN-036: Публикация на GitHub.
- KAN-041: Синхронизация README с реальным состоянием проекта.

**Приоритет 3 — backlog:**
- KAN-016: Системный трей.
- KAN-023: Архитектура LAN-связи.
- KAN-007: Оптимизация под SSD.
- KAN-027: Play/Stop кнопки.
- KAN-040: Retention/cleanup и health-check сервис.

## First Files To Read

1. `CLAUDE.md` — полный справочник (структура, модули, конфигурация, ловушки)
2. `CODEX.md` — короткая Codex-памятка по текущей развилке
3. `docs/project/overview.md` — дашборд задач с приоритетами
4. `docs/project/progress.md` (последняя запись)
5. `docs/project/author-checklist-2026-03-15.md` — короткий вопросник для автора
6. `docs/project/author-review-2026-03-15.md` — подробный документ на согласование
7. `docs/project/decision-note-2026-03-15-queue-print-cleanup.md` — варианты решений по queue/autoprint/cleanup
8. `docs/project/kan-038-score-design-brief.md` — базовый brief для новой score-модели
9. `docs/project/new-chat-prompt-2026-03-15.md` — copy-paste prompt для новой сессии
10. `src/config.json` — все настройки
11. `src/scorer.py` — текущее место упрощения score до 3 компонентов
12. `workdir/logs/ser001_report.json` — наглядный пример, где fallback-кадр выигрывает у кадра с найденным лицом
13. `src/app.py` — pywebview launcher
14. `src/series_browser.py` — главный веб-модуль (~1500 строк)
15. `src/watcher.py` — важно для перехода на сетевую входящую папку

## Known Pitfalls

- Порт 8787: убивать старые процессы перед перезапуском.
- Порт 8788: приёмник на отдельном порту.
- pywebview/WebView2: Set-Cookie из fetch() не сохраняется — использовать HTML form POST + 302 redirect.
- Документация частично рассинхронизирована: README и часть архитектурных описаний отстают от кода и новой вводной.
- Нельзя автоматически считать `receiver/` финальным ядром продукта, пока не закрыт KAN-037.
- Нельзя автоматически считать текущие 3 score-компонента достаточными для сложных серий.
- Тесты: только через `.venv/Scripts/python.exe`, не через системный Python.
- В bash: `cd C:/Users/user/Projects/kanatka2 && .venv/Scripts/python.exe ...`.
- `.venv` была создана для `kanatka`, pip может ставить пакеты не туда — использовать `--target`.
- Инсталляторы: PhotoSelector_Setup.exe ~53 МБ, KanatkaReceiver_Setup.exe ~15 МБ — это нормально.
