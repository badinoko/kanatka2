---
name: kanatka-score-debug
description: Debug kanatka photo scoring and rejection logic. Use when explaining why a photo got its score, inspecting rejected or selected series, calibrating score tables, or tracing score_breakdown and series fallback behavior.
---

# kanatka-score-debug

Use this skill when the task is about score interpretation or calibration.

## Inspect These Sources

1. `workdir/rejected/**/*.json`
2. `workdir/selected/*.json`
3. `workdir/logs/ser*_report.json`
4. `workdir/logs/annotated/**/*`
5. `src/scorer.py`
6. `src/selector.py`
7. `src/config.json`

## Debug Workflow

1. Open the photo and its matching JSON.
2. Read `score`, `score_breakdown`, `raw_score`, `score_reason`, `score_reference_file`.
3. Check the full series report in `workdir/logs/ser*_report.json`.
4. Explain whether the result came from direct face detection or series fallback.
5. If proposing a fix, state clearly whether it is:
   - threshold tuning;
   - weight tuning;
   - scoring logic change;
   - series selection logic change.

## Notes

- The score overlay on images is temporary and intended for calibration.
- Empty series vs occupied series with lost faces must be distinguished explicitly.

