from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import learn_plan
from learn_workflow.gates import formal_plan_write_blockers
from learn_workflow.state_machine import build_workflow_state


class PlanningArtifactGateTest(unittest.TestCase):
    def _clarification(self) -> dict:
        return {
            "questionnaire": {
                "topic": "Python",
                "goal": "通过期末考试",
                "success_criteria": ["完成基础语法题"],
                "current_level_self_report": "零基础",
                "time_constraints": {"frequency": "每天", "session_length": "30分钟"},
                "mastery_preferences": {"max_assessment_rounds_preference": 1, "questions_per_round_preference": 5},
            },
            "consultation_state": {
                "current_topic_id": "learning_purpose",
                "topics": [
                    {"id": "learning_purpose", "required": True, "status": "resolved", "exit_criteria": ["目标明确"]},
                    {"id": "exam_or_job_target", "required": True, "status": "resolved", "exit_criteria": ["考试范围明确"]},
                    {"id": "success_criteria", "required": True, "status": "resolved", "exit_criteria": ["达标证据明确"]},
                    {"id": "current_level", "required": True, "status": "resolved", "exit_criteria": ["水平有证据"]},
                    {"id": "constraints", "required": True, "status": "resolved", "exit_criteria": ["节奏明确"]},
                    {"id": "assessment_scope", "required": True, "status": "resolved", "exit_criteria": ["测评预算明确"]},
                ],
            },
            "clarification_state": {"open_questions": []},
            "preference_state": {"pending_items": []},
            "evidence": ["clarification fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "clarification", "generator": "test-fixture", "status": "ok"},
            "traceability": [{"kind": "test", "ref": "clarification"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def _diagnostic(self) -> dict:
        return {
            "diagnostic_plan": {
                "delivery": "web-session",
                "assessment_kind": "initial-test",
                "session_intent": "assessment",
                "target_capability_ids": ["syntax"],
                "scoring_rubric": ["正确率"],
                "diagnostic_items": ["语法"],
                "round_index": 1,
                "max_rounds": 1,
                "questions_per_round": 5,
                "follow_up_needed": False,
                "stop_reason": "complete",
            },
            "diagnostic_result": {
                "status": "evaluated",
                "recommended_entry_level": "入门",
                "confidence": 0.8,
                "stop_reason": "complete",
                "follow_up_needed": False,
                "capability_assessment": ["基础语法"],
            },
            "diagnostic_profile": {"recommended_entry_level": "入门", "confidence": 0.8, "follow_up_needed": False, "stop_reason": "complete"},
            "evidence": ["diagnostic fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "diagnostic", "generator": "test-fixture", "status": "ok"},
            "traceability": [{"kind": "test", "ref": "diagnostic"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def _approval(self) -> dict:
        return {
            "approval_state": {
                "approval_status": "approved",
                "ready_for_execution": True,
                "confirmed_material_strategy": True,
                "confirmed_daily_execution_style": True,
                "confirmed_mastery_checks": True,
                "pending_decisions": [],
            },
            "material_curation": {
                "schema_version": "learn-plan.material-curation.v1",
                "status": "confirmed",
                "materials": [
                    {
                        "id": "python-main",
                        "title": "Python Main",
                        "role": "mainline",
                        "selection_status": "confirmed",
                        "cache_status": "cached",
                        "curation_reason": "覆盖基础语法",
                        "risks": [],
                        "excerpt_briefs": [{"segment_id": "seg-1", "source_status": "extracted"}],
                    }
                ],
                "open_risks": [],
                "user_confirmation": {"confirmed": True, "pending_questions": []},
            },
            "evidence": ["approval fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "approval", "generator": "test-fixture", "status": "ok"},
            "traceability": [{"kind": "test", "ref": "approval"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def _profile(self) -> dict:
        return learn_plan.build_planning_profile(
            "Python",
            "通过期末考试",
            "零基础",
            "每天30分钟",
            "混合",
            clarification=self._clarification(),
            research={},
            diagnostic=self._diagnostic(),
            approval=self._approval(),
            mode="finalize",
        )

    def _curriculum(self) -> dict:
        return learn_plan.build_curriculum("Python", "零基础", "混合")

    def test_missing_planning_candidate_does_not_build_deterministic_plan_candidate(self) -> None:
        with patch("learn_plan.build_plan_candidate", side_effect=AssertionError("deterministic planning fallback should not run")):
            artifact, metadata = learn_plan.build_planning_artifact(
                "Python",
                "通过期末考试",
                "零基础",
                "每天30分钟",
                "混合",
                self._profile(),
                self._curriculum(),
                injected_candidate=None,
            )

        self.assertEqual(metadata.get("status"), "missing-external-artifact")
        self.assertNotIn("plan_candidate", artifact)
        self.assertEqual(artifact.get("stage"), "planning")
        self.assertEqual(artifact.get("candidate_error", {}).get("message"), "external_candidate_required")
        self.assertFalse(artifact.get("quality_review", {}).get("valid"))
        self.assertIn("planning.external_candidate_required", artifact.get("quality_review", {}).get("issues", []))

    def test_missing_planning_candidate_blocks_ready_state_and_formal_write(self) -> None:
        artifact, _ = learn_plan.build_planning_artifact(
            "Python",
            "通过期末考试",
            "零基础",
            "每天30分钟",
            "混合",
            self._profile(),
            self._curriculum(),
            injected_candidate=None,
        )

        workflow_state = build_workflow_state(
            topic="Python",
            goal="通过期末考试",
            requested_mode="finalize",
            current_mode="finalize",
            clarification=self._clarification(),
            research={},
            diagnostic=self._diagnostic(),
            approval=self._approval(),
            planning=artifact,
            quality_issues=[],
        )

        self.assertEqual(workflow_state.get("blocking_stage"), "planning")
        self.assertIn("planning.plan_candidate", workflow_state.get("missing_requirements", []))
        blockers = formal_plan_write_blockers(workflow_state, "finalize")
        self.assertIn("formal_plan.blocking_stage.planning", blockers)


if __name__ == "__main__":
    unittest.main()
