# Startup

Обновлено: 2026-03-16 (v3.0 UX Wave — DONE)

## Read Order

1. `CLAUDE.md`
2. `CODEX.md`
3. `docs/project/overview.md`
4. `docs/project/roadmap.md`
5. `docs/project/startup.md`
6. tail `docs/project/progress.md`
7. `archive/project/2026-03-15/kan-038-score-design-brief.md` if работа идёт по score

## Quick Context

- `kanatka2` — коммерческая программа отбора фото с горнолыжной канатки.
- Пользователь — не программист, готовит систему и инженера к реальной установке на объекте.
- **Продукт = одна программа (PhotoSelector).** Один EXE, один инсталлятор.
- `receiver/` — legacy-код, не поставляется, не собирается по умолчанию.
- Камера складывает фото в папку → PhotoSelector делает всё остальное.
- Серии должны формироваться по времени создания файла; рабочий ориентир заказчика — не больше 2 секунд внутри серии.
- В engineer settings формулировки series timing уже переименованы в более понятные:
  - `Макс. разрыв внутри серии`
  - `Ожидание тишины перед разбором`
- Основной выход — автоматически печатаемые листы.
- `nearby/rescue`: функционал «Рядом» удалён (KAN-081). Остаётся только кнопка «Заменить» на странице серии.

## Canonical Docs

- `docs/project/overview.md` — короткий дашборд задач и проблем.
- `docs/project/roadmap.md` — развёрнутая картина продукта и этапов.
- `docs/project/startup.md` — этот файл.
- `docs/project/progress.md` — append-only журнал (полная история до v2.0 → `archive/project/2026-03-16/progress_full_v2.md`).
- `archive/project/2026-03-15/kan-038-score-design-brief.md` — технический brief по score (архивирован, KAN-038 DONE).

Одноразовые обсужденческие документы 2026-03-15 вынесены в:
- `archive/project/2026-03-15/`

Временные пользовательские файлы с `!!!!!` не считаются каноническими docs.

## What Exists Right Now

- Основной app:
  - pywebview + `series_browser.py`;
  - watcher -> analyzer -> scorer -> selector -> sheet composer;
  - настройки инженера уже есть;
  - мониторинг INBOX уже есть;
  - функционал «Рядом» (nearby) запланирован к удалению (KAN-081).
- Отгружен финальный installer v2.0:
  - `installers/PhotoSelector_Setup_v2.exe` (пересобран 2026-03-16 со всеми фиксами)
  - в поставке: `INBOX`, `simulate_camera.bat`, `process_folder.bat`, `README.md`.
  - Заказчик тестирует на своих 270 фото.
- `receiver/` — legacy-код, не часть продукта.
- Все задачи KAN-040, 062, 068, 069 — DONE. Мониторинг, ZIP, disk indicator, log toggle, обратная сортировка, фикс нумерации серий при перезапуске.
- Главный технический риск:
  - Score-модель требует калибровки на реальных данных заказчика;
  - grouping серии критичен и должен опираться именно на время создания файла.

## Immediate Priorities

- **v3.0 UX Wave (KAN-080..090) — DONE** (реализованы 2026-03-16, 61 тест пройден).
- **KAN-079** (navbar v3): PR #1 на ветке `kan-079-navbar-v3-redesign`. Нужен merge в main.
- **KAN-050**: прогнать реальный датасет заказчика, собрать замечания, откалибровать дефолты score и series grouping.
- KAN-033 (BACKLOG): deployment guide для инженера — позже.

## Execution Brief For New Chat

Если новая сессия должна сразу переходить к работе, а не к повторному анализу, стартовая дисциплина такая:

1. Прочитать:
   - `CLAUDE.md`
   - `CODEX.md`
   - `docs/project/overview.md`
   - `docs/project/roadmap.md`
   - `docs/project/startup.md`
   - tail `docs/project/progress.md`
   - `archive/project/2026-03-15/kan-038-score-design-brief.md`
2. Принять как исходные условия:
   - основной workflow живёт на нижнем ПК;
   - оператору не нужен live-photo stream;
   - серии формируются по времени создания файла, целевое окно внутри серии = до 2 секунд;
   - спорные серии должны полностью выходить из текущего workflow и не тормозить остальные листы;
   - cleanup подтверждён как scheduled subprocess worker;
   - `installers/` больше не игнорируется;
   - актуальный артефакт для заказчика: `installers/PhotoSelector_Setup_v2.exe` (собран 2026-03-16);
   - следующий milestone — feedback от заказчика по его тест-пачке и калибровка score.
3. v3.0 UX Wave — **ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ** (KAN-080..090 DONE).
   Следующий шаг: merge PR #1 (`kan-079-navbar-v3-redesign`) → main.
4. Кодовый фокус:
   - `src/series_browser.py` (основной объём UX Wave)
   - `src/selector.py` (KAN-084)
   - `src/sheet_composer.py` (KAN-089)
5. Не тратить время на:
   - `receiver/` (legacy, не часть продукта);
   - тяжёлый live-UI;
   - постоянный cleanup daemon.

## Useful Mental Model

Не думать о продукте как о “программе, которая показывает оператору поток фото”.

Правильнее думать так:
- основной поток — автоматический;
- экран на нижнем ПК — control panel, print/test preview и exception console;
- оператор вмешивается редко, когда система сама неуверенна или когда клиент просит другой кадр.

## First Code Files To Read For Next Step

1. `src/scorer.py`
2. `src/analyzer.py`
3. `src/selector.py`
4. `src/series_browser.py`
5. `src/config.json`
6. `workdir/logs/s_1_report.json` (после KAN-084) или `ser001_report.json` (до)

## Build & Verify

Перед любой сборкой EXE/инсталлятора — обязательно пройти чеклист: `docs/build_and_verify.md`.

Юнит-тесты не ловят проблемы PyInstaller-бандла. E2E тест из `dist/` — обязателен.

## Known Pitfalls

- Порт 8787: старые процессы нужно убивать перед перезапуском.
- Тесты запускать только через `.venv`.
- Не путать `mtime` и время создания файла: для series grouping заказчик подтвердил именно creation time.
- Не расширять `overview.md` narrative-секциями обратно.
