# AGENTS.md

Entry point for assistants in this repository.

1. Read `CLAUDE.md`.
2. Then read:
   - `docs/project/overview.md`
   - `docs/project/startup.md`
   - tail of `docs/project/progress.md`
3. Do not mark work as finally complete without explicit user confirmation.
4. Keep `docs/project/progress.md` append-only.
5. Do not remove tasks from `docs/project/overview.md` without explicit user permission.
6. When a task clearly matches a repo-local skill, read its `SKILL.md` before proceeding.

## Repo-local skills

- `skills/kanatka-docs-maintainer`
  - Use for `CLAUDE.md`, `AGENTS.md`, `docs/project/*`, handoff hygiene, and keeping the dashboard current.
- `skills/kanatka-score-debug`
  - Use for explaining scores, reading rejected/selected results, calibrating weights, and investigating why a frame was rejected.
- `skills/kanatka-pipeline-smoke`
  - Use for end-to-end checks of simulator -> incoming -> selector -> rejected/selected -> sheets.

## Core repo laws

- Source of current project state: `docs/project/overview.md`
- Session memory: `docs/project/progress.md`
- Fast handoff context: `docs/project/startup.md`
- Product intent and constraints: `TZ_PhotoSelector.md`

