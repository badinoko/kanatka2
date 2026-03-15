# Project Overview

Последнее обновление: 2026-03-15

## Product Snapshot

`kanatka2` — программа автоматического отбора фотографий с горнолыжной канатки.

Текущее рабочее понимание:
- верхний ПК у камеры в основном передаёт фото по сети;
- нижний ПК у принтера делает основной workflow;
- основной боевой режим: автоматическая сборка и печать листов;
- `nearby/rescue` нужен как исключительный инструмент, а не как обязательный live-stage;
- `receiver/` пока считается optional/legacy, не обязательным ядром продукта.

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
| KAN-019 | DONE | Deploy | Упаковка в 2 EXE + Inno Setup инсталляторы | Оба setup готовы |
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
| KAN-031 | DONE | App | Программа-приёмник для типографии | Реализована, продуктовая необходимость переоценивается |
| KAN-032 | DONE | Tools | E2E тест + симулятор камеры | |
| KAN-033 | TODO | Docs | Deployment README | Настройка сети и запуска |
| KAN-034 | TODO | Docs | Подробный гайд по настройкам | Для инженера |
| KAN-035 | DONE | Docs | Укрепление CLAUDE.md | Полная инвентаризация модулей |
| KAN-036 | TODO | Infra | Публикация на GitHub | `badinoko/kanatka2` |
| KAN-037 | TODO | Arch | Зафиксировать целевую схему компьютеров и режим поставки | Практически подтверждено, нужно дочистить код и docs |
| KAN-038 | TODO | Scoring | Пересобрать score-модель поверх face-метрик | Главный следующий кодовый шаг |
| KAN-039 | TODO | UX | Ввести режим ambiguous series вместо жёсткого авто-выбора | `delta_score` + manual review |
| KAN-040 | TODO | Ops | Спроектировать retention/cleanup и health-check сервис | Без рискованных побочных эффектов |
| KAN-041 | TODO | Docs | Синхронизировать README и deploy-docs с фактической архитектурой | README отстаёт |
| KAN-042 | TODO | Docs | Закрыть согласование продуктовой концепции с автором | Источник решений уже сведен в roadmap |
| KAN-043 | DONE | Docs | Пройти с автором короткий checklist и собрать ответы | Ответы получены |
| KAN-044 | TODO | UX | Спроектировать exception-flow для rescue без блокировки автопечати | Variant B подтверждён: `delta_score` настраивается, спорные серии полностью уходят из workflow и не задерживают листы |
| KAN-045 | TODO | Print | Добавить переключаемый режим автопечати | `autoprint on/off` |
| KAN-046 | TODO | Ops | Решить изоляцию cleanup-подсистемы | Variant C подтверждён: scheduled subprocess worker |
| KAN-047 | TODO | Docs | Зафиксировать финальное решение по queue/autoprint/cleanup | После внешних уточнений |
| KAN-048 | TODO | Docs | Утвердить design brief по новой score-модели | База: `kan-038-score-design-brief.md` |
| KAN-049 | DONE | Docs | Подготовить startup prompt для новой сессии | Архивный артефакт |
| KAN-050 | TODO | Workflow | Привести продукт к реальному полевому workflow заказчика | Автопечать по умолчанию, rescue как исключение |
| KAN-051 | TODO | UX | Добавить test mode с эмуляцией печати и preview листов | Zoom + debug overlays без реальной печати |

## Current Priorities

- KAN-038: переписать score так, чтобы пустое кресло и слабый fallback не побеждали читаемые кадры.
- KAN-039: добавить статус `ambiguous_manual_review` вместо ложной уверенности автоматики.
- KAN-044: спроектировать exception-flow для rescue без остановки основного потока.
- KAN-045: ввести переключаемый `autoprint`.
- KAN-050: довести продукт до реального полевого workflow заказчика.
- KAN-051: сделать безопасный test mode с экранной эмуляцией печати.

## Current Problems

- `score` слишком чувствителен к порогам и упрощён до 3 компонентов.
- README и deployment-docs не синхронизированы с новым пониманием архитектуры.
- Нужна чёткая грань между боевым автопотоком и инженерным режимом настройки/эмуляции.
