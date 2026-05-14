"""证明课件管线质量问题：模板把叙事拆成 bullet points，md/ipynb 同内容双写。"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


def make_rich_narrative_lesson() -> dict:
    """构造一段有叙事感的课件 JSON——就像 Agent 会写的那种。"""
    return {
        "title": "Python 对象引用：从一次数据事故说起",
        "why_today": "变量引用机制是 Python 编程中最容易踩坑的概念之一，今天通过真实事故案例彻底搞懂它。",
        "plan_execution_mode": "normal",
        "materials_used": [
            {"material_title": "流畅的 Python", "locator": "第8章 对象引用、可变性和垃圾回收"}
        ],
        "today_focus": {
            "summary": "理解 Python 变量是对象的标签而非容器，掌握引用语义与对象复制的区别。",
            "focus_points": [
                {"point": "变量名绑定对象引用", "why_it_matters": "这是理解 list/dict 可变性、函数传参、copy 模块的前提", "mastery_check": "能解释 a=[1]; b=a; b.append(2) 后 a 的值及其原因"}
            ],
        },
        "project_driven_explanation": {
            "summary": "通过一个数据清洗事故，展示变量引用如何导致隐藏的副作用。",
            "tasks": [{
                "task_name": "修复数据清洗流水线",
                "real_context": "你所在的团队维护一条每日数据清洗流水线。上周五，小王提交了一个 clean_scores 函数，周一早上你发现原始数据被意外修改了。",
                "blocker": "修改'副本'时发现原数据也被改了——但明明用 .copy() 复制了列表",
                "why_now": "这是 Python 新手和中级开发者都会反复遇到的核心概念混淆",
                "knowledge_points": ["变量引用语义", "浅拷贝 vs 深拷贝", "可变对象 vs 不可变对象"],
                "explanation": "Python 中的赋值语句不会创建新对象，而是将变量名绑定到已有对象。a = [1,2,3]; b = a 使得 a 和 b 指向同一个列表。.copy() 创建浅拷贝——新列表对象，但内部元素仍共享引用。对于嵌套结构，需要 copy.deepcopy()。",
                "how_to_apply": "1) 需要独立副本时用 .copy() 或 copy.deepcopy(); 2) 函数内部不要修改传入的可变参数，改为返回新对象; 3) 用 pytest 验证输入不被污染",
                "extension": "函数默认参数在定义时求值，[] 作为默认参数会被多次调用共享——这是引用语义的另一个常见陷阱。",
            }],
        },
        "review_suggestions": {
            "summary": "今日复习要点",
            "today_review": ["画图解释 a=[1,2]; b=a; c=a.copy() 三种情况下对象和引用的关系"],
            "progress_review": ["回顾之前写的脚本，检查是否有直接修改入参的情况"],
            "next_actions": ["下次学习 copy 模块和 deepcopy 的递归行为"],
        },
        "case_courseware": {
            "knowledge_preview_flashcards": [
                {"term": "对象引用", "explanation": "变量名指向内存中的对象，而非存储对象本身", "mastery_check": "判断正误：b = a 总是创建副本"}
            ],
            "case_background": {
                "situation": "周一早晨，你打开数据看板，发现上周五的清洗结果全部异常。排查后发现：小王写的 clean_scores 函数在内部对传入列表调用了 .sort()，导致上游原始数据被永久改变了。整个周末的备份数据都已被这个修改污染。你需要在一小时内找到根因、修复代码、并确保类似问题不再发生。",
                "problem_to_solve": "如何彻底理清变量引用与对象复制的关系，并建立防止副作用污染的编码习惯？",
                "protagonist": "数据工程师小张",
            },
            "guided_story_practice": [
                {
                    "scene": "你打开小王的 commit，看到 clean_scores 的实现。函数接收一个 scores 列表，内部直接调用了 scores.sort() 然后返回。",
                    "challenge": "为什么 scores.sort() 会影响调用者的原始数据？a = b 不是赋值吗？难道函数参数是传值的？",
                    "teaching_move": "在纸上画出内存图：scores 变量 → 列表对象 [95, 67, 88]。函数参数名和调用者的变量名指向同一个对象。.sort() 修改的是那个共享的对象本身——不关参数传递方式的事，这是对象引用语义。",
                    "resolution": "修改 clean_scores：先创建副本 result = list(scores)，在 result 上做操作，最后返回 result。原始 scores 保持不变。再加上 pytest 验证：assert 调用前后原始列表不变。",
                },
                {
                    "scene": "你继续排查，发现另一个函数处理的是嵌套结构：records = [{'name': 'Alice', 'tags': ['math', 'cs']}, ...]。同事用 copied = records.copy() 尝试保护原始数据，但 copied[0]['tags'].append('stats') 仍然污染了原始 records。",
                    "challenge": "明明用了 .copy()，为什么嵌套结构还是被改了？list 的 copy 方法不是复制了吗？",
                    "teaching_move": "引入浅拷贝概念。画两层图：外层 list 是新对象，但内部元素（dict、子 list）仍然是原来的引用。records.copy() 只复制了外层容器。要深度保护嵌套结构，需要用 copy.deepcopy()。同时引入替代方案：与其 deepcopy 整个结构，不如在清洗时逐条构造新 dict。",
                    "resolution": "根据场景选择策略：1) 扁平列表：list.copy() 够用；2) 嵌套结构且只需要改外层：构造新 list of 新 dict；3) 嵌套结构且深度修改：考虑 copy.deepcopy() 或 immutable 数据结构。加上测试用例覆盖嵌套边界。",
                },
                {
                    "scene": "修完两个 bug 后，你想到一个问题：如果未来又有同事不小心写了有副作用的函数，怎么才能第一时间发现？",
                    "challenge": "口头约定'不要修改输入参数'不可靠。需要自动化验证来守住这条规则。",
                    "teaching_move": "引入 pytest 自动化验证模式：每个工具函数都要有对应的测试用例，专门验证'输入是否被污染'。写一个简单的 fixture pattern：记录输入快照 → 调用函数 → assert 输入 == 快照。这是防御性编程的最小闭环。",
                    "resolution": "建立团队规范：每个数据清洗函数必须有对应的 test_side_effect_free.py 测试。CI 中运行完整测试套件。将今天的教训写入团队 Wiki 的'常见陷阱'页面。",
                },
            ],
            "review_sources": [
                {"material_title": "流畅的 Python", "locator": "第8章 对象引用、可变性和垃圾回收", "review_focus": "深入理解标识、相等性和别名"},
                {"material_title": "Python 官方文档", "locator": "copy — Shallow and deep copy operations", "review_focus": "浅拷贝和深拷贝的官方说明"},
            ],
            "exercise_policy": {"embedded_questions": False},
        },
        "review_targets": ["对象引用语义", "浅拷贝 vs 深拷贝", "函数副作用防护"],
    }


# ---- 管线质量复现 ----

class LessonPipelineQualityTest(unittest.TestCase):
    def test_deprecated_renderer_uses_explanation_sections(self):
        """已废弃 renderer 仍可渲染旧 case_courseware，但默认结构改为严谨讲解。"""
        from learn_runtime.lesson_builder import render_daily_lesson_plan_markdown

        lesson = make_rich_narrative_lesson()
        output = render_daily_lesson_plan_markdown(lesson)

        self.assertIn("## 讲解背景", output)
        self.assertIn("## 核心问题", output)
        self.assertIn("## 本期知识点讲解", output)
        self.assertNotIn("## 跟着案例学", output)

    def test_notebook_and_markdown_output_content_overlap(self):
        """已废弃：notebook 和 markdown 渲染器产出同质内容——这是它们被废弃的原因。"""
        from learn_runtime.lesson_builder import render_daily_lesson_plan_markdown
        from learn_runtime.notebook_renderer import render_daily_lesson_notebook

        lesson = make_rich_narrative_lesson()
        md_output = render_daily_lesson_plan_markdown(lesson)
        notebook = render_daily_lesson_notebook(lesson)

        notebook_text = ""
        for cell in notebook.get("cells", []):
            if cell.get("cell_type") == "markdown":
                for line in cell.get("source", []):
                    notebook_text += line

        md_normalized = re.sub(r"\s+", "", md_output)
        nb_normalized = re.sub(r"\s+", "", notebook_text)
        overlap = len(set(md_normalized) & set(nb_normalized)) / max(1, len(set(md_normalized) | set(nb_normalized)))

        self.assertGreater(overlap, 0.80,
            f"Markdown 和 Notebook 内容重合度 {overlap:.0%}——双重文件没有附加值，已被废弃")

    def test_deprecated_renderer_no_longer_uses_story_section_by_default(self):
        """已废弃 renderer 不再把默认课件写成故事结构。"""
        from learn_runtime.lesson_builder import render_daily_lesson_plan_markdown

        minimal = {
            "title": "测试",
            "case_courseware": {
                "knowledge_preview_flashcards": [{"term": "t", "explanation": "e", "mastery_check": "m"}],
                "case_background": {"situation": "背景描述足够长以通过最低字数检查", "problem_to_solve": "解决一个问题"},
                "guided_story_practice": [{
                    "scene": "一段很长的场景描述。",
                    "challenge": "学生面临的核心困惑。",
                    "teaching_move": "知识点的引入方式。",
                    "resolution": "问题解决后的状态。",
                }],
                "review_sources": [{"material_title": "测试书", "locator": "第1章", "review_focus": "重点"}],
                "exercise_policy": {"embedded_questions": False},
            },
            "today_focus": {"summary": "s", "focus_points": [{"point": "p", "why_it_matters": "w", "mastery_check": "m"}]},
            "project_driven_explanation": {"summary": "s", "tasks": [{"task_name": "t", "real_context": "c", "blocker": "b", "why_now": "w", "knowledge_points": ["k"], "explanation": "e", "how_to_apply": "h", "extension": "x"}]},
            "review_suggestions": {"summary": "s", "today_review": ["r"], "progress_review": ["p"], "next_actions": ["n"]},
            "materials_used": [{"material_title": "t", "locator": "l"}],
            "plan_execution_mode": "normal",
            "why_today": "w",
            "review_targets": ["rt"],
        }
        output = render_daily_lesson_plan_markdown(minimal)

        self.assertIn("## 本期知识点讲解", output)
        self.assertNotIn("## 跟着案例学", output)


if __name__ == "__main__":
    unittest.main()
