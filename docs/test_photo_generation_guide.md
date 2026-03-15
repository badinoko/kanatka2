# Шпаргалка: генерация тестовых фото для Kanatka2

## Два workflow — два шага

### Шаг 1: БАЗОВЫЙ КАДР (workflow MAIN)
- **Файл:** `qwen_simple_edit_MAIN_FIXED.json`
- **Что делает:** генерирует 1 фото с нуля по промпту
- **EmptyLatentImage:** width=1536, height=1024, batch_size=1
- **KSampler:** denoise=1.0, seed=randomize
- **LoadImage:** загрузи белую картинку 1536×1024 (или любое фото-заглушку)
- **Результат:** 1 базовый кадр одной скамейки канатки

### Шаг 2: ВАРИАЦИИ (workflow VARIATIONS)
- **Файл:** `kanatka_VARIATIONS.json` ← НОВЫЙ, я его создал
- **Что делает:** берёт базовый кадр → делает 8 вариаций (как серийная съёмка)
- **LoadImage:** загрузи базовый кадр из Шага 1
- **RepeatLatentBatch:** amount=8 (можно менять)
- **KSampler:** denoise=**0.20**, seed=randomize
- **Результат:** 8 фото тех же людей с микро-вариациями (поворот головы, выражение лица)

### Важно про denoise
- **0.15** = очень похожие кадры (минимальные отличия)
- **0.20** = хороший баланс (рекомендуется)
- **0.30** = заметные отличия (одежда может чуть меняться)
- **0.40+** = слишком сильные изменения, уже не та же скамейка

---

## Пошаговая инструкция

### Этап A: Генерация базовых кадров

1. Открой `qwen_simple_edit_MAIN_FIXED.json` в ComfyUI
2. Установи EmptyLatentImage: **width=1536, height=1024, batch_size=1**
3. Скопируй ПРОМПТ 01 (см. ниже) в ноду "Your Prompt Here"
4. В SaveImage prefix поставь `base_SER01`
5. Нажми **Generate** → получишь 1 базовый кадр
6. Если результат не нравится — жми Generate ещё раз (другой seed)
7. Когда доволен — запомни имя файла, переходи к Шагу B
8. Повтори для каждого промпта из таблицы

### Этап B: Генерация вариаций (серий по 8)

1. Открой `kanatka_VARIATIONS.json` в ComfyUI
2. В ноде "BASE IMAGE" загрузи базовый кадр из Этапа A
3. В промпте напиши: `This exact same photograph with very slight natural variation`
4. В SaveImage prefix поставь `SER01`
5. Нажми **Generate** → получишь 8 вариаций одной скамейки
6. Повтори для каждого базового кадра

### Этап C: Скачивание и раскладка

Скачай фото с RunPod. Разложи по подпапкам в INBOX:
```
INBOX/
  SER01_2people_hats_a/     ← 8 фото (первая пара в шапках)
  SER02_2people_hats_b/     ← 8 фото (вторая пара в шапках, другой базовый)
  SER03_2people_helmets_a/  ← 8 фото
  ...
  SER10_empty_chair_a/      ← 8 фото (пустое кресло)
```

---

## Таблица серий

| # | Сценарий | Промпт (номер ниже) | Базовых кадров | Вариаций (×8) | Итого фото |
|---|----------|---------------------|----------------|---------------|------------|
| 01 | 2 чел, шапки, в камеру | ПРОМПТ 01 | 3 | 3×8=24 | 24 |
| 02 | 2 чел, шлемы, очки на лбу | ПРОМПТ 02 | 3 | 3×8=24 | 24 |
| 03 | 2 чел, лица закрыты | ПРОМПТ 03 | 2 | 2×8=16 | 16 |
| 04 | 1 чел по центру | ПРОМПТ 04 | 2 | 2×8=16 | 16 |
| 05 | 1 чел справа | ПРОМПТ 05 | 2 | 2×8=16 | 16 |
| 06 | Пустое кресло | ПРОМПТ 06 | 3 | 3×8=24 | 24 |
| 07 | Один отвернулся | ПРОМПТ 07 | 2 | 2×8=16 | 16 |
| 08 | Контровый свет | ПРОМПТ 08 | 2 | 2×8=16 | 16 |
| 09 | Снегопад | ПРОМПТ 09 | 1 | 1×8=8 | 8 |
| 10 | Машут руками | ПРОМПТ 10 | 2 | 2×8=16 | 16 |
| **ИТОГО** | | | **22** | **22 серии** | **176 фото** |

---

## Промпты для Этапа A (базовые кадры)

