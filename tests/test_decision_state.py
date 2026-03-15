from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from selector import _compute_decision_state


class DecisionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "decision": {
                "delta_score": 8.0,
                "manual_review_enabled": True,
            },
        }

    def _result(self, score: float, quality_gate: str = "pass") -> dict:
        return {
            "score": score,
            "score_breakdown": {"quality_gate": quality_gate},
        }

    def test_single_frame_auto_selected(self) -> None:
        occupied = [self._result(60.0)]
        state = _compute_decision_state(occupied, occupied[0], self.config)
        self.assertEqual(state, "auto_selected")

    def test_large_delta_auto_selected(self) -> None:
        top = self._result(70.0)
        occupied = [top, self._result(50.0)]
        state = _compute_decision_state(occupied, top, self.config)
        self.assertEqual(state, "auto_selected")

    def test_small_delta_ambiguous(self) -> None:
        top = self._result(55.0)
        occupied = [top, self._result(50.0)]
        state = _compute_decision_state(occupied, top, self.config)
        self.assertEqual(state, "ambiguous_manual_review")

    def test_weak_quality_gate_ambiguous(self) -> None:
        top = self._result(60.0, quality_gate="weak")
        occupied = [top]
        state = _compute_decision_state(occupied, top, self.config)
        self.assertEqual(state, "ambiguous_manual_review")

    def test_manual_review_disabled(self) -> None:
        config = {"decision": {"delta_score": 8.0, "manual_review_enabled": False}}
        top = self._result(55.0, quality_gate="weak")
        occupied = [top, self._result(50.0)]
        state = _compute_decision_state(occupied, top, config)
        self.assertEqual(state, "auto_selected")

    def test_exact_delta_threshold_auto_selected(self) -> None:
        top = self._result(58.0)
        occupied = [top, self._result(50.0)]
        state = _compute_decision_state(occupied, top, self.config)
        self.assertEqual(state, "auto_selected")


if __name__ == "__main__":
    unittest.main()
