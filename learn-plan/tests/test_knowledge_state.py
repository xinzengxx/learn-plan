from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from learn_knowledge import (
    KnowledgeStateError,
    build_default_knowledge_state,
    build_interaction_knowledge_evidence_items,
    build_lesson_target_slice,
    build_review_before_progress_gate,
    build_session_knowledge_evidence_items,
    build_test_coverage_slice,
    count_applicable_session_evidence,
    save_knowledge_state,
    update_state_from_session_evidence,
    validate_knowledge_state,
)


class KnowledgeStateTest(unittest.TestCase):
    def _leaf(self, state: dict) -> dict:
        return next(node for node in state["nodes"] if node["level"] in {"knowledge_point", "atomic_knowledge_point"})

    def _state(self) -> dict:
        return build_default_knowledge_state(
            topic="Pandas 时间序列",
            goal="能解析时间列并完成基础窗口统计",
            level="零基础",
            schedule="每天 30 分钟",
            preference="混合",
            planning={
                "stage_plan": [
                    {"name": "时间类型构造", "focus": ["解析时间列", "Timestamp 与 Timedelta 基础"]},
                    {"name": "窗口计算", "focus": ["滚动窗口统计", "按时间窗口聚合"]},
                ]
            },
            diagnostic={"max_rounds": 2, "questions_per_round": 4},
        )

    def test_build_default_state_uses_layered_atomic_graph(self) -> None:
        state = self._state()

        self.assertEqual(state["contract_version"], "learn-plan.knowledge-state.v1")
        self.assertEqual(state["schema_version"], "1.1")
        self.assertEqual(state["status"], "draft")
        self.assertTrue(state["dag_validation"]["valid"])
        levels = {node["level"] for node in state["nodes"]}
        self.assertEqual(levels, {"domain", "module", "concept_cluster", "concept", "atomic_knowledge_point"})
        leaves = [node for node in state["nodes"] if node["level"] == "atomic_knowledge_point"]
        self.assertGreaterEqual(len(leaves), 8)
        self.assertTrue(all(node.get("required_evidence_types") for node in leaves))
        self.assertTrue(all(node.get("diagnostic_tasks") for node in leaves))
        self.assertTrue(all("mastery" not in node for node in state["nodes"] if node["level"] != "atomic_knowledge_point"))

    def test_pandas_topic_generates_api_level_atomic_points(self) -> None:
        state = self._state()
        api_nodes = [node for node in state["nodes"] if node["level"] == "atomic_knowledge_point" and node.get("api_signature")]
        api_titles = {node["title"] for node in api_nodes}

        self.assertIn("pd.to_datetime", api_titles)
        self.assertIn("DataFrame.rolling", api_titles)
        self.assertTrue(all(node.get("common_misconceptions") for node in api_nodes))

    def test_validation_rejects_cycle_and_upper_mastery(self) -> None:
        state = self._state()
        domain = next(node for node in state["nodes"] if node["level"] == "domain")
        concept = next(node for node in state["nodes"] if node["level"] == "concept")
        leaf = next(node for node in state["nodes"] if node["level"] == "atomic_knowledge_point" and node["parent_id"] == concept["id"])
        domain["mastery"] = 10
        state["edges"].append({"from": leaf["id"], "to": concept["id"], "type": "hard"})

        with self.assertRaises(KnowledgeStateError) as context:
            validate_knowledge_state(state)

        message = str(context.exception)
        self.assertIn("knowledge.node.upper_mastery_forbidden", message)
        self.assertIn("knowledge.dag.cycle", message)

    def test_build_lesson_and_test_slices(self) -> None:
        state = self._state()
        lesson_slice = build_lesson_target_slice(state, stage="阶段 1", topic="时间类型构造", time_budget="30 分钟")
        test_slice = build_test_coverage_slice(state, test_goal="初始诊断", rounds=2, questions_per_round=3)

        self.assertIn("primary_points", lesson_slice)
        self.assertTrue(lesson_slice["primary_points"])
        self.assertIn("readiness", lesson_slice)
        self.assertEqual(test_slice["coverage_budget"], {"rounds": 2, "questions_per_round": 3})
        self.assertTrue(test_slice["selected_points"])
        self.assertEqual(test_slice["selection_strategy"], "information_gain_hub_prerequisite_first")
        self.assertTrue(test_slice["diagnostic_values"])
        self.assertTrue(test_slice["early_stop_policy"]["enabled"])
        self.assertGreater(test_slice["expected_confidence_update"]["coverage_ratio"], 0)

    def test_update_state_from_session_evidence_caps_delta_and_writes_log(self) -> None:
        state = self._state()
        point = self._leaf(state)
        updated = update_state_from_session_evidence(
            state,
            session_dir=Path("/tmp/session"),
            session_type="test",
            evidence_items=[
                {
                    "knowledge_point_ids": [point["id"]],
                    "evidence_types": ["explanation", "implementation"],
                    "mastery_delta": 45,
                    "confidence_after": "medium",
                    "summary": "综合题能解释但实现仍需练习",
                }
            ],
            summary={"overall": "完成初始诊断"},
        )

        updated_point = next(node for node in updated["nodes"] if node["id"] == point["id"])
        self.assertEqual(updated_point["mastery"], 20)
        self.assertEqual(updated_point["confidence"], "medium")
        self.assertEqual(updated_point["status_label"], "不熟悉")
        self.assertTrue(updated_point["last_tested"])
        self.assertEqual(len(updated["evidence_log"]), 1)
        self.assertEqual(updated["evidence_log"][0]["mastery_delta"], 20)

    def test_high_quality_diagnostic_evidence_can_exceed_default_delta_limit(self) -> None:
        state = self._state()
        point = self._leaf(state)
        point["mastery"] = 70
        updated = update_state_from_session_evidence(
            state,
            session_dir=Path("/tmp/session"),
            session_type="test",
            evidence_items=[
                {
                    "knowledge_point_ids": [point["id"]],
                    "evidence_types": ["explanation", "transfer"],
                    "mastery_delta": -45,
                    "confidence_after": "low",
                    "diagnostic_evidence": {
                        "source": "reflection.diagnoses",
                        "severity": "high",
                        "confidence": 0.88,
                        "question_quality_guard": "passed",
                        "round_count": 2,
                    },
                    "summary": "多轮复盘确认迁移解释不稳",
                }
            ],
            summary={"overall": "诊断确认退化"},
        )

        updated_point = next(node for node in updated["nodes"] if node["id"] == point["id"])
        self.assertEqual(updated_point["mastery"], 25)
        self.assertEqual(updated["evidence_log"][0]["mastery_delta"], -45)
        self.assertEqual(updated["evidence_log"][0]["diagnostic_evidence"]["source"], "reflection.diagnoses")

    def test_review_before_progress_gate_recommends_review_without_auto_blocking(self) -> None:
        gate = build_review_before_progress_gate(
            [
                {
                    "id": "kp-window",
                    "title": "滚动窗口统计",
                    "level": "knowledge_point",
                    "baseline_mastery": 85,
                    "previous_stage_mastery": 82,
                    "weekly_mastery": 78,
                    "mastery": 42,
                    "stability": "declining",
                }
            ]
        )

        self.assertEqual(gate["recommended_action"], "review_first")
        self.assertTrue(gate["requires_user_confirmation"])
        self.assertFalse(gate["blocks_advance"])
        self.assertEqual(gate["review_targets"], ["kp-window"])

    def test_invalid_session_evidence_does_not_write_history_or_log(self) -> None:
        state = self._state()
        before_history_len = len(state["history"])

        updated = update_state_from_session_evidence(
            state,
            session_dir=Path("/tmp/session"),
            session_type="test",
            evidence_items=[
                {
                    "knowledge_point_ids": ["missing-point"],
                    "evidence_types": ["explanation"],
                    "mastery_delta": 10,
                    "confidence_after": "medium",
                }
            ],
            summary={"overall": "无效绑定"},
        )

        self.assertEqual(count_applicable_session_evidence(state, [{"knowledge_point_ids": ["missing-point"]}]), 0)
        self.assertEqual(updated["evidence_log"], [])
        self.assertEqual(len(updated["history"]), before_history_len)

    def test_missing_evidence_type_binding_does_not_generate_or_apply_evidence(self) -> None:
        state = self._state()
        point = self._leaf(state)
        before_history_len = len(state["history"])
        progress = {
            "completion_signal": {"status": "received"},
            "mastery_judgement": {"status": "mastered", "prompting_level": "none"},
            "questions": {"q1": {"stats": {"attempts": 1, "correct_count": 1}}},
        }
        questions_map = {"q1": {"id": "q1", "category": "concept", "title": "时间解析", "knowledge_point_ids": [point["id"]]}}

        evidence = build_session_knowledge_evidence_items(
            progress,
            questions_map,
            session_type="today",
            gate={"completion_received": True, "reflection_completed": True},
        )
        updated = update_state_from_session_evidence(
            state,
            session_dir=Path("/tmp/session"),
            session_type="today",
            evidence_items=[{"knowledge_point_ids": [point["id"]], "mastery_delta": 8}],
            summary={"overall": "缺少 evidence type"},
        )

        self.assertEqual(evidence, [])
        self.assertEqual(count_applicable_session_evidence(state, [{"knowledge_point_ids": [point["id"]]}]), 0)
        self.assertEqual(updated["evidence_log"], [])
        self.assertEqual(len(updated["history"]), before_history_len)

    def test_build_session_evidence_requires_gate_and_bound_scorable_questions(self) -> None:
        progress = {
            "completion_signal": {"status": "received"},
            "mastery_judgement": {"status": "mastered", "prompting_level": "none"},
            "questions": {
                "q1": {"stats": {"attempts": 1, "correct_count": 1}},
                "q2": {"stats": {"attempts": 1, "correct_count": 1}},
                "q3": {"stats": {"attempts": 1, "correct_count": 0}},
            },
        }
        questions_map = {
            "q1": {"id": "q1", "category": "concept", "title": "时间解析", "knowledge_point_ids": ["kp-time"], "evidence_types": ["explanation"]},
            "q2": {"id": "q2", "category": "open", "title": "开放复盘", "knowledge_point_ids": ["kp-open"], "evidence_types": ["explanation"]},
            "q3": {"id": "q3", "category": "concept", "title": "窗口判断"},
        }

        blocked = build_session_knowledge_evidence_items(
            progress,
            questions_map,
            session_type="test",
            gate={"completion_received": True, "reflection_completed": False},
        )
        evidence = build_session_knowledge_evidence_items(
            progress,
            questions_map,
            session_type="test",
            gate={"completion_received": True, "reflection_completed": True},
        )

        self.assertEqual(blocked, [])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["knowledge_point_ids"], ["kp-time"])
        self.assertEqual(evidence[0]["mastery_delta"], 10)

    def test_legacy_three_layer_state_remains_valid_and_updatable(self) -> None:
        state = {
            "contract_version": "learn-plan.knowledge-state.v1",
            "schema_version": "1.0",
            "goal": {"topic": "Python", "goal": "掌握赋值", "level": "零基础", "schedule": "每天", "preference": "混合"},
            "status": "active",
            "nodes": [
                {"id": "domain-python", "title": "Python", "level": "domain", "parent_id": None, "derived_mastery": 0, "child_ids": ["topic-basic"]},
                {"id": "topic-basic", "title": "基础语法", "level": "topic", "parent_id": "domain-python", "derived_mastery": 0, "child_ids": ["kp-assign"]},
                {
                    "id": "kp-assign",
                    "title": "变量赋值",
                    "level": "knowledge_point",
                    "parent_id": "topic-basic",
                    "mastery": 0,
                    "confidence": "low",
                    "target_mastery": 80,
                    "required_evidence_types": ["explanation"],
                    "evidence_refs": [],
                },
            ],
            "edges": [{"from": "topic-basic", "to": "kp-assign", "type": "recommended"}],
            "evidence_log": [],
            "history": [],
        }

        validate_knowledge_state(state)
        updated = update_state_from_session_evidence(
            state,
            session_dir=Path("/tmp/session"),
            session_type="today",
            evidence_items=[{"knowledge_point_ids": ["kp-assign"], "evidence_types": ["explanation"], "mastery_delta": 8}],
        )

        point = next(node for node in updated["nodes"] if node["id"] == "kp-assign")
        self.assertEqual(point["mastery"], 8)
        self.assertEqual(updated["schema_version"], "1.0")

    def test_interaction_facts_generate_review_debt_evidence(self) -> None:
        evidence = build_interaction_knowledge_evidence_items(
            {
                "completion_signal_facts": {"status": "received"},
                "reflection_facts": {
                    "status": "completed",
                    "round_count": 2,
                    "diagnoses": [
                        {
                            "knowledge_point_id": "kp-closure",
                            "diagnosis": "mental_model_gap",
                            "severity": "high",
                            "confidence": 0.86,
                            "question_quality_guard": "passed",
                            "rationale": "用户需要提示后才能解释闭包变量仍被引用。",
                        }
                    ],
                },
                "mastery_judgement_facts": {"status": "solid_after_intervention", "prompting_level": "hinted", "confidence": 0.78},
                "interaction_event_facts": [
                    {
                        "knowledge_points": ["kp-closure"],
                        "severity": "medium",
                        "follow_up_status": "partial",
                        "prompting_level": "hinted",
                        "summary": "用户追问闭包变量为什么还存在",
                    }
                ],
            },
            session_type="today",
        )

        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(item["mastery_delta"] < 0 for item in evidence))
        self.assertEqual(evidence[0]["source"], "/learn-today:interaction")
        self.assertEqual(evidence[1]["diagnostic_evidence"]["source"], "reflection.diagnoses")

    def test_unprompted_reflection_mastery_generates_small_positive_evidence(self) -> None:
        evidence = build_interaction_knowledge_evidence_items(
            {
                "completion_signal_facts": {"status": "received"},
                "reflection_facts": {
                    "status": "completed",
                    "round_count": 1,
                    "rounds": [
                        {"knowledge_points": ["kp-time"], "result": "unprompted_correct", "prompting_level": "none"}
                    ],
                },
                "mastery_judgement_facts": {"status": "mastered", "prompting_level": "none", "confidence": 0.82},
            },
            session_type="today",
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["knowledge_point_ids"], ["kp-time"])
        self.assertEqual(evidence[0]["mastery_delta"], 5)
        self.assertEqual(evidence[0]["confidence_after"], "medium")

    def test_save_writes_state_and_map_next_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "learn-plan.md"
            paths = save_knowledge_state(plan_path, self._state())

            self.assertTrue(paths["knowledge_state"].exists())
            self.assertTrue(paths["knowledge_map"].exists())
            saved = json.loads(paths["knowledge_state"].read_text(encoding="utf-8"))
            self.assertEqual(saved["contract_version"], "learn-plan.knowledge-state.v1")
            self.assertIn("## 层级知识图谱", paths["knowledge_map"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
