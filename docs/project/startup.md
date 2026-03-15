# Startup

Обновлено: 2026-03-15

## Read Order

1. `CLAUDE.md`
2. `CODEX.md`
3. `docs/project/overview.md`
4. `docs/project/roadmap.md`
5. `docs/project/startup.md`
6. tail `docs/project/progress.md`
7. `docs/project/kan-038-score-design-brief.md` if работа идёт по score

## Quick Context

- `kanatka2` — коммерческая программа отбора фото с горнолыжной канатки.
- Пользователь — не программист, готовит систему и инженера к реальной установке на объекте.
- **Продукт = одна программа (PhotoSelector).** Один EXE, один инсталлятор.
- `receiver/` — legacy-код, не поставляется, не собирается по умолчанию.
- Камера складывает фото в папку → PhotoSelector делает всё остальное.
- Основной выход — автоматически печатаемые листы.
- `nearby/rescue` — инструмент исключений, не основной workflow.

## Canonical Docs

- `docs/project/overview.md` — короткий дашборд задач и проблем.
- `docs/project/roadmap.md` — развёрнутая картина продукта и этапов.
- `docs/project/startup.md` — этот файл.
- `docs/project/progress.md` — append-only журнал.
- `docs/project/kan-038-score-design-brief.md` — технический brief для следующего score-шага.

Одноразовые обсужденческие документы 2026-03-15 вынесены в:
- `archive/project/2026-03-15/`

Временные пользовательские файлы с `!!!!!` не считаются каноническими docs.

## What Exists Right Now

- Основной app:
  - pywebview + `series_browser.py`;
  - watcher -> analyzer -> scorer -> selector -> sheet composer;
  - настройки инженера уже есть;
  - nearby/rescue уже есть;
  - мониторинг INBOX уже есть.
- `receiver/` — legacy-код, не часть продукта.
- Главный технический риск:
  - score слишком упрощён;
  - результат слишком чувствителен к thresholds;
  - fallback и пустые/слабые кадры могут вести себя неправильно.
- По raw feedback автора на decision-note уже подтверждено:
  - operator queue = variant B;
  - `delta_score` должен настраиваться;
  - спорные серии полностью выходят из workflow до решения по ним и не тормозят остальные листы;
  - cleanup = variant C, scheduled subprocess worker.

## Immediate Priorities

- KAN-038: переписать score-модель.
- KAN-039: ввести `ambiguous_manual_review`.
- KAN-044: сделать exception-flow без блокировки автопечати.
- KAN-045: ввести переключаемый `autoprint`.
- KAN-050: привести продукт к реальному workflow заказчика.
- KAN-051: сделать test mode с экранной эмуляцией печати.

## Execution Brief For New Chat

Если новая сессия должна сразу переходить к работе, а не к повторному анализу, стартовая дисциплина такая:

1. Прочитать:
   - `CLAUDE.md`
   - `CODEX.md`
   - `docs/project/overview.md`
   - `docs/project/roadmap.md`
   - `docs/project/startup.md`
   - tail `docs/project/progress.md`
   - `docs/project/kan-038-score-design-brief.md`
2. Принять как исходные условия:
   - основной workflow живёт на нижнем ПК;
   - оператору не нужен live-photo stream;
   - спорные серии должны полностью выходить из текущего workflow и не тормозить остальные листы;
   - cleanup подтверждён как scheduled subprocess worker;
   - `installers/` больше не игнорируется, но старые `.exe` удалены и ждут новой сборки.
3. Выполнять задачи в таком порядке:
   - KAN-038: новая score-модель;
   - KAN-039: `decision_state` и `ambiguous_manual_review`;
   - KAN-044: exception-flow без остановки автопечати;
   - KAN-045: `autoprint on/off`;
   - KAN-051: test mode с экранной эмуляцией печати.
4. Кодовый фокус первой волны:
   - `src/scorer.py`
   - `src/analyzer.py`
   - `src/selector.py`
   - затем только нужные части `src/series_browser.py`
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
6. `workdir/logs/ser001_report.json`

## Known Pitfalls

- Порт 8787: старые процессы нужно убивать перед перезапуском.
- Тесты запускать только через `.venv`.
- README и deployment-docs ещё не синхронизированы с текущей архитектурой.
- Не расширять `overview.md` narrative-секциями обратно.