### ПРОМПТ 01 — 2 человека, шапки, смотрят в камеру

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. The chairlift has a bright
green-yellow safety bar across the front and two separate foot rests.
Both people visible from head to dangling feet with ski boots.
One wearing a red padded ski jacket, the other in blue. Dark ski pants.
Knit beanies on heads, ski goggles pushed up on foreheads.
Faces clearly visible, both looking forward at camera, relaxed expressions.
Background: snowy Siberian forest with birch trees and pine trees,
overcast winter sky. Natural winter daylight.
Canon EOS R100, photorealistic, sharp focus on faces. Aspect ratio 3:2.
```

### ПРОМПТ 02 — 2 человека, шлемы + очки на лбу

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. Green-yellow safety bar,
two foot rests. Both visible head to feet with ski boots.
One in black ski jacket, the other in bright green.
Both wearing ski helmets with goggles pushed up on top.
Faces clearly visible, looking at camera.
Snowy forest background with birch and pine trees, winter overcast sky.
Canon EOS R100, photorealistic, sharp focus. Aspect ratio 3:2.
```

### ПРОМПТ 03 — 2 человека, лица закрыты (шлем + очки)

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. Green-yellow safety bar,
two foot rests. Both visible head to feet.
Both wearing ski helmets with ski goggles covering their eyes,
face masks covering lower face. One in orange jacket, other in dark gray.
Background: snowy forest, overcast sky.
Canon EOS R100, photorealistic. Aspect ratio 3:2.
```

### ПРОМПТ 04 — 1 человек по центру

```
Full body photograph of one person sitting alone in the center of a
two-seater ski chairlift, shot from below at 20-30 degree upward angle.
Green-yellow safety bar, two foot rests (one empty).
Person visible head to feet with ski boots, wearing bright red ski jacket,
dark pants, knit beanie. Face clearly visible, looking at camera with
slight smile. Snowy forest background, overcast winter sky.
Canon EOS R100, photorealistic, sharp focus. Aspect ratio 3:2.
```

### ПРОМПТ 05 — 1 человек справа

```
Full body photograph of one person sitting on the right side of a
two-seater ski chairlift, left seat empty. Shot from below at 20-30
degree upward angle. Green-yellow safety bar, two foot rests.
Person visible head to feet, wearing dark ski jacket, ski helmet,
goggles on forehead. Face visible, looking slightly to the side.
Snowy forest background. Canon EOS R100, photorealistic. Aspect ratio 3:2.
```

### ПРОМПТ 06 — Пустое кресло

```
Empty two-seater ski chairlift chair with no people sitting on it.
Shot from below at 20-30 degree upward angle. Green-yellow safety bar
in raised position, two empty foot rests visible. Metal frame and
empty plastic seat. Snowy Siberian forest background with birch trees
and pine trees, overcast winter sky. Canon EOS R100, photorealistic,
natural winter daylight. Aspect ratio 3:2.
```

### ПРОМПТ 07 — один отвернулся

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. Green-yellow safety bar,
two foot rests. Both visible head to feet.
Left person in white jacket looking directly at camera.
Right person in dark jacket turned away, looking to the right,
showing profile view. Both wearing knit beanies.
Snowy forest background. Canon EOS R100, photorealistic. Aspect ratio 3:2.
```

### ПРОМПТ 08 — контровый свет (солнце)

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. Green-yellow safety bar.
Strong backlight from low winter sun behind them, creating lens flare
and silhouette effect. Faces partially in shadow but still visible.
Both wearing colorful ski jackets and knit hats.
Bright snowy background, sun visible through trees.
Canon EOS R100, photorealistic, challenging lighting. Aspect ratio 3:2.
```

### ПРОМПТ 09 — снегопад

```
Full body photograph of two people sitting on a two-seater ski chairlift
during heavy snowfall. Shot from below at 20-30 degree upward angle.
Green-yellow safety bar. Snowflakes visible in the air, reduced visibility.
Both wearing ski jackets with hoods up, snow accumulating on shoulders.
Faces partially visible through falling snow.
Snowy forest background, gray overcast sky.
Canon EOS R100, photorealistic. Aspect ratio 3:2.
```

### ПРОМПТ 10 — машут руками

```
Full body photograph of two people sitting on a two-seater ski chairlift,
shot from below at 20-30 degree upward angle. Green-yellow safety bar.
Both people waving hands at the camera enthusiastically, big smiles.
Wearing colorful ski jackets (one red, one yellow), knit beanies.
Arms raised, gloved hands waving. Dynamic cheerful pose.
Snowy forest background, bright winter day.
Canon EOS R100, photorealistic, sharp focus. Aspect ratio 3:2.
```

---

## Промпт для Этапа B (вариации)

Для workflow `kanatka_VARIATIONS.json` используй один и тот же промпт:

```
This exact same photograph of people on a ski chairlift with very slight natural variation in pose and expression
```

Или для пустых кресел:
```
This exact same photograph of an empty ski chairlift with very slight natural variation
```

---

## Быстрый чеклист

- [ ] EmptyLatentImage: 1536×1024, batch=1 (для базовых)
- [ ] RepeatLatentBatch: amount=8 (для вариаций)
- [ ] KSampler denoise: 1.0 (базовые) / 0.20 (вариации)
- [ ] SaveImage prefix: менять для каждой серии
- [ ] Каждый базовый кадр → проверить визуально перед вариациями
- [ ] 22 базовых кадра → 22 серии → 176 фото
