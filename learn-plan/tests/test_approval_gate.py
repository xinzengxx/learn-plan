from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_workflow.stage_review import review_stage_candidate
from learn_workflow.state_machine import build_workflow_state


class ApprovalGateTest(unittest.TestCase):
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
                "round_index": 1,
                "max_rounds": 1,
                "questions_per_round": 5,
                "follow_up_needed": False,
                "stop_reason": "complete",
            },
            "diagnostic_items": [{"id": "q1", "capability_id": "syntax", "expected_signals": ["能回答"]}],
            "diagnostic_result": {
                "status": "evaluated",
                "recommended_entry_level": "入门",
                "confidence": 0.8,
                "stop_reason": "complete",
                "follow_up_needed": False,
                "capability_assessment": [{"capability_id": "syntax", "current_level": "入门", "confidence": 0.8}],
            },
            "diagnostic_profile": {"status": "validated", "recommended_entry_level": "入门", "confidence": 0.8, "follow_up_needed": False, "stop_reason": "complete"},
            "evidence": ["diagnostic fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "diagnostic", "generator": "test-fixture", "status": "ok"},
            "traceability": [{"kind": "test", "ref": "diagnostic"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def _material_curation(self, *, confirmed: bool = True, cache_status: str = "cached") -> dict:
        return {
            "schema_version": "learn-plan.material-curation.v1",
            "status": "confirmed" if confirmed else "needs-user-confirmation",
            "materials": [
                {
                    "id": "python-main",
                    "title": "Python Main",
                    "role": "mainline",
                    "selection_status": "confirmed",
                    "cache_status": cache_status,
                    "curation_reason": "覆盖基础语法",
                    "risks": [] if cache_status == "cached" else ["缓存不可用"],
                    "excerpt_briefs": [{"segment_id": "seg-1", "source_status": "extracted"}],
                }
            ],
            "open_risks": [] if cache_status == "cached" else ["缓存不可用"],
            "user_confirmation": {"confirmed": confirmed, "pending_questions": [] if confirmed else ["待确认"]},
        }

    def _approval(self, approval_state: dict, material_curation: dict | None = None) -> dict:
        payload = {
            "approval_state": approval_state,
            "evidence": ["approval fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "approval", "generator": "test-fixture", "status": "ok"},
            "traceability": [{"kind": "test", "ref": "approval"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }
        if material_curation is not None:
            payload["material_curation"] = material_curation
        return payload

    def _workflow_state_for_approval(self, approval_state: dict, material_curation: dict | None = None) -> dict:
        return build_workflow_state(
            topic="Python",
            goal="通过期末考试",
            requested_mode="finalize",
            current_mode="finalize",
            clarification=self._clarification(),
            research={},
            diagnostic=self._diagnostic(),
            approval=self._approval(approval_state, material_curation),
            quality_issues=[],
        )

    def test_missing_confirmed_fields_block_approval(self) -> None:
        workflow_state = self._workflow_state_for_approval({"approval_status": "approved", "ready_for_execution": True})

        self.assertEqual(workflow_state.get("blocking_stage"), "approval")
        self.assertIn("approval.confirmed_material_strategy", workflow_state.get("missing_requirements", []))
        self.assertIn("approval.confirmed_daily_execution_style", workflow_state.get("missing_requirements", []))
        self.assertIn("approval.confirmed_mastery_checks", workflow_state.get("missing_requirements", []))

    def test_missing_or_non_approved_status_blocks_approval(self) -> None:
        for status in (None, "pending", "rejected", "draft"):
            approval_state = {
                "ready_for_execution": True,
                "confirmed_material_strategy": True,
                "confirmed_daily_execution_style": True,
                "confirmed_mastery_checks": True,
            }
            if status is not None:
                approval_state["approval_status"] = status
            workflow_state = self._workflow_state_for_approval(approval_state)
            self.assertEqual(workflow_state.get("blocking_stage"), "approval")
            self.assertIn("approval.approval_status", workflow_state.get("missing_requirements", []))

    def test_complete_approved_state_passes_approval_gate(self) -> None:
        workflow_state = self._workflow_state_for_approval(
            {
                "approval_status": "approved",
                "ready_for_execution": True,
                "confirmed_material_strategy": True,
                "confirmed_daily_execution_style": True,
                "confirmed_mastery_checks": True,
                "pending_decisions": [],
            },
            self._material_curation(),
        )

        self.assertNotEqual(workflow_state.get("blocking_stage"), "approval")
        self.assertNotIn("approval.ready_for_execution", workflow_state.get("missing_requirements", []))

    def test_missing_material_curation_blocks_material_strategy(self) -> None:
        workflow_state = self._workflow_state_for_approval(
            {
                "approval_status": "approved",
                "ready_for_execution": True,
                "confirmed_material_strategy": True,
                "confirmed_daily_execution_style": True,
                "confirmed_mastery_checks": True,
                "pending_decisions": [],
            }
        )

        self.assertEqual(workflow_state.get("blocking_stage"), "approval")
        self.assertIn("approval.material_curation", workflow_state.get("missing_requirements", []))

    def test_unconfirmed_material_curation_blocks_material_strategy(self) -> None:
        workflow_state = self._workflow_state_for_approval(
            {
                "approval_status": "approved",
                "ready_for_execution": True,
                "confirmed_material_strategy": True,
                "confirmed_daily_execution_style": True,
                "confirmed_mastery_checks": True,
                "pending_decisions": [],
            },
            self._material_curation(confirmed=False),
        )

        self.assertEqual(workflow_state.get("blocking_stage"), "approval")
        self.assertIn("approval.material_curation.status", workflow_state.get("missing_requirements", []))
        self.assertIn("approval.material_curation.pending_user_confirmation", workflow_state.get("missing_requirements", []))

    def test_stage_review_requires_complete_approval_fields(self) -> None:
        reviewed = review_stage_candidate(
            "approval",
            self._approval({"approval_status": "approved", "ready_for_execution": True}),
        )

        issues = reviewed.get("quality_review", {}).get("issues", [])
        self.assertIn("approval.confirmed_material_strategy_missing", issues)
        self.assertIn("approval.confirmed_daily_execution_style_missing", issues)
        self.assertIn("approval.confirmed_mastery_checks_missing", issues)
        self.assertIn("approval.material_curation_missing", issues)


if __name__ == "__main__":
    unittest.main()
