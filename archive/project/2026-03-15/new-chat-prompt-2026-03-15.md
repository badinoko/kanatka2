# New Chat Prompt

Используй этот prompt как стартовый текст для нового окна чата.

```text
Работаем в репозитории kanatka2.

Сначала прочитай:
1. CLAUDE.md
2. CODEX.md
3. docs/project/overview.md
4. docs/project/roadmap.md
5. docs/project/startup.md
6. tail docs/project/progress.md
7. docs/project/kan-038-score-design-brief.md

Контекст:
- Архитектура уже достаточно подтверждена: верхний ПК в основном передаёт фото, нижний ПК делает основной workflow.
- Отдельный receiver не считается обязательной частью поставки.
- Главная текущая проблема проекта: score и выбор лучшего кадра.
- Ответы автора уже подтверждают, что smile должен быть только слабым бонусом, а ambiguous-series должны помечаться для ручной проверки.

Что можно начинать делать уже сейчас, не дожидаясь новых ответов автора:
1. Подготовить implementation plan для KAN-038 на основе docs/project/kan-038-score-design-brief.md.
2. Перепроектировать score в коде вокруг:
   - occupancy gate
   - quality gate
   - ranking score
3. Добавить richer score_breakdown и decision_state в логи/metadata.
4. Ограничить силу fallback-кадров, чтобы они не доминировали над кадрами с читаемыми лицами.
5. Подготовить selector к статусам:
   - selected
   - ambiguous_manual_review
   - discarded_empty
6. Не внедрять пока финальный queue UX для оператора, автопечать и cleanup isolation — по ним есть решения в roadmap, но внешние хвосты ещё не до конца закрыты.

Практический фокус этой сессии:
- сначала scorer.py
- потом analyzer.py / selector.py
- затем при необходимости series_browser.py только в части новых статусов, без тяжёлого UI

Для проверки опирайся на:
- src/scorer.py
- src/analyzer.py
- src/selector.py
- src/series_browser.py
- workdir/logs/ser001_report.json

Если понадобятся docs-обновления, сохраняй append-only дисциплину для docs/project/progress.md.
Не объявляй работу окончательно завершённой без подтверждения пользователя.
```
