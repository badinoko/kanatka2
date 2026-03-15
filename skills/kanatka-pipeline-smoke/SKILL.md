---
name: kanatka-pipeline-smoke
description: Run practical smoke checks for the kanatka processing pipeline. Use when validating simulator -> incoming -> selector -> rejected or selected -> sheets, or when verifying that a code change still works end to end.
---

# kanatka-pipeline-smoke

Use this skill for realistic pipeline verification.

## Focus Areas

1. `tools/camera_simulator.py`
2. `tools/poc_test.py`
3. `src/watcher.py`
4. `src/selector.py`
5. `src/sheet_composer.py`
6. `workdir/`

## Workflow

1. Read the active task in `docs/project/overview.md`.
2. Choose the smallest practical verification path:
   - single-series dry run;
   - folder processing smoke test;
   - sheet composition smoke test.
3. Do not delete existing user artifacts unless explicitly asked.
4. Report concrete evidence:
   - output files;
   - log files;
   - selected vs rejected counts;
   - visible regressions.

## Output

Summarize:
- what was exercised;
- what artifacts were produced;
- what still needs manual review.

