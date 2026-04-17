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
    render_daily_roadmap as planning_render_daily_roadmap,
    render_learning_route as planning_render_learning_route,
    render_mastery_checks as planning_render_mastery_checks,
    render_materials_section as planning_render_materials_section,
    render_plan as planning_render_plan,
    render_plan_report as planning_render_plan_report,
    render_planning_constraints as planning_render_planning_constraints,
    render_planning_profile as planning_render_planning_profile,
    render_stage_overview as planning_render_stage_overview,
    render_today_generation_rules as planning_render_today_generation_rules,
    validate_plan_quality as planning_validate_plan_quality,
)
from learn_workflow import (
    annotate_formal_plan_gate,
    build_stage_context,
    build_workflow_state,
    can_write_formal_plan,
    generate_stage_candidate,
    load_workflow_inputs,
    review_stage_candidate,
    resolve_assessment_depth_preference,
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
                "cache_note": "在线词典，建议在线使用",
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
                "cache_note": "在线内容，可手动保存特定文章",
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
                "cache_note": "权威写作指南，建议在线查阅",
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
                "cache_note": "音频与文本内容，建议在线使用",
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
                "cache_note": "需认证访问，不支持自动下载",
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
                "cache_note": "可手动下载 PDF 版本",
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
                "cache_note": "支持 PDF 下载，可手动获取",
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
                "cache_note": "视频内容，建议在线观看",
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
                "cache_note": "需认证访问，不支持自动下载",
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
                "cache_note": "站点内容适合做知识参考，可手动下载特定页面",
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
                "cache_note": "动态内容，不支持自动下载",
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
                "cache_note": "交互式内容，建议在线使用",
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
                "cache_note": "课程站点，建议在线学习",
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
                "cache_note": "官方手册，适合查阅",
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
                "cache_note": "在线文档，建议按专题阅读",
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
                "cache_note": "在线示例库，适合高频查询",
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
                "cache_note": "官方文档，建议按 Prompt / RAG / Tools / Agents 模块阅读",
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
                "cache_note": "官方文档，适合在理解 LangChain 基础后继续阅读",
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
                "cache_note": "官方文档，适合查 API 设计与应用模式",
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
                "cache_note": "示例型文档，适合作为对照案例阅读",
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
                "cache_note": "权威 HTTP 入门参考",
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
                "cache_note": "官方文档，适合作实战参考",
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
                "cache_note": "权威前端参考文档",
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
                "cache_note": "官方文档，适合按专题练习",
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
                "cache_note": "官方文档，适合参考",
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
                "cache_note": "交互式网站，建议在线使用",
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
                "cache_note": "若本地已有 PDF，可在 materials/index.json 中自动标记。",
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
                "cache_note": "若本地已有 PDF，可在 materials/index.json 中自动标记。",
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
                "cache_note": "若本地已有 PDF，可在 materials/index.json 中自动标记。",
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
                "cache_note": "官方在线教程。",
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
                "cache_note": "官方在线文档。",
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
                "cache_note": "权威 HTTP 参考",
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
                "cache_note": "适合工程通识打底",
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
                "cache_note": "官方在线书籍，适合系统阅读",
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
    parser.add_argument("--download-timeout", type=int, default=30, help="自动下载材料的超时时间（秒）")
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


def write_text(path: Path, content: str) -> None:
    core_write_text(path, content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    core_write_json(path, data)


def normalize_preference(value: str) -> str:
    value = (value or "").strip()
    if value in VALID_PREFERENCES:
        return value
    return "混合"


def recommend_workflow_mode(topic: str, goal: str, clarification: dict[str, Any], research: dict[str, Any], diagnostic: dict[str, Any], approval: dict[str, Any], requested_mode: str) -> tuple[str, list[str], str]:
    reasons: list[str] = []
    normalized_goal = f"{topic} {goal}".lower()
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    assessment_depth_preference = resolve_assessment_depth_preference(clarification, diagnostic)

    has_open_questions = bool(clarification_state.get("open_questions"))
    preference_pending = not preference_state or bool(preference_state.get("pending_items"))
    depth_choice_required = assessment_depth_preference not in {"simple", "deep"}
    needs_research = any(keyword in normalized_goal for keyword in ["工作", "就业", "转岗", "面试", "岗位", "求职", "职业", "大模型", "llm", "agent", "rag"]) \
        or any(keyword in normalized_goal for keyword in ["langchain", "langgraph", "模型应用", "应用开发"])
    level_uncertain = any(keyword in normalized_goal for keyword in ["不确定", "说不清", "不清楚", "不会判断", "不知道自己什么水平"]) \
        or not diagnostic

    if has_open_questions:
        reasons.append("仍存在待澄清问题，应优先补齐顾问式澄清")
        return "draft", reasons, "clarification"
    if preference_pending:
        reasons.append("学习风格与练习方式尚未确认，应先补齐 preference confirmation")
        return "draft", reasons, "preference"
    if depth_choice_required:
        reasons.append("起始测评深度尚未确认，应先让用户明确选择 simple 或 deep；在此之前不能默认进入简单测评")
        return "draft", reasons, "clarification"

    if needs_research and not research and level_uncertain:
        reasons.append("目标带有明显职业导向，且当前水平不稳定，应先进入 mixed：先研究再诊断")
        return "research-report", reasons, "research"
    if needs_research and not research:
        reasons.append("目标带有明显职业导向，应优先确认外部能力标准与材料取舍")
        return "research-report", reasons, "research"
    if level_uncertain and not diagnostic:
        reasons.append(f"当前水平仍不可靠，应优先发起 {assessment_depth_preference} 起始测试网页 session，让用户先作答再分析结果")
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



def render_stage_overview(curriculum: dict[str, Any]) -> str:
    return planning_render_stage_overview(curriculum)



def render_learning_route(curriculum: dict[str, Any]) -> str:
    return planning_render_learning_route(curriculum)



def render_daily_roadmap(curriculum: dict[str, Any]) -> str:
    return planning_render_daily_roadmap(curriculum)



def render_materials_section(curriculum: dict[str, Any], materials_dir: Path, materials_index: Path) -> str:
    return planning_render_materials_section(
        curriculum,
        materials_dir,
        materials_index,
        family_configs=TOPIC_FAMILIES,
    )



def infer_material_recommended_day(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[str]:
    return materials_infer_material_recommended_day(entry, curriculum)



def enrich_material_entry(entry: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    return materials_enrich_material_entry(entry, curriculum)


def build_planning_profile(topic: str, goal: str, level: str, schedule: str, preference: str, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, planning: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, Any]:
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



def merge_workflow_candidate(existing: dict[str, Any] | None, generated: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(generated, dict) or not generated:
        return dict(existing or {})
    merged = dict(existing or {})
    if "candidate_error" in merged and "candidate_error" not in generated:
        merged.pop("candidate_error", None)
    for key, value in generated.items():
        merged[key] = value
    return merged



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
    workflow_state: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_context = build_stage_context(
        "planning",
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        clarification=clarification or {},
        research=research or {},
        diagnostic=diagnostic or {},
        approval=approval or {},
        workflow_state=workflow_state or {},
        artifacts={
            **(artifacts or {}),
            "planning_profile": profile,
            "curriculum": curriculum,
        },
    )
    candidate, metadata = generate_stage_candidate(
        "planning",
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        context=stage_context,
        existing_state={
            "planning_profile": profile,
            "curriculum": curriculum,
        },
    )
    if not isinstance(candidate, dict):
        fallback = build_plan_candidate(profile, curriculum)
        fallback["fallback_metadata"] = metadata
        fallback["evidence"] = normalize_string_list(
            list(fallback.get("evidence") or [])
            + [f"planning_fallback_status={metadata.get('status') or 'candidate_generation_failed'}"]
        )
        reviewed = review_stage_candidate("planning", fallback)
        reviewed["stage"] = "planning"
        reviewed["candidate_version"] = reviewed.get("candidate_version") or fallback.get("generation_trace", {}).get("prompt_version")
        reviewed["generation_mode"] = "deterministic-fallback"
        return reviewed, metadata

    reviewed = review_stage_candidate("planning", candidate)
    reviewed["stage"] = "planning"
    reviewed["candidate_version"] = reviewed.get("candidate_version") or candidate.get("candidate_version") or candidate.get("generation_trace", {}).get("prompt_version")
    reviewed["generation_mode"] = "llm-candidate"
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
    workflow_state: dict[str, Any],
    artifacts: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not stage:
        return None, {}
    stage_context = build_stage_context(
        stage,
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        workflow_state=workflow_state,
        artifacts=artifacts,
    )
    existing_state = {
        "clarification": clarification,
        "research": research,
        "diagnostic": diagnostic,
        "approval": approval,
    }.get(stage) or {}
    candidate, metadata = generate_stage_candidate(
        stage,
        topic=topic,
        goal=goal,
        level=level,
        schedule=schedule,
        preference=preference,
        context=stage_context,
        existing_state=existing_state,
    )
    if candidate is None:
        if isinstance(existing_state, dict) and existing_state:
            preserved = dict(existing_state)
            preserved.pop("candidate_error", None)
            preserved["stage"] = stage
            return review_stage_candidate(stage, preserved), metadata
        fallback = apply_quality_envelope(
            {
                "stage": stage,
                "candidate_error": {
                    "message": "candidate_generation_failed",
                    "metadata": metadata,
                },
            },
            stage=stage,
            generator=f"stage-candidate:{stage}",
            evidence=normalize_string_list(
                [
                    f"stage={stage}",
                    f"generation_status={metadata.get('status') or 'failed'}",
                    f"mode={metadata.get('mode') or 'stage-candidate'}",
                ]
            ),
            confidence=0.0,
            quality_review={
                "reviewer": "stage-generator-fallback",
                "valid": False,
                "issues": [f"{stage}.candidate_generation_failed"],
                "warnings": [],
                "confidence": 0.0,
                "verdict": "needs-revision",
                "evidence_adequacy": "partial",
            },
            generation_trace=metadata,
            traceability=[
                build_traceability_entry(
                    kind="stage-candidate",
                    ref=stage,
                    title=f"{stage} candidate generation failed",
                    stage=stage,
                    status=str(metadata.get("status") or "failed"),
                )
            ],
        )
        return review_stage_candidate(stage, fallback), metadata
    return review_stage_candidate(stage, candidate), metadata



def build_plan_sections(topic: str, goal: str, level: str, schedule: str, preference: str, materials_dir: Path, materials_index: Path, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, planning: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, str]:
    curriculum = build_curriculum(topic, level, preference)
    profile = build_planning_profile(topic, goal, level, schedule, preference, clarification=clarification, research=research, diagnostic=diagnostic, approval=approval, planning=planning, mode=mode)
    report = build_plan_report(profile, curriculum)
    return {
        "学习画像": render_planning_profile(profile),
        "规划假设与约束": render_planning_constraints(profile),
        "能力指标与起点判断": render_capability_model_section(profile),
        "检索结论与取舍": render_plan_report(report),
        "阶段总览": render_stage_overview(curriculum),
        "阶段路线图": render_learning_route(curriculum),
        "资料清单与阅读定位": render_materials_section(curriculum, materials_dir, materials_index),
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
    assessment_depth_choice_required = "clarification.assessment_depth_preference" in list(workflow_state.get("missing_requirements") or [])
    summary = {
        "topic": topic,
        "requested_mode": requested_mode,
        "mode": mode,
        "recommended_mode": recommended_mode,
        "blocking_stage": blocking_stage,
        "routing_reasons": routing_reasons,
        "assessment_depth_choice_required": assessment_depth_choice_required,
        "diagnostic_delivery": "web-session",
        "diagnostic_update_entrypoint": "/learn-test-update",
        "is_intermediate_product": is_intermediate_product,
        "should_continue_workflow": should_continue_workflow,
        "next_action": next_action,
        "workflow_loop_hint": "若 should_continue_workflow 为 true，则外层应继续下一轮澄清/research/diagnostic/approval；仅当 next_action = enter:/learn-today 时才退出 /learn-plan 工作流。",
        "plan_path": str(plan_path),
        "materials_dir": str(materials_dir),
        "materials_index": str(materials_index),
        "planning_state": planning_state or {},
        "next_step": next_step_by_mode.get(mode, "/learn-today"),
        "quality_issues": quality_issues,
        "formal_plan_write_allowed": bool(workflow_state.get("formal_plan_write_allowed")),
        "formal_plan_write_blockers": list(workflow_state.get("formal_plan_write_blockers") or []),
    }
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
    blocking_reasons = quality_issues or list(workflow_state.get("missing_requirements") or []) or routing_reasons
    formal_plan_write_allowed = bool(workflow_state.get("formal_plan_write_allowed"))
    formal_plan_write_blockers = list(workflow_state.get("formal_plan_write_blockers") or [])
    if should_continue_workflow:
        print("计划状态：草案 / 待确认 / 待补条件")
        if blocking_reasons:
            print("阻塞原因：" + "；".join(str(item) for item in blocking_reasons))
        print(f"下一步建议：先切换到 {recommended_mode} mode，继续补齐 gate")
        if assessment_depth_choice_required:
            print("测评深度选择：必须先让用户选择 simple 或 deep；未选择前不得默认进入简单测评")
        if blocking_stage == "diagnostic":
            print("诊断交付：使用 initial-test 网页 session，让用户在网站作答后再执行 /learn-test-update")
        if is_intermediate_product:
            print("当前交付：这是中间产物，不应直接当作正式主线计划执行")
    else:
        print("计划状态：可作为正式学习计划")
        print(f"下一步建议：{next_step_by_mode.get(mode, '/learn-today')}")
    if not formal_plan_write_allowed:
        print("正式计划写入：已阻止")
        if formal_plan_write_blockers:
            print("写入阻止原因：" + "；".join(str(item) for item in formal_plan_write_blockers))
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
    mastery_preferences = questionnaire.get("mastery_preferences") if isinstance(questionnaire.get("mastery_preferences"), dict) else {}
    diagnostic_plan = diagnostic.get("diagnostic_plan") if isinstance(diagnostic.get("diagnostic_plan"), dict) else {}
    diagnostic_result = diagnostic.get("diagnostic_result") if isinstance(diagnostic.get("diagnostic_result"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}

    assessment_depth = str(
        diagnostic_plan.get("assessment_depth")
        or diagnostic_profile.get("assessment_depth")
        or mastery_preferences.get("assessment_depth_preference")
        or "simple"
    ).strip()
    if assessment_depth not in {"simple", "deep"}:
        assessment_depth = "simple"

    round_index_raw = diagnostic_plan.get("round_index") or diagnostic_profile.get("round_index") or 1
    max_rounds_raw = diagnostic_plan.get("max_rounds") or diagnostic_profile.get("max_rounds") or round_index_raw or 1
    try:
        round_index = max(1, int(round_index_raw))
    except (TypeError, ValueError):
        round_index = 1
    try:
        max_rounds = max(round_index, int(max_rounds_raw))
    except (TypeError, ValueError):
        max_rounds = round_index

    follow_up_needed = diagnostic_result.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = diagnostic_profile.get("follow_up_needed")
    if follow_up_needed is None:
        follow_up_needed = round_index < max_rounds

    stop_reason = str(
        diagnostic_result.get("stop_reason")
        or diagnostic_plan.get("status")
        or diagnostic_profile.get("status")
        or "diagnostic-pending"
    ).strip()

    focus_dimensions = normalize_string_list(diagnostic_profile.get("dimensions") or [])
    observed_weaknesses = normalize_string_list(diagnostic_result.get("observed_weaknesses") or diagnostic_profile.get("observed_weaknesses") or [])
    observed_strengths = normalize_string_list(diagnostic_result.get("observed_strengths") or diagnostic_profile.get("observed_strengths") or [])
    target_capability_ids = normalize_string_list(diagnostic_plan.get("target_capability_ids") or [])
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

    today = time.strftime("%Y-%m-%d")
    session_suffix = "-test" if round_index <= 1 else f"-test-round-{round_index}"
    session_dir = plan_path.parent / "sessions" / f"{today}{session_suffix}"
    return {
        "session_dir": session_dir,
        "assessment_depth": assessment_depth,
        "round_index": round_index,
        "max_rounds": max_rounds,
        "follow_up_needed": bool(follow_up_needed),
        "stop_reason": stop_reason,
        "current_stage": str(workflow_state.get("blocking_stage") or "diagnostic"),
        "current_day": f"Diagnostic Round {round_index}",
        "today_topic": f"{topic} 起始诊断",
        "review": review_points,
        "new_learning": new_learning_points,
        "exercise_focus": exercise_focus,
        "time_budget": str(diagnostic_plan.get("estimated_time") or "").strip() or None,
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
        "--assessment-depth",
        str(diagnostic_session.get("assessment_depth") or "simple"),
        "--round-index",
        str(diagnostic_session.get("round_index") or 1),
        "--max-rounds",
        str(diagnostic_session.get("max_rounds") or 1),
        "--stop-reason",
        str(diagnostic_session.get("stop_reason") or "diagnostic-pending"),
    ]
    if diagnostic_session.get("follow_up_needed"):
        command.append("--follow-up-needed")
    if diagnostic_session.get("time_budget"):
        command.extend(["--time-budget", str(diagnostic_session["time_budget"])])
    for value in diagnostic_session.get("review") or []:
        command.extend(["--review", str(value)])
    for value in diagnostic_session.get("new_learning") or []:
        command.extend(["--new-learning", str(value)])
    for value in diagnostic_session.get("exercise_focus") or []:
        command.extend(["--exercise-focus", str(value)])

    result = subprocess.run(command, check=False, capture_output=True, text=True)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    return {
        "status": "started" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "session_dir": str(diagnostic_session["session_dir"]),
        "assessment_depth": diagnostic_session.get("assessment_depth"),
        "round_index": diagnostic_session.get("round_index"),
        "max_rounds": diagnostic_session.get("max_rounds"),
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
    workflow_artifacts = workflow_inputs.get("artifacts") or {}
    bootstrap_workflow_state = build_workflow_state(
        topic=topic,
        goal=goal,
        requested_mode=requested_mode,
        current_mode=(requested_mode if requested_mode != "auto" else "draft"),
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        quality_issues=[],
        artifacts=workflow_artifacts,
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
            workflow_state=bootstrap_workflow_state,
            artifacts=workflow_artifacts,
        )
        if active_stage == "clarification" and generated_stage_artifact:
            clarification = merge_workflow_candidate(clarification, generated_stage_artifact)
        elif active_stage == "research" and generated_stage_artifact:
            research = merge_workflow_candidate(research, generated_stage_artifact)
        elif active_stage == "diagnostic" and generated_stage_artifact:
            diagnostic = merge_workflow_candidate(diagnostic, generated_stage_artifact)
        elif active_stage == "approval" and generated_stage_artifact:
            approval = merge_workflow_candidate(approval, generated_stage_artifact)

    workflow_paths = workflow_inputs.get("paths") or {}
    for artifact_name, artifact_payload in (
        ("clarification_json", clarification),
        ("research_json", research),
        ("diagnostic_json", diagnostic),
        ("approval_json", approval),
    ):
        artifact_path = workflow_paths.get(artifact_name)
        if isinstance(artifact_path, Path) and isinstance(artifact_payload, dict) and artifact_payload:
            write_json(artifact_path, artifact_payload)

    original = read_text_if_exists(plan_path)
    curriculum = build_curriculum(topic, level, preference)
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
        mode=mode,
    )
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
        workflow_state=bootstrap_workflow_state,
        artifacts=workflow_artifacts,
    )
    profile = dict(profile)
    profile["planning_artifact"] = planning_artifact
    profile["planning_quality_review"] = planning_artifact.get("quality_review") or {}
    if planning_generation_metadata:
        profile["planning_generation_metadata"] = planning_generation_metadata
    if isinstance(planning_artifact.get("plan_candidate"), dict):
        profile["plan_candidate"] = planning_artifact.get("plan_candidate")

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
        quality_issues=quality_issues,
        artifacts=workflow_artifacts,
    )
    if generated_stage_metadata:
        workflow_state["active_stage_generation"] = generated_stage_metadata
    workflow_state["planning_artifact"] = planning_artifact
    workflow_state = annotate_formal_plan_gate(workflow_state, mode)
    workflow_state_path = workflow_paths.get("workflow_state_json")
    if isinstance(workflow_state_path, Path):
        write_workflow_state(workflow_state_path, workflow_state)
    sections = append_quality_warning(sections, quality_issues)

    rendered = render_plan(topic, goal, level, schedule, preference, sections)
    allow_formal_plan_write = can_write_formal_plan(workflow_state, mode)
    if allow_formal_plan_write:
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
        diagnostic_session_result = launch_diagnostic_session(
            topic=topic,
            plan_path=plan_path,
            diagnostic_session=diagnostic_session_payload,
        )

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
