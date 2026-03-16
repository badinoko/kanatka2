# Project Overview

Последнее обновление: 2026-03-16

## Product Snapshot

`kanatka2` — **одна программа** (PhotoSelector) для автоматического отбора фотографий с горнолыжной канатки.

**Продукт — это одна программа.** Не две, не клиент-серверная пара. Одна программа на одном компьютере.

Что она делает:
- Мониторит папку с входящими фото от камеры.
- Группирует кадры в серии по времени.
- В каждой серии выбирает лучший кадр (MediaPipe face + Haar upper body fallback).
- Отбрасывает пустые кресла.
- Собирает печатные листы (сетка 2x4).
- Автоматически печатает или сохраняет в тестовом режиме.

Что НЕ является частью продукта:
- `receiver/` — legacy-код, не поставляется заказчику, не собирается по умолчанию.
- Отдельный UI для верхнего компьютера — вне скоупа.
- Live-stream фото оператору — не нужен.

## Canonical Docs

- `docs/project/overview.md` — дашборд задач и проблем.
- `docs/project/roadmap.md` — развёрнутый продуктовый план и этапы.
- `docs/project/startup.md` — быстрый handoff для следующей сессии.
- `docs/project/progress.md` — append-only журнал.
- `docs/project/kan-038-score-design-brief.md` — технический brief по score.

## Dashboard

