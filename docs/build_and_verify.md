# Build & Verify Checklist

Пошаговая инструкция по сборке PhotoSelector EXE и инсталлятора Windows.
Создана после инцидента v2.0, когда 6 пересборок потребовались из-за невидимых runtime-зависимостей.

Последнее обновление: 2026-03-16.

---

## Предварительные требования

- Python 3.11+ с виртуальным окружением `.venv/`
- PyInstaller: `pip install pyinstaller`
- Inno Setup 6: `winget install JRSoftware.InnoSetup`
- Все зависимости из `requirements.txt` установлены в `.venv/`

---

## Шаг 1: Юнит-тесты

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
```

Все тесты должны быть зелёными. Если нет — не продолжать.

> Юнит-тесты НЕ проверяют полноту PyInstaller-бандла. Они нужны только как gate на корректность логики.

---

## Шаг 2: Сборка EXE

```bash
.venv/Scripts/python.exe build/build.py --exe
```

Результат: `dist/PhotoSelector/PhotoSelector.exe` + `dist/PhotoSelector/_internal/`.

---

## Шаг 3: Проверка бандла (до запуска EXE)

Проверить, что критические файлы включены в бандл. Каждый пункт ниже — это зависимость, которая НЕ обнаруживается юнит-тестами и проявляется только в runtime frozen EXE.

### 3.1. ML-модели

```bash
ls dist/PhotoSelector/_internal/models/face_detector.tflite
ls dist/PhotoSelector/_internal/models/face_landmarker.task
```

Оба файла должны существовать. Если нет — проверить `datas` в `build/kanatka.spec`.

**Почему ломается:** `face_utils.py` загружает модели по пути `sys._MEIPASS / "models/"`. Если модели не в `datas`, файл не найден → `FileNotFoundError` при первой детекции.

### 3.2. MediaPipe C runtime

```bash
ls dist/PhotoSelector/_internal/mediapipe/tasks/c/libmediapipe.dll
```

Файл должен существовать. Если нет — проверить `binaries` в `build/kanatka.spec`.

**Почему ломается:** MediaPipe загружает `libmediapipe.dll` через `importlib.resources.files('mediapipe.tasks.c')` — это невидимо для статического анализа PyInstaller. Ошибка: `No module named 'mediapipe.tasks.c'`.

### 3.3. OpenCV Haar cascades

```bash
ls dist/PhotoSelector/_internal/cv2/data/haarcascade_upperbody.xml
```

Файл должен существовать. Если нет — проверить `datas` в `build/kanatka.spec`.

**Почему ломается:** `CascadeClassifier()` молча возвращает пустой объект → `detectMultiScale` assertion → ВСЕ серии пропускаются с WARNING, ни одна фото не обрабатывается. Самая коварная ошибка: UI работает, мониторинг «запускается», но ничего не происходит.

### 3.4. Конфиг

```bash
ls dist/PhotoSelector/_internal/config.json
```

---

## Шаг 4: E2E тест из dist/ (до создания инсталлятора)

Этот шаг обязателен. Именно он ловит проблемы, которые пропускают юнит-тесты.

### 4.1. Подготовка

```bash
# Создать рабочие папки рядом с EXE
mkdir -p dist/PhotoSelector/workdir/incoming
mkdir -p dist/PhotoSelector/workdir/selected
mkdir -p dist/PhotoSelector/workdir/sheets
mkdir -p dist/PhotoSelector/workdir/discarded
mkdir -p dist/PhotoSelector/workdir/rejected
mkdir -p dist/PhotoSelector/workdir/archive
mkdir -p dist/PhotoSelector/workdir/ambiguous
mkdir -p dist/PhotoSelector/workdir/logs
mkdir -p dist/PhotoSelector/INBOX
```

### 4.2. Запуск EXE с консолью (для отладки)

Временно поменять `console=False` на `console=True` в `build/kanatka.spec`, пересобрать, и запустить:

```bash
dist/PhotoSelector/PhotoSelector.exe
```

Или, если не хочется пересобирать, запустить из dist/ и проверять `crash_log.txt` и `workdir/logs/photo_selector.log`.

### 4.3. Проверка API

```bash
# Сервер должен слушать на 8787
curl -s http://127.0.0.1:8787/ | head -20

