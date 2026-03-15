---
name: kanatka-docs-maintainer
description: Maintain CLAUDE.md, AGENTS.md, and docs/project/* for the kanatka repository. Use when the user asks to organize documentation, fix handoff hygiene, update overview/progress/startup, or preserve project state between long sessions.
---

# kanatka-docs-maintainer

Use this skill when the task is about repository discipline and preserving context.

## Read First

1. `CLAUDE.md`
2. `docs/project/overview.md`
3. `docs/project/startup.md`
4. tail of `docs/project/progress.md`

## Rules

1. `overview.md` is the dashboard.
2. `progress.md` is append-only.
3. Do not mark final completion without explicit user confirmation.
4. If a new workstream appears, add it to `overview.md` before leaving the session.
5. Keep the docs bundle minimal and current.

## Typical Workflow

1. Capture the current repository state in `overview.md`.
2. Update `startup.md` if the next-session entry path changed.
3. Append a short factual note to `progress.md`.
4. If root workflow rules changed, sync `AGENTS.md` and `CLAUDE.md` in the same session.