| ID | Status | Area | Task | Notes |
|---|---|---|---|---|
| KAN-001 | DONE | Docs | Docs-bundle, переход на `CLAUDE.md` | `CODEX.md` перенесен в archive/ |
| KAN-003 | DONE | Debug | Score-overlay поверх фото для отладки | 3 колонки |
| KAN-004 | DONE | Outputs | Per-photo JSON отключены по умолчанию | |
| KAN-005 | NEXT | Config | Оформить настройки путей и логов | `src/config.json` |
| KAN-006 | DONE | Verification | Smoke-проход по реальным сериям | 22/25 selected, 3 discarded |
| KAN-007 | BACKLOG | Performance | Оптимизация под SSD | |
| KAN-008 | DONE | UX | Score-table в шкале 1..5 с подписями | ★★★★☆ + подписи |
| KAN-010 | DONE | Scoring | Упрощение системы скоринга: 6 компонентов → 3 | Теперь требует пересборки |
| KAN-011 | DONE | Detection | Замена HOG на Haar upper body cascade | 22/25 серий вместо 8/25 |
| KAN-012 | DONE | GUI | Веб-просмотрщик серий + ZIP + сетевая синхронизация | `series_browser.py` |
| KAN-013 | DONE | GUI | Временной браузер соседних фото | nearby + batch rescue |
| KAN-014 | DONE | GUI | Фильтрация по дате в ZIP-экспорте | |
| KAN-015 | DONE | GUI | Баг: путь INBOX в file dialog | Исправлено батниками |
| KAN-016 | BACKLOG | GUI | Сворачивание в системный трей | |
| KAN-017 | DONE | GUI | Пароль на настройки | cookie-сессия |
| KAN-018 | BACKLOG | Config | Параметры детекции серий в GUI | Для полевой настройки |
| KAN-019 | DONE | Deploy | Упаковка в EXE + Inno Setup инсталлятор | Пересобрано 2026-03-15, PhotoSelector_Setup.exe 53MB |
| KAN-020 | DONE | GUI | Веб-интерфейс: app-like, sticky nav | |
| KAN-021 | DONE | Config | Страница настроек инженера | 20+ параметров |
| KAN-022 | DONE | Config | Haar cascade параметры в config.json | |
| KAN-023 | BACKLOG | Arch | Полная архитектура LAN-связи двух компьютеров | SMB, порты, firewall |
| KAN-024 | DONE | UX | Автономный режим: мониторинг INBOX | Start/Stop в UI |
| KAN-025 | DONE | GUI | Пагинация серий + «Загрузить ещё» | |
| KAN-026 | BACKLOG | GUI | Встроенное окно вместо браузерной вкладки | Заменён на KAN-030 |
| KAN-027 | BACKLOG | GUI | Play/Stop кнопки управления обработкой | |
| KAN-028 | DONE | GUI | Переключатель размера карточек | 3 режима |
| KAN-029 | DONE | GUI | Улучшить контраст кнопки «Рядом» | |
| KAN-030 | DONE | GUI | Встроенное окно (pywebview) для основной программы | WebView2 |
| KAN-031 | LEGACY | App | Программа-приёмник для типографии | Legacy-код, не поставляется заказчику |
| KAN-032 | DONE | Tools | E2E тест + симулятор камеры | |
| KAN-033 | BACKLOG | Docs | Engineer deployment guide | Отдельный гайд для инженера: установка, WebView2, пути, принтер, сеть, troubleshooting |
| KAN-034 | TODO | Docs | Подробный гайд по настройкам | Для инженера |
| KAN-035 | DONE | Docs | Укрепление CLAUDE.md | Полная инвентаризация модулей |
| KAN-036 | TODO | Infra | Публикация на GitHub | `badinoko/kanatka2` |
| KAN-037 | TODO | Arch | Зафиксировать целевую схему компьютеров и режим поставки | Практически подтверждено, нужно дочистить код и docs |
| KAN-038 | DONE | Scoring | Пересобрать score-модель поверх face-метрик | 3-слойная модель: occupancy → quality → ranking (7 компонентов) |
| KAN-039 | DONE | UX | Ввести режим ambiguous series вместо жёсткого авто-выбора | `decision_state` + `delta_score` + manual review |
| KAN-040 | DONE | Ops | Low-disk warning, cleanup policy и fail mode | `check_disk_space()` в watcher.py; `/api/health`; индикатор в navbar; блокировка мониторинга при critical. Подтверждено пользователем. |
| KAN-041 | DONE | Docs | Синхронизировать README и deploy-docs с фактической архитектурой | Переписано 2026-03-15 |
| KAN-042 | TODO | Docs | Закрыть согласование продуктовой концепции с автором | Источник решений уже сведен в roadmap |
| KAN-043 | DONE | Docs | Пройти с автором короткий checklist и собрать ответы | Ответы получены |
| KAN-044 | DONE | UX | Exception-flow: rescue без блокировки автопечати | Ambiguous → `workdir/ambiguous/`, UI подтверждение, API confirm |
| KAN-045 | DONE | Print | Добавить переключаемый режим автопечати | `autoprint on/off`, `print_utils.py`, UI toggle |
| KAN-046 | TODO | Ops | Решить изоляцию cleanup-подсистемы | Variant C подтверждён: scheduled subprocess worker |
| KAN-047 | DONE | Docs | Зафиксировать финальное решение по queue/autoprint/cleanup | Зафиксировано в roadmap.md по итогам ответов автора |
| KAN-048 | DONE | Docs | Утвердить design brief по новой score-модели | Реализован в KAN-038; brief в `kan-038-score-design-brief.md` |
| KAN-049 | DONE | Docs | Подготовить startup prompt для новой сессии | Архивный артефакт |
| KAN-050 | NEXT | Workflow | Полевой validation-run и калибровка score на реальном датасете | Прогнать датасет заказчика, собрать замечания по сериям/выбору и подобрать рабочие дефолты |
| KAN-051 | DONE | UX | Добавить test mode с эмуляцией печати и preview листов | `/sheets` галерея, zoom, ручная печать, TEST MODE индикатор |
| KAN-056 | DONE | Deploy | Пакет для заказчика: пути в настройках, руководство, инсталляторы | 2026-03-15 |
| KAN-058 | DONE | Workflow | Перевести grouping серий на время создания файла | Подтверждено пользователем в v2 |
| KAN-059 | DONE | Config | Вывести `delta_score` и manual-review в настройки инженера | Подтверждено пользователем в v2 |
| KAN-060 | DONE | Docs | Навести порядок в root `docs/` и синхронизировать пользовательские гайды | Подтверждено пользователем в v2 |
| KAN-061 | BACKLOG | UX | Operator dashboard: только если появится новый запрос от заказчика | Сейчас интерфейса хватает; возвращаться к задаче только после нового UX-feedback |
| KAN-062 | DONE | Workflow | ZIP-архивирование в основном app | Кнопка «Архив» в navbar web-UI: модал с пресетами, `/api/export-zip`. PNG в ZIP починен. ZIP сохраняется на Windows Desktop. Подтверждено пользователем. |
| KAN-063 | DONE | Runtime | Починить старт мониторинга в установленной сборке | Подтверждено пользователем в v2 |
| KAN-064 | DONE | UX | Унифицировать lightbox для листов и фото серий + добавить debug overlay | Подтверждено пользователем в v2 |
| KAN-065 | DONE | Cleanup | Перепроектировать семантику очистки рабочих данных и истории серий | Подтверждено пользователем в v2 |
| KAN-066 | DONE | Tools | Пересмотреть дефолтные интервалы `camera_simulator.py` | Подтверждено пользователем в v2 |
| KAN-067 | DONE | Deploy | Собрать customer test-pack v2 installer с `INBOX`, батниками и актуальным guide | Собран `installers/PhotoSelector_Setup_v2.exe`, пользователь подтвердил рабочий пакет v2 |
| KAN-068 | DONE | Config | Переключатель записи лог-файла в настройках инженера | `log_to_file` в config.json; `build_logger()` принимает флаг; toggle в settings page; нужен рестарт для применения |
| KAN-069 | DONE | UX | Обратный хронологический порядок серий + фикс нумерации | `load_all_series()` reverse=True; `series_idx` продолжается с max существующего, не перезаписывает старые отчёты |