# Мониторинг должен стартовать без ошибок
curl -s -X POST http://127.0.0.1:8787/api/monitor \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"start\"}"

# Health endpoint
curl -s http://127.0.0.1:8787/api/health
```

### 4.4. Подать тестовые фото

Скопировать 10-20 тестовых JPG/PNG в `dist/PhotoSelector/INBOX/` или `dist/PhotoSelector/workdir/incoming/`, подождать обработки.

### 4.5. Проверить результат

```bash
# Должны появиться файлы
ls dist/PhotoSelector/workdir/selected/
ls dist/PhotoSelector/workdir/sheets/
ls dist/PhotoSelector/workdir/logs/ser*_report.json

# В логе не должно быть ERROR или traceback
grep -i "error\|traceback\|exception" dist/PhotoSelector/workdir/logs/photo_selector.log
```

**Критерий успеха:** хотя бы 1 серия обработана, 1 фото в `selected/`, лог без ошибок.

---

## Шаг 5: Сборка инсталлятора

Только после успешного прохождения шага 4.

```bash
.venv/Scripts/python.exe build/build.py --installer
```

Результат: `installers/PhotoSelector_Setup_vX.exe`.

> Не забыть обновить `MyAppVersion` и `OutputBaseFilename` в `build/photoselector.iss` при смене версии.

---

## Шаг 6: Верификация инсталлятора (опционально, но рекомендуется)

1. Установить из `installers/PhotoSelector_Setup_vX.exe`.
2. Запустить из Start Menu или ярлыка на рабочем столе.
3. Повторить шаги 4.3-4.5 (API, подать фото, проверить результат).
4. Деинсталлировать через «Программы и компоненты» — убедиться, что `workdir/` и `INBOX/` удалены.

---

## Быстрая команда (всё в одну строку)

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" && .venv/Scripts/python.exe build/build.py
```

Это запускает тесты, затем собирает EXE + инсталлятор. Но **не заменяет** ручную проверку шагов 3-4.

---

## Справочник: что в spec и зачем

| Секция в `kanatka.spec` | Что включает | Зачем |
|--------------------------|-------------|-------|
| `datas: config.json` | Конфигурация | Загружается при старте |
| `datas: models/*.task, *.tflite` | ML-модели | MediaPipe face detection/landmarks |
| `datas: cv2/data/` | Haar cascade XMLs | Upper body detection fallback |
| `binaries: libmediapipe.dll` | MediaPipe C runtime | Загружается через importlib.resources (невидим PyInstaller) |
| `hiddenimports: mediapipe.*` | MediaPipe Python модули | Ленивые импорты, не видны static analysis |
| `hiddenimports: watchdog.*` | Filesystem watcher | Мониторинг входящей папки |
| `hiddenimports: webview` | pywebview | Нативное окно приложения |

---

## Типичные ошибки и как их диагностировать

| Симптом | Причина | Где смотреть |
|---------|---------|-------------|
| Окно открывается, но белый экран | HTTP-сервер не запустился | `crash_log.txt` рядом с EXE |
| «Не найдена модель детектора лиц» | Модели не в бандле | `dist/.../models/` |
| `No module named 'mediapipe.tasks.c'` | `libmediapipe.dll` отсутствует | `dist/.../mediapipe/tasks/c/` |
| Мониторинг запущен, но 0 серий | Haar cascade не в бандле | `workdir/logs/photo_selector.log` — WARNING на каждом фото |
| `Failed to fetch` при старте мониторинга | Import error в backend | Запустить с `console=True`, читать stderr |
| Серии обработаны, но нет карточек в UI | `_series_has_live_assets()` не находит файлы | Проверить пути в `config.json` vs реальное расположение |
