# Progress

> Полный журнал сессий до v2.0 включительно: [`archive/project/2026-03-16/progress_full_v2.md`](../../archive/project/2026-03-16/progress_full_v2.md)

---

## Хронология проекта (summary)

### 2026-03-14 — Старт kanatka2

- Проект скопирован из `kanatka` для независимого развития.
- Введена docs-структура: `overview.md`, `startup.md`, `progress.md`, `roadmap.md`.
- Радикальное упрощение скоринга: 6 компонентов → 3 (`person_present`, `sharpness`, `exposure`).
- HOG person detection заменён на Haar upper body cascade — результат вырос с 4/25 до 22/25 selected серий.
- Реализован веб-просмотрщик серий (`series_browser.py`) на stdlib `http.server`, порт 8787.
- Реализованы утилиты экспорта (`export_utils.py`): ZIP + сетевая синхронизация.
- Интеграция в tkinter GUI: кнопки «Просмотр серий», «Упаковать ZIP».

### 2026-03-14 — Фидбэк пользователя и продуктовое видение

- Определено: продукт на продажу, не внутренний инструмент.
- Веб-интерфейс — основной UI (app-like UX, sticky navbar).
- Настройки инженера за паролем (admin mode, дефолт `1234`).
- Временной браузер (nearby) для rescue вместо простого «Спасти фото».
- Двухкомпьютерная архитектура: верхний ПК (камера) → сетевая папка → нижний ПК (обработка + печать).

### 2026-03-15 — Критический путь к поставке

- **KAN-030:** Встроенное окно через pywebview (WebView2/Edge).
- **KAN-031:** Программа-приёмник для типографии (`receiver/`) — позже переведена в legacy.
- **KAN-019:** PyInstaller сборка в EXE, Inno Setup инсталляторы.
- Архитектурная переоценка: один продукт (PhotoSelector) на нижнем ПК, `receiver/` — optional/legacy.
- Согласование с автором проекта через checklist и decision-note.
- Зафиксирован реальный workflow заказчика: автоматический печатный конвейер, rescue — по исключению.

### 2026-03-15 — Score-модель v2 и полное тестирование

- **KAN-038:** Новая 3-слойная score-модель: occupancy gate → quality gate → ranking (7 компонентов, сумма 100).
  - Компоненты: `head_readability` (30), `head_pose` (15), `head_sharpness` (20), `head_exposure` (15), `readable_count` (10), `frame_quality` (8), `smile_bonus` (2).
  - Fallback-кадры ограничены потолком 45.
- **KAN-039:** decision_state: `auto_selected` / `ambiguous_manual_review`.
- **KAN-044:** Ambiguous серии не блокируют автопечать.
- **KAN-045:** Autoprint on/off через `print_utils.py` (mspaint /p).
- **KAN-051:** Test mode + sheets preview с zoom.
- Первое тестирование на 273 реальных фото: найдены и исправлены баги с PNG, группировкой серий, ambiguous-логикой. Результат: 47 серий → 46 selected, 5 листов.
- Инсталлятор v1 собран и отправлен заказчику.

### 2026-03-16 (сессия 1) — Series timing, UX, docs

- **KAN-058:** Группировка серий переведена на время создания файла (creation time).
- **KAN-059:** `delta_score` + `manual_review_enabled` выведены в настройки инженера.
- **KAN-060:** Hint на zoom листов, PNG в `/photo`.
- **KAN-064:** Lightbox с prev/next/Esc/стрелками + debug score toggle в navbar.
- **KAN-065:** Live series vs History — после cleanup карточки не показывают «живые» данные для удалённых файлов.
- **KAN-066:** Симулятор с более реалистичными интервалами (3-4 сек вместо 12-20).
- **KAN-067:** Customer test-pack v2, переименование настроек серий, инсталлятор v2.

### 2026-03-16 (сессия 2) — KAN-062/KAN-040 и подготовка к v3.0

- **KAN-062:** ZIP-экспорт добавлен в основной веб-интерфейс (кнопка «Архив» в navbar, модал с пресетами, PNG-поддержка в export_utils).
- **KAN-040:** Low-disk warning: `check_disk_space()` в watcher, `/api/health`, polling в navbar, блокировка мониторинга при critical. Настройки `min_free_gb` / `critical_free_gb` в settings.
- 58 тестов, все проходят.

### 2026-03-16 (сессия 3) — EXE debugging и финализация v2.0

**Корневая причина всех проблем в установленной версии:**
- PyInstaller не включал: `cv2/data/haarcascade_upperbody.xml`, `libmediapipe.dll`, модели ML.
- Юнит-тесты (58/58 зелёные) не ловили проблемы бандла — нужен E2E тест из dist/.

**Решение — полная ревизия `kanatka.spec`:**
- `cv2/data` в datas, `libmediapipe.dll` в binaries, расширенный `hiddenimports`.
- `face_utils.py`: `sys._MEIPASS` для моделей в frozen EXE.
- Crash handler `_crash_log()` в `app.py`.

**Другие фиксы:**
- Серии не показывались после сборки листов: `_series_has_live_assets()` проверяет и `output_archive`.
- Кнопка «Запустить» обновляется мгновенно через `_setMonitorBtnState()`.
- Модалка инструкции закрывается по клику вне окна.
- `confirm_close=True` в pywebview — подтверждение перед закрытием.
- `[UninstallDelete]` в Inno Setup — удаление `workdir`/`INBOX` при деинсталляции.

**Урок:** E2E тестирование установленного EXE обязательно. `console=True` → запуск из dist/ → curl API → проверка файлов.

**Итог:** пользователь подтвердил полную работоспособность установленной версии. Тег v2.0 установлен.

---

## Текущее состояние (на 2026-03-16)

- **Версия:** v2.0 (инсталлятор `PhotoSelector_Setup_v2.exe`, ~55 МБ).
- **Тесты:** 58 тестов, 12 файлов, все проходят.
- **Веб-интерфейс:** порт 8787 — серии, листы, настройки, nearby/rescue, ZIP-экспорт, disk health.
- **Score:** 3-слойная модель, 7 компонентов ranking, потолок 45 для fallback.
- **Мониторинг:** watchdog + auto-processing + auto-sheet + autoprint (test_mode).

### Ключевые открытые задачи

| ID | Задача | Статус |
|----|--------|--------|
| KAN-050 | Полевая калибровка score на реальном датасете | NEXT |
| KAN-062 | ZIP-экспорт в web UI | DONE |
| KAN-040 | Low-disk warning + fail mode | DONE |
| KAN-016 | Сворачивание в системный трей | BACKLOG |
| KAN-033 | Engineer deployment guide | BACKLOG |
| KAN-061 | Operator dashboard redesign | BACKLOG |

> Полный dashboard задач: [`docs/project/overview.md`](overview.md)