| KAN-070 | DONE | Deploy | Фикс Haar cascade в PyInstaller бандле | `cv2/data/` не включался → все серии пропускались. Добавлен в spec datas. E2E тест из dist/ пройден. |
| KAN-071 | DONE | UX | Серии видимы после сборки листов | `_series_has_live_assets()` теперь проверяет `output_archive` |
| KAN-072 | DONE | UX | Мгновенное обновление кнопки Start/Stop | `_setMonitorBtnState()` в DOM без задержки |
| KAN-073 | DONE | UX | Подтверждение перед закрытием + модалка по клику вне | `confirm_close=True` + overlay onclick |
| KAN-016 | BACKLOG | GUI | Сворачивание в системный трей | Требует `pystray`, новая зависимость. Пользователь обсуждает. |
| KAN-074 | DONE | UX | Фикс лайтбокса на странице Листы: кнопки закрыть/стрелки | `z-index:10` + `overflow:hidden` на `.lightbox-main` |
| KAN-075 | DONE | UX | Превью серии в карточках — показывать лучшее фото | Fallback в `_resolve_series_card_thumb` сортирует по score desc |
| KAN-076 | DONE | UX | Убрать score-бейджи с печатных листов | `sheet.show_score_badge: false` в config.json |
| KAN-077 | DONE | UX | Score в лайтбоксе: убрать дубль, сделать крупным и цветным | Всегда-видимый бейдж в sidebar; для листов — «Средняя оценка по листу» (голубой) |
| KAN-078 | DONE | UX | Score по каждой серии в лайтбоксе листа | `sheet_composer` сохраняет сайдкар JSON; `_render_sheets_gallery` строит мини-сетку 2×N в debug-панели |
| KAN-079 | IN PROGRESS | UX | Редизайн навигационной панели v3.0 | Pill-свитчер Серии/Листы, icon-кнопки 42×42 с tooltip'ами, мониторинг в навбаре на всех страницах, шестерёнка настроек справа, адаптивность до 960px. TEST MODE убран из навбара. Начато 2026-03-16. |
| KAN-080 | DONE | Config/UX | Настройки: фильтр-сайдбар (клик → показывает только один раздел) | Заменить scroll-to-section на show/hide по клику. `series_browser.py` settings render + sidebar JS |
| KAN-081 | DONE | UX/Cleanup | Удалить функционал «Рядом» полностью | Маршрут `/nearby/`, `_render_nearby()`, кнопка «Посмотреть рядом», batch rescue, `/rescue-batch`. Избыточен. |
| KAN-082 | DONE | UX | Страница серии: ручная замена лучшего фото | «Спасти фото» → «Заменить» (зелёная). Убрать бейдж «Уже выбрано» → зелёная рамка + переместить на 1-е место в сетке (JS, без перезагрузки). |
| KAN-083 | DONE | UX | Хлебные крошки: крупнее + добавить на страницу Листов | font-size 17px, насыщенный цвет #2563c7. Breadcrumb добавлен на страницу Листов. |
| KAN-084 | DONE | UX/Data | Переименование серий: SER065 → S_65 | `selector.py` + `series_browser.py` + тесты. Старые SER* не мигрируются. |
| KAN-085 | DONE | UX | Индикатор диска → прогресс-бар | Горизонтальный бар 64×8px, зелёный/жёлтый/красный по `status`. `total_gb` добавлен в `check_disk_space()`. |
| KAN-086 | DONE | UX | Кнопка «Печать»: убрать confirm() диалог | `confirm()` удалён из `printSheet()`. Только toast по результату. |
| KAN-087 | DONE | Config | Выбор принтера: Windows диалог | `<select>` из `win32print.EnumPrinters()`, `/api/list-printers`, авто-загрузка на DOMContentLoaded. `pywin32` в requirements. |
| KAN-088 | DONE | Config/Cleanup | Убрать сетевые настройки из UI | Секция «Сеть» удалена из `_SETTINGS_SCHEMA`. `sync_sheets_to_network()` в коде оставлена. |
| KAN-089 | DONE | Workflow/UX | Приоритетная очередь печати (bump-механика) | `compose_if_ready()` в `sheet_composer.py`: при rescue сразу собирает лист если хватает фото. Мониторинг не прерывается. |
| KAN-090 | DONE | UX/Workflow | Сценарий 3: клиент просит другое фото | Покрывается KAN-082 (кнопка «Заменить») + KAN-089 (bump-печать). Отдельного режима не требуется. |

