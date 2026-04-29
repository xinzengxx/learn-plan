#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists as core_read_json_if_exists, read_text_if_exists as core_read_text_if_exists, write_json as core_write_json, write_text as core_write_text
from learn_core.quality_review import apply_quality_envelope, build_traceability_entry
from learn_core.text_utils import normalize_string_list, sanitize_filename as core_sanitize_filename
from learn_core.topic_family import detect_topic_family_from_configs as core_detect_topic_family_from_configs, infer_domain_from_configs as core_infer_domain_from_configs
from learn_feedback import apply_approval_patch_decisions, consume_approved_patches, write_patch_queue
from learn_materials import (
    build_default_material_entries as materials_build_default_material_entries,
    build_materials_index as materials_build_materials_index,
    build_reading_segments as materials_build_reading_segments,
    build_special_reading_segments as materials_build_special_reading_segments,
    enrich_material_entry as materials_enrich_material_entry,
    group_topics_for_segments as materials_group_topics_for_segments,
    infer_material_recommended_day as materials_infer_material_recommended_day,
    merge_material_entries as materials_merge_material_entries,
    merge_reading_segments as materials_merge_reading_segments,
    process_materials,
)
from learn_planning import (
    build_curriculum as planning_build_curriculum,
    build_plan_candidate as planning_build_plan_candidate,
    build_plan_report as planning_build_plan_report,
    build_planning_profile as planning_build_planning_profile,
    choose_existing_section as planning_choose_existing_section,
    render_capability_model_section,
    render_capability_report as planning_render_capability_report,
    render_capability_report_html as planning_render_capability_report_html,
    render_daily_roadmap as planning_render_daily_roadmap,
    render_diagnostic_scope_preview as planning_render_diagnostic_scope_preview,
    render_learning_route as planning_render_learning_route,
    render_mastery_checks as planning_render_mastery_checks,
    render_materials_section as planning_render_materials_section,
    render_plan as planning_render_plan,
    render_plan_report as planning_render_plan_report,
    review_public_plan_markdown as planning_review_public_plan_markdown,
    render_planning_constraints as planning_render_planning_constraints,
    render_planning_profile as planning_render_planning_profile,
    render_research_plan as planning_render_research_plan,
    render_stage_overview as planning_render_stage_overview,
    render_today_generation_rules as planning_render_today_generation_rules,
    validate_plan_quality as planning_validate_plan_quality,
)
from learn_workflow import (
    annotate_formal_plan_gate,
    build_stage_context,
    build_workflow_state,
    can_write_formal_plan,
    diagnostic_blueprint_missing_fields,
    load_workflow_inputs,
    normalize_clarification_artifact,
    resolve_assessment_budget_preference,
    resolve_learning_root,
    review_stage_candidate,
    write_workflow_state,
)


SKILL_DIR = Path(__file__).resolve().parent
SESSION_ORCHESTRATOR = SKILL_DIR / "session_orchestrator.py"


VALID_PREFERENCES = {"偏题海", "偏讲解", "偏测试", "混合"}


