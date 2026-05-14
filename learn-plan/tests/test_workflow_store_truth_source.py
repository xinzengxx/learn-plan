from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_workflow.workflow_store import refresh_workflow_state


class WorkflowStoreTruthSourceTest(unittest.TestCase):
    def test_refresh_ignores_legacy_planning_artifact_from_workflow_state_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            workflow_dir = root / ".learn-workflow"
            workflow_dir.mkdir()
            (workflow_dir / "clarification.json").write_text(
                json.dumps(
                    {
                        "questionnaire": {
                            "topic": "Python",
                            "goal": "通过考试",
                            "success_criteria": ["能通过期末考试"],
                            "current_level_self_report": "零基础",
                            "time_constraints": {"frequency": "每天"},
                            "max_assessment_rounds_preference": 1,
                            "questions_per_round_preference": 3,
                        },
                        "clarification_state": {"open_questions": []},
                        "preference_state": {"pending_items": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workflow_dir / "diagnostic.json").write_text(
                json.dumps(
                    {
                        "diagnostic_plan": {
                            "delivery": "web-session",
                            "assessment_kind": "initial-test",
                            "session_intent": "assessment",
                            "plan_execution_mode": "diagnostic",
                            "target_capability_ids": ["python-basic"],
                            "scoring_rubric": [{"dimension": "基础", "criteria": ["能解释变量"]}],
                            "round_index": 1,
                            "max_rounds": 1,
                            "questions_per_round": 3,
                            "follow_up_needed": False,
                            "stop_reason": "sufficient-info",
                        },
                        "diagnostic_result": {"status": "evaluated", "capability_assessment": [{"id": "python-basic"}], "recommended_entry_level": "阶段 1", "confidence": 0.8, "follow_up_needed": False, "stop_reason": "sufficient-info"},
                        "diagnostic_items": [{"id": "q1", "target_capability_ids": ["python-basic"]}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workflow_dir / "approval.json").write_text(
                json.dumps(
                    {
                        "approval_state": {
                            "approval_status": "approved",
                            "ready_for_execution": True,
                            "pending_decisions": [],
                            "confirmed_material_strategy": "use_cached_mainline",
                            "confirmed_daily_execution_style": "rigorous",
                            "confirmed_mastery_checks": "quiz_and_reflection",
                        },
                        "material_curation": {
                            "status": "confirmed",
                            "user_confirmation": {"confirmed": True},
                            "materials": [{"role": "mainline", "selection_status": "confirmed", "cache_status": "cached"}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workflow_dir / "workflow_state.json").write_text(
                json.dumps(
                    {
                        "topic": "Python",
                        "goal": "通过考试",
                        "planning_artifact": {
                            "plan_candidate": {"stages": [{"title": "旧缓存阶段"}]},
                            "quality_review": {"valid": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = refresh_workflow_state(plan_path, topic="Python", goal="通过考试", current_mode="finalize")

            self.assertNotIn("planning_artifact", state)
            self.assertTrue(state.get("legacy_planning_artifact_ignored"))
            self.assertEqual(state.get("blocking_stage"), "planning")
            self.assertIn("planning.plan_candidate", state.get("missing_requirements", []))


if __name__ == "__main__":
    unittest.main()
