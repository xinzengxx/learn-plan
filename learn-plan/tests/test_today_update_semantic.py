from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import learn_today_update
from learn_knowledge import build_default_knowledge_state, save_knowledge_state


class TodayUpdateSemanticTest(unittest.TestCase):
    def _progress(self) -> dict:
        return {
            "topic": "Python 基础",
            "date": "2026-04-24",
            "session": {"type": "today", "status": "active", "started_at": "2026-04-24T08:00:00"},
            "summary": {"total": 2, "attempted": 2, "correct": 1},
            "questions": {
                "q1": {"stats": {"attempts": 1, "correct_count": 1, "last_status": "correct"}},
                "q2": {"stats": {"attempts": 2, "correct_count": 0, "last_status": "wrong"}},
            },
            "mastery_checks": {
                "reading_checklist": ["变量"],
                "session_exercises": ["q1", "q2"],
                "reflection": ["复盘"],
            },
            "context": {
                "mastery_targets": {"reading_checklist": ["变量"], "session_exercises": ["基础题"], "reflection": ["复盘"]},
                "today_teaching_brief": {"new_learning_focus": ["函数"]},
                "lesson_focus_points": ["变量", "条件判断"],
            },
        }

    def _questions_map(self, *, knowledge_point_id: str | None = None) -> dict:
        q1 = {"title": "变量赋值", "category": "concept", "tags": ["变量"]}
        if knowledge_point_id:
            q1["knowledge_point_ids"] = [knowledge_point_id]
            q1["evidence_types"] = ["explanation"]
        return {
            "q1": q1,
            "q2": {"title": "条件判断", "category": "concept", "tags": ["条件"]},
        }

    def test_missing_semantic_summary_does_not_generate_natural_language_advice(self) -> None:
        summary = learn_today_update.summarize_progress(self._progress(), self._questions_map())

        self.assertEqual(summary.get("semantic_status"), "missing_artifact")
        self.assertIsNone(summary.get("overall"))
        self.assertEqual(summary.get("review_focus"), [])
        self.assertEqual(summary.get("next_learning"), [])
        self.assertEqual(summary.get("high_freq_errors"), ["条件判断"])
        self.assertEqual(summary.get("semantic_missing_requirements"), ["semantic_summary"])

    def _semantic_summary(self) -> dict:
        return {
            "overall": "条件判断需要回炉",
            "review_focus": ["重做条件判断错题"],
            "next_learning": ["学习函数定义"],
            "should_review": True,
            "can_advance": False,
            "evidence": ["q2 错两次"],
            "confidence": 0.8,
            "generation_trace": {"stage": "today-update", "generator": "subagent-fixture", "status": "ok", "artifact_source": "agent-subagent"},
            "traceability": [{"kind": "test", "ref": "semantic-summary"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def test_diagnostic_triggers_are_aggregated_into_summary_targets(self) -> None:
        progress = self._progress()
        progress["questions"]["q2"]["stats"]["last_submit_result"] = {
            "question_id": "q2",
            "question_type": "single_choice",
            "is_correct": False,
            "selected": [1],
            "unsure": [0],
            "diagnostic_triggers": [
                {
                    "trigger_type": "wrong_answer",
                    "question_id": "q2",
                    "question_type": "single_choice",
                    "option_index": 1,
                    "selected": True,
                    "is_correct_option": False,
                    "knowledge_point_ids": ["kp-condition"],
                    "misconception_ids": ["mc-condition-branch"],
                    "capability_tags": ["条件"],
                    "evidence": ["user selected option 1"],
                    "severity": "medium",
                    "requires_follow_up": True,
                    "diagnostic_mapping_status": "mapped",
                }
            ],
            "submitted_at": "2026-04-24T08:30:00Z",
        }

        summary = learn_today_update.summarize_progress(progress, self._questions_map())

        self.assertEqual(len(summary["diagnostic_triggers"]), 1)
        self.assertEqual(summary["diagnostic_targets"][0]["knowledge_point_id"], "kp-condition")
        self.assertEqual(summary["diagnostic_targets"][0]["misconception_ids"], ["mc-condition-branch"])
        self.assertEqual(summary["result_summary"]["raw_score"], {"correct": 1, "attempted": 2, "total": 2, "ratio": 0.5})
        self.assertEqual(summary["result_summary"]["learning_score"]["level"], "medium_low")
        self.assertEqual(summary["result_summary"]["review_recommendation"]["recommended_action"], "review_first")

    def test_valid_semantic_summary_populates_semantic_fields(self) -> None:
        summary = learn_today_update.summarize_progress(self._progress(), self._questions_map(), semantic_summary=self._semantic_summary())

        self.assertEqual(summary.get("semantic_status"), "ok")
        self.assertEqual(summary.get("overall"), "条件判断需要回炉")
        self.assertEqual(summary.get("review_focus"), ["重做条件判断错题"])
        self.assertEqual(summary.get("next_learning"), ["学习函数定义"])
        self.assertTrue(summary.get("should_review"))
        self.assertFalse(summary.get("can_advance"))

    def test_cli_semantic_summary_json_updates_learning_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            progress_path = session_dir / "progress.json"
            progress_path.write_text(json.dumps(self._progress(), ensure_ascii=False), encoding="utf-8")
            questions_path = session_dir / "questions.json"
            questions_path.write_text(json.dumps({"questions": [{"id": qid, **item} for qid, item in self._questions_map().items()]}, ensure_ascii=False), encoding="utf-8")
            semantic_path = root / "semantic.json"
            semantic_path.write_text(json.dumps(self._semantic_summary(), ensure_ascii=False), encoding="utf-8")
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")

            with patch.object(sys, "argv", [
                "learn_today_update.py",
                "--session-dir", str(session_dir),
                "--plan-path", str(plan_path),
                "--semantic-summary-json", str(semantic_path),
            ]), patch("learn_today_update.refresh_workflow_state", return_value={}), patch("sys.stdout", new_callable=io.StringIO):
                exit_code = learn_today_update.main()

            self.assertEqual(exit_code, 0)
            updated_progress = json.loads(progress_path.read_text(encoding="utf-8"))
            learning_state = updated_progress.get("learning_state", {})
            self.assertEqual(learning_state.get("overall"), "条件判断需要回炉")
            self.assertEqual(learning_state.get("review_focus"), ["重做条件判断错题"])
            self.assertEqual(learning_state.get("next_learning"), ["学习函数定义"])
            self.assertIn("semantic summary 状态：ok", plan_path.read_text(encoding="utf-8"))

    def test_knowledge_state_update_skips_draft_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received"}
            progress["mastery_judgement"] = {"status": "mastered", "prompting_level": "none"}
            questions_map = self._questions_map(knowledge_point_id=point["id"])

            result = learn_today_update.update_knowledge_state_from_progress(plan_path, session_dir, progress, questions_map, self._semantic_summary())

            self.assertEqual(result, {"status": "skipped", "reason": "knowledge_state_not_confirmed", "evidence_count": 0})
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 0)
            self.assertEqual(saved_state["evidence_log"], [])

    def test_knowledge_state_update_skips_missing_semantic_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            state["status"] = "active"
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received"}
            progress["mastery_judgement"] = {"status": "mastered", "prompting_level": "none"}
            summary = learn_today_update.summarize_progress(progress, self._questions_map(knowledge_point_id=point["id"]))

            result = learn_today_update.update_knowledge_state_from_progress(plan_path, session_dir, progress, self._questions_map(knowledge_point_id=point["id"]), summary)

            self.assertEqual(result, {"status": "skipped", "reason": "semantic_summary_missing", "evidence_count": 0})
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 0)
            self.assertEqual(saved_state["evidence_log"], [])

    def test_knowledge_state_update_skips_missing_evidence_type_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            state["status"] = "active"
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received"}
            progress["mastery_judgement"] = {"status": "mastered", "prompting_level": "none"}
            questions_map = self._questions_map(knowledge_point_id=point["id"])
            questions_map["q1"].pop("evidence_types")

            result = learn_today_update.update_knowledge_state_from_progress(plan_path, session_dir, progress, questions_map, self._semantic_summary())

            self.assertEqual(result, {"status": "skipped", "reason": "no_bound_question_evidence", "evidence_count": 0})
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 0)
            self.assertEqual(saved_state["evidence_log"], [])

    def test_knowledge_state_update_skips_invalid_point_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            state["status"] = "active"
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received"}
            progress["mastery_judgement"] = {"status": "mastered", "prompting_level": "none"}
            questions_map = self._questions_map(knowledge_point_id="missing-point")

            result = learn_today_update.update_knowledge_state_from_progress(plan_path, session_dir, progress, questions_map, self._semantic_summary())

            self.assertEqual(result, {"status": "skipped", "reason": "invalid_knowledge_point_binding", "evidence_count": 0})
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 0)
            self.assertEqual(saved_state["evidence_log"], [])

    def test_knowledge_state_update_uses_interaction_evidence_without_bound_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            point["mastery"] = 50
            point["confidence"] = "medium"
            state["status"] = "active"
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received", "source": "user"}
            progress["mastery_judgement"] = {"status": "solid_after_intervention", "prompting_level": "hinted", "confidence": 0.82}
            progress["interaction_evidence"] = [
                {
                    "phase": "exercise-review",
                    "type": "follow_up_question",
                    "summary": "用户追问变量赋值后原对象是否还会被引用，需要提示后才部分解释清楚。",
                    "knowledge_points": [point["id"]],
                    "severity": "medium",
                    "follow_up_status": "partial",
                    "prompting_level": "hinted",
                }
            ]
            (session_dir / "reflection.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "rounds": [
                            {
                                "round_index": 1,
                                "question_type": "oral",
                                "knowledge_points": [point["id"]],
                                "result": "prompted_partial",
                                "prompting_level": "hinted",
                            }
                        ],
                        "diagnoses": [
                            {
                                "knowledge_point_id": point["id"],
                                "diagnosis": "mental_model_gap",
                                "severity": "medium",
                                "confidence": 0.81,
                                "question_quality_guard": "passed",
                                "rationale": "用户复盘时需要提示才能解释变量名与对象绑定关系。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            questions_map = self._questions_map()
            summary = learn_today_update.summarize_progress(progress, questions_map, semantic_summary=self._semantic_summary())

            result = learn_today_update.update_knowledge_state_from_progress(plan_path, session_dir, progress, questions_map, summary)

            self.assertEqual(result, {"status": "updated", "reason": None, "evidence_count": 2})
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 41)
            self.assertEqual(saved_point["confidence"], "low")
            sources = [item["source"] for item in saved_state["evidence_log"]]
            self.assertEqual(sources, ["/learn-today:interaction", "/learn-today:reflection-diagnosis"])
            self.assertFalse(any(source.startswith("/learn-today:question:") for source in sources))

    def test_cli_updates_knowledge_state_when_questions_are_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_dir = root / "session"
            session_dir.mkdir()
            plan_path = root / "learn-plan.md"
            plan_path.write_text("# Test Plan\n", encoding="utf-8")
            state = build_default_knowledge_state(topic="Python 基础", goal="掌握变量赋值", level="零基础", schedule="每天", preference="混合")
            point = next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})
            state["status"] = "active"
            save_knowledge_state(plan_path, state)
            progress = self._progress()
            progress["completion_signal"] = {"status": "received"}
            progress["mastery_judgement"] = {"status": "mastered", "prompting_level": "none"}
            progress_path = session_dir / "progress.json"
            progress_path.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")
            questions_path = session_dir / "questions.json"
            questions_path.write_text(
                json.dumps({"questions": [{"id": qid, **item} for qid, item in self._questions_map(knowledge_point_id=point["id"]).items()]}, ensure_ascii=False),
                encoding="utf-8",
            )
            semantic_path = root / "semantic.json"
            semantic_path.write_text(json.dumps(self._semantic_summary(), ensure_ascii=False), encoding="utf-8")

            with patch.object(sys, "argv", [
                "learn_today_update.py",
                "--session-dir", str(session_dir),
                "--plan-path", str(plan_path),
                "--semantic-summary-json", str(semantic_path),
            ]), patch("learn_today_update.refresh_workflow_state", return_value={}), patch("sys.stdout", new_callable=io.StringIO):
                exit_code = learn_today_update.main()

            self.assertEqual(exit_code, 0)
            saved_state = json.loads((root / "knowledge-state.json").read_text(encoding="utf-8"))
            saved_point = next(node for node in saved_state["nodes"] if node["id"] == point["id"])
            self.assertEqual(saved_point["mastery"], 8)
            self.assertEqual(saved_state["evidence_log"][0]["knowledge_point_ids"], [point["id"]])
            self.assertTrue((root / "knowledge-map.md").exists())


if __name__ == "__main__":
    unittest.main()
