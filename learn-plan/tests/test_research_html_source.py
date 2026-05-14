from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


class ResearchHtmlSourceTest(unittest.TestCase):
    def _clarification(self) -> dict:
        return {
            "questionnaire": {
                "topic": "Python 大模型应用开发",
                "goal": "求职一线城市大模型应用岗位",
                "success_criteria": ["达到岗位项目面试要求"],
                "current_level_self_report": "有 Python 基础",
                "time_constraints": {"frequency": "每天", "session_length": "30分钟"},
                "mastery_preferences": {"max_assessment_rounds_preference": 1, "questions_per_round_preference": 5},
            },
            "consultation_state": {
                "current_topic_id": "learning_purpose",
                "topics": [
                    {"id": "learning_purpose", "required": True, "status": "resolved", "exit_criteria": ["目标明确"]},
                    {"id": "exam_or_job_target", "required": True, "status": "resolved", "exit_criteria": ["岗位范围明确"]},
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
            "generation_trace": {"stage": "clarification", "generator": "test-fixture", "status": "ok", "artifact_source": "user"},
            "traceability": [{"kind": "test", "ref": "clarification"}],
            "quality_review": {"reviewer": "test", "valid": True, "issues": [], "confidence": 0.8},
        }

    def _research_candidate(self, user_facing_report: dict) -> dict:
        return {
            "research_report": {
                "report_status": "completed",
                "research_brief": "岗位要求分析",
                "goal_target_band": "初级大模型应用开发岗位",
                "required_level_definition": "能用 Python 完成 API、RAG 与简单 Agent 项目",
                "user_facing_report": user_facing_report,
                "must_master_core": ["Python 工程基础", "API 调用", "RAG 基础"],
                "evidence_expectations": ["能完成项目代码", "能解释技术取舍"],
                "evaluator_roles": ["HR", "技术负责人", "一线实践者"],
                "source_categories": ["岗位描述", "经验文档", "课程", "书籍", "练习题", "开源仓库"],
                "web_source_evidence": [{"title": "岗位描述", "url": "https://example.com/job", "claim": "要求 Python 工程能力"}],
                "capability_metrics": [
                    {
                        "capability_id": "python-engineering",
                        "observable_behaviors": ["能拆分函数"],
                        "quantitative_indicators": ["完成率"],
                        "diagnostic_methods": ["编码题"],
                        "learning_evidence": ["项目提交"],
                        "source_evidence": ["岗位描述"],
                    }
                ],
                "evidence_summary": ["岗位描述"],
                "selection_rationale": ["目标匹配"],
                "diagnostic_scope": {
                    "target_capability_ids": ["python-engineering"],
                    "scoring_dimensions": ["正确性"],
                    "gap_judgement_basis": ["编码表现"],
                },
            },
            "research_review": {"status": "confirmed"},
            "evidence": ["research fixture"],
            "confidence": 0.8,
            "generation_trace": {"stage": "research", "generator": "subagent-fixture", "status": "ok", "artifact_source": "agent-subagent"},
            "traceability": [{"kind": "test", "ref": "research"}],
        }

    def _run_research_report(self, root: Path, user_facing_report: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
        clarification_path = root / "clarification.json"
        research_candidate_path = root / "research_candidate.json"
        clarification_path.write_text(json.dumps(self._clarification(), ensure_ascii=False), encoding="utf-8")
        research_candidate_path.write_text(json.dumps(self._research_candidate(user_facing_report), ensure_ascii=False), encoding="utf-8")

        result = subprocess.run(
            [
                "python3",
                str(SKILL_DIR / "learn_plan.py"),
                "--topic",
                "Python 大模型应用开发",
                "--goal",
                "求职一线城市大模型应用岗位",
                "--level",
                "有 Python 基础",
                "--schedule",
                "每天30分钟",
                "--preference",
                "混合",
                "--plan-path",
                str(root / "learn-plan.md"),
                "--materials-dir",
                str(root / "materials"),
                "--mode",
                "research-report",
                "--stdout-json",
                "--clarification-json",
                str(clarification_path),
                "--stage-candidate-json",
                str(research_candidate_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn(result.returncode, {0, 2}, result.stderr)
        research = json.loads((root / ".learn-workflow" / "research.json").read_text(encoding="utf-8"))
        return result, research

    def test_subagent_research_report_path_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="learn-plan-html-source.") as tmp:
            root = Path(tmp)
            subagent_html = root / "subagent-report.html"
            subagent_html.write_text("<h1>Subagent report</h1>", encoding="utf-8")
            _, research = self._run_research_report(
                root,
                {"format": "html", "path": str(subagent_html), "summary": ["掌握 Python 工程基础"]},
            )

            user_facing_report = research["research_report"]["user_facing_report"]
            self.assertEqual(user_facing_report.get("path"), str(subagent_html))
            self.assertNotEqual(user_facing_report.get("path"), str(root / ".learn-workflow" / "research-report.html"))
            self.assertEqual(user_facing_report.get("presentation_source"), "subagent_path")

    def test_subagent_inline_html_is_written_without_renderer_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="learn-plan-html-inline.") as tmp:
            root = Path(tmp)
            _, research = self._run_research_report(
                root,
                {"format": "html", "html": "<h1>Inline subagent report</h1>", "summary": ["掌握 Python 工程基础"]},
            )

            user_facing_report = research["research_report"]["user_facing_report"]
            html_path = Path(user_facing_report["path"]).resolve()
            self.assertEqual(user_facing_report.get("presentation_source"), "subagent_inline_html")
            self.assertEqual(html_path, (root / "reports" / "purpose-analysis.html").resolve())
            self.assertIn("Inline subagent report", html_path.read_text(encoding="utf-8"))

    def test_renderer_fallback_is_marked_when_subagent_html_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="learn-plan-html-fallback.") as tmp:
            root = Path(tmp)
            _, research = self._run_research_report(
                root,
                {"format": "html", "summary": ["掌握 Python 工程基础"]},
            )

            user_facing_report = research["research_report"]["user_facing_report"]
            self.assertEqual(user_facing_report.get("presentation_source"), "renderer_fallback")
            self.assertEqual(user_facing_report.get("semantic_source"), "agent-subagent")
            self.assertEqual(user_facing_report.get("based_on"), "research_report")
            self.assertEqual(Path(user_facing_report["path"]).resolve(), (root / "reports" / "purpose-analysis.html").resolve())
            self.assertTrue(Path(user_facing_report["path"]).resolve().exists())


if __name__ == "__main__":
    unittest.main()