| KAN-091 | BUG | UX | Monitor button: stale state на /settings | Polling статуса мониторинга идёт только на страницах `series-list` и `sheets`. На `/settings` кнопка не обновляется — показывает устаревшее состояние. Фикс: добавить `settings` в условие DOMContentLoaded JS-поллинга. |
| KAN-092 | BUG | Config | Принтер не сохраняется в настройках | `<select name="print.printer_name">` — но `saveSettings()` сериализует ключи через `__`. Точечный сепаратор → изменение принтера молча игнорируется. Фикс: `name="print__printer_name"`. |
| KAN-093 | BUG | Data | Неправильная сортировка серий при >9 штук | `load_all_series()` сортирует `s_*_report.json` лексикографически → `s_9` будет после `s_10`. Фикс: числовая сортировка через извлечение индекса. |
| KAN-094 | BUG | Data | Sheet metadata: серия записывается как `"S"` | `name.split('_')[0]` возвращает `"S"` вместо `"S_1"`. Фикс: парсить полный префикс `S_<n>` через regex или `split('_', 2)[:2]`. |

## Current Priorities

- **KAN-091..094 (BUG)**: 4 бага, выявленных code review ботом при merge PR #1 — **приоритет первой сессии после merge**.
- **KAN-079 + v3.0 UX Wave**: PR #1 (`kan-079-navbar-v3-redesign`) — слияние с main выполняет пользователь.
- **KAN-050**: прогнать реальный датасет заказчика, собрать замечания и откалибровать дефолтные параметры score и series grouping.
- **KAN-016** (BACKLOG): сворачивание в системный трей — обсуждается.
- **KAN-033** (BACKLOG): deployment guide для инженера — позже.

## Current Problems

- **4 бага после KAN-084/087** — выявлены ботом при PR review (KAN-091..094), нужен фикс до следующей поставки.
- Score-модель требует калибровки весов на реальных полевых данных.
- Политика хранения оригиналов пока не зафиксирована: keep/delete/archive для `incoming` и уже обработанных кадров описаны не до конца.
- PyInstaller бандл требует ручного E2E тестирования из dist/ — юнит-тесты не ловят проблемы упаковки.