TOPIC_FAMILIES = {
    "english": {
        "keywords": ["英语", "词汇", "语法", "阅读", "写作", "英文"],
        "stages": [
            ("阶段 1", "核心词汇与基础语法", "建立最基础的输入能力", "词汇卡片 + 基础语法辨析", "完成 1 次词汇/语法小测后进入下一阶段"),
            ("阶段 2", "句子理解与短文阅读", "把词汇和语法放到上下文里", "短阅读 + 句子改写", "阅读正确率稳定后进入下一阶段"),
            ("阶段 3", "输出训练与综合测试", "开始做写作/翻译或综合训练", "写作模仿 + 综合测试", "综合测试结果稳定后扩展难度"),
        ],
        "materials": [
            {
                "id": "eng-cambridge-dict",
                "title": "Cambridge Dictionary",
                "kind": "reference",
                "source_name": "Cambridge University Press",
                "source_type": "official",
                "url": "https://dictionary.cambridge.org/",
                "use": "查词义、例句与发音",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["english", "dictionary", "reference"],
                "downloadable": False,
            },
            {
                "id": "eng-grammarly-handbook",
                "title": "Grammarly Handbook",
                "kind": "tutorial",
                "source_name": "Grammarly",
                "source_type": "official",
                "url": "https://www.grammarly.com/blog/category/handbook/",
                "use": "学习语法规则与常见错误",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["english", "grammar", "tutorial"],
                "downloadable": False,
            },
            {
                "id": "eng-purdue-owl",
                "title": "Purdue OWL Writing Resources",
                "kind": "reference",
                "source_name": "Purdue University",
                "source_type": "official",
                "url": "https://owl.purdue.edu/owl/purdue_owl.html",
                "use": "学术写作与语法参考",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["english", "writing", "academic", "reference"],
                "downloadable": False,
            },
            {
                "id": "eng-voa-learning",
                "title": "VOA Learning English",
                "kind": "practice",
                "source_name": "Voice of America",
                "source_type": "official",
                "url": "https://learningenglish.voanews.com/",
                "use": "听力与阅读练习",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["english", "listening", "reading", "practice"],
                "downloadable": False,
            },
        ],
    },
    "math": {
        "keywords": ["数学", "线代", "高数", "概率", "离散", "微积分"],
        "stages": [
            ("阶段 1", "基础概念与核心公式", "先补定义、符号和常见公式", "概念题 + 基础计算题", "完成 1 轮基础测试后进入下一阶段"),
            ("阶段 2", "典型题型与步骤拆解", "掌握常见题型的解法步骤", "专题练习 + 错题回看", "典型题型正确率稳定后进入下一阶段"),
            ("阶段 3", "综合应用与阶段测试", "把不同知识点串起来", "综合题 + 阶段测试", "阶段测试稳定后扩展新专题"),
        ],
        "materials": [
            {
                "id": "math-khan-math",
                "title": "Khan Academy Math",
                "kind": "tutorial",
                "source_name": "Khan Academy",
                "source_type": "official",
                "url": "https://www.khanacademy.org/math",
                "use": "补基础概念、例题与分阶段练习",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["math", "tutorial"],
                "downloadable": False,
            },
            {
                "id": "math-paul-notes",
                "title": "Paul's Online Math Notes",
                "kind": "reference",
                "source_name": "Lamar University",
                "source_type": "official",
                "url": "https://tutorial.math.lamar.edu/",
                "use": "查微积分、代数、常见公式与例题",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["math", "reference", "calculus"],
                "downloadable": False,
            },
            {
                "id": "math-openstax-algebra",
                "title": "OpenStax Algebra and Trigonometry",
                "kind": "book",
                "source_name": "OpenStax",
                "source_type": "official",
                "url": "https://openstax.org/details/books/algebra-and-trigonometry",
                "use": "系统化学习代数与三角函数",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["math", "book", "algebra"],
                "downloadable": False,
            },
            {
                "id": "math-3blue1brown-essence",
                "title": "3Blue1Brown Essence of Calculus",
                "kind": "video",
                "source_name": "3Blue1Brown",
                "source_type": "community",
                "url": "https://www.youtube.com/playlist?list=PLZHQObOWTQDMsr9K-rj53DwVRMYO3t5Yr",
                "use": "直观理解微积分核心概念",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["math", "video", "calculus", "visualization"],
                "downloadable": False,
            },
        ],
    },
    "algorithm": {
        "keywords": ["算法", "数据结构", "刷题", "LeetCode", "leetcode", "双指针", "二分", "DFS", "BFS", "动态规划"],
        "stages": [
            ("阶段 1", "数组与哈希 / 基础概念", "先建立题感和基础数据结构认知", "概念题 + easy 函数题", "完成 1 次基础测试后进入下一阶段"),
            ("阶段 2", "双指针 / 滑窗 / 二分查找", "掌握常见线性与查找技巧", "专题练习 + 同类题巩固", "典型题型正确率稳定后进入下一阶段"),
            ("阶段 3", "栈队列 / DFS-BFS / 综合测试", "把常见套路串起来", "medium 函数题 + 阶段测试", "阶段测试稳定后扩展到更高阶专题"),
        ],
        "materials": [
            {
                "id": "algo-leetcode-study-plan",
                "title": "LeetCode Study Plan",
                "kind": "practice",
                "source_name": "LeetCode",
                "source_type": "official",
                "url": "https://leetcode.com/studyplan/",
                "use": "按阶段补数组、双指针、滑窗、DFS/BFS 等常见题型",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["algorithm", "practice", "leetcode"],
                "downloadable": False,
            },
            {
                "id": "algo-oi-wiki-basics",
                "title": "OI Wiki 基础算法",
                "kind": "tutorial",
                "source_name": "OI Wiki",
                "source_type": "community",
                "url": "https://oi-wiki.org/",
                "use": "查概念、模板与常见算法知识点",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["algorithm", "tutorial", "reference"],
                "downloadable": False,
            },
            {
                "id": "algo-neetcode-roadmap",
                "title": "NeetCode Roadmap",
                "kind": "roadmap",
                "source_name": "NeetCode",
                "source_type": "community",
                "url": "https://neetcode.io/roadmap",
                "use": "按题型组织刷题路径，适合阶段性训练",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["algorithm", "roadmap", "practice"],
                "downloadable": False,
            },
            {
                "id": "algo-visualgo",
                "title": "VisuAlgo 算法可视化",
                "kind": "tutorial",
                "source_name": "VisuAlgo",
                "source_type": "community",
                "url": "https://visualgo.net/",
                "use": "可视化理解排序、图、树等算法执行过程",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["algorithm", "visualization", "tutorial"],
                "downloadable": False,
            },
        ],
    },
    "linux": {
        "keywords": ["Linux", "linux", "GNU/Linux", "shell", "Shell", "bash", "zsh", "命令行", "终端", "操作系统", "系统管理", "系统运维", "服务器"],
        "stages": [
            ("阶段 1", "命令行基础与文件系统", "掌握高频命令、路径、文件操作与文本查看", "命令练习 + 小型终端任务", "能独立完成常见文件与目录操作后进入下一阶段"),
            ("阶段 2", "权限 / 进程 / 包管理", "理解用户权限、进程控制、环境变量与包管理", "概念辨析 + 常见运维命令练习", "能定位常见权限与进程问题后进入下一阶段"),
            ("阶段 3", "网络 / 服务 / 排障", "掌握日志、网络、服务管理与基础排障路径", "场景题 + 命令诊断练习", "能完成基础排障闭环后扩展到更复杂场景"),
        ],
        "materials": [
            {
                "id": "linux-missing-semester",
                "title": "The Missing Semester of Your CS Education",
                "kind": "tutorial",
                "source_name": "MIT",
                "source_type": "official",
                "url": "https://missing.csail.mit.edu/",
                "use": "系统学习 shell、命令行、编辑器、版本控制与自动化基础",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["linux", "shell", "tutorial"],
                "downloadable": False,
            },
            {
                "id": "linux-gnu-bash-manual",
                "title": "GNU Bash Manual",
                "kind": "reference",
                "source_name": "GNU",
                "source_type": "official",
                "url": "https://www.gnu.org/software/bash/manual/",
                "use": "查 shell 语法、变量、函数与脚本细节",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["linux", "bash", "reference"],
                "downloadable": False,
            },
            {
                "id": "linux-ubuntu-server-guide",
                "title": "Ubuntu Server Guide",
                "kind": "tutorial",
                "source_name": "Ubuntu",
                "source_type": "official",
                "url": "https://documentation.ubuntu.com/server/",
                "use": "学习服务管理、网络配置、存储与系统管理基础",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["linux", "server", "ops"],
                "downloadable": False,
            },
            {
                "id": "linux-tldr-pages",
                "title": "tldr pages",
                "kind": "reference",
                "source_name": "tldr-pages",
                "source_type": "community",
                "url": "https://tldr.sh/",
                "use": "快速查常用命令示例，适合实战练习时辅助记忆",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["linux", "commands", "reference"],
                "downloadable": False,
            },
        ],
    },
    "llm-app": {
        "keywords": ["LangChain", "langchain", "LangGraph", "langgraph", "RAG", "rag", "Agent", "agent", "提示工程", "大模型", "LLM", "llm", "向量数据库", "embedding", "embeddings", "prompt", "Claude API", "Anthropic API", "模型应用"],
        "stages": [
            ("阶段 1", "LLM 基础 / Prompting / Structured Output", "理解模型能力边界、消息结构、提示设计与结构化输出约束", "概念题 + 小型提示实验 + 输出格式改写", "能稳定写出清晰提示并约束 JSON 等结构化输出后进入下一阶段"),
            ("阶段 2", "RAG / Tool Calling / LangChain Workflow", "掌握检索增强、向量检索、工具调用与 LangChain 基础工作流组织", "框架阅读 + 检索链路拆解 + 小型组件拼装", "能独立完成一个简单 RAG 或工具调用流程后进入下一阶段"),
            ("阶段 3", "Agent / LangGraph / Eval / 落地项目", "学习多步代理、状态编排、评测、可观测性与小型应用落地", "项目题 + 诊断题 + 阶段测试", "能完成端到端小项目并定位常见质量问题后扩展到更复杂系统"),
        ],
        "materials": [
            {
                "id": "llm-langchain-docs",
                "title": "LangChain Documentation",
                "kind": "tutorial",
                "source_name": "LangChain",
                "source_type": "official",
                "url": "https://python.langchain.com/docs/introduction/",
                "use": "学习 prompts、retrievers、chains、tools 与 LangChain 基础工作流搭建",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["llm-app", "langchain", "framework"],
                "downloadable": False,
            },
            {
                "id": "llm-langgraph-docs",
                "title": "LangGraph Documentation",
                "kind": "tutorial",
                "source_name": "LangGraph",
                "source_type": "official",
                "url": "https://langchain-ai.github.io/langgraph/",
                "use": "学习有状态 agent workflow、graph 编排、人机协同与多步流程控制",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["llm-app", "langgraph", "agent"],
                "downloadable": False,
            },
            {
                "id": "llm-anthropic-docs",
                "title": "Anthropic Documentation",
                "kind": "reference",
                "source_name": "Anthropic",
                "source_type": "official",
                "url": "https://docs.anthropic.com/",
                "use": "查 Claude API、messages、tool use、prompting、structured output 与安全实践",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["llm-app", "claude", "api"],
                "downloadable": False,
            },
            {
                "id": "llm-openai-rag-guide",
                "title": "OpenAI Cookbook RAG Examples",
                "kind": "reference",
                "source_name": "OpenAI Cookbook",
                "source_type": "official",
                "url": "https://cookbook.openai.com/",
                "use": "补充 RAG、eval、检索链路与应用工程示例思路",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["llm-app", "rag", "examples"],
                "downloadable": False,
            },
        ],
    },
    "backend": {
        "keywords": ["后端", "backend", "API", "api", "Flask", "Django", "FastAPI", "Spring", "Node.js", "服务端", "微服务"],
        "stages": [
            ("阶段 1", "HTTP / API / 基础服务", "掌握请求响应、路由、状态码与基本服务结构", "接口阅读 + 小型服务练习", "能独立设计简单 CRUD 接口后进入下一阶段"),
            ("阶段 2", "数据持久化与鉴权", "理解数据库连接、鉴权、配置管理与错误处理", "接口题 + 调试题", "能完成一条端到端业务链路后进入下一阶段"),
            ("阶段 3", "部署 / 监控 / 性能", "掌握日志、测试、部署与基础性能优化", "项目题 + 场景诊断", "能完成小型后端服务上线闭环后扩展专题"),
        ],
        "materials": [
            {
                "id": "backend-mdn-http",
                "title": "MDN HTTP Overview",
                "kind": "reference",
                "source_name": "MDN",
                "source_type": "official",
                "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
                "use": "补 HTTP 基础、方法、状态码与缓存认知",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["backend", "http", "reference"],
                "downloadable": False,
            },
            {
                "id": "backend-fastapi-docs",
                "title": "FastAPI Documentation",
                "kind": "tutorial",
                "source_name": "FastAPI",
                "source_type": "official",
                "url": "https://fastapi.tiangolo.com/",
                "use": "学习现代 Python API 开发路径",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["backend", "fastapi", "api"],
                "downloadable": False,
            },
        ],
    },
    "frontend": {
        "keywords": ["前端", "frontend", "React", "react", "Vue", "vue", "Next.js", "next.js", "HTML", "CSS", "JavaScript", "TypeScript", "浏览器"],
        "stages": [
            ("阶段 1", "页面基础与组件认知", "掌握 HTML/CSS/JS 基础与组件化思维", "页面拆解 + 交互练习", "能独立完成基础页面后进入下一阶段"),
            ("阶段 2", "状态管理与数据交互", "理解组件状态、异步请求与表单处理", "组件题 + 调试题", "能完成前后端联调后进入下一阶段"),
            ("阶段 3", "工程化与性能", "掌握构建、路由、性能优化与可维护性", "项目题 + 诊断题", "能完成中小型前端项目闭环后扩展专题"),
        ],
        "materials": [
            {
                "id": "frontend-mdn-web",
                "title": "MDN Web Docs",
                "kind": "reference",
                "source_name": "MDN",
                "source_type": "official",
                "url": "https://developer.mozilla.org/",
                "use": "补浏览器、HTML、CSS、JavaScript 基础与 API 使用",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["frontend", "web", "reference"],
                "downloadable": False,
            },
            {
                "id": "frontend-react-docs",
                "title": "React Documentation",
                "kind": "tutorial",
                "source_name": "React",
                "source_type": "official",
                "url": "https://react.dev/",
                "use": "学习组件、状态、effect 与现代 React 模式",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["frontend", "react", "framework"],
                "downloadable": False,
            },
        ],
    },
    "database": {
        "keywords": ["数据库", "database", "SQL", "sql", "MySQL", "PostgreSQL", "postgres", "Redis", "索引", "事务"],
        "stages": [
            ("阶段 1", "关系模型与基本查询", "掌握表、约束、CRUD 与基本 SQL 查询", "查询练习 + 概念题", "能独立写常见查询后进入下一阶段"),
            ("阶段 2", "索引 / 事务 / 设计", "理解索引、事务隔离与表设计", "SQL 题 + 设计题", "能分析常见慢查询与设计问题后进入下一阶段"),
            ("阶段 3", "优化 / 备份 / 工程实践", "掌握性能、迁移、备份与线上使用注意点", "场景题 + 排障题", "能完成基础数据库运维与优化闭环后扩展专题"),
        ],
        "materials": [
            {
                "id": "database-postgres-docs",
                "title": "PostgreSQL Documentation",
                "kind": "reference",
                "source_name": "PostgreSQL",
                "source_type": "official",
                "url": "https://www.postgresql.org/docs/",
                "use": "查 SQL、索引、事务与数据库管理细节",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["database", "postgres", "reference"],
                "downloadable": False,
            },
            {
                "id": "database-sqlbolt",
                "title": "SQLBolt",
                "kind": "practice",
                "source_name": "SQLBolt",
                "source_type": "community",
                "url": "https://sqlbolt.com/",
                "use": "通过交互式练习快速掌握 SQL 基础",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["database", "sql", "practice"],
                "downloadable": False,
            },
        ],
    },
    "python": {
        "keywords": ["Python", "python", "pandas", "Pandas", "numpy", "NumPy", "数据分析", "pythonic", "Jupyter", "jupyter"],
        "stages": [
            ("阶段 1", "函数 / 文件 / 异常 / 调试", "把会看代码推进到能稳定写、能调通、能拆函数", "小函数题 + 文件读写练习 + try-except 改错 + 顺序脚本函数化", "能独立写出 50~100 行脚本并调通后进入下一阶段"),
            ("阶段 2", "pandas / NumPy 数据分析主线", "掌握读取、清洗、聚合、合并、重塑、时间处理与结果输出", "真实表格清洗 + groupby/merge/pivot 练习 + mini analysis task", "能独立完成一个小型数据分析任务后进入下一阶段"),
            ("阶段 3", "Pythonic 表达与代码质量", "减少笨重写法，学会推导式、生成器、上下文管理器与标准库优先思维", "重构练习 + 普通写法 vs Pythonic 写法对比 + 生成器专题", "能持续改写冗长代码并说明取舍后进入下一阶段"),
            ("阶段 4", "综合项目训练", "围绕数据分析与 AI 应用场景完成可讲解、可复用的小项目", "CSV/Excel 项目 + API 数据处理 + notebook 与 script 组合", "能独立完成 200~500 行量级项目闭环后扩展专题"),
        ],
        "materials": [
            {
                "id": "python-crash-course-3e",
                "title": "Python编程：从入门到实践（第3版）",
                "kind": "book",
                "source_name": "Local / Book",
                "source_type": "local",
                "url": None,
                "use": "阶段 1 主补强：函数、文件、异常、测试与脚本组织。",
                "summary": "偏入门到可独立写脚本，适合把基础语法和工程习惯补稳。",
                "focus_topics": ["函数", "文件读写", "异常处理", "测试", "脚本组织"],
                "recommended_stage": ["阶段 1"],
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["python", "foundation", "functions", "exceptions", "testing"],
                "downloadable": False,
            },
            {
                "id": "python-for-data-analysis",
                "title": "利用Python进行数据分析",
                "kind": "book",
                "source_name": "Local / Book",
                "source_type": "local",
                "url": None,
                "use": "阶段 2 主线材料：pandas / NumPy / 数据清洗 / 聚合 / 重塑 / 时间处理。",
                "summary": "围绕真实数据分析工作流，适合建立 pandas 与 NumPy 的主线实战能力。",
                "focus_topics": ["pandas", "NumPy", "数据清洗", "groupby", "merge", "reshape", "时间序列"],
                "recommended_stage": ["阶段 2", "阶段 4"],
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["python", "data-analysis", "pandas", "numpy"],
                "downloadable": False,
            },
            {
                "id": "fluent-python",
                "title": "流畅的Python",
                "kind": "book",
                "source_name": "Local / Book",
                "source_type": "local",
                "url": None,
                "use": "阶段 3 提升材料：Pythonic 写法、迭代器、生成器、上下文管理器、数据模型。",
                "summary": "适合中后期做写法升级，解决“会做但写得笨重”的问题。",
                "focus_topics": ["Pythonic", "迭代器", "生成器", "上下文管理器", "数据模型"],
                "recommended_stage": ["阶段 3"],
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["python", "advanced", "pythonic", "generators"],
                "downloadable": False,
            },
            {
                "id": "python-official-tutorial",
                "title": "The Python Tutorial",
                "kind": "tutorial",
                "source_name": "Python Docs",
                "source_type": "official",
                "url": "https://docs.python.org/3/tutorial/",
                "use": "补基础语法与官方推荐写法，适合阶段 1 和阶段 3 穿插查阅。",
                "summary": "官方教程，适合核对语言基础与标准表达。",
                "focus_topics": ["语法", "控制流", "函数", "模块", "输入输出"],
                "recommended_stage": ["阶段 1", "阶段 3"],
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["python", "official", "tutorial"],
                "downloadable": False,
            },
            {
                "id": "pandas-user-guide",
                "title": "pandas User Guide",
                "kind": "reference",
                "source_name": "pandas",
                "source_type": "official",
                "url": "https://pandas.pydata.org/docs/user_guide/index.html",
                "use": "按主题补真实 API 用法、数据清洗、分组、合并、时间处理细节。",
                "summary": "官方主题式文档，适合在做题和项目时查 API 细节。",
                "focus_topics": ["IO", "missing data", "groupby", "merge", "reshape", "time series"],
                "recommended_stage": ["阶段 2", "阶段 4"],
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["python", "pandas", "official", "reference"],
                "downloadable": False,
            },
        ],
    },
    "general-cs": {
        "keywords": [],
        "stages": [
            ("阶段 1", "工程基础与通识", "建立命令行、HTTP、JSON、调试、Git 等基础工程认知", "概念题 + 小型实操作业", "能完成基本开发协作任务后进入下一阶段"),
            ("阶段 2", "常见系统组件与数据流", "理解前后端、数据库、部署、日志与测试之间的关系", "模块练习 + 场景题", "能说清一条典型数据流后进入下一阶段"),
            ("阶段 3", "综合项目与问题定位", "围绕真实项目做功能实现、调试与复盘", "综合题 + 阶段测试", "能独立推进一个小型项目闭环后扩展到专题方向"),
        ],
        "materials": [
            {
                "id": "general-cs-mdn-http",
                "title": "MDN HTTP Overview",
                "kind": "reference",
                "source_name": "MDN",
                "source_type": "official",
                "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
                "use": "建立 Web 与接口通信基础认知",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["general-cs", "http", "reference"],
                "downloadable": False,
            },
            {
                "id": "general-cs-missing-semester",
                "title": "The Missing Semester of Your CS Education",
                "kind": "tutorial",
                "source_name": "MIT",
                "source_type": "official",
                "url": "https://missing.csail.mit.edu/",
                "use": "补命令行、自动化、版本控制与工程工具基础",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["general-cs", "tooling", "tutorial"],
                "downloadable": False,
            },
            {
                "id": "general-cs-git-book",
                "title": "Pro Git Book",
                "kind": "reference",
                "source_name": "Pro Git",
                "source_type": "official",
                "url": "https://git-scm.com/book/en/v2",
                "use": "系统学习 Git 工作流与协作基础",
                "cache_status": "metadata-only",
                "local_path": None,
                "tags": ["general-cs", "git", "reference"],
                "downloadable": False,
            },
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or update learn-plan.md for learn-plan workflow")
    parser.add_argument("--topic", required=True, help="学习主题")
    parser.add_argument("--goal", required=True, help="学习目的")
    parser.add_argument("--level", required=True, help="当前水平")
    parser.add_argument("--schedule", default="未指定", help="时间/频率约束")
    parser.add_argument("--preference", default="混合", help="学习偏好：偏题海 / 偏讲解 / 偏测试 / 混合")
    parser.add_argument("--plan-path", default="learn-plan.md", help="学习计划文件路径")
    parser.add_argument("--materials-dir", help="材料缓存目录；默认使用 <plan目录>/materials")
    parser.add_argument("--mode", choices=["auto", "draft", "research-report", "diagnostic", "finalize"], default="auto", help="/learn-plan 当前所处 workflow 阶段；auto 会根据已有输入自动推荐并切换")
    parser.add_argument("--clarification-json", help="顾问式澄清结果 JSON 文件路径")
    parser.add_argument("--research-json", help="deepsearch 决策或研究报告 JSON 文件路径")
    parser.add_argument("--diagnostic-json", help="诊断结果 JSON 文件路径")
    parser.add_argument("--approval-json", help="计划确认结果 JSON 文件路径")
    parser.add_argument("--skip-material-download", action="store_true", help="生成 materials/index.json 后跳过自动下载")
    parser.add_argument("--enable-semantic-review", action="store_true", help="在确定性检查通过后启用 LLM 语义审查（advisory，不硬阻塞）")
    parser.add_argument("--search-context-json", help="research 阶段的 web search 结果 JSON 文件路径")
    parser.add_argument("--confirm-research-review", action="store_true", help="将当前 research report 标记为用户已确认，可继续进入 diagnostic")
    parser.add_argument("--stage-candidate-json", help="由外部 harness/subagent 生成的 stage candidate JSON 文件路径；提供后由 Python 消费并推进 gate")
    parser.add_argument("--stage-review-json", help="由外部 harness/subagent 生成的 semantic review JSON 文件路径；仅补充 semantic_issues / improvement_suggestions")
    parser.add_argument("--planning-candidate-json", help="由外部 harness/subagent 生成的 planning candidate JSON 文件路径；提供后由 Python 消费并推进 gate")
    parser.add_argument("--planning-review-json", help="由外部 harness/subagent 生成的 planning semantic review JSON 文件路径；仅补充 semantic_issues / improvement_suggestions")
    parser.add_argument("--download-timeout", type=int, default=30, help="自动下载材料的超时时间（秒）")
    parser.add_argument("--force-home-root", action="store_true", help="允许学习根目录解析为用户主目录（默认拒绝）")
    parser.add_argument("--stdout-json", action="store_true", help="额外输出 JSON 摘要")
    return parser.parse_args()


def read_text_if_exists(path: Path) -> str:
    return core_read_text_if_exists(path)


def read_json_if_exists(path: Path) -> dict[str, Any]:
    return core_read_json_if_exists(path)



def load_optional_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    return read_json_if_exists(path)


def load_optional_payload(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    payload = read_json_if_exists(path)
    return payload if isinstance(payload, dict) and payload else None


def write_text(path: Path, content: str) -> None:
    core_write_text(path, content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    core_write_json(path, data)


def normalize_preference(value: str) -> str:
    value = (value or "").strip()
    if value in VALID_PREFERENCES:
        return value
    return "混合"


def apply_research_review_confirmation(research: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        return research
    updated = dict(research or {})
    review = updated.get("research_review") if isinstance(updated.get("research_review"), dict) else {}
    updated["research_review"] = {
        **review,
        "status": "confirmed",
        "confirmation_source": "cli-flag",
        "confirmation_note": "用户在当前会话中确认继续下一阶段。",
    }
    return updated


def recommend_workflow_mode(topic: str, goal: str, clarification: dict[str, Any], research: dict[str, Any], diagnostic: dict[str, Any], approval: dict[str, Any], requested_mode: str) -> tuple[str, list[str], str]:
    reasons: list[str] = []
    normalized_goal = f"{topic} {goal}".lower()
    clarification = normalize_clarification_artifact(clarification, diagnostic)
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    assessment_budget = resolve_assessment_budget_preference(clarification, diagnostic)
    max_rounds_preference = assessment_budget.get("max_assessment_rounds_preference")
    questions_per_round_preference = assessment_budget.get("questions_per_round_preference")

    has_open_questions = bool(clarification_state.get("open_questions"))
    preference_pending = bool(preference_state.get("pending_items"))
    assessment_budget_required = max_rounds_preference is None or questions_per_round_preference is None
    needs_research = any(keyword in normalized_goal for keyword in ["工作", "就业", "转岗", "面试", "岗位", "求职", "职业", "大模型", "llm", "agent", "rag"]) \
        or any(keyword in normalized_goal for keyword in ["langchain", "langgraph", "模型应用", "应用开发"])
    level_uncertain = any(keyword in normalized_goal for keyword in ["不确定", "说不清", "不清楚", "不会判断", "不知道自己什么水平"]) \
        or not diagnostic

    if has_open_questions:
        reasons.append("仍存在待澄清问题，应优先补齐顾问式澄清")
        return "draft", reasons, "clarification"
    if preference_pending:
        reasons.append("学习风格与练习方式尚未确认，应先补齐 preference confirmation")
        return "draft", reasons, "clarification"
    if assessment_budget_required:
        reasons.append("起始测评预算尚未确认，应先确认最多几轮测试与每轮几题，再进入诊断")
        return "draft", reasons, "clarification"

    if needs_research and not research and level_uncertain:
        reasons.append("目标带有明显职业导向，且当前水平不稳定，应先研究再诊断")
        return "research-report", reasons, "research"
    if needs_research and not research:
        reasons.append("目标带有明显职业导向，应优先确认外部能力标准与材料取舍")
        return "research-report", reasons, "research"
    if level_uncertain and not diagnostic:
        reasons.append(f"当前水平仍不可靠，应优先发起最多 {max_rounds_preference} 轮、每轮 {questions_per_round_preference} 题的起始测试网页 session")
        return "diagnostic", reasons, "diagnostic"

    if requested_mode == "finalize" and not approval_state.get("ready_for_execution"):
        reasons.append("当前未满足 ready_for_execution，finalize 仍会被 gate 拦住")
        return "draft", reasons, "approval"
    if approval_state.get("ready_for_execution"):
        return "finalize", reasons, "ready"
    return (requested_mode if requested_mode != "auto" else "draft"), reasons, "approval"



def sanitize_filename(name: str) -> str:
    return core_sanitize_filename(name)


def detect_topic_family(topic: str) -> str:
    return core_detect_topic_family_from_configs(topic, TOPIC_FAMILIES)


def infer_domain(topic: str) -> str:
    return core_infer_domain_from_configs(topic, TOPIC_FAMILIES)


FAMILY_STAGE_DETAILS: dict[str, list[dict[str, Any]]] = {
    "english": [
        {
            "reading": ["Cambridge Dictionary：高频词与例句", "Grammarly Handbook：基础语法", "Purdue OWL：基础写作规则"],
            "exercise_types": ["词汇卡片复习", "语法辨析题", "基础句子改写"],
            "future_use": "建立读技术文档、写基础英文表达的底层能力。",
        },
        {
            "reading": ["VOA Learning English：短文与听力", "Purdue OWL：句子结构", "Grammarly Handbook：易错语法专题"],
            "exercise_types": ["短阅读", "句子重写", "段落理解题"],
            "future_use": "支撑技术资料阅读、英文说明理解与基础写作。",
        },
        {
            "reading": ["Purdue OWL：写作结构", "VOA Learning English：综合输入", "Cambridge Dictionary：搭配与例句"],
            "exercise_types": ["短写作", "翻译", "综合测试"],
            "future_use": "让输入能力过渡到稳定输出与综合应用。",
        },
    ],
    "math": [
        {
            "reading": ["Khan Academy Math：基础概念", "Paul's Online Math Notes：公式与例题", "OpenStax：基础章节"],
            "exercise_types": ["概念判断题", "基础计算题", "公式代入题"],
            "future_use": "为后续算法、概率、线代与数据分析打稳数学底座。",
        },
        {
            "reading": ["Paul's Online Math Notes：专题例题", "OpenStax：典型题型章节", "3Blue1Brown：直观理解视频"],
            "exercise_types": ["专题练习", "解题步骤拆解", "错题回做"],
            "future_use": "把定义和公式转成可重复的解题路径。",
        },
        {
            "reading": ["OpenStax：综合章节", "Khan Academy：阶段测验", "3Blue1Brown：概念回看"],
            "exercise_types": ["综合题", "阶段测试", "知识点串联题"],
            "future_use": "支撑更复杂建模、算法分析与工程问题抽象。",
        },
    ],
    "algorithm": [
        {
            "reading": ["OI Wiki：数组/哈希/复杂度", "LeetCode Study Plan：基础部分", "VisuAlgo：数组与查找可视化"],
            "exercise_types": ["easy 函数题", "复杂度辨析题", "基础数据结构题"],
            "future_use": "建立题感与高频基础套路。",
        },
        {
            "reading": ["OI Wiki：双指针/滑窗/二分", "NeetCode Roadmap：对应题型", "VisuAlgo：搜索过程可视化"],
            "exercise_types": ["同类题对比", "模板改写", "专题刷题"],
            "future_use": "把常见线性和查找技巧练成熟练套路。",
        },
        {
            "reading": ["OI Wiki：栈/图遍历", "LeetCode Study Plan：进阶专题", "NeetCode Roadmap：综合模块"],
            "exercise_types": ["medium 题", "阶段测试", "套路归纳"],
            "future_use": "支撑面试、竞赛基础与更复杂问题拆解。",
        },
    ],
    "linux": [
        {
            "reading": ["Missing Semester：Shell 与命令行", "tldr pages：高频命令示例", "GNU Bash Manual：基础语法"],
            "exercise_types": ["命令抄练", "文件系统操作", "文本查看小任务"],
            "future_use": "支撑日常开发环境操作与基础自动化。",
        },
        {
            "reading": ["Ubuntu Server Guide：用户/权限/进程", "GNU Bash Manual：变量与脚本", "tldr pages：权限和进程命令"],
            "exercise_types": ["权限辨析题", "进程管理练习", "环境变量配置题"],
            "future_use": "支持定位常见环境、权限和进程问题。",
        },
        {
            "reading": ["Ubuntu Server Guide：网络与服务", "Missing Semester：自动化与排障思路", "tldr pages：网络与日志命令"],
            "exercise_types": ["日志分析", "网络排障题", "服务管理场景题"],
            "future_use": "支撑服务器运维、部署和基础故障排查。",
        },
    ],
    "llm-app": [
        {
            "reading": ["Anthropic Documentation：messages/tool use", "LangChain Docs：prompts/output parsers", "提示工程基础资料"],
            "exercise_types": ["prompt 改写", "结构化输出练习", "小型 API 调用实验"],
            "future_use": "建立稳定调用模型与约束输出的能力。",
        },
        {
            "reading": ["LangChain Docs：retrievers/tools", "Anthropic Documentation：tool use", "RAG 示例资料"],
            "exercise_types": ["链路拆解", "检索实验", "tools 组合练习"],
            "future_use": "支撑 RAG、工具调用与应用工作流搭建。",
        },
        {
            "reading": ["LangGraph Docs：stateful workflow", "Anthropic Documentation：评测与安全实践", "应用案例"],
            "exercise_types": ["agent workflow 小项目", "eval 设计", "诊断题"],
            "future_use": "支撑 Agent、编排、评测与真实应用落地。",
        },
    ],
    "backend": [
        {
            "reading": ["MDN HTTP Overview", "FastAPI Documentation：路由/请求响应", "接口设计基础资料"],
            "exercise_types": ["接口阅读", "CRUD 小服务", "状态码辨析题"],
            "future_use": "建立服务端请求-响应与 API 设计基础。",
        },
        {
            "reading": ["FastAPI Documentation：依赖/鉴权", "数据库基础资料", "配置与错误处理专题"],
            "exercise_types": ["鉴权流程题", "数据持久化练习", "调试题"],
            "future_use": "支撑端到端业务链路实现与问题定位。",
        },
        {
            "reading": ["部署与日志监控资料", "FastAPI Documentation：部署", "性能优化基础资料"],
            "exercise_types": ["服务化 mini project", "日志排障", "阶段测试"],
            "future_use": "支撑小型后端服务上线、观测与优化。",
        },
    ],
    "frontend": [
        {
            "reading": ["MDN Web Docs：HTML/CSS/JS", "React Documentation：组件基础", "浏览器基础资料"],
            "exercise_types": ["页面拆解", "基础交互练习", "组件改写"],
            "future_use": "建立页面结构、样式与基础交互能力。",
        },
        {
            "reading": ["React Documentation：state/effects", "MDN：Fetch/Form", "前后端交互资料"],
            "exercise_types": ["表单与状态练习", "异步请求题", "调试题"],
            "future_use": "支撑真实页面的数据驱动交互与联调。",
        },
        {
            "reading": ["工程化与路由资料", "React Documentation：性能优化", "构建工具基础资料"],
            "exercise_types": ["组件重构", "项目题", "性能诊断题"],
            "future_use": "支撑中小型前端项目维护与优化。",
        },
    ],
    "database": [
        {
            "reading": ["PostgreSQL Documentation：SQL 基础", "SQLBolt：查询入门", "关系模型基础资料"],
            "exercise_types": ["CRUD 查询题", "建表理解题", "基础 SQL 练习"],
            "future_use": "建立数据表、查询与关系模型基础。",
        },
        {
            "reading": ["PostgreSQL Documentation：索引/事务", "SQL 设计专题", "慢查询基础资料"],
            "exercise_types": ["索引辨析题", "事务场景题", "表设计练习"],
            "future_use": "支撑数据库设计、事务理解与性能分析。",
        },
        {
            "reading": ["PostgreSQL Documentation：备份/运维", "数据库迁移与优化资料", "故障排查专题"],
            "exercise_types": ["优化题", "排障题", "阶段测试"],
            "future_use": "支撑线上数据库维护与性能治理。",
        },
    ],
    "python": [
        {
            "reading": ["《Python编程：从入门到实践（第3版）》：函数/文件/异常", "The Python Tutorial：函数/模块/输入输出", "基础调试资料"],
            "exercise_types": ["小函数题", "文件读写练习", "try-except 改错", "脚本函数化"],
            "future_use": "支撑后续数据分析、API 调用与 AI 数据预处理。",
        },
        {
            "reading": ["《利用Python进行数据分析》：NumPy/pandas", "pandas User Guide：groupby/merge/reshape", "NumPy User Guide"],
            "exercise_types": ["真实表格清洗", "groupby/merge 练习", "mini analysis task"],
            "future_use": "支撑数据分析、报表统计与结构化数据处理。",
        },
        {
            "reading": ["《流畅的Python》：生成器/上下文管理器/数据模型", "Python 官方文档：标准库", "重构对照案例"],
            "exercise_types": ["代码重写", "普通写法 vs Pythonic", "生成器专题"],
            "future_use": "让代码更简洁、稳定、可维护。",
        },
        {
            "reading": ["回看《利用Python进行数据分析》相关章节", "回看《流畅的Python》相关专题", "按项目查官方文档"],
            "exercise_types": ["CSV/Excel 项目", "API 数据处理项目", "AI 预处理工具"],
            "future_use": "把零散知识转成项目与作品。",
        },
    ],
    "general-cs": [
        {
            "reading": ["Missing Semester：工具与命令行", "MDN HTTP Overview", "Pro Git Book：基础工作流"],
            "exercise_types": ["基础概念题", "工具使用练习", "小型工程任务"],
            "future_use": "建立开发协作所需的通用工程基础。",
        },
        {
            "reading": ["系统组件与数据流基础资料", "MDN HTTP Overview：请求链路", "Pro Git Book：协作流程"],
            "exercise_types": ["模块练习", "场景题", "数据流分析"],
            "future_use": "能说清常见系统组件如何协同工作。",
        },
        {
            "reading": ["综合项目案例", "排障与调试资料", "版本协作与发布资料"],
            "exercise_types": ["综合题", "阶段测试", "小项目复盘"],
            "future_use": "支撑独立推进小型工程任务。",
        },
    ],
}


FAMILY_DAILY_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "english": [
        {"day": "Day 1：词汇与基础语法", "当前阶段": "阶段 1", "今日主题": "高频词、词性、基础句型", "复习点": "已记单词；be 动词；一般现在时", "新学习点": "词根词缀；主谓一致；基础句子改写", "练习重点": "词汇卡片 + 语法辨析 + 3 句改写", "推荐材料": "Cambridge Dictionary；Grammarly Handbook", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：短文阅读", "当前阶段": "阶段 2", "今日主题": "句子理解与短文信息提取", "复习点": "时态；从句基础", "新学习点": "连接词；段落主旨；关键信息定位", "练习重点": "1 篇短阅读 + 句子重写 + 生词整理", "推荐材料": "VOA Learning English；Purdue OWL", "难度目标": "concept medium，code easy"},
        {"day": "Day 3：输出与复盘", "当前阶段": "阶段 3", "今日主题": "短写作与翻译", "复习点": "前两天生词和语法", "新学习点": "段落组织；常见表达替换", "练习重点": "1 段短写作 + 1 题翻译 + 自查", "推荐材料": "Purdue OWL；Cambridge Dictionary", "难度目标": "concept medium/hard，code medium"},
    ],
    "math": [
        {"day": "Day 1：概念与公式", "当前阶段": "阶段 1", "今日主题": "定义、符号、核心公式", "复习点": "旧公式；基本运算", "新学习点": "新定义；公式适用条件", "练习重点": "基础计算题 + 概念辨析题", "推荐材料": "Khan Academy Math；Paul's Online Math Notes", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：题型拆解", "当前阶段": "阶段 2", "今日主题": "典型题型步骤", "复习点": "概念与公式", "新学习点": "解题步骤；常见陷阱", "练习重点": "专题题 + 错题回做", "推荐材料": "OpenStax；Paul's Online Math Notes", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：综合应用", "当前阶段": "阶段 3", "今日主题": "综合题与阶段小测", "复习点": "高频错题", "新学习点": "知识点串联", "练习重点": "综合题 + 阶段测试", "推荐材料": "OpenStax；Khan Academy Math", "难度目标": "concept medium/hard，code medium"},
    ],
    "algorithm": [
        {"day": "Day 1：数组与哈希", "当前阶段": "阶段 1", "今日主题": "复杂度、数组、哈希表", "复习点": "for 循环；查找；去重", "新学习点": "Big-O；哈希思维；常见题型", "练习重点": "2~3 道 easy 题 + 复杂度辨析", "推荐材料": "OI Wiki；LeetCode Study Plan", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：双指针与二分", "当前阶段": "阶段 2", "今日主题": "双指针、滑窗、二分", "复习点": "数组基础", "新学习点": "收缩/扩张窗口；有序数组查找", "练习重点": "同类题对比 + 3 道专题题", "推荐材料": "NeetCode Roadmap；OI Wiki", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：DFS/BFS 与复盘", "当前阶段": "阶段 3", "今日主题": "图遍历与综合测试", "复习点": "双指针；二分", "新学习点": "DFS/BFS 模板；层序思维", "练习重点": "2 道 medium 题 + 1 次阶段小测", "推荐材料": "OI Wiki；VisuAlgo", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "linux": [
        {"day": "Day 1：文件系统与高频命令", "当前阶段": "阶段 1", "今日主题": "路径、ls/cd/cp/mv/rm/cat/less", "复习点": "终端基本操作", "新学习点": "绝对路径与相对路径；文本查看", "练习重点": "命令抄练 + 文件操作小任务", "推荐材料": "The Missing Semester；tldr pages", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：权限与进程", "当前阶段": "阶段 2", "今日主题": "chmod/chown/ps/top/kill", "复习点": "文件操作", "新学习点": "权限位；用户组；前后台进程", "练习重点": "权限辨析 + 进程管理练习", "推荐材料": "Ubuntu Server Guide；GNU Bash Manual", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：日志与网络排障", "当前阶段": "阶段 3", "今日主题": "grep/journalctl/ss/curl/systemctl", "复习点": "进程与权限", "新学习点": "日志定位；端口占用；服务状态", "练习重点": "故障排查场景题 + 命令诊断", "推荐材料": "Ubuntu Server Guide；tldr pages", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "llm-app": [
        {"day": "Day 1：Prompt 与结构化输出", "当前阶段": "阶段 1", "今日主题": "消息结构、prompt 拆解、JSON 约束", "复习点": "模型输入输出基础", "新学习点": "系统提示；few-shot；结构化输出", "练习重点": "prompt 改写 + JSON 输出实验", "推荐材料": "Anthropic Documentation；LangChain Documentation", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：RAG 与 Tools", "当前阶段": "阶段 2", "今日主题": "retriever、tool calling、链路拼装", "复习点": "prompt 基础", "新学习点": "检索增强；工具路由；上下文注入", "练习重点": "1 条 RAG 链路拆解 + 1 个 tools 示例", "推荐材料": "LangChain Documentation；Anthropic Documentation", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：Agent Workflow", "当前阶段": "阶段 3", "今日主题": "多步代理与评测", "复习点": "RAG 与 tool use", "新学习点": "stateful workflow；eval；观测", "练习重点": "agent mini project + 诊断题", "推荐材料": "LangGraph Documentation；Anthropic Documentation", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "backend": [
        {"day": "Day 1：HTTP 与路由", "当前阶段": "阶段 1", "今日主题": "请求响应、方法、状态码、路由", "复习点": "JSON；客户端与服务端角色", "新学习点": "REST 风格；路径参数；响应结构", "练习重点": "接口阅读 + 1 个 CRUD 小服务", "推荐材料": "MDN HTTP Overview；FastAPI Documentation", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：数据库与鉴权", "当前阶段": "阶段 2", "今日主题": "持久化、鉴权、错误处理", "复习点": "路由与请求", "新学习点": "数据库连接；token/session；异常处理", "练习重点": "端到端接口练习 + 调试题", "推荐材料": "FastAPI Documentation；数据库基础资料", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：部署与排障", "当前阶段": "阶段 3", "今日主题": "日志、测试、部署、性能", "复习点": "数据库与鉴权", "新学习点": "部署入口；日志定位；基础优化", "练习重点": "服务化 mini project + 排障题", "推荐材料": "FastAPI Documentation；部署资料", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "frontend": [
        {"day": "Day 1：页面结构与样式", "当前阶段": "阶段 1", "今日主题": "HTML/CSS/基础 JS", "复习点": "浏览器基础", "新学习点": "语义标签；布局；基础交互", "练习重点": "页面拆解 + 样式练习", "推荐材料": "MDN Web Docs；React Documentation", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：状态与数据交互", "当前阶段": "阶段 2", "今日主题": "状态管理、表单、异步请求", "复习点": "组件基础", "新学习点": "state/effect；fetch；表单处理", "练习重点": "组件题 + 请求联调练习", "推荐材料": "React Documentation；MDN Web Docs", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：工程化与优化", "当前阶段": "阶段 3", "今日主题": "路由、构建、性能与维护", "复习点": "状态与请求", "新学习点": "代码拆分；性能分析；可维护性", "练习重点": "项目题 + 性能诊断题", "推荐材料": "React Documentation；工程化资料", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "database": [
        {"day": "Day 1：SQL 基础查询", "当前阶段": "阶段 1", "今日主题": "SELECT/WHERE/ORDER BY/JOIN 基础", "复习点": "表与字段概念", "新学习点": "条件过滤；多表关联", "练习重点": "基础 SQL 题 + 结果分析", "推荐材料": "SQLBolt；PostgreSQL Documentation", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：索引与事务", "当前阶段": "阶段 2", "今日主题": "索引、隔离级别、表设计", "复习点": "基础查询", "新学习点": "索引命中；事务边界；范式", "练习重点": "设计题 + 事务场景题", "推荐材料": "PostgreSQL Documentation", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：优化与排障", "当前阶段": "阶段 3", "今日主题": "慢查询、备份、迁移", "复习点": "索引与事务", "新学习点": "执行计划；备份恢复；上线注意点", "练习重点": "优化题 + 排障题 + 小测", "推荐材料": "PostgreSQL Documentation", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "python": [
        {"day": "Day 1：函数与返回值稳定", "当前阶段": "阶段 1", "今日主题": "函数参数、返回值、列表推导式回顾", "复习点": "列表推导式；函数返回多个值；字符串大小写敏感判断", "新学习点": "默认参数；位置参数与关键字参数；把重复逻辑封装成函数", "练习重点": "3 道函数题 + 1 道列表处理题", "推荐材料": "Python编程：从入门到实践（第3版）；The Python Tutorial", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：文件读写基础", "当前阶段": "阶段 1", "今日主题": "pathlib.Path 文本读写、异常与 JSON", "复习点": "路径字符串与 Path 对象；基础异常类型；字典/列表与 JSON 的关系", "新学习点": "Path.read_text()；Path.write_text()；try-except；json.dumps()；json.loads()", "练习重点": "Path 读写文本 + 文件/JSON 异常处理 + JSON 序列化/反序列化", "推荐材料": "Python编程：从入门到实践（第3版）第 10 章", "难度目标": "concept easy/medium，code easy/medium"},
        {"day": "Day 3：异常处理与调试", "当前阶段": "阶段 1", "今日主题": "traceback 阅读、常见异常类型、try-except 基本模式", "复习点": "NameError / TypeError / ValueError 的区别", "新学习点": "try-except-else-finally；基于报错定位行号与变量值", "练习重点": "2 道异常辨析题 + 1 道改错题 + 1 道调试题", "推荐材料": "Python编程：从入门到实践（第3版）", "难度目标": "concept medium，code easy/medium"},
        {"day": "Day 4：脚本函数化拆分", "当前阶段": "阶段 1", "今日主题": "主流程 + 函数拆分", "复习点": "函数返回值；文件读写；异常处理", "新学习点": "main() 组织；职责拆分；输入处理与结果输出分离", "练习重点": "把一段顺序脚本改成主流程 + 2~4 个函数", "推荐材料": "Python编程：从入门到实践（第3版）", "难度目标": "concept medium，code medium/project"},
        {"day": "Day 5：pandas 入门读取与筛选", "当前阶段": "阶段 2", "今日主题": "Series / DataFrame、读取 CSV、列选择与行筛选", "复习点": "字典 / 列表 / 布尔表达式", "新学习点": "read_csv；列选择；条件筛选；布尔掩码", "练习重点": "1 组筛选题 + 1 组列处理题 + 1 个 mini data task", "推荐材料": "利用Python进行数据分析；pandas User Guide", "难度目标": "concept easy/medium，code easy/medium"},
        {"day": "Day 6：groupby / merge / pivot", "当前阶段": "阶段 2", "今日主题": "聚合、合并、重塑", "复习点": "筛选与列处理", "新学习点": "groupby-agg；merge；pivot_table", "练习重点": "2 道 groupby 题 + 1 道 merge 题 + 1 道重塑题", "推荐材料": "利用Python进行数据分析；pandas User Guide", "难度目标": "concept medium，code medium"},
        {"day": "Day 7：时间列处理与阶段复盘", "当前阶段": "阶段 2", "今日主题": "日期解析、时间筛选、按时间聚合", "复习点": "groupby / merge / 缺失值处理", "新学习点": "to_datetime；dt 访问器；按日/周/月统计", "练习重点": "1 个日志或销售时间序列 mini task + 1 次阶段小测", "推荐材料": "利用Python进行数据分析；pandas User Guide", "难度目标": "concept medium/hard，code medium/project"},
    ],
    "general-cs": [
        {"day": "Day 1：工程基础", "当前阶段": "阶段 1", "今日主题": "命令行、HTTP、Git 基础", "复习点": "开发环境与文件结构", "新学习点": "请求响应；Git 基础命令；JSON", "练习重点": "小型工程任务 + 概念题", "推荐材料": "The Missing Semester；MDN HTTP Overview；Pro Git Book", "难度目标": "concept easy/medium，code easy"},
        {"day": "Day 2：系统组件与数据流", "当前阶段": "阶段 2", "今日主题": "前后端、数据库、日志、部署关系", "复习点": "HTTP 与 Git", "新学习点": "一条数据流的组件拆解", "练习重点": "模块练习 + 场景题", "推荐材料": "MDN HTTP Overview；Pro Git Book", "难度目标": "concept medium，code medium"},
        {"day": "Day 3：综合任务与排障", "当前阶段": "阶段 3", "今日主题": "综合项目与问题定位", "复习点": "组件关系与数据流", "新学习点": "调试闭环；协作交付", "练习重点": "综合题 + 小项目复盘", "推荐材料": "The Missing Semester；Pro Git Book", "难度目标": "concept medium/hard，code medium/project"},
    ],
}


def build_curriculum(topic: str, level: str, preference: str) -> dict[str, Any]:
    return planning_build_curriculum(
        topic,
        level,
        preference,
        family_configs=TOPIC_FAMILIES,
        stage_details=FAMILY_STAGE_DETAILS,
        daily_templates=FAMILY_DAILY_TEMPLATES,
    )



def render_stage_overview(curriculum: dict[str, Any], planning: dict[str, Any] | None = None) -> str:
    return planning_render_stage_overview(curriculum, planning)



def render_learning_route(curriculum: dict[str, Any], planning: dict[str, Any] | None = None) -> str:
    return planning_render_learning_route(curriculum, planning)



def render_daily_roadmap(curriculum: dict[str, Any]) -> str:
    return planning_render_daily_roadmap(curriculum)



def render_materials_section(curriculum: dict[str, Any], materials_dir: Path, materials_index: Path, material_curation: dict[str, Any] | None = None) -> str:
    return planning_render_materials_section(
        curriculum,
        materials_dir,
        materials_index,
        family_configs=TOPIC_FAMILIES,
        material_curation=material_curation,
    )



def infer_material_recommended_day(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[str]:
    return materials_infer_material_recommended_day(entry, curriculum)



def enrich_material_entry(entry: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    return materials_enrich_material_entry(entry, curriculum)


def build_planning_profile(topic: str, goal: str, level: str, schedule: str, preference: str, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, planning: dict[str, Any] | None = None, learner_model: dict[str, Any] | None = None, curriculum_patch_queue: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, Any]:
    return planning_build_planning_profile(
        topic,
        goal,
        level,
        schedule,
        preference,
        family_configs=TOPIC_FAMILIES,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=planning,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        mode=mode,
    )



def render_planning_profile(profile: dict[str, Any]) -> str:
    return planning_render_planning_profile(profile)



def build_plan_candidate(profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    return planning_build_plan_candidate(profile, curriculum)



def render_planning_constraints(profile: dict[str, Any]) -> str:
    return planning_render_planning_constraints(profile)



def build_plan_report(profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    return planning_build_plan_report(profile, curriculum)



def render_plan_report(report: dict[str, Any]) -> str:
    return planning_render_plan_report(report)



def render_mastery_checks(curriculum: dict[str, Any]) -> str:
    return planning_render_mastery_checks(curriculum)



def render_today_generation_rules(curriculum: dict[str, Any]) -> str:
    return planning_render_today_generation_rules(curriculum)



def resolve_stage_mode(mode: str, workflow_state: dict[str, Any] | None = None) -> str | None:
    blocking_stage = str((workflow_state or {}).get("blocking_stage") or "").strip().lower()
    if blocking_stage in {"clarification", "research", "diagnostic", "approval"}:
        return blocking_stage
    normalized_mode = str(mode or "").strip().lower()
    mapping = {
        "draft": "clarification",
        "research-report": "research",
        "diagnostic": "diagnostic",
    }
    return mapping.get(normalized_mode)



def _value_is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, set, tuple)):
        return bool(value)
    return True


def _normalized_merge_list(values: Any) -> list[Any]:
    items = values if isinstance(values, list) else []
    normalized: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _merge_candidate_value(existing: Any, generated: Any, key: str | None = None) -> Any:
    if isinstance(existing, dict) and isinstance(generated, dict):
        merged = dict(existing)
        for child_key, child_value in generated.items():
            previous = merged.get(child_key)
            merged[child_key] = _merge_candidate_value(previous, child_value, child_key)
        return merged
    if isinstance(existing, list) and isinstance(generated, list):
        if key in {"resolved_items", "accepted_tradeoffs", "approved_patch_ids", "rejected_patch_ids"}:
            return _normalized_merge_list([*existing, *generated])
        if key in {"open_questions", "pending_items"}:
            return _normalized_merge_list(generated)
        if key in {"issues", "warnings", "semantic_issues", "improvement_suggestions"}:
            return _normalized_merge_list(generated)
        if key in {"success_criteria", "constraints", "non_goals", "confirmed", "items"}:
            return _normalized_merge_list(generated or existing)
        return generated if generated else existing
    if _value_is_meaningful(generated):
        return generated
    return existing


def _merge_consultation_state(existing: Any, generated: Any) -> Any:
    if not isinstance(existing, dict) or not isinstance(generated, dict):
        return _merge_candidate_value(existing, generated, "consultation_state")
    merged = {**existing, **generated}
    existing_topics = {
        str(item.get("id") or "").strip(): dict(item)
        for item in existing.get("topics") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    generated_topics = {
        str(item.get("id") or "").strip(): dict(item)
        for item in generated.get("topics") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    topic_ids = list(dict.fromkeys([*existing_topics.keys(), *generated_topics.keys()]))
    merged["topics"] = [
        _merge_candidate_value(existing_topics.get(topic_id), generated_topics.get(topic_id), "consultation_topic")
        for topic_id in topic_ids
    ]
    existing_thread = [item for item in existing.get("thread") or [] if isinstance(item, dict)]
    generated_thread = [item for item in generated.get("thread") or [] if isinstance(item, dict)]
    seen: set[str] = set()
    thread: list[dict[str, Any]] = []
    for item in [*existing_thread, *generated_thread]:
        key = str(item.get("turn_id") or item.get("id") or item.get("question") or item).strip()
        if key in seen:
            continue
        seen.add(key)
        thread.append(item)
    merged["thread"] = thread
    for list_key in ("open_questions", "assumptions"):
        values = []
        seen_values: set[str] = set()
        for item in [*(existing.get(list_key) or []), *(generated.get(list_key) or [])]:
            key = str(item.get("question") if isinstance(item, dict) else item).strip().lower()
            if not key or key in seen_values:
                continue
            seen_values.add(key)
            values.append(item)
        merged[list_key] = values
    return merged


def merge_workflow_candidate(existing: dict[str, Any] | None, generated: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(generated, dict) or not generated:
        return dict(existing or {})
    merged = dict(existing or {})
    if "candidate_error" in merged and "candidate_error" not in generated:
        merged.pop("candidate_error", None)

    existing_approval_state = merged.get("approval_state") if isinstance(merged.get("approval_state"), dict) else {}
    generated_approval_state = generated.get("approval_state") if isinstance(generated.get("approval_state"), dict) else {}
    preserve_ready_approval = bool(existing_approval_state.get("ready_for_execution")) and not bool(generated_approval_state.get("ready_for_execution"))
    deep_merge_keys = {
        "questionnaire",
        "clarification_state",
        "preference_state",
        "user_model",
        "goal_model",
        "schedule",
        "approval_state",
    }

    for key, value in generated.items():
        if preserve_ready_approval and key == "approval_state":
            continue
        if key == "consultation_state":
            merged[key] = _merge_consultation_state(merged.get(key), value)
            continue
        if key in deep_merge_keys and isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_candidate_value(merged.get(key), value, key)
        else:
            merged[key] = _merge_candidate_value(merged.get(key), value, key)
    return merged



def build_research_fallback_candidate(
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    clarification: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clarification = clarification or {}
    diagnostic = diagnostic or {}
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    success_criteria = normalize_string_list(questionnaire.get("success_criteria") or [])
    budget = resolve_assessment_budget_preference(clarification, diagnostic)
    max_rounds = budget.get("max_assessment_rounds_preference") or 2
    questions_per_round = budget.get("questions_per_round_preference") or 8
    target_band = "3-4 个月内达到中国大陆一线城市数据科学 / 大模型应用开发岗位的 Python 面试可通过到较从容应对区间"
    must_master_core = [
        "Python 核心语法、常用数据结构与函数式组织能力",
        "文件处理、异常处理、调试定位与标准库使用能力",
        "NumPy / pandas 基础数据处理与结果解释能力",
        "常见 Python 面试题手写、复杂度表达与边界说明能力",
        "面向数据任务或 LLM 应用脚本的小型代码实现与讲解能力",
    ]
    evidence_expectations = [
        "能在限时下独立写出常见 Python 基础题并解释关键边界",
        "能完成基础数据读写、清洗、筛选、聚合与简单统计分析",
        "能说明常见题目的复杂度、调试路径与实现取舍",
        "能读懂并实现一个数据处理或 LLM API 调用的小脚本片段",
    ]
    research_brief = "该目标不是泛学 Python，而是面向数据科学与大模型应用开发岗位，在 3-4 个月窗口内优先补齐高频面试 Python 能力、数据处理基本功，以及可迁移到 AI 应用脚本的编码表达能力。"
    capability_metrics = [
        {
            "id": "python-core-coding",
            "name": "Python 核心编码与表达",
            "layer": "mainline",
            "target_level": "能稳定完成高频 Python 基础题并解释实现取舍",
            "observable_behaviors": [
                "独立完成字符串、列表、字典、集合、函数封装等常见手写题",
                "能解释边界条件、常见坑和时间空间复杂度",
            ],
            "quantitative_indicators": [
                {
                    "metric": "基础题完成度",
                    "threshold": "常见 Python 基础题达到可独立完成并能口头解释",
                    "measurement_method": "起始测评 + 后续阶段测试",
                }
            ],
            "diagnostic_methods": ["小代码题", "口头解释", "复杂度追问"],
            "learning_evidence": [
                "基础题手写结果",
                "函数封装与调试说明",
            ],
            "source_evidence": [
                "目标岗位明确包含 Python 面试与后续数据/LLM 应用支撑需求",
                "用户 success criteria 包含手写题、数据处理、项目讲解与追问应对",
            ],
            "material_implications": ["前期主线需优先覆盖语法、数据结构、函数、异常、文件与调试"],
            "priority": "must",
        },
        {
            "id": "python-data-processing",
            "name": "Python 数据处理基础",
            "layer": "mainline",
            "target_level": "能完成基础数据任务并解释处理结果",
            "observable_behaviors": [
                "使用 pandas / NumPy 完成读写、清洗、筛选、聚合、缺失值处理",
                "能对结果做基本解释并输出结构化结论",
            ],
            "quantitative_indicators": [
                {
                    "metric": "数据任务闭环",
                    "threshold": "基础表格数据处理任务可独立完成",
                    "measurement_method": "场景题 + 小型数据任务",
                }
            ],
            "diagnostic_methods": ["数据处理小题", "代码阅读", "结果解释"],
            "learning_evidence": ["pandas / NumPy 小任务", "数据清洗练习"],
            "source_evidence": [
                "目标岗位包含数据科学方向",
                "用户 success criteria 明确要求 pandas / NumPy 基础处理能力",
            ],
            "material_implications": ["研究与课程主线需包含 NumPy / pandas 基础场景"],
            "priority": "must",
        },
        {
            "id": "python-llm-script",
            "name": "Python 场景化脚本与 LLM 应用基础",
            "layer": "supporting",
            "target_level": "能读懂并实现简单 AI 应用脚本片段",
            "observable_behaviors": [
                "能组织简单模块、函数与配置调用模型/API",
                "能解释脚本结构、输入输出与异常处理",
            ],
            "quantitative_indicators": [
                {
                    "metric": "脚本实现能力",
                    "threshold": "能完成简单 API 调用或文本处理脚本",
                    "measurement_method": "脚本题 + 项目讲解",
                }
            ],
            "diagnostic_methods": ["脚本阅读", "小实现题", "场景追问"],
            "learning_evidence": ["LLM API 调用小脚本", "文本处理或批处理脚本"],
            "source_evidence": [
                "目标岗位包含大模型应用开发方向",
                "用户 success criteria 明确要求能完成并讲清 1 个小型数据或 LLM 应用项目",
            ],
            "material_implications": ["后续应加入 API 调用、脚本组织与工程习惯的训练"],
            "priority": "should",
        },
    ]
    evidence_summary = [
        f"目标岗位：{goal}",
        f"当前水平：{level}",
        f"学习节奏：{schedule}",
        f"学习偏好：{preference}",
        *(success_criteria[:4] if success_criteria else []),
    ]
    selection_rationale = [
        "先聚焦 Python 高频面试能力与数据处理基本功，而不是泛化覆盖整个 Python 生态。",
        "数据科学方向要求尽早具备 pandas / NumPy 的基础读写与清洗能力。",
        "大模型应用开发方向要求具备脚本组织、API 调用、异常处理与代码讲解能力。",
        "由于学习时间按 30 分钟颗粒度推进，后续 diagnostic 应优先识别最影响求职效率的短板。",
    ]
    target_capability_ids = [item["id"] for item in capability_metrics]
    diagnostic_scope = {
        "target_goal_band": target_band,
        "target_capability_ids": target_capability_ids,
        "target_capabilities": [item["name"] for item in capability_metrics],
        "scope_rationale": [
            "先测 Python 核心编码与表达，因为它决定面试手写与追问稳定性。",
            "再测数据处理基础，因为数据科学岗位和多数实际 Python 面试都会覆盖此类任务。",
            "补测简单脚本 / API 场景，判断能否顺利迁移到 LLM 应用开发方向。",
        ],
        "evidence_expectations": evidence_expectations,
        "scoring_dimensions": [
            "正确性与边界意识",
            "代码组织与可读性",
            "数据处理熟练度",
            "复杂度与讲解表达",
        ],
        "gap_judgement_basis": [
            "能否在限时下稳定完成基础题",
            "能否完成基础数据处理任务",
            "能否解释脚本结构、调试路径与设计取舍",
        ],
        "non_priority_items": [
            "暂不优先考察完整 Web 框架或底层解释器原理",
            "暂不优先考察与目标岗位弱相关的生态细节",
        ],
    }
    traceability = [
        build_traceability_entry(kind="input", ref="goal", title="学习目标", detail=goal, stage="research", status="confirmed"),
        build_traceability_entry(kind="input", ref="level", title="当前水平", detail=level, stage="research", status="confirmed"),
        build_traceability_entry(kind="input", ref="schedule", title="学习节奏", detail=schedule, stage="research", status="confirmed"),
    ]
    return apply_quality_envelope(
        {
            "contract_version": "learn-plan.workflow.v2",
            "stage": "research",
            "candidate_version": "learn-plan.research-fallback.v1",
            "deepsearch_status": "completed",
            "research_plan": {
                "status": "completed",
                "research_questions": [
                    "面向中国大陆一线城市数据科学 / 大模型应用开发岗位，Python 需要达到什么面试层级？",
                    "哪些 Python 能力是 3-4 个月窗口内最影响求职效率的 must-have？",
                    "这些能力通常通过什么题型或场景被验证？",
                ],
                "source_types": ["用户目标与约束", "岗位导向能力抽象", "后续 diagnostic 需求"],
                "selection_criteria": [
                    "优先覆盖求职高频与后续迁移价值高的能力",
                    "优先选择能在 30 分钟学习单元里推进的训练对象",
                ],
            },
            "research_report": {
                "report_status": "completed",
                "goal_target_band": target_band,
                "must_master_core": must_master_core,
                "evidence_expectations": evidence_expectations,
                "research_brief": research_brief,
                "capability_metrics": capability_metrics,
                "mainline_capabilities": [item["name"] for item in capability_metrics[:2]],
                "supporting_capabilities": [capability_metrics[2]["name"]],
                "deferred_capabilities": [
                    "完整 Web 框架专项",
                    "解释器原理与底层实现细节",
                    "与目标岗位弱相关的泛生态专题",
                ],
                "selection_rationale": selection_rationale,
                "evidence_summary": evidence_summary,
                "open_risks": [
                    "当前真实起点仍未通过 diagnostic 校准，research 只能先给目标能力带与诊断范围。",
                    "两个岗位方向仍是并行目标，后续 planning 需要根据 diagnostic 结果进一步调主次。",
                ],
                "diagnostic_scope": diagnostic_scope,
            },
        },
        stage="research",
        generator="stage-candidate:research-fallback",
        evidence=normalize_string_list([
            f"topic={topic}",
            f"goal={goal}",
            f"level={level}",
            f"schedule={schedule}",
            f"preference={preference}",
            f"fallback_reason={metadata.get('reason') if isinstance(metadata, dict) else 'external_candidate_required'}",
        ]),
        confidence=0.62,
        generation_trace={
            "prompt_version": "learn-plan.research-fallback.v1",
            "generator": "learn-plan-research-fallback",
            "status": "completed",
            "fallback": True,
            "fallback_reason": metadata.get("reason") if isinstance(metadata, dict) else "external_candidate_required",
        },
        traceability=traceability,
    )



def build_diagnostic_fallback_candidate(
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
    diagnostic_scope = research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {}
    budget = resolve_assessment_budget_preference(clarification, diagnostic)
    round_index = 1
    max_rounds = budget.get("max_assessment_rounds_preference") or 2
    questions_per_round = budget.get("questions_per_round_preference") or 8
    target_capability_ids = normalize_string_list(diagnostic_scope.get("target_capability_ids") or [])
    scoring_dimensions = normalize_string_list(diagnostic_scope.get("scoring_dimensions") or [])
    gap_judgement_basis = normalize_string_list(diagnostic_scope.get("gap_judgement_basis") or [])
    evidence_expectations = normalize_string_list(diagnostic_scope.get("evidence_expectations") or [])
    capability_metrics = research_report.get("capability_metrics") if isinstance(research_report.get("capability_metrics"), list) else []
    capability_lookup = {
        str(item.get("id") or "").strip(): item
        for item in capability_metrics
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    target_capability_ids = target_capability_ids or [capability_id for capability_id in capability_lookup.keys()]
    scoring_rubric = [
        {"metric": "正确性与边界意识", "threshold": "能完成核心步骤并说明关键边界与常见坑"},
        {"metric": "代码组织与可读性", "threshold": "命名、函数拆分和表达清晰，可解释实现取舍"},
        {"metric": "复杂度与讲解表达", "threshold": "能说明复杂度、调试路径与设计理由"},
    ]
    if any("数据处理" in item for item in scoring_dimensions):
        scoring_rubric.append({"metric": "数据处理熟练度", "threshold": "能完成基础读写、清洗、筛选、聚合并解释结果"})
    diagnostic_items: list[dict[str, Any]] = []
    for capability_id in target_capability_ids:
        metric = capability_lookup.get(capability_id, {})
        capability_name = str(metric.get("name") or capability_id).strip()
        expected_signals = normalize_string_list(metric.get("observable_behaviors") or []) or evidence_expectations[:2]
        if capability_id == "python-core-coding":
            prompt = "实现一个函数，完成字符串/列表/字典的常见处理任务，并说明边界条件与时间复杂度。"
            item_type = "code"
        elif capability_id == "python-data-processing":
            prompt = "阅读一段表格数据处理需求，使用 pandas 思路说明清洗、筛选、聚合步骤，并写出关键代码框架。"
            item_type = "data-task"
        elif capability_id == "python-llm-script":
            prompt = "阅读一个简单的 Python API/脚本场景，说明如何组织函数、输入输出和异常处理，并补全关键代码。"
            item_type = "script"
        else:
            prompt = f"围绕 {capability_name} 设计一题最小可验证任务，并说明你的实现思路。"
            item_type = "code"
        diagnostic_items.append(
            {
                "id": capability_id,
                "capability_id": capability_id,
                "title": capability_name,
                "type": item_type,
                "prompt": prompt,
                "expected_signals": expected_signals,
            }
        )
    diagnostic_plan = {
        "delivery": "web-session",
        "diagnostic_delivery": "web-session",
        "assessment_kind": "initial-test",
        "session_intent": "assessment",
        "plan_execution_mode": "diagnostic",
        "target_capability_ids": target_capability_ids,
        "scoring_rubric": scoring_rubric,
        "round_index": round_index,
        "max_rounds": max_rounds,
        "questions_per_round": questions_per_round,
        "follow_up_needed": max_rounds > round_index,
        "stop_reason": "diagnostic-pending",
        "status": "ready",
    }
    diagnostic_profile = {
        "status": "ready",
        "assessment_kind": "initial-test",
        "session_intent": "assessment",
        "plan_execution_mode": "diagnostic",
        "round_index": round_index,
        "max_rounds": max_rounds,
        "questions_per_round": questions_per_round,
        "follow_up_needed": max_rounds > round_index,
        "baseline_level": level,
        "dimensions": scoring_dimensions,
        "observed_weaknesses": gap_judgement_basis,
    }
    diagnostic_result = {
        "status": "pending",
        "follow_up_needed": max_rounds > round_index,
        "stop_reason": "diagnostic-pending",
    }
    traceability = [
        build_traceability_entry(kind="input", ref="goal", title="学习目标", detail=goal, stage="diagnostic", status="confirmed"),
        build_traceability_entry(kind="research", ref="research.diagnostic_scope", title="诊断范围来源", detail="继承 research diagnostic_scope", stage="diagnostic", status="confirmed"),
        build_traceability_entry(kind="input", ref="schedule", title="学习节奏", detail=schedule, stage="diagnostic", status="confirmed"),
    ]
    return apply_quality_envelope(
        {
            "contract_version": "learn-plan.workflow.v2",
            "stage": "diagnostic",
            "candidate_version": "learn-plan.diagnostic-fallback.v1",
            "research_report": research_report,
            "diagnostic_plan": diagnostic_plan,
            "diagnostic_items": diagnostic_items,
            "diagnostic_result": diagnostic_result,
            "diagnostic_profile": diagnostic_profile,
        },
        stage="diagnostic",
        generator="stage-candidate:diagnostic-fallback",
        evidence=normalize_string_list([
            f"topic={topic}",
            f"goal={goal}",
            f"level={level}",
            f"schedule={schedule}",
            f"preference={preference}",
            f"fallback_reason={metadata.get('reason') if isinstance(metadata, dict) else 'external_candidate_required'}",
        ]),
        confidence=0.58,
        generation_trace={
            "prompt_version": "learn-plan.diagnostic-fallback.v1",
            "generator": "learn-plan-diagnostic-fallback",
            "status": "completed",
            "fallback": True,
            "fallback_reason": metadata.get("reason") if isinstance(metadata, dict) else "external_candidate_required",
        },
        traceability=traceability,
    )



def build_planning_prompt_profile(profile: dict[str, Any]) -> dict[str, Any]:
    research_report = profile.get("research_report") if isinstance(profile.get("research_report"), dict) else {}
    diagnostic_profile = profile.get("diagnostic_profile") if isinstance(profile.get("diagnostic_profile"), dict) else {}
    approval_state = profile.get("approval_state") if isinstance(profile.get("approval_state"), dict) else {}
    patch_queue = profile.get("curriculum_patch_queue") if isinstance(profile.get("curriculum_patch_queue"), dict) else {}
    return {
        "topic": profile.get("topic"),
        "goal": profile.get("goal"),
        "level": profile.get("level"),
        "family": profile.get("family"),
        "research_report": {
            "goal_target_band": research_report.get("goal_target_band"),
            "must_master_core": normalize_string_list(research_report.get("must_master_core") or []),
            "evidence_expectations": normalize_string_list(research_report.get("evidence_expectations") or []),
            "research_brief": research_report.get("research_brief"),
            "evidence_summary": normalize_string_list(research_report.get("evidence_summary") or []),
        },
        "diagnostic_profile": {
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level"),
            "confidence": diagnostic_profile.get("confidence"),
            "strengths": normalize_string_list(diagnostic_profile.get("strengths") or []),
            "weaknesses": normalize_string_list(diagnostic_profile.get("weaknesses") or []),
        },
        "approval_state": {
            "approval_status": approval_state.get("approval_status"),
            "ready_for_execution": approval_state.get("ready_for_execution"),
            "pending_decisions": normalize_string_list(approval_state.get("pending_decisions") or []),
            "accepted_tradeoffs": normalize_string_list(approval_state.get("accepted_tradeoffs") or []),
            "approved_patch_ids": normalize_string_list(approval_state.get("approved_patch_ids") or []),
            "rejected_patch_ids": normalize_string_list(approval_state.get("rejected_patch_ids") or []),
        },
        "curriculum_patch_queue": {
            "pending_patch_count": patch_queue.get("pending_patch_count"),
            "pending_patch_topics": normalize_string_list(patch_queue.get("pending_patch_topics") or []),
            "applied_patch_topics": normalize_string_list(patch_queue.get("applied_patch_topics") or []),
            "rejected_patch_topics": normalize_string_list(patch_queue.get("rejected_patch_topics") or []),
        },
    }



def build_planning_prompt_curriculum(curriculum: dict[str, Any]) -> dict[str, Any]:
    stages = curriculum.get("stages") if isinstance(curriculum.get("stages"), list) else []
    return {
        "family": curriculum.get("family"),
        "stages": [
            {
                "name": stage.get("name"),
                "goal": stage.get("goal"),
                "focus": stage.get("focus"),
                "reading": normalize_string_list(stage.get("reading") or [])[:2],
                "exercise_types": normalize_string_list(stage.get("exercise_types") or [])[:2],
                "test_gate": stage.get("test_gate"),
            }
            for stage in stages
            if isinstance(stage, dict)
        ],
    }



def build_planning_prompt_context(
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    *,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
    workflow_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clarification_state = clarification.get("clarification_state") if isinstance((clarification or {}).get("clarification_state"), dict) else {}
    research_report = research.get("research_report") if isinstance((research or {}).get("research_report"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance((diagnostic or {}).get("diagnostic_profile"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance((approval or {}).get("approval_state"), dict) else {}
    compact_workflow_state = workflow_state if isinstance(workflow_state, dict) else {}
    compact_patch_queue = curriculum_patch_queue if isinstance(curriculum_patch_queue, dict) else {}
    return build_stage_context(
        "planning",
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        clarification={
            "clarification_state": {
                "status": clarification_state.get("status"),
                "confirmed_goals": normalize_string_list(clarification_state.get("confirmed_goals") or []),
                "constraints": normalize_string_list(clarification_state.get("constraints") or []),
                "preferences": normalize_string_list(clarification_state.get("preferences") or []),
                "non_goals": normalize_string_list(clarification_state.get("non_goals") or []),
            }
        },
        research={
            "research_report": {
                "goal_target_band": research_report.get("goal_target_band"),
                "must_master_core": normalize_string_list(research_report.get("must_master_core") or []),
                "evidence_expectations": normalize_string_list(research_report.get("evidence_expectations") or []),
                "research_brief": research_report.get("research_brief"),
            }
        },
        diagnostic={
            "diagnostic_profile": {
                "recommended_entry_level": diagnostic_profile.get("recommended_entry_level"),
                "confidence": diagnostic_profile.get("confidence"),
                "strengths": normalize_string_list(diagnostic_profile.get("strengths") or []),
                "weaknesses": normalize_string_list(diagnostic_profile.get("weaknesses") or []),
            }
        },
        approval={
            "approval_state": {
                "approval_status": approval_state.get("approval_status"),
                "ready_for_execution": approval_state.get("ready_for_execution"),
                "pending_decisions": normalize_string_list(approval_state.get("pending_decisions") or []),
                "accepted_tradeoffs": normalize_string_list(approval_state.get("accepted_tradeoffs") or []),
                "approved_patch_ids": normalize_string_list(approval_state.get("approved_patch_ids") or []),
                "rejected_patch_ids": normalize_string_list(approval_state.get("rejected_patch_ids") or []),
            }
        },
        learner_model={},
        curriculum_patch_queue={
            "pending_patch_count": compact_patch_queue.get("pending_patch_count"),
            "pending_patch_topics": normalize_string_list(compact_patch_queue.get("pending_patch_topics") or []),
            "applied_patch_topics": normalize_string_list(compact_patch_queue.get("applied_patch_topics") or []),
            "rejected_patch_topics": normalize_string_list(compact_patch_queue.get("rejected_patch_topics") or []),
        },
        workflow_state={
            "blocking_stage": compact_workflow_state.get("blocking_stage"),
            "recommended_mode": compact_workflow_state.get("recommended_mode"),
            "missing_requirements": normalize_string_list(compact_workflow_state.get("missing_requirements") or []),
            "routing_reasons": normalize_string_list(compact_workflow_state.get("routing_reasons") or []),
            "quality_issues": normalize_string_list(compact_workflow_state.get("quality_issues") or []),
        },
        artifacts={},
    )



def hydrate_planning_candidate(candidate: dict[str, Any], profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(candidate))
    plan_candidate = normalized.get("plan_candidate") if isinstance(normalized.get("plan_candidate"), dict) else {}
    fallback = build_plan_candidate(profile, curriculum)
    fallback_candidate = fallback.get("plan_candidate") if isinstance(fallback.get("plan_candidate"), dict) else {}
    for key in ("stage_goals", "mastery_checks", "material_roles", "daily_execution_logic"):
        if not normalize_string_list(plan_candidate.get(key)):
            plan_candidate[key] = normalize_string_list(fallback_candidate.get(key) or [])
    if plan_candidate:
        normalized["plan_candidate"] = plan_candidate
    if not normalize_string_list(normalized.get("evidence") or []):
        normalized["evidence"] = normalize_string_list(fallback.get("evidence") or [])
    return normalized


def build_planning_artifact(
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    profile: dict[str, Any],
    curriculum: dict[str, Any],
    *,
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    learner_model: dict[str, Any] | None = None,
    curriculum_patch_queue: dict[str, Any] | None = None,
    workflow_state: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    injected_candidate: dict[str, Any] | None = None,
    injected_semantic_review: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt_profile = build_planning_prompt_profile(profile)
    prompt_curriculum = build_planning_prompt_curriculum(curriculum)
    existing_state = {
        "planning_profile": prompt_profile,
        "curriculum": prompt_curriculum,
    }
    if isinstance(injected_candidate, dict) and injected_candidate:
        candidate = injected_candidate
        metadata = {
            "stage": "planning",
            "mode": "stage-candidate",
            "status": "ok",
            "artifact_source": "harness-injected",
            "reason": "planning-candidate-json",
        }
    else:
        candidate = None
        metadata = {
            "stage": "planning",
            "mode": "stage-candidate",
            "status": "missing-external-artifact",
            "artifact_source": "harness-required",
            "reason": "planning-candidate-json-required",
        }
    if not isinstance(candidate, dict):
        missing_artifact = apply_quality_envelope(
            {
                "stage": "planning",
                "candidate_error": {
                    "message": "external_candidate_required",
                    "error_code": "missing_planning_candidate_artifact",
                    "metadata": metadata,
                },
                "artifact_source": "harness-required",
                "generation_mode": "missing-external-artifact",
            },
            stage="planning",
            generator="planning-candidate:external-artifact-gate",
            evidence=["planning_candidate_json_required"],
            confidence=0.0,
            quality_review={
                "reviewer": "planning-artifact-gate",
                "valid": False,
                "issues": ["planning.external_candidate_required"],
                "warnings": [],
                "confidence": 0.0,
                "evidence_adequacy": "partial",
                "verdict": "needs-revision",
            },
            generation_trace={
                **metadata,
                "generator": "planning-candidate:external-artifact-gate",
            },
            traceability=[
                build_traceability_entry(
                    kind="planning-candidate",
                    ref="planning-candidate-json",
                    title="planning candidate external artifact required",
                    stage="planning",
                    status="missing-external-artifact",
                )
            ],
        )
        return missing_artifact, metadata

    candidate = hydrate_planning_candidate(candidate, profile, curriculum)
    reviewed = review_stage_candidate("planning", candidate)
    reviewed["stage"] = "planning"
    reviewed["candidate_version"] = reviewed.get("candidate_version") or candidate.get("candidate_version") or candidate.get("generation_trace", {}).get("prompt_version")
    reviewed["generation_mode"] = "harness-injected" if isinstance(injected_candidate, dict) and injected_candidate else "deterministic-fallback"
    if isinstance(injected_semantic_review, dict) and injected_semantic_review:
        quality_review = reviewed.get("quality_review") if isinstance(reviewed.get("quality_review"), dict) else {}
        reviewed["quality_review"] = {
            **quality_review,
            "semantic_issues": normalize_string_list(injected_semantic_review.get("semantic_issues")),
            "improvement_suggestions": normalize_string_list(injected_semantic_review.get("improvement_suggestions")),
            "semantic_review_status": str(injected_semantic_review.get("status") or "completed").strip(),
            "semantic_review_artifact_source": str(injected_semantic_review.get("artifact_source") or "harness-injected").strip(),
            "semantic_review_verdict": str(injected_semantic_review.get("overall_verdict") or "pass").strip(),
        }
    return reviewed, metadata



def maybe_generate_stage_candidate(
    stage: str | None,
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    clarification: dict[str, Any],
    research: dict[str, Any],
    diagnostic: dict[str, Any],
    approval: dict[str, Any],
    learner_model: dict[str, Any],
    curriculum_patch_queue: dict[str, Any],
    workflow_state: dict[str, Any],
    artifacts: dict[str, Any],
    enable_semantic_review: bool = False,
    search_context: dict[str, Any] | None = None,
    injected_candidate: dict[str, Any] | None = None,
    injected_semantic_review: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not stage:
        return None, {}
    existing_state = {
        "clarification": clarification,
        "research": research,
        "diagnostic": diagnostic,
        "approval": approval,
    }.get(stage) or {}
    if isinstance(injected_candidate, dict) and injected_candidate:
        candidate = injected_candidate
        metadata = {
            "stage": stage,
            "mode": "stage-candidate",
            "status": "ok",
            "artifact_source": "harness-injected",
            "reason": "stage-candidate-json",
        }
    else:
        candidate = None
        metadata = {
            "stage": stage,
            "mode": "stage-candidate",
            "status": "missing-external-artifact",
            "artifact_source": "harness-required",
            "reason": "stage-candidate-json-required",
        }
    if candidate is None:
        missing_artifact = apply_quality_envelope(
            {
                "stage": stage,
                "candidate_error": {
                    "message": "external_candidate_required",
                    "metadata": metadata,
                },
                "artifact_source": "harness-required",
                "generation_mode": "missing-external-artifact",
            },
            stage=stage,
            generator=f"stage-candidate:{stage}:external-artifact-gate",
            evidence=normalize_string_list(
                [
                    f"stage={stage}",
                    f"generation_status={metadata.get('status') or 'failed'}",
                    f"mode={metadata.get('mode') or 'stage-candidate'}",
                ]
            ),
            confidence=0.0,
            quality_review={
                "reviewer": "stage-artifact-gate",
                "valid": False,
                "issues": [f"{stage}.external_candidate_required"],
                "warnings": [],
                "confidence": 0.0,
                "verdict": "needs-revision",
                "evidence_adequacy": "partial",
            },
            generation_trace={
                **metadata,
                "generator": f"stage-candidate:{stage}:external-artifact-gate",
            },
            traceability=[
                build_traceability_entry(
                    kind="stage-candidate",
                    ref=stage,
                    title=f"{stage} candidate external artifact required",
                    stage=stage,
                    status=str(metadata.get("status") or "failed"),
                )
            ],
        )
        return missing_artifact, metadata
    candidate_to_review = merge_workflow_candidate(existing_state, candidate)
    reviewed = review_stage_candidate(stage, candidate_to_review)
    if isinstance(injected_semantic_review, dict) and injected_semantic_review:
        quality_review = reviewed.get("quality_review") if isinstance(reviewed.get("quality_review"), dict) else {}
        reviewed["quality_review"] = {
            **quality_review,
            "semantic_issues": normalize_string_list(injected_semantic_review.get("semantic_issues")),
            "improvement_suggestions": normalize_string_list(injected_semantic_review.get("improvement_suggestions")),
            "semantic_review_status": str(injected_semantic_review.get("status") or "completed").strip(),
            "semantic_review_artifact_source": str(injected_semantic_review.get("artifact_source") or "harness-injected").strip(),
            "semantic_review_verdict": str(injected_semantic_review.get("overall_verdict") or "pass").strip(),
        }
    elif enable_semantic_review:
        quality_review = reviewed.get("quality_review") if isinstance(reviewed.get("quality_review"), dict) else {}
        reviewed["quality_review"] = {
            **quality_review,
            "semantic_issues": normalize_string_list(quality_review.get("semantic_issues")),
            "improvement_suggestions": normalize_string_list(quality_review.get("improvement_suggestions")),
            "semantic_review_status": "missing-external-artifact",
            "semantic_review_artifact_source": "harness-required",
            "semantic_review_verdict": "pending",
        }
    if isinstance(injected_candidate, dict) and injected_candidate:
        reviewed["generation_mode"] = "harness-injected"
    else:
        reviewed["generation_mode"] = "deterministic-fallback"
    return reviewed, metadata



def should_build_planning_artifact(workflow_state: dict[str, Any] | None = None) -> bool:
    blocking_stage = str((workflow_state or {}).get("blocking_stage") or "").strip().lower()
    return blocking_stage in {"approval", "planning", "ready"}



def should_prepare_formal_plan(mode: str, workflow_state: dict[str, Any] | None = None) -> bool:
    blocking_stage = str((workflow_state or {}).get("blocking_stage") or "").strip().lower()
    return str(mode or "").strip().lower() == "finalize" and blocking_stage == "ready"



def build_plan_sections(topic: str, goal: str, level: str, schedule: str, preference: str, materials_dir: Path, materials_index: Path, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, planning: dict[str, Any] | None = None, learner_model: dict[str, Any] | None = None, curriculum_patch_queue: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, str]:
    curriculum = build_curriculum(topic, level, preference)
    profile = build_planning_profile(topic, goal, level, schedule, preference, clarification=clarification, research=research, diagnostic=diagnostic, approval=approval, planning=planning, learner_model=learner_model, curriculum_patch_queue=curriculum_patch_queue, mode=mode)
    report = build_plan_report(profile, curriculum)
    return {
        "学习画像": render_planning_profile(profile),
        "规划假设与约束": render_planning_constraints(profile),
        "能力指标与起点判断": render_capability_model_section(profile),
        "检索结论与取舍": render_plan_report(report),
        "阶段总览": render_stage_overview(curriculum, planning),
        "阶段路线图": render_learning_route(curriculum, planning),
        "资料清单与阅读定位": render_materials_section(curriculum, materials_dir, materials_index, profile.get("material_curation") if isinstance(profile, dict) else None),
        "掌握度检验设计": render_mastery_checks(curriculum),
        "今日生成规则": render_today_generation_rules(curriculum),
        "每日推进表": render_daily_roadmap(curriculum),
        "学习记录": "",
        "测试记录": "",
    }


def extract_section(text: str, heading: str) -> str | None:
    marker = f"## {heading}"
    if marker not in text:
        return None
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == marker:
            start = idx + 1
            break
    if start is None:
        return None

    while start < len(lines) and not lines[start].strip():
        start += 1

    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def choose_existing_section(original: str, heading: str, default: str) -> str:
    return planning_choose_existing_section(original, heading, default)


def render_plan(topic: str, goal: str, level: str, schedule: str, preference: str, sections: dict[str, str]) -> str:
    return planning_render_plan(topic, goal, level, schedule, preference, sections)


def review_public_plan_markdown(markdown: str) -> list[str]:
    return planning_review_public_plan_markdown(markdown)


def group_topics_for_segments(focus_topics: list[str], *, chunk_size: int = 3) -> list[list[str]]:
    return materials_group_topics_for_segments(focus_topics, chunk_size=chunk_size)



def build_special_reading_segments(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    return materials_build_special_reading_segments(entry, curriculum)



def build_reading_segments(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    return materials_build_reading_segments(entry, curriculum)



def build_default_material_entries(topic: str, domain: str, materials_dir: Path, curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    return materials_build_default_material_entries(
        topic,
        domain,
        materials_dir,
        curriculum,
        family_configs=TOPIC_FAMILIES,
    )


def merge_reading_segments(default_segments: list[dict[str, Any]], existing_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return materials_merge_reading_segments(default_segments, existing_segments)



def merge_material_entries(existing_entries: list[dict[str, Any]], default_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return materials_merge_material_entries(existing_entries, default_entries)


def build_materials_index(topic: str, goal: str, level: str, schedule: str, preference: str, materials_dir: Path, plan_path: Path, existing: dict[str, Any]) -> dict[str, Any]:
    curriculum = build_curriculum(topic, level, preference)
    return materials_build_materials_index(
        topic,
        goal,
        level,
        schedule,
        preference,
        materials_dir,
        plan_path,
        existing,
        domain=infer_domain(topic),
        curriculum=curriculum,
        family_configs=TOPIC_FAMILIES,
    )


def validate_plan_quality(sections: dict[str, str], materials_data: dict[str, Any], *, profile: dict[str, Any]) -> list[str]:
    return planning_validate_plan_quality(sections, materials_data, profile=profile)



def append_quality_warning(sections: dict[str, str], quality_issues: list[str]) -> dict[str, str]:
    if not quality_issues:
        return sections
    updated = dict(sections)
    warning_block = "\n".join(
        [
            "- 当前计划仅可视为待确认 / 待补资料草案，尚不满足正式高质量主线要求。",
            "- 当前阻塞原因：",
            *[f"  - {item}" for item in quality_issues],
            "- 建议：优先补充可本地获得的主线资料（如 PDF、电子书、可下载文档、可本地克隆仓库），再重新生成正式计划。",
        ]
    )
    existing = updated.get("检索结论与取舍", "").strip()
    updated["检索结论与取舍"] = f"{existing}\n\n### 当前阻塞与待补资料\n{warning_block}".strip()
    updated["今日生成规则"] = (updated.get("今日生成规则", "").strip() + "\n- 若当前计划仍处于待补资料状态，则 /learn-today 不应直接推进正式学习，而应先补齐主线资料。"
    ).strip()
    return updated



def _humanize_workflow_issue(issue: Any) -> str:
    text = str(issue or "").strip()
    if not text:
        return ""
    mapping = {
        "planning.plan_candidate": "正式计划所需的结构化 plan candidate 还没有准备好",
        "diagnostic.follow_up_pending": "起点诊断尚未完成，仍需继续下一轮诊断或收口诊断结果。请继续 diagnostic workflow，不要手动补中间态 JSON。",
        "approval.pending_decisions": "计划草案仍有待确认决策，尚不能进入正式落盘。请回到 approval 阶段完成确认，不要手动改 approval JSON。",
        "approval.ready_for_execution": "approval gate 尚未确认 ready_for_execution。请回到 approval 阶段重新确认，不要手动补 ready 标记。",
        "research.report_status": "research 报告尚未完成或未达到可消费状态。请回到 research 阶段重新产出，不要手动补 research JSON。",
        "research.plan_status": "research plan 尚未确认，不能把 report 当作完成态。请回到 research 阶段确认，不要手动改研究中间态。",
        "research.user_review_confirmation": "目的解析报告尚未经过用户审阅确认。请停留在 research 阶段等待确认，不要手动把 research.json 改成已确认。",
        "research.diagnostic_scope": "research 已确认需要测试，但尚未形成可机器消费的 diagnostic scope。请回到 research 阶段重新产出，不要手动补 diagnostic blueprint。",
        "research.diagnostic_scope.target_capability_ids": "research 的测试范围还没明确接下来要测哪些能力。请回到 research 阶段重新产出，不要手动补 diagnostic JSON。",
        "research.diagnostic_scope.scoring_dimensions": "research 的测试范围还没明确这轮测试的评分维度。请回到 research 阶段重新产出，不要手动补 diagnostic JSON。",
        "research.diagnostic_scope.gap_judgement_basis": "research 的测试范围还没明确如何判断与目标水平的差距。请回到 research 阶段重新产出，不要手动补 diagnostic JSON。",
        "diagnostic.research_scope": "research 的测试范围还没有进入 diagnostic 链路。请先回到 research-report 阶段完成承接，不要手动编辑 diagnostic blueprint。",
        "diagnostic.scope_alignment": "当前 diagnostic blueprint 没有承接 research 已定义的测试范围。请回到 diagnostic 阶段重新生成，不要手动补 blueprint 字段。",
        "clarification.max_assessment_rounds_preference": "还未确认起始测评最多接受几轮",
        "clarification.questions_per_round_preference": "还未确认起始测评每轮最多几题",
        "formal_plan.mode_not_finalize": "当前还不在 finalize 模式，正式计划写入被阻止",
        "formal_plan.blocking_stage.planning": "当前仍处于 finalize 前的 planning 过渡态，正式计划写入被阻止",
        "formal_plan.blocking_stage.diagnostic": "当前仍卡在 diagnostic 阶段，正式计划写入被阻止",
        "formal_plan.missing_requirements": "正式计划写入所需条件尚未补齐",
        "diagnostic.preflight_invalid": "诊断启动前自检未通过，当前不能直接启动 initial-test session",
        "diagnostic.preflight_blockers": "诊断蓝图仍不完整，需先补齐 diagnostic blueprint 再启动 session",
    }
    if text in mapping:
        return mapping[text]
    prefix_mapping = {
        "clarification.": "clarification 仍有未补齐项：",
        "research.": "research 仍有未补齐项：",
        "diagnostic.": "diagnostic 仍有未补齐项：",
        "approval.": "approval 仍有未补齐项：",
        "planning.": "planning 仍有未补齐项：",
        "formal_plan.": "正式计划写入仍受阻：",
    }
    for prefix, label in prefix_mapping.items():
        if text.startswith(prefix):
            return f"{label}{text[len(prefix):]}"
    return text


def print_summary(
    topic: str,
    goal: str,
    plan_path: Path,
    materials_dir: Path,
    materials_index: Path,
    *,
    stdout_json: bool,
    requested_mode: str,
    mode: str,
    workflow_state: dict[str, Any] | None = None,
    planning_state: dict[str, Any] | None = None,
    download_result: dict[str, Any] | None = None,
    auto_download_enabled: bool = True,
    quality_issues: list[str] | None = None,
    diagnostic_session: dict[str, Any] | None = None,
) -> None:
    workflow_state = workflow_state or {}
    quality_issues = quality_issues or list(workflow_state.get("quality_issues") or [])
    recommended_mode = str(workflow_state.get("recommended_mode") or mode)
    blocking_stage = str(workflow_state.get("blocking_stage") or "approval")
    routing_reasons = list(workflow_state.get("routing_reasons") or [])
    next_action = str(workflow_state.get("next_action") or f"switch_to:{recommended_mode}")
    should_continue_workflow = bool(workflow_state.get("should_continue_workflow"))
    is_intermediate_product = bool(workflow_state.get("is_intermediate_product"))
    next_step_by_mode = {
        "draft": "继续完成澄清、研究、诊断或确认 gate，再进入 finalize",
        "research-report": "先确认研究计划/研究摘要，再决定是否进入诊断或 finalize",
        "diagnostic": "先完成最小水平验证并确认起步层级，再进入 finalize",
        "finalize": "/learn-today",
    }
    planning_stage_note = "当前处于 finalize 前的过渡态：前序 gate 已基本满足，但系统仍在等待或生成结构化 plan_candidate，这不是 workflow 回退。"
    next_step_hint = next_step_by_mode.get(mode, "/learn-today")
    if blocking_stage == "planning":
        next_step_hint = "继续补齐或生成 plan_candidate，然后再次进入 finalize"
    missing_requirements = list(workflow_state.get("missing_requirements") or [])
    actionable_missing_requirements = list(workflow_state.get("actionable_missing_requirements") or [])
    reference_missing_requirements = list(workflow_state.get("reference_missing_requirements") or [])
    actionable_quality_issues = list(workflow_state.get("actionable_quality_issues") or [])
    reference_quality_issues = list(workflow_state.get("reference_quality_issues") or [])
    actionable_stage = str(workflow_state.get("actionable_stage") or blocking_stage)
    workflow_instruction = str(workflow_state.get("workflow_instruction") or "").strip()
    manual_patch_warning = str(workflow_state.get("manual_patch_warning") or "").strip()
    stage_exit_contract = workflow_state.get("stage_exit_contract") if isinstance(workflow_state.get("stage_exit_contract"), dict) else {}
    stage_exit_missing_values = normalize_string_list(workflow_state.get("stage_exit_missing_values") or [])
    stage_exit_required_artifacts = normalize_string_list(workflow_state.get("stage_exit_required_artifacts") or [])
    stage_exit_user_visible_next_step = str(workflow_state.get("stage_exit_user_visible_next_step") or "").strip()
    assessment_budget_confirmation_required = (
        "clarification.max_assessment_rounds_preference" in actionable_missing_requirements
        or "clarification.questions_per_round_preference" in actionable_missing_requirements
    )
    research_report = workflow_state.get("research_report") if isinstance(workflow_state.get("research_report"), dict) else {}
    research_plan = workflow_state.get("research_plan") if isinstance(workflow_state.get("research_plan"), dict) else {}
    user_facing_report = research_report.get("user_facing_report") if isinstance(research_report.get("user_facing_report"), dict) else {}
    research_report_html_path = str(user_facing_report.get("path") or (workflow_state.get("artifacts") or {}).get("research_report_html") or "").strip()
    should_show_research_report = bool(workflow_state.get("should_show_research_report"))
    blocking_reasons = actionable_quality_issues or actionable_missing_requirements or routing_reasons
    display_blocking_reasons = [item for item in (_humanize_workflow_issue(item) for item in blocking_reasons) if item]
    display_reference_requirements = [item for item in (_humanize_workflow_issue(item) for item in reference_missing_requirements) if item]
    display_reference_quality_issues = [item for item in (_humanize_workflow_issue(item) for item in reference_quality_issues) if item]
    formal_plan_write_allowed = bool(workflow_state.get("formal_plan_write_allowed"))
    formal_plan_write_blockers = list(workflow_state.get("formal_plan_write_blockers") or [])
    display_formal_plan_write_blockers = [item for item in (_humanize_workflow_issue(item) for item in formal_plan_write_blockers) if item]
    research_core_summary = {
        "goal_target_band": str(research_report.get("goal_target_band") or "").strip(),
        "must_master_core": normalize_string_list(research_report.get("must_master_core") or []),
        "evidence_expectations": normalize_string_list(research_report.get("evidence_expectations") or []),
        "research_brief": str(research_report.get("research_brief") or "").strip(),
    }
    summary = {
        "topic": topic,
        "requested_mode": requested_mode,
        "mode": mode,
        "recommended_mode": recommended_mode,
        "blocking_stage": blocking_stage,
        "routing_reasons": routing_reasons,
        "actionable_stage": actionable_stage,
        "actionable_missing_requirements": actionable_missing_requirements,
        "reference_missing_requirements": reference_missing_requirements,
        "actionable_quality_issues": actionable_quality_issues,
        "reference_quality_issues": reference_quality_issues,
        "workflow_instruction": workflow_instruction,
        "manual_patch_warning": manual_patch_warning,
        "research_report_html_path": research_report_html_path,
        "stage_exit_contract": stage_exit_contract,
        "stage_exit_missing_values": stage_exit_missing_values,
        "stage_exit_required_artifacts": stage_exit_required_artifacts,
        "stage_exit_user_visible_next_step": stage_exit_user_visible_next_step,
        "assessment_budget_confirmation_required": assessment_budget_confirmation_required,
        "diagnostic_delivery": "web-session",
        "diagnostic_update_handler": "learn_test_update.py",
        "is_intermediate_product": is_intermediate_product,
        "should_continue_workflow": should_continue_workflow,
        "next_action": next_action,
        "workflow_loop_hint": "若 should_continue_workflow 为 true，则外层应继续下一轮澄清/research/diagnostic/approval；仅当 next_action = enter:/learn-today 时才退出 /learn-plan 工作流。",
        "plan_path": str(plan_path),
        "materials_dir": str(materials_dir),
        "materials_index": str(materials_index),
        "planning_state": planning_state or {},
        "next_step": next_step_hint,
        "quality_issues": quality_issues,
        "display_blocking_reasons": display_blocking_reasons,
        "formal_plan_write_allowed": bool(workflow_state.get("formal_plan_write_allowed")),
        "formal_plan_write_blockers": list(workflow_state.get("formal_plan_write_blockers") or []),
        "display_write_blockers": display_formal_plan_write_blockers,
    }
    if any(research_core_summary.values()):
        summary["research_core_summary"] = research_core_summary
    if workflow_state:
        summary["workflow_state"] = workflow_state
    if diagnostic_session is not None:
        summary["diagnostic_session"] = diagnostic_session
    if download_result is not None:
        summary["material_download"] = {
            "enabled": auto_download_enabled,
            "downloaded": download_result.get("downloaded", 0),
            "skipped": download_result.get("skipped", 0),
            "failed": download_result.get("failed", 0),
            "message": download_result.get("message", ""),
        }
    print(f"学习主题：{topic}")
    print(f"workflow mode：{mode}")
    if mode != requested_mode:
        print(f"自动切换 mode：{requested_mode} -> {mode}")
    print(f"推荐 mode：{recommended_mode}")
    print(f"当前阻塞阶段：{blocking_stage}")
    if stage_exit_required_artifacts:
        print("当前阶段退出所需产物：" + "；".join(stage_exit_required_artifacts))
    if stage_exit_missing_values:
        display_stage_exit_missing = [item for item in (_humanize_workflow_issue(item) for item in stage_exit_missing_values) if item]
        print("当前阶段退出缺口：" + "；".join(display_stage_exit_missing or stage_exit_missing_values))
    if stage_exit_user_visible_next_step:
        print(f"当前阶段下一步：{stage_exit_user_visible_next_step}")
    if should_show_research_report:
        research_review = workflow_state.get("research_review") if isinstance(workflow_state.get("research_review"), dict) else {}
        research_report_payload = {
            "research_core_summary": research_core_summary,
            "research_questions": normalize_string_list(research_plan.get("research_questions") or []),
            "source_types": normalize_string_list(research_plan.get("source_types") or []),
            "candidate_directions": normalize_string_list(research_plan.get("candidate_directions") or []),
            "selection_criteria": normalize_string_list(research_plan.get("selection_criteria") or []),
            "must_master": normalize_string_list(research_report.get("must_master_capabilities") or research_report.get("must_master") or []),
            "mainline_capabilities": normalize_string_list(research_report.get("mainline_capabilities") or []),
            "supporting_capabilities": normalize_string_list(research_report.get("supporting_capabilities") or []),
            "deferred_capabilities": normalize_string_list(research_report.get("deferred_capabilities") or []),
            "selection_rationale": normalize_string_list(research_report.get("selection_rationale") or []),
            "evidence_summary": normalize_string_list(research_report.get("evidence_summary") or research_report.get("source_evidence") or []),
            "open_risks": normalize_string_list(research_report.get("open_risks") or []),
            "diagnostic_scope": research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {},
        }
        capability_report_text = planning_render_capability_report(research_report_payload)
        diagnostic_scope_text = planning_render_diagnostic_scope_preview(research_report_payload)
        research_plan_text = planning_render_research_plan(research_report_payload)
        print("目的解析报告：")
        print(capability_report_text)
        print("")
        print(diagnostic_scope_text)
        if research_plan_text.strip():
            print("")
            print("研究范围与取舍依据：")
            print(research_plan_text)
        review_status = str(research_review.get("status") or "待审阅").strip()
        print("")
        print(f"报告审阅状态：{review_status}")
        if research_report_html_path:
            print(f"HTML 能力报告：{research_report_html_path}")
        print("报告用途：这是 research 中间产物，请先审阅是否需要补充检索、修正方向或继续下一阶段。")
    print(f"计划文件：{plan_path}")
    print(f"材料目录：{materials_dir}")
    print(f"材料索引：{materials_index}")
    if auto_download_enabled:
        if download_result is not None:
            print(
                "自动下载结果："
                f"downloaded={download_result.get('downloaded', 0)}, "
                f"skipped={download_result.get('skipped', 0)}, "
                f"failed={download_result.get('failed', 0)}"
            )
        else:
            print("自动下载结果：未执行")
    else:
        print("自动下载结果：已跳过")
    if should_continue_workflow:
        print("计划状态：草案 / 待确认 / 待补条件")
        print(f"下一步动作：{next_action}")
        if workflow_instruction:
            print(f"执行约束：{workflow_instruction}")
        if display_blocking_reasons:
            print("当前需处理：" + "；".join(display_blocking_reasons))
        if display_reference_requirements or display_reference_quality_issues:
            reference_items = [*display_reference_requirements, *display_reference_quality_issues]
            print("后续参考（暂不处理）：" + "；".join(reference_items))
        if manual_patch_warning:
            print(f"禁止事项：{manual_patch_warning}")
        if blocking_stage == "planning":
            print(f"阶段说明：{planning_stage_note}")
            print(f"下一步建议：{next_step_hint}")
        else:
            print(f"下一步建议：按 next_action 继续当前 workflow，不要退出 /learn-plan")
        if assessment_budget_confirmation_required:
            print("起始测评预算：必须先确认最多几轮测试与每轮几题；未确认前不得进入诊断 session")
        if blocking_stage == "diagnostic":
            print("诊断交付：使用 initial-test 网页 session；完成作答后会自动停服、自动 update，并自动重新进入 /learn-plan")
        if should_continue_workflow:
            print("workflow 提示：除非 next_action = enter:/learn-today，否则继续当前 workflow，不要手动补中间态 JSON。")
        if is_intermediate_product:
            print("当前交付：这是中间产物，不应直接当作正式主线计划执行")
    else:
        print("计划状态：可作为正式学习计划")
        print(f"下一步建议：{next_step_hint}")
    if not formal_plan_write_allowed:
        print("正式计划写入：已阻止")
        if display_formal_plan_write_blockers:
            print("写入阻止原因：" + "；".join(display_formal_plan_write_blockers))
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_diagnostic_session_payload(
    *,
    topic: str,
    plan_path: Path,
    clarification: dict[str, Any],
    diagnostic: dict[str, Any],
    workflow_state: dict[str, Any],
) -> dict[str, Any]:
    questionnaire = clarification.get("questionnaire") if isinstance(clarification.get("questionnaire"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    research_report = workflow_state.get("research_report") if isinstance(workflow_state.get("research_report"), dict) else {}
    diagnostic_scope = research_report.get("diagnostic_scope") if isinstance(research_report.get("diagnostic_scope"), dict) else {}
    capability_metrics = research_report.get("capability_metrics") if isinstance(research_report.get("capability_metrics"), list) else []
    capability_lookup = {
        str(item.get("id") or "").strip(): item
        for item in capability_metrics
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    gap_judgement_basis = normalize_string_list(diagnostic_scope.get("gap_judgement_basis") or [])
    assessment_budget = resolve_assessment_budget_preference(clarification, diagnostic)

    round_index_raw = diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1
    max_rounds_raw = diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or assessment_budget.get("max_assessment_rounds_preference") or round_index_raw or 1
    questions_per_round_raw = diagnostic_plan.get("questions_per_round") or diagnostic_profile.get("questions_per_round") or assessment_budget.get("questions_per_round_preference") or 0
    try:
        round_index = max(1, int(round_index_raw))
    except (TypeError, ValueError):
        round_index = 1
    try:
        max_rounds = max(round_index, int(max_rounds_raw))
    except (TypeError, ValueError):
        max_rounds = round_index
    try:
        questions_per_round = max(1, int(questions_per_round_raw))
    except (TypeError, ValueError):
        questions_per_round = max(1, int(assessment_budget.get("questions_per_round_preference") or 1))

    follow_up_needed = diagnostic_result.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = round_index < max_rounds

    result_status = str(diagnostic_result.get("status") or "").strip().lower()
    profile_status = str(diagnostic_profile.get("status") or "").strip().lower()
    completed_round = result_status == "evaluated" or profile_status in {"validated", "in-progress"}
    next_round_index = round_index
    if completed_round and bool(follow_up_needed) and round_index < max_rounds:
        next_round_index = round_index + 1

    stop_reason = str(
        diagnostic_result.get("stop_reason")
        or diagnostic_plan.get("status")
        or diagnostic_profile.get("status")
        or "diagnostic-pending"
    ).strip()
    if completed_round and bool(follow_up_needed) and next_round_index > round_index:
        stop_reason = "diagnostic-follow-up"

    focus_dimensions = normalize_string_list(diagnostic_profile.get("dimensions") or [])
    observed_weaknesses = normalize_string_list(diagnostic_result.get("observed_weaknesses") or diagnostic_profile.get("observed_weaknesses") or [])
    observed_strengths = normalize_string_list(diagnostic_result.get("observed_strengths") or diagnostic_profile.get("observed_strengths") or [])
    target_capability_ids = normalize_string_list(diagnostic_plan.get("target_capability_ids") or [])
    scoring_rubric = diagnostic_plan.get("scoring_rubric") if isinstance(diagnostic_plan.get("scoring_rubric"), list) else []
    diagnostic_items = diagnostic.get("diagnostic_items") if isinstance(diagnostic.get("diagnostic_items"), list) else []
    rubric_points = []
    for item in diagnostic_plan.get("scoring_rubric") or []:
        if isinstance(item, dict):
            metric = str(item.get("metric") or item.get("name") or item.get("criterion") or "").strip()
            threshold = str(item.get("threshold") or item.get("target") or "").strip()
            text = f"{metric}：{threshold}".strip("：")
            if text:
                rubric_points.append(text)
        elif item:
            rubric_points.append(str(item).strip())

    review_points = normalize_string_list([
        *focus_dimensions[:3],
        *observed_weaknesses[:2],
    ]) or ["先确认当前水平与真实薄弱点，不直接推进新主线"]
    new_learning_points = normalize_string_list([
        *target_capability_ids[:3],
        *observed_strengths[:2],
    ]) or ["完成最小诊断验证：解释题、小测试或小代码题"]
    exercise_focus = normalize_string_list([
        *focus_dimensions[:3],
        *rubric_points[:3],
    ]) or ["本次 session 以诊断为主，用来决定起步阶段和推进节奏"]
    lesson_focus_points = normalize_string_list([
        "解释为什么当前还不能直接进入正式主线学习",
        "说明本轮 diagnostic gate 的作用，以及结果如何决定起步层级",
        *[str(capability_lookup.get(capability_id, {}).get("name") or capability_id) for capability_id in target_capability_ids[:3]],
    ])
    project_tasks = normalize_string_list([
        "完成起始诊断并产出可解释证据",
        "根据 diagnostic 结果判断 Python 学习应从哪一层开始",
        "把结果回流到后续 learn-plan planning",
    ])
    project_blockers = normalize_string_list([
        "当前真实起点尚未校准，不能直接进入正式主线",
        "需要区分问题属于概念理解、题意转译、代码表达还是边界判断",
        "需要判断是否具备数据处理与脚本场景的起步能力",
    ])
    review_targets = normalize_string_list([
        "能否用自己的话解释为什么今天先做 diagnostic 而不是正式推进",
        "能否把答题表现转成起步层级与下一轮补强建议",
        *gap_judgement_basis[:2],
    ])
    clarification_user_model = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    clarification_goal_model = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    resume_constraints = normalize_string_list(clarification_user_model.get("constraints") or [])
    resume_preferences = normalize_string_list(clarification_user_model.get("preferences") or [])

    today = time.strftime("%Y-%m-%d")
    session_suffix = "-test" if next_round_index <= 1 else f"-test-round-{next_round_index}"
    session_dir = plan_path.parent / "sessions" / f"{today}{session_suffix}"
    preflight_blockers = [f"diagnostic.{field}" for field in diagnostic_blueprint_missing_fields(target_capability_ids, scoring_rubric, diagnostic_items)]
    if str(diagnostic_plan.get("delivery") or diagnostic_plan.get("diagnostic_delivery") or "").strip() != "web-session":
        preflight_blockers.append("diagnostic.delivery")
    if not str(stop_reason).strip():
        preflight_blockers.append("diagnostic.stop_reason")
    preflight_valid = not preflight_blockers
    current_stage = str(workflow_state.get("actionable_stage") or workflow_state.get("blocking_stage") or "diagnostic")
    next_action = str(workflow_state.get("next_action") or "switch_to:diagnostic")
    workflow_instruction = str(workflow_state.get("workflow_instruction") or "").strip()
    manual_patch_warning = str(workflow_state.get("manual_patch_warning") or "").strip()
    return {
        "session_dir": session_dir,
        "round_index": next_round_index,
        "max_rounds": max_rounds,
        "questions_per_round": questions_per_round,
        "follow_up_needed": bool(follow_up_needed),
        "stop_reason": stop_reason,
        "locked_plan_execution_mode": "diagnostic",
        "resume_topic": topic,
        "resume_goal": str(clarification_goal_model.get("mainline_goal") or topic),
        "resume_level": str(diagnostic_profile.get("baseline_level") or diagnostic_profile.get("recommended_entry_level") or "待进一步确认"),
        "resume_schedule": "；".join(resume_constraints) or "未指定",
        "resume_preference": "；".join(resume_preferences) or "混合",
        "current_stage": current_stage,
        "current_day": f"Diagnostic Round {next_round_index}",
        "today_topic": f"{topic} 起始诊断",
        "review": review_points,
        "new_learning": new_learning_points,
        "exercise_focus": exercise_focus,
        "lesson_focus_points": lesson_focus_points,
        "project_tasks": project_tasks,
        "project_blockers": project_blockers,
        "review_targets": review_targets,
        "time_budget": str(diagnostic_plan.get("estimated_time") or "").strip() or None,
        "blueprint_ready": preflight_valid,
        "preflight_valid": preflight_valid,
        "preflight_blockers": preflight_blockers,
        "preflight_resolution_stage": current_stage,
        "preflight_resolution_action": next_action,
        "preflight_resolution_message": workflow_instruction,
        "manual_patch_forbidden_message": manual_patch_warning,
    }



def launch_diagnostic_session(
    *,
    topic: str,
    plan_path: Path,
    diagnostic_session: dict[str, Any],
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SESSION_ORCHESTRATOR),
        "--session-dir",
        str(diagnostic_session["session_dir"]),
        "--topic",
        topic,
        "--plan-path",
        str(plan_path),
        "--session-type",
        "test",
        "--test-mode",
        "general",
        "--current-stage",
        str(diagnostic_session.get("current_stage") or "diagnostic"),
        "--current-day",
        str(diagnostic_session.get("current_day") or "Diagnostic Round 1"),
        "--today-topic",
        str(diagnostic_session.get("today_topic") or f"{topic} 起始诊断"),
        "--round-index",
        str(diagnostic_session.get("round_index") or 1),
        "--max-rounds",
        str(diagnostic_session.get("max_rounds") or 1),
        "--questions-per-round",
        str(diagnostic_session.get("questions_per_round") or 1),
        "--stop-reason",
        str(diagnostic_session.get("stop_reason") or "diagnostic-pending"),
    ]
    if diagnostic_session.get("locked_plan_execution_mode"):
        command.extend([
            "--locked-plan-execution-mode",
            str(diagnostic_session.get("locked_plan_execution_mode")),
        ])
    if diagnostic_session.get("follow_up_needed"):
        command.append("--follow-up-needed")
    if diagnostic_session.get("resume_topic"):
        command.extend(["--resume-topic", str(diagnostic_session.get("resume_topic"))])
    if diagnostic_session.get("resume_goal"):
        command.extend(["--resume-goal", str(diagnostic_session.get("resume_goal"))])
    if diagnostic_session.get("resume_level"):
        command.extend(["--resume-level", str(diagnostic_session.get("resume_level"))])
    if diagnostic_session.get("resume_schedule"):
        command.extend(["--resume-schedule", str(diagnostic_session.get("resume_schedule"))])
    if diagnostic_session.get("resume_preference"):
        command.extend(["--resume-preference", str(diagnostic_session.get("resume_preference"))])
    if diagnostic_session.get("time_budget"):
        command.extend(["--time-budget", str(diagnostic_session["time_budget"])])
    for value in diagnostic_session.get("review") or []:
        command.extend(["--review", str(value)])
    for value in diagnostic_session.get("new_learning") or []:
        command.extend(["--new-learning", str(value)])
    for value in diagnostic_session.get("exercise_focus") or []:
        command.extend(["--exercise-focus", str(value)])
    for value in diagnostic_session.get("lesson_focus_points") or []:
        command.extend(["--lesson-focus-point", str(value)])
    for value in diagnostic_session.get("project_tasks") or []:
        command.extend(["--project-task", str(value)])
    for value in diagnostic_session.get("project_blockers") or []:
        command.extend(["--project-blocker", str(value)])
    for value in diagnostic_session.get("review_targets") or []:
        command.extend(["--review-target", str(value)])

    if not diagnostic_session.get("preflight_valid", True):
        return {
            "status": "blocked",
            "returncode": 2,
            "session_dir": str(diagnostic_session["session_dir"]),
            "round_index": diagnostic_session.get("round_index"),
            "max_rounds": diagnostic_session.get("max_rounds"),
            "questions_per_round": diagnostic_session.get("questions_per_round"),
            "follow_up_needed": diagnostic_session.get("follow_up_needed"),
            "stop_reason": diagnostic_session.get("stop_reason"),
            "preflight_valid": False,
            "preflight_blockers": list(diagnostic_session.get("preflight_blockers") or []),
            "preflight_resolution_stage": diagnostic_session.get("preflight_resolution_stage"),
            "preflight_resolution_action": diagnostic_session.get("preflight_resolution_action"),
            "preflight_resolution_message": diagnostic_session.get("preflight_resolution_message"),
            "manual_patch_forbidden_message": diagnostic_session.get("manual_patch_forbidden_message"),
            "stdout": "",
            "stderr": "diagnostic preflight blocked",
            "command": command,
        }
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    return {
        "status": "started" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "session_dir": str(diagnostic_session["session_dir"]),
        "round_index": diagnostic_session.get("round_index"),
        "max_rounds": diagnostic_session.get("max_rounds"),
        "questions_per_round": diagnostic_session.get("questions_per_round"),
        "follow_up_needed": diagnostic_session.get("follow_up_needed"),
        "stop_reason": diagnostic_session.get("stop_reason"),
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
    }



def main() -> int:
    args = parse_args()
    topic = args.topic.strip()
    goal = args.goal.strip()
    level = args.level.strip()
    schedule = (args.schedule or "未指定").strip() or "未指定"
    preference = normalize_preference(args.preference)
    requested_mode = args.mode

    plan_path = Path(args.plan_path).expanduser().resolve()
    if resolve_learning_root(plan_path) == Path.home() and not args.force_home_root:
        print("WARNING: 学习根目录解析为用户主目录，建议 --plan-path 指定项目子目录", file=sys.stderr)
        print("如确认在主目录创建，请添加 --force-home-root", file=sys.stderr)
        return 1
    materials_dir = Path(args.materials_dir).expanduser().resolve() if args.materials_dir else (plan_path.parent / "materials")
    materials_index = materials_dir / "index.json"
    workflow_inputs = load_workflow_inputs(
        plan_path,
        materials_index,
        clarification_path=args.clarification_json,
        research_path=args.research_json,
        diagnostic_path=args.diagnostic_json,
        approval_path=args.approval_json,
    )
    clarification = dict(workflow_inputs.get("clarification") or {})
    research = dict(workflow_inputs.get("research") or {})
    diagnostic = dict(workflow_inputs.get("diagnostic") or {})
    approval = dict(workflow_inputs.get("approval") or {})
    learner_model = dict(workflow_inputs.get("learner_model") or {})
    curriculum_patch_queue = dict(workflow_inputs.get("curriculum_patch_queue") or {})
    existing_workflow_state = dict(workflow_inputs.get("workflow_state") or {})
    existing_workflow_type = str(existing_workflow_state.get("workflow_type") or "").strip()
    workflow_artifacts = workflow_inputs.get("artifacts") or {}
    workflow_paths = workflow_inputs.get("paths") or {}
    research = apply_research_review_confirmation(research, args.confirm_research_review)
    search_context: dict[str, Any] | None = None
    if args.search_context_json:
        try:
            search_context = json.loads(Path(args.search_context_json).read_text(encoding="utf-8"))
        except Exception:
            search_context = None
    injected_stage_candidate = load_optional_payload(args.stage_candidate_json)
    injected_stage_review = load_optional_payload(args.stage_review_json)
    injected_planning_candidate = load_optional_payload(args.planning_candidate_json)
    injected_planning_review = load_optional_payload(args.planning_review_json)
    curriculum_patch_queue, patch_decision_updates = apply_approval_patch_decisions(
        curriculum_patch_queue,
        approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {},
    )
    patch_queue_path = workflow_paths.get("curriculum_patch_queue_json")
    if isinstance(patch_queue_path, Path):
        write_patch_queue(patch_queue_path, curriculum_patch_queue)
    bootstrap_workflow_state = build_workflow_state(
        topic=topic,
        goal=goal,
        requested_mode=requested_mode,
        current_mode=(requested_mode if requested_mode != "auto" else "draft"),
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        quality_issues=[],
        artifacts=workflow_artifacts,
        workflow_type=existing_workflow_type,
    )
    mode = str(bootstrap_workflow_state.get("recommended_mode") or "draft") if requested_mode == "auto" else requested_mode
    active_stage = resolve_stage_mode(mode, bootstrap_workflow_state)
    generated_stage_metadata: dict[str, Any] = {}
    if active_stage in {"clarification", "research", "diagnostic", "approval"}:
        generated_stage_artifact, generated_stage_metadata = maybe_generate_stage_candidate(
            active_stage,
            topic=topic,
            goal=goal,
            level=level,
            schedule=schedule,
            preference=preference,
            clarification=clarification,
            research=research,
            diagnostic=diagnostic,
            approval=approval,
            learner_model=learner_model,
            curriculum_patch_queue=curriculum_patch_queue,
            workflow_state=bootstrap_workflow_state,
            artifacts=workflow_artifacts,
            enable_semantic_review=args.enable_semantic_review,
            search_context=search_context,
            injected_candidate=injected_stage_candidate,
            injected_semantic_review=injected_stage_review,
        )
        generated_stage_review = generated_stage_artifact.get("quality_review") if isinstance(generated_stage_artifact, dict) else {}
        generated_stage_issues = set(normalize_string_list(generated_stage_review.get("issues") if isinstance(generated_stage_review, dict) else []))
        research_renderer_can_complete_presentation = (
            active_stage == "research"
            and isinstance(generated_stage_artifact, dict)
            and isinstance(generated_stage_artifact.get("research_report"), dict)
            and generated_stage_issues.issubset({"research.user_facing_report.html_missing"})
        )
        should_persist_generated_stage = (
            isinstance(generated_stage_artifact, dict)
            and bool(generated_stage_artifact)
            and not generated_stage_artifact.get("candidate_error")
            and (bool(generated_stage_review.get("valid")) or research_renderer_can_complete_presentation)
        )
        if active_stage == "clarification" and should_persist_generated_stage:
            clarification = merge_workflow_candidate(clarification, generated_stage_artifact)
        elif active_stage == "research" and should_persist_generated_stage:
            research = merge_workflow_candidate(research, generated_stage_artifact)
        elif active_stage == "diagnostic" and should_persist_generated_stage:
            diagnostic = merge_workflow_candidate(diagnostic, generated_stage_artifact)
        elif active_stage == "approval" and should_persist_generated_stage:
            approval = merge_workflow_candidate(approval, generated_stage_artifact)

    for artifact_name, artifact_payload in (
        ("clarification_json", clarification),
        ("research_json", research),
        ("diagnostic_json", diagnostic),
        ("approval_json", approval),
    ):
        artifact_path = workflow_paths.get(artifact_name)
        if isinstance(artifact_path, Path) and isinstance(artifact_payload, dict) and artifact_payload:
            write_json(artifact_path, artifact_payload)

    research_report_html_path = workflow_paths.get("research_report_html")
    research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
    if isinstance(research_report_html_path, Path) and research_report:
        user_facing_report = dict(research_report.get("user_facing_report") or {}) if isinstance(research_report.get("user_facing_report"), dict) else {}
        subagent_html_path = str(user_facing_report.get("path") or "").strip()
        subagent_inline_html = str(user_facing_report.get("html") or "").strip()
        research = dict(research)
        research_report = dict(research_report)
        workflow_artifacts = dict(workflow_artifacts)
        if subagent_html_path:
            workflow_artifacts["research_report_html"] = subagent_html_path
            user_facing_report.setdefault("format", "html")
            user_facing_report.setdefault("presentation_source", "subagent_path")
        elif subagent_inline_html:
            write_text(research_report_html_path, subagent_inline_html)
            workflow_artifacts["research_report_html"] = str(research_report_html_path)
            user_facing_report.setdefault("format", "html")
            user_facing_report["path"] = str(research_report_html_path)
            user_facing_report.setdefault("presentation_source", "subagent_inline_html")
        else:
            research_report_html = planning_render_capability_report_html(research_report)
            write_text(research_report_html_path, research_report_html)
            workflow_artifacts["research_report_html"] = str(research_report_html_path)
            user_facing_report.setdefault("format", "html")
            user_facing_report["path"] = str(research_report_html_path)
            user_facing_report["presentation_source"] = "renderer_fallback"
            user_facing_report["semantic_source"] = "agent-subagent"
            user_facing_report["based_on"] = "research_report"
        research_report["user_facing_report"] = user_facing_report
        research["research_report"] = research_report
        research_json_path = workflow_paths.get("research_json")
        if isinstance(research_json_path, Path):
            write_json(research_json_path, research)

    original = read_text_if_exists(plan_path)
    planning_artifact: dict[str, Any] = {}
    planning_generation_metadata: dict[str, Any] = {}
    profile = build_planning_profile(
        topic,
        goal,
        level,
        schedule,
        preference,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=None,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        mode=mode,
    )
    workflow_state = build_workflow_state(
        topic=topic,
        goal=goal,
        requested_mode=requested_mode,
        current_mode=mode,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=None,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        quality_issues=[],
        artifacts=workflow_artifacts,
        workflow_type=existing_workflow_type,
    )
    if generated_stage_metadata:
        workflow_state["active_stage_generation"] = generated_stage_metadata

    if should_build_planning_artifact(workflow_state):
        curriculum = build_curriculum(topic, level, preference)
        planning_artifact, planning_generation_metadata = build_planning_artifact(
            topic,
            goal,
            level,
            schedule,
            preference,
            profile,
            curriculum,
            clarification=clarification,
            research=research,
            diagnostic=diagnostic,
            approval=approval,
            learner_model=learner_model,
            curriculum_patch_queue=curriculum_patch_queue,
            workflow_state=workflow_state,
            artifacts=workflow_artifacts,
            injected_candidate=injected_planning_candidate,
            injected_semantic_review=injected_planning_review,
        )
        profile = dict(profile)
        profile["planning_artifact"] = planning_artifact
        profile["planning_quality_review"] = planning_artifact.get("quality_review") or {}
        if planning_generation_metadata:
            profile["planning_generation_metadata"] = planning_generation_metadata
        if isinstance(planning_artifact.get("plan_candidate"), dict):
            profile["plan_candidate"] = planning_artifact.get("plan_candidate")

    workflow_state = build_workflow_state(
        topic=topic,
        goal=goal,
        requested_mode=requested_mode,
        current_mode=mode,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=planning_artifact,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        quality_issues=[],
        artifacts=workflow_artifacts,
        workflow_type=existing_workflow_type,
    )
    if generated_stage_metadata:
        workflow_state["active_stage_generation"] = generated_stage_metadata
    if planning_artifact:
        workflow_state["planning_artifact"] = planning_artifact

    sections: dict[str, str] = {}
    materials_data: dict[str, Any] = {}
    quality_issues: list[str] = []
    rendered = ""
    consumed_patches: list[dict[str, Any]] = []

    if should_prepare_formal_plan(mode, workflow_state):
        base_sections = build_plan_sections(
            topic,
            goal,
            level,
            schedule,
            preference,
            materials_dir,
            materials_index,
            clarification=clarification,
            research=research,
            diagnostic=diagnostic,
            approval=approval,
            planning=planning_artifact,
            learner_model=learner_model,
            curriculum_patch_queue=curriculum_patch_queue,
            mode=mode,
        )
        sections = {
            "学习画像": base_sections["学习画像"],
            "规划假设与约束": base_sections["规划假设与约束"],
            "能力指标与起点判断": base_sections["能力指标与起点判断"],
            "检索结论与取舍": base_sections["检索结论与取舍"],
            "阶段总览": base_sections["阶段总览"],
            "阶段路线图": base_sections["阶段路线图"],
            "资料清单与阅读定位": base_sections["资料清单与阅读定位"],
            "掌握度检验设计": base_sections["掌握度检验设计"],
            "今日生成规则": base_sections["今日生成规则"],
            "每日推进表": base_sections["每日推进表"],
            "学习记录": choose_existing_section(original, "学习记录", base_sections["学习记录"]),
            "测试记录": choose_existing_section(original, "测试记录", base_sections["测试记录"]),
        }
        existing_index = read_json_if_exists(materials_index)
        materials_data = build_materials_index(topic, goal, level, schedule, preference, materials_dir, plan_path, existing_index)
        quality_issues = validate_plan_quality(sections, materials_data, profile=profile)
        quality_issues = normalize_string_list([
            *quality_issues,
            *(planning_artifact.get("quality_review", {}).get("issues") or []),
        ])
        sections = append_quality_warning(sections, quality_issues)
        rendered = render_plan(topic, goal, level, schedule, preference, sections)

    workflow_state = build_workflow_state(
        topic=topic,
        goal=goal,
        requested_mode=requested_mode,
        current_mode=mode,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning=planning_artifact,
        learner_model=learner_model,
        curriculum_patch_queue=curriculum_patch_queue,
        quality_issues=quality_issues,
        artifacts=workflow_artifacts,
        workflow_type=existing_workflow_type,
    )
    if generated_stage_metadata:
        workflow_state["active_stage_generation"] = generated_stage_metadata
    if planning_artifact:
        workflow_state["planning_artifact"] = planning_artifact
    workflow_state = annotate_formal_plan_gate(workflow_state, mode)
    workflow_state_path = workflow_paths.get("workflow_state_json")
    if isinstance(workflow_state_path, Path):
        write_workflow_state(workflow_state_path, workflow_state)

    allow_formal_plan_write = can_write_formal_plan(workflow_state, mode)
    if allow_formal_plan_write:
        curriculum_patch_queue, consumed_patches = consume_approved_patches(curriculum_patch_queue)
        patch_queue_path = workflow_paths.get("curriculum_patch_queue_json")
        if isinstance(patch_queue_path, Path):
            write_patch_queue(patch_queue_path, curriculum_patch_queue)
        if consumed_patches:
            profile = build_planning_profile(
                topic,
                goal,
                level,
                schedule,
                preference,
                clarification=clarification,
                research=research,
                diagnostic=diagnostic,
                approval=approval,
                planning=planning_artifact,
                learner_model=learner_model,
                curriculum_patch_queue=curriculum_patch_queue,
                mode=mode,
            )
            workflow_state = build_workflow_state(
                topic=topic,
                goal=goal,
                requested_mode=requested_mode,
                current_mode=mode,
                clarification=clarification,
                research=research,
                diagnostic=diagnostic,
                approval=approval,
                planning=planning_artifact,
                learner_model=learner_model,
                curriculum_patch_queue=curriculum_patch_queue,
                quality_issues=quality_issues,
                artifacts=workflow_artifacts,
                workflow_type=existing_workflow_type,
            )
            if generated_stage_metadata:
                workflow_state["active_stage_generation"] = generated_stage_metadata
            if planning_artifact:
                workflow_state["planning_artifact"] = planning_artifact
            workflow_state = annotate_formal_plan_gate(workflow_state, mode)
            if isinstance(workflow_state_path, Path):
                write_workflow_state(workflow_state_path, workflow_state)
            base_sections = build_plan_sections(
                topic,
                goal,
                level,
                schedule,
                preference,
                materials_dir,
                materials_index,
                clarification=clarification,
                research=research,
                diagnostic=diagnostic,
                approval=approval,
                planning=planning_artifact,
                learner_model=learner_model,
                curriculum_patch_queue=curriculum_patch_queue,
                mode=mode,
            )
            sections = {
                "学习画像": base_sections["学习画像"],
                "规划假设与约束": base_sections["规划假设与约束"],
                "能力指标与起点判断": base_sections["能力指标与起点判断"],
                "检索结论与取舍": base_sections["检索结论与取舍"],
                "阶段总览": base_sections["阶段总览"],
                "阶段路线图": base_sections["阶段路线图"],
                "资料清单与阅读定位": base_sections["资料清单与阅读定位"],
                "掌握度检验设计": base_sections["掌握度检验设计"],
                "今日生成规则": base_sections["今日生成规则"],
                "每日推进表": base_sections["每日推进表"],
                "学习记录": choose_existing_section(original, "学习记录", base_sections["学习记录"]),
                "测试记录": choose_existing_section(original, "测试记录", base_sections["测试记录"]),
            }
            sections = append_quality_warning(sections, quality_issues)
            rendered = render_plan(topic, goal, level, schedule, preference, sections)
        public_plan_issues = review_public_plan_markdown(rendered)
        if public_plan_issues:
            quality_issues = normalize_string_list([*quality_issues, *public_plan_issues])
            workflow_state["formal_plan_gate"] = {
                **(workflow_state.get("formal_plan_gate") or {}),
                "public_plan_hygiene_issues": public_plan_issues,
                "can_write_formal_plan": False,
            }
            if isinstance(workflow_state_path, Path):
                write_workflow_state(workflow_state_path, workflow_state)
        else:
            write_text(plan_path, rendered)
            write_json(materials_index, materials_data)

    download_result = None
    should_download = allow_formal_plan_write and not args.skip_material_download
    if should_download:
        download_result = process_materials(
            materials_dir,
            None,
            force=False,
            dry_run=False,
            timeout=args.download_timeout,
        )

    diagnostic_session_result = None
    if str(workflow_state.get("blocking_stage") or "") == "diagnostic":
        diagnostic_session_payload = build_diagnostic_session_payload(
            topic=topic,
            plan_path=plan_path,
            clarification=clarification,
            diagnostic=diagnostic,
            workflow_state=workflow_state,
        )
        if diagnostic_session_payload.get("preflight_valid"):
            diagnostic_session_result = launch_diagnostic_session(
                topic=topic,
                plan_path=plan_path,
                diagnostic_session=diagnostic_session_payload,
            )
        else:
            diagnostic_session_result = {
                "status": "blocked",
                "returncode": 2,
                "session_dir": str(diagnostic_session_payload.get("session_dir")),
                "round_index": diagnostic_session_payload.get("round_index"),
                "max_rounds": diagnostic_session_payload.get("max_rounds"),
                "questions_per_round": diagnostic_session_payload.get("questions_per_round"),
                "follow_up_needed": diagnostic_session_payload.get("follow_up_needed"),
                "stop_reason": diagnostic_session_payload.get("stop_reason"),
                "preflight_valid": False,
                "preflight_blockers": list(diagnostic_session_payload.get("preflight_blockers") or []),
                "preflight_resolution_stage": diagnostic_session_payload.get("preflight_resolution_stage"),
                "preflight_resolution_action": diagnostic_session_payload.get("preflight_resolution_action"),
                "preflight_resolution_message": diagnostic_session_payload.get("preflight_resolution_message"),
                "manual_patch_forbidden_message": diagnostic_session_payload.get("manual_patch_forbidden_message"),
                "stdout": "",
                "stderr": "diagnostic preflight blocked",
            }

    print_summary(
        topic,
        goal,
        plan_path,
        materials_dir,
        materials_index,
        stdout_json=args.stdout_json,
        requested_mode=requested_mode,
        mode=mode,
        workflow_state=workflow_state,
        planning_state=profile.get("planning_state") if isinstance(profile, dict) else {},
        download_result=download_result,
        auto_download_enabled=should_download,
        quality_issues=quality_issues,
        diagnostic_session=diagnostic_session_result,
    )
    if diagnostic_session_result is not None and diagnostic_session_result.get("status") == "blocked":
        print("diagnostic 启动前自检未通过。")
        print(f"当前只应处理的 workflow 阶段：{diagnostic_session_result.get('preflight_resolution_stage') or workflow_state.get('actionable_stage') or workflow_state.get('blocking_stage') or 'diagnostic'}")
        print(f"下一步动作：{diagnostic_session_result.get('preflight_resolution_action') or workflow_state.get('next_action') or 'switch_to:diagnostic'}")
        blockers = [item for item in (_humanize_workflow_issue(item) for item in (diagnostic_session_result.get("preflight_blockers") or [])) if item]
        if blockers:
            print("当前需补齐：" + "；".join(blockers))
        resolution_message = str(diagnostic_session_result.get("preflight_resolution_message") or workflow_state.get("workflow_instruction") or "").strip()
        if resolution_message:
            print(f"执行约束：{resolution_message}")
        forbidden_message = str(diagnostic_session_result.get("manual_patch_forbidden_message") or workflow_state.get("manual_patch_warning") or "").strip()
        if forbidden_message:
            print(f"禁止事项：{forbidden_message}")
        return int(diagnostic_session_result.get("returncode") or 2)
    if diagnostic_session_result is not None and diagnostic_session_result.get("status") != "started":
        stdout = diagnostic_session_result.get("stdout") or ""
        stderr = diagnostic_session_result.get("stderr") or ""
        print("诊断网页 session 启动失败。")
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        return int(diagnostic_session_result.get("returncode") or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
