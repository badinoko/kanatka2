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
| KAN-040 | TODO | Ops | Low-disk warning, cleanup policy и fail mode | Нужны предупреждение о заполнении диска и понятное поведение при нехватке места |
| KAN-041 | DONE | Docs | Синхронизировать README и deploy-docs с фактической архитектурой | Переписано 2026-03-15 |
| KAN-042 | TODO | Docs | Закрыть согласование продуктовой концепции с автором | Источник решений уже сведен в roadmap |
| KAN-043 | DONE | Docs | Пройти с автором короткий checklist и собрать ответы | Ответы получены |
| KAN-044 | DONE | UX | Exception-flow: rescue без блокировки автопечати | Ambiguous → `workdir/ambiguous/`, UI подтверждение, API confirm |
| KAN-045 | DONE | Print | Добавить переключаемый режим автопечати | `autoprint on/off`, `print_utils.py`, UI toggle |
| KAN-046 | TODO | Ops | Решить изоляцию cleanup-подсистемы | Variant C подтверждён: scheduled subprocess worker |
| KAN-047 | TODO | Docs | Зафиксировать финальное решение по queue/autoprint/cleanup | После внешних уточнений |
| KAN-048 | TODO | Docs | Утвердить design brief по новой score-модели | База: `kan-038-score-design-brief.md` |
| KAN-049 | DONE | Docs | Подготовить startup prompt для новой сессии | Архивный артефакт |
| KAN-050 | NEXT | Workflow | Полевой validation-run и калибровка score на реальном датасете | Прогнать датасет заказчика, собрать замечания по сериям/выбору и подобрать рабочие дефолты |
| KAN-051 | DONE | UX | Добавить test mode с эмуляцией печати и preview листов | `/sheets` галерея, zoom, ручная печать, TEST MODE индикатор |
| KAN-056 | DONE | Deploy | Пакет для заказчика: пути в настройках, руководство, инсталляторы | 2026-03-15 |
| KAN-058 | DONE | Workflow | Перевести grouping серий на время создания файла | Подтверждено пользователем в v2 |
| KAN-059 | DONE | Config | Вывести `delta_score` и manual-review в настройки инженера | Подтверждено пользователем в v2 |
| KAN-060 | DONE | Docs | Навести порядок в root `docs/` и синхронизировать пользовательские гайды | Подтверждено пользователем в v2 |
| KAN-061 | BACKLOG | UX | Operator dashboard: только если появится новый запрос от заказчика | Сейчас интерфейса хватает; возвращаться к задаче только после нового UX-feedback |
| KAN-062 | TODO | Workflow | Зафиксировать политику хранения оригиналов и ZIP-архивирования | Нужно решить судьбу исходников и вернуть явный ZIP-flow в основной app, а не только в legacy launcher |
| KAN-063 | DONE | Runtime | Починить старт мониторинга в установленной сборке | Подтверждено пользователем в v2 |
| KAN-064 | DONE | UX | Унифицировать lightbox для листов и фото серий + добавить debug overlay | Подтверждено пользователем в v2 |
| KAN-065 | DONE | Cleanup | Перепроектировать семантику очистки рабочих данных и истории серий | Подтверждено пользователем в v2 |
| KAN-066 | DONE | Tools | Пересмотреть дефолтные интервалы `camera_simulator.py` | Подтверждено пользователем в v2 |
| KAN-067 | DONE | Deploy | Собрать customer test-pack v2 installer с `INBOX`, батниками и актуальным guide | Собран `installers/PhotoSelector_Setup_v2.exe`, пользователь подтвердил рабочий пакет v2 |

## Current Priorities

- KAN-050: прогнать реальный датасет заказчика, собрать замечания и откалибровать дефолтные параметры.
- KAN-062: определить политику хранения оригиналов и вернуть удобную ZIP-выгрузку в основной app.
- KAN-040: добавить low-disk warning и зафиксировать fail mode при нехватке места.
- KAN-033: позже оформить отдельный deployment guide для инженера.

## Current Problems

- Score-модель требует калибровки весов на реальных полевых данных.
- В основном `pywebview` app нет явной ZIP-выгрузки, хотя сам механизм жив и работает в legacy `tkinter` launcher.
- Политика хранения оригиналов пока не зафиксирована: keep/delete/archive для `incoming` и уже обработанных кадров описаны не до конца.
- Нет явного low-disk warning и формально зафиксированного fail mode при нехватке места на диске.
