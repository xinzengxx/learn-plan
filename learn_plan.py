#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from material_downloader import process_materials


VALID_PREFERENCES = {"偏题海", "偏讲解", "偏测试", "混合"}

TOPIC_PROFILE_FILE_CANDIDATES = (
    ".learn-plan-topic-profile.json",
    "topic-profile.json",
)


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
    "git": {
        "keywords": ["Git", "git", "版本控制", "version control", "commit", "branch", "merge", "rebase", "GitHub", "github", "pull request", "PR"],
        "stages": [
            ("阶段 1", "Git 心智模型", "建立仓库、工作区、暂存区、提交、HEAD、分支这些基础心智模型", "概念辨析题 + status 观察题 + 最小仓库演示", "能解释 add、commit、HEAD、branch 的作用与区别后进入下一阶段"),
            ("阶段 2", "本地版本管理闭环", "掌握 status、diff、add、commit、log、restore 等个人项目常用闭环", "顺序操作题 + 误操作恢复题 + 小型本地仓库练习", "能独立完成修改、暂存、提交、查看历史与撤销修改闭环后进入下一阶段"),
            ("阶段 3", "分支与远程协作", "掌握 branch、switch、merge、clone、fetch、pull、push 与 GitHub flow 的最小协作闭环", "分支练习 + 远程同步题 + PR 流程复盘", "能完成功能分支开发并说清远程协作最小闭环后进入下一阶段"),
            ("阶段 4", "冲突处理与进阶入口", "掌握基础冲突处理与常见报错直觉，并建立 rebase / stash / internals 的用途感", "冲突场景题 + 同步失败恢复题 + 进阶主题识别题", "能完成一次基础冲突处理并判断哪些进阶主题当前可后置"),
        ],
        "materials": [
            {
                "id": "git-pro-git-book",
                "title": "Pro Git Book",
                "kind": "book",
                "source_name": "Pro Git",
                "source_type": "official",
                "url": "https://git-scm.com/book/en/v2",
                "use": "系统学习 Git 心智模型、本地工作流、分支协作与 GitHub 相关内容。",
                "cache_status": "metadata-only",
                "local_path": None,
                "cache_note": "若本地已克隆官方仓库或下载离线版本，可作为正式主线。",
                "tags": ["git", "version-control", "book"],
                "downloadable": False,
            },
            {
                "id": "git-missing-semester",
                "title": "The Missing Semester - Version Control",
                "kind": "tutorial",
                "source_name": "MIT",
                "source_type": "official",
                "url": "https://missing.csail.mit.edu/2020/version-control/",
                "use": "补 Git 快照、提交图、引用与最小工作流心智模型。",
                "cache_status": "metadata-only",
                "local_path": None,
                "cache_note": "若本地已克隆 Missing Semester 仓库，可离线阅读。",
                "tags": ["git", "tutorial", "mental-model"],
                "downloadable": False,
            },
            {
                "id": "git-github-flow",
                "title": "GitHub Flow and Hello World",
                "kind": "reference",
                "source_name": "GitHub Docs",
                "source_type": "official",
                "url": "https://docs.github.com/en/get-started/start-your-journey/hello-world",
                "use": "补 Pull Request、分支协作与 GitHub flow 的最小协作流程。",
                "cache_status": "metadata-only",
                "local_path": None,
                "cache_note": "官方在线文档，适合作为补充参考。",
                "tags": ["git", "github", "workflow"],
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
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if path.exists() and path.is_file():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}



def load_optional_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    return read_json_if_exists(path)


def load_workflow_json_with_fallback(explicit_path: str | None, base_dir: Path, *candidate_names: str) -> dict[str, Any]:
    if explicit_path:
        return load_optional_json(explicit_path)
    for name in candidate_names:
        candidate = base_dir / name
        data = read_json_if_exists(candidate)
        if data:
            return data
    return {}


def normalize_topic_profile(profile: dict[str, Any], topic: str) -> dict[str, Any]:
    if not isinstance(profile, dict) or not profile:
        return {}
    normalized = json.loads(json.dumps(profile))
    normalized_topic = str(normalized.get("topic") or topic).strip() or topic
    normalized["topic"] = normalized_topic
    domain = str(normalized.get("domain") or normalized.get("family") or "").strip()
    if domain:
        normalized["domain"] = domain
        normalized["family"] = domain
    stages = normalized.get("stages")
    if isinstance(stages, list):
        cleaned_stages = []
        for index, stage in enumerate(stages, start=1):
            if isinstance(stage, dict):
                name = str(stage.get("name") or f"阶段 {index}").strip() or f"阶段 {index}"
                focus = str(stage.get("focus") or stage.get("title") or name).strip() or name
                goal = str(stage.get("goal") or focus).strip() or focus
                practice = str(stage.get("practice") or stage.get("practice_hint") or "概念题 + 小练习").strip() or "概念题 + 小练习"
                test_gate = str(stage.get("test_gate") or stage.get("mastery_gate") or f"完成 {name} 掌握检验后进入下一阶段").strip() or f"完成 {name} 掌握检验后进入下一阶段"
                cleaned_stages.append({
                    "name": name,
                    "focus": focus,
                    "goal": goal,
                    "practice": practice,
                    "test_gate": test_gate,
                    "reading": normalize_string_list(stage.get("reading") or stage.get("materials") or []),
                    "exercise_types": normalize_string_list(stage.get("exercise_types") or stage.get("exercise_focus") or []),
                    "future_use": str(stage.get("future_use") or goal).strip() or goal,
                })
        normalized["stages"] = cleaned_stages
    daily_templates = normalized.get("daily_templates")
    if isinstance(daily_templates, list):
        cleaned_days = []
        for index, day in enumerate(daily_templates, start=1):
            if not isinstance(day, dict):
                continue
            label = str(day.get("day") or day.get("label") or f"Day {index}").strip() or f"Day {index}"
            cleaned_days.append({
                "day": label,
                "当前阶段": str(day.get("当前阶段") or day.get("current_stage") or "阶段 1").strip() or "阶段 1",
                "今日主题": str(day.get("今日主题") or day.get("today_topic") or normalized_topic).strip() or normalized_topic,
                "复习点": str(day.get("复习点") or day.get("review") or "").strip(),
                "新学习点": str(day.get("新学习点") or day.get("new_learning") or "").strip(),
                "练习重点": str(day.get("练习重点") or day.get("exercise_focus") or "").strip(),
                "推荐材料": str(day.get("推荐材料") or day.get("recommended_materials") or "").strip(),
                "难度目标": str(day.get("难度目标") or day.get("difficulty_target") or "concept easy/medium，code easy").strip() or "concept easy/medium，code easy",
            })
        normalized["daily_templates"] = cleaned_days
    return normalized


def load_topic_profile(plan_path: Path, topic: str) -> dict[str, Any]:
    for name in TOPIC_PROFILE_FILE_CANDIDATES:
        candidate = plan_path.parent / name
        data = read_json_if_exists(candidate)
        if data:
            return normalize_topic_profile(data, topic)
    return {}


def resolve_material_local_path(entry: dict[str, Any]) -> Path | None:
    for value in [entry.get("local_path"), ((entry.get("local_artifact") or {}).get("path") if isinstance(entry.get("local_artifact"), dict) else None)]:
        text = str(value or "").strip()
        if text:
            return Path(text).expanduser()
    return None


def recompute_material_runtime_fields(entry: dict[str, Any], materials_dir: Path | None = None) -> dict[str, Any]:
    updated = json.loads(json.dumps(entry))
    path_candidates: list[Path] = []
    resolved = resolve_material_local_path(updated)
    if resolved is not None:
        path_candidates.append(resolved)
    local_artifact = updated.get("local_artifact") if isinstance(updated.get("local_artifact"), dict) else {}
    artifact_path = str(local_artifact.get("path") or "").strip() if local_artifact else ""
    if artifact_path:
        path_candidates.append(Path(artifact_path).expanduser())
    local_path_text = str(updated.get("local_path") or "").strip()
    if local_path_text:
        path_candidates.append(Path(local_path_text).expanduser())

    existing_path = next((candidate for candidate in path_candidates if candidate.exists()), None)
    exists_locally = existing_path is not None
    downloadable = bool(updated.get("downloadable"))
    source_type = str(updated.get("source_type") or "").strip()
    is_local_source = source_type == "local"

    if exists_locally:
        canonical_path = str(existing_path)
        updated["local_path"] = canonical_path
        artifact = dict(local_artifact) if local_artifact else {}
        artifact["path"] = canonical_path
        artifact["file_type"] = existing_path.suffix.lstrip(".") or ("dir" if existing_path.is_dir() else None)
        artifact.setdefault("downloaded_at", time.strftime("%Y-%m-%d"))
        updated["local_artifact"] = artifact
        updated["exists_locally"] = True
        updated["cache_status"] = "cached"
        updated["availability"] = "cached"
        updated["selection_status"] = "confirmed"
        updated["role_in_plan"] = str(updated.get("role_in_plan") or "mainline")
        if updated["role_in_plan"] == "optional":
            updated["role_in_plan"] = "mainline"
        updated["discovery_notes"] = "主线资料：已检测到本地缓存文件，可作为正式学习材料。"
        updated["cache_note"] = str(updated.get("cache_note") or "已检测到本地缓存文件")
    else:
        updated["exists_locally"] = False
        if downloadable or is_local_source:
            updated["availability"] = "local-downloadable"
            updated["selection_status"] = "confirmed"
            updated["role_in_plan"] = "mainline"
            updated.setdefault("cache_status", "metadata-only")
            updated["discovery_notes"] = "主线资料：可下载或应补充本地文件后正式使用。"
        else:
            updated["availability"] = "metadata-only"
            updated["selection_status"] = "candidate"
            updated["role_in_plan"] = "optional"
            updated.setdefault("cache_status", "metadata-only")
            updated["discovery_notes"] = "候选资料：当前无法直接落地到本地，仅作补充参考，不应直接进入主线。"
    return updated


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_preference(value: str) -> str:
    value = (value or "").strip()
    if value in VALID_PREFERENCES:
        return value
    return "混合"


def normalize_string_list(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def recommend_workflow_mode(topic: str, goal: str, clarification: dict[str, Any], research: dict[str, Any], diagnostic: dict[str, Any], approval: dict[str, Any], requested_mode: str) -> tuple[str, list[str], str]:
    reasons: list[str] = []
    normalized_goal = f"{topic} {goal}".lower()
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}

    has_open_questions = bool(clarification_state.get("open_questions"))
    preference_pending = not preference_state or bool(preference_state.get("pending_items"))
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

    if needs_research and not research and level_uncertain:
        reasons.append("目标带有明显职业导向，且当前水平不稳定，应先进入 mixed：先研究再诊断")
        return "research-report", reasons, "research"
    if needs_research and not research:
        reasons.append("目标带有明显职业导向，应优先确认外部能力标准与材料取舍")
        return "research-report", reasons, "research"
    if level_uncertain and not diagnostic:
        reasons.append("当前水平仍不可靠，应优先完成最小水平诊断")
        return "diagnostic", reasons, "diagnostic"

    if requested_mode == "finalize" and not approval_state.get("ready_for_execution"):
        reasons.append("当前未满足 ready_for_execution，finalize 仍会被 gate 拦住")
        return "draft", reasons, "approval"
    if approval_state.get("ready_for_execution"):
        return "finalize", reasons, "ready"
    return (requested_mode if requested_mode != "auto" else "draft"), reasons, "approval"



def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:200]


def detect_topic_family(topic: str, topic_profile: dict[str, Any] | None = None) -> str:
    if isinstance(topic_profile, dict):
        explicit = str(topic_profile.get("domain") or topic_profile.get("family") or "").strip()
        if explicit:
            return explicit
    text = (topic or "").strip()
    for family, config in TOPIC_FAMILIES.items():
        for keyword in config.get("keywords", []):
            if keyword and keyword in text:
                return family
    return "general-cs"


def infer_domain(topic: str, topic_profile: dict[str, Any] | None = None) -> str:
    return detect_topic_family(topic, topic_profile)


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
        {"day": "Day 2：文件读写基础", "当前阶段": "阶段 1", "今日主题": "文本文件 / CSV 文件读取与写出", "复习点": "open / with / 编码；路径与相对路径", "新学习点": "read / readlines / write；把读取逻辑拆成函数", "练习重点": "1 道文本清洗题 + 1 道 CSV 处理题 + 1 道文件异常题", "推荐材料": "Python编程：从入门到实践（第3版）；The Python Tutorial", "难度目标": "concept easy/medium，code easy/medium"},
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


def build_curriculum(topic: str, level: str, preference: str, topic_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(topic_profile, dict) and topic_profile:
        family = str(topic_profile.get("domain") or topic_profile.get("family") or detect_topic_family(topic, topic_profile)).strip() or "general-cs"
        profile_stages = topic_profile.get("stages") if isinstance(topic_profile.get("stages"), list) else []
        stages = []
        for stage in profile_stages:
            if not isinstance(stage, dict):
                continue
            stages.append(
                {
                    "name": str(stage.get("name") or stage.get("focus") or "阶段").strip(),
                    "focus": str(stage.get("focus") or stage.get("name") or "阶段主题").strip(),
                    "goal": str(stage.get("goal") or stage.get("focus") or "").strip(),
                    "practice": str(stage.get("practice") or "概念题 + 小练习").strip() or "概念题 + 小练习",
                    "test_gate": str(stage.get("test_gate") or f"完成 {stage.get('name') or '当前阶段'} 掌握检验后进入下一阶段").strip(),
                    "reading": normalize_string_list(stage.get("reading") or []),
                    "exercise_types": normalize_string_list(stage.get("exercise_types") or []),
                    "future_use": str(stage.get("future_use") or stage.get("goal") or "").strip() or str(stage.get("focus") or stage.get("name") or "").strip(),
                }
            )
        daily_templates = topic_profile.get("daily_templates") if isinstance(topic_profile.get("daily_templates"), list) else []
        if stages:
            return {
                "family": family,
                "topic": topic,
                "level": level,
                "preference": preference,
                "stages": stages,
                "daily_templates": daily_templates or (FAMILY_DAILY_TEMPLATES.get(family) or FAMILY_DAILY_TEMPLATES["general-cs"]),
            }
    family = detect_topic_family(topic, topic_profile)
    family_config = TOPIC_FAMILIES.get(family, TOPIC_FAMILIES["general-cs"])
    raw_stages = list(family_config.get("stages", []))
    stage_details = FAMILY_STAGE_DETAILS.get(family) or FAMILY_STAGE_DETAILS["general-cs"]
    stages: list[dict[str, Any]] = []
    for index, stage in enumerate(raw_stages):
        name, focus, goal, practice, test_gate = stage
        detail = stage_details[index] if index < len(stage_details) else {}
        stages.append(
            {
                "name": name,
                "focus": focus,
                "goal": goal,
                "practice": practice,
                "test_gate": test_gate,
                "reading": detail.get("reading", []),
                "exercise_types": detail.get("exercise_types", []),
                "future_use": detail.get("future_use", goal),
            }
        )
    return {
        "family": family,
        "topic": topic,
        "level": level,
        "preference": preference,
        "stages": stages,
        "daily_templates": FAMILY_DAILY_TEMPLATES.get(family) or FAMILY_DAILY_TEMPLATES["general-cs"],
    }



def render_stage_overview(curriculum: dict[str, Any]) -> str:
    blocks: list[str] = []
    for stage in curriculum["stages"]:
        blocks.extend(
            [
                f"### {stage['name']}：{stage['focus']}",
                f"- 阶段摘要：{stage['goal']}",
                f"- 具体阅读：{'；'.join(stage['reading'])}",
                f"- 练习类型：{'；'.join(stage['exercise_types']) or stage['practice']}",
                f"- 未来用途：{stage['future_use']}",
                f"- 阶段门槛：{stage['test_gate']}",
                "",
            ]
        )
    return "\n".join(blocks).strip()



def render_learning_route(curriculum: dict[str, Any]) -> str:
    blocks: list[str] = []
    for stage in curriculum["stages"]:
        blocks.extend(
            [
                f"### {stage['name']}：{stage['focus']}",
                "- 具体阅读：",
                *[f"  - {item}" for item in stage["reading"]],
                "- 练习类型：",
                *[f"  - {item}" for item in stage["exercise_types"]],
                f"- 阶段目标：{stage['goal']}",
                f"- 推荐练习方式：{stage['practice']}",
                f"- 阶段通过标准：{stage['test_gate']}",
                "",
            ]
        )
    return "\n".join(blocks).strip()



def render_daily_roadmap(curriculum: dict[str, Any]) -> str:
    blocks: list[str] = []
    for day in curriculum["daily_templates"]:
        blocks.extend(
            [
                f"### {day['day']}",
                f"- 当前阶段：{day['当前阶段']}",
                f"- 今日主题：{day['今日主题']}",
                f"- 复习点：{day['复习点']}",
                f"- 新学习点：{day['新学习点']}",
                f"- 练习重点：{day['练习重点']}",
                f"- 推荐材料：{day['推荐材料']}",
                f"- 难度目标：{day['难度目标']}",
                "",
            ]
        )
    blocks.extend(
        [
            "### 使用规则",
            "- /learn-today 默认优先读取最新一个 Day 区块作为当日计划。",
            "- /learn-today-update 应把下次复习重点、下次新学习建议与推进判断写回学习记录。",
            "- 若阶段测试结果显示需要回退，应优先回到最近相关 Day 区块继续巩固。",
        ]
    )
    return "\n".join(blocks).strip()



def render_materials_section(curriculum: dict[str, Any], materials_dir: Path, materials_index: Path) -> str:
    material_titles = []
    for item in TOPIC_FAMILIES.get(curriculum["family"], TOPIC_FAMILIES["general-cs"]).get("materials", []):
        title = item.get("title")
        use = item.get("use")
        if title and use:
            material_titles.append(f"  - {title}：{use}")
    lines = [
        f"- 本地目录：`{materials_dir}`",
        f"- 索引文件：`{materials_index}`",
        "- 主线材料：",
        *(material_titles or ["  - 暂无预置主线材料"]),
        "- 说明：当前版本会把材料摘要、聚焦主题、推荐阶段、推荐日与练习类型写入索引，供 session 使用。",
    ]
    return "\n".join(lines)



def infer_material_recommended_day(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[str]:
    title_blob = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("use") or ""),
            " ".join(str(tag) for tag in entry.get("tags") or []),
        ]
    ).lower()
    matched: list[str] = []
    for day in curriculum["daily_templates"]:
        today_topic = str(day.get("今日主题") or "")
        if any(token and token in title_blob for token in re.split(r"[\s/、，；:：]+", today_topic.lower()) if len(token) >= 2):
            matched.append(str(day["day"]))
    return matched[:3]



def enrich_material_entry(entry: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(entry)
    kind = str(enriched.get("kind") or "")
    if not enriched.get("summary"):
        enriched["summary"] = enriched.get("use") or f"{enriched.get('title', '材料')}，用于 {curriculum['topic']} 学习。"
    if kind == "book":
        enriched["summary"] = enriched.get("summary") or enriched.get("use")
        enriched["teaching_style"] = "chapter-lecture"
    elif kind == "tutorial":
        enriched["summary"] = enriched.get("summary") or f"这是一份偏步骤型教程，适合按概念、步骤、结果的顺序学习 {curriculum['topic']}。"
        enriched["teaching_style"] = "step-by-step"
    elif kind == "reference":
        enriched["summary"] = enriched.get("summary") or f"这是一份偏查阅型参考资料，适合围绕定义、接口、使用边界学习 {curriculum['topic']}。"
        enriched["teaching_style"] = "concept-reference"
    else:
        enriched.setdefault("teaching_style", "general")
    if not enriched.get("focus_topics"):
        tags = [str(tag) for tag in enriched.get("tags") or [] if str(tag).strip()]
        enriched["focus_topics"] = tags[:5] or [curriculum["topic"]]
    if not enriched.get("recommended_stage"):
        stages = [stage["name"] for stage in curriculum["stages"]]
        if kind in {"reference", "tutorial"}:
            enriched["recommended_stage"] = stages[:2] or stages
        elif kind in {"practice", "roadmap"}:
            enriched["recommended_stage"] = stages[1:] or stages
        else:
            enriched["recommended_stage"] = stages
    if not enriched.get("recommended_day"):
        enriched["recommended_day"] = infer_material_recommended_day(enriched, curriculum)
    if not enriched.get("exercise_types"):
        enriched["exercise_types"] = [stage["practice"] for stage in curriculum["stages"][:2]]
    return enriched


def build_planning_profile(topic: str, goal: str, level: str, schedule: str, preference: str, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, topic_profile: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, Any]:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}
    topic_profile = normalize_topic_profile(topic_profile or {}, topic)
    family = detect_topic_family(topic, topic_profile)
    clarification_state = clarification.get("clarification_state") if isinstance(clarification.get("clarification_state"), dict) else {}
    research_plan = research.get("research_plan") if isinstance(research.get("research_plan"), dict) else {}
    research_report = research.get("research_report") if isinstance(research.get("research_report"), dict) else {}
    diagnostic_profile = diagnostic.get("diagnostic_profile") if isinstance(diagnostic.get("diagnostic_profile"), dict) else {}
    approval_state = approval.get("approval_state") if isinstance(approval.get("approval_state"), dict) else {}
    preference_state = clarification.get("preference_state") if isinstance(clarification.get("preference_state"), dict) else {}

    user_model_seed = clarification.get("user_model") if isinstance(clarification.get("user_model"), dict) else {}
    goal_model_seed = clarification.get("goal_model") if isinstance(clarification.get("goal_model"), dict) else {}
    user_model = {
        "profile": user_model_seed.get("profile") or f"当前围绕 {topic} 建立长期学习路线，当前水平为：{level}。",
        "constraints": list(user_model_seed.get("constraints") or [schedule or "未指定时间约束"]),
        "preferences": list(user_model_seed.get("preferences") or [preference]),
        "strengths": list(user_model_seed.get("strengths") or ["已有一定基础，需要从当前水平继续推进而非回到纯模板入门"]),
        "weaknesses": list(user_model_seed.get("weaknesses") or ["仍需通过诊断、session 和复盘持续校准真实薄弱点"]),
        "learning_style": list(preference_state.get("learning_style") or []),
        "practice_style": list(preference_state.get("practice_style") or []),
        "delivery_preference": list(preference_state.get("delivery_preference") or []),
    }
    goal_model = {
        "mainline_goal": goal_model_seed.get("mainline_goal") or goal,
        "supporting_capabilities": list(goal_model_seed.get("supporting_capabilities") or [
            f"支撑 {topic} 主线推进的基础表达与概念稳定性",
            "阅读、练习、复盘三类证据闭环",
        ]),
        "enhancement_modules": list(goal_model_seed.get("enhancement_modules") or [f"围绕 {family} family 的进阶专题与应用扩展"]),
    }
    normalized_goal = f"{topic} {goal}".lower()
    needs_research = any(keyword in normalized_goal for keyword in ["工作", "就业", "转岗", "面试", "岗位", "求职", "职业", "大模型", "llm", "agent", "rag", "langchain", "langgraph", "模型应用", "应用开发"])
    planning_state = {
        "clarification_status": clarification_state.get("status") or ("confirmed" if clarification else ("captured" if mode != "draft" else "needs-more")),
        "deepsearch_status": research.get("deepsearch_status") or ("completed" if research_report else ("needed-pending-plan" if needs_research else "not-needed")),
        "diagnostic_status": diagnostic_profile.get("status") or ("validated" if diagnostic_profile else ("in-progress" if mode == "diagnostic" else "not-started")),
        "preference_status": preference_state.get("status") or ("confirmed" if preference_state else ("needs-confirmation" if mode == "finalize" else "not-started")),
        "plan_status": approval_state.get("approval_status") or ("approved" if mode == "finalize" and approval_state.get("ready_for_execution") else ("pending-confirmation" if mode == "finalize" else "draft")),
    }
    return {
        "topic": topic,
        "goal": goal,
        "level": level,
        "schedule": schedule,
        "preference": preference,
        "family": family,
        "mode": mode,
        "topic_profile": topic_profile,
        "user_model": user_model,
        "goal_model": goal_model,
        "planning_state": planning_state,
        "clarification_state": {
            "questions": list(clarification_state.get("questions") or []),
            "resolved_items": list(clarification_state.get("resolved_items") or []),
            "open_questions": list(clarification_state.get("open_questions") or []),
            "assumptions": list(clarification_state.get("assumptions") or []),
            "constraints_confirmed": list(clarification_state.get("constraints_confirmed") or user_model["constraints"]),
            "non_goals": list(clarification_state.get("non_goals") or []),
        },
        "preference_state": {
            "status": preference_state.get("status") or planning_state["preference_status"],
            "learning_style": list(preference_state.get("learning_style") or user_model.get("learning_style") or []),
            "practice_style": list(preference_state.get("practice_style") or user_model.get("practice_style") or []),
            "delivery_preference": list(preference_state.get("delivery_preference") or user_model.get("delivery_preference") or []),
            "pending_items": list(preference_state.get("pending_items") or []),
        },
        "research_plan": {
            "research_questions": list(research_plan.get("research_questions") or research_plan.get("questions") or []),
            "source_types": list(research_plan.get("source_types") or []),
            "candidate_directions": list(research_plan.get("candidate_directions") or []),
            "selection_criteria": list(research_plan.get("selection_criteria") or []),
        },
        "research_report": {
            "must_master_capabilities": list(research_report.get("must_master_capabilities") or research_report.get("must_master") or []),
            "capability_layers": list(research_report.get("capability_layers") or []),
            "mainline_capabilities": list(research_report.get("mainline_capabilities") or []),
            "supporting_capabilities": list(research_report.get("supporting_capabilities") or []),
            "deferred_capabilities": list(research_report.get("deferred_capabilities") or []),
            "candidate_paths": list(research_report.get("candidate_paths") or []),
            "candidate_materials": list(research_report.get("candidate_materials") or []),
            "selection_rationale": list(research_report.get("selection_rationale") or []),
            "evidence_summary": list(research_report.get("evidence_summary") or []),
            "report_status": research_report.get("report_status") or ("completed" if research_report else "missing"),
            "open_risks": list(research_report.get("open_risks") or []),
        },
        "diagnostic_profile": {
            "baseline_level": diagnostic_profile.get("baseline_level") or level,
            "dimensions": list(diagnostic_profile.get("dimensions") or []),
            "observed_strengths": list(diagnostic_profile.get("observed_strengths") or []),
            "observed_weaknesses": list(diagnostic_profile.get("observed_weaknesses") or []),
            "evidence": list(diagnostic_profile.get("evidence") or []),
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level") or level,
            "confidence": diagnostic_profile.get("confidence"),
            "status": diagnostic_profile.get("status") or planning_state["diagnostic_status"],
        },
        "approval_state": {
            "approval_status": approval_state.get("approval_status") or planning_state["plan_status"],
            "pending_decisions": list(approval_state.get("pending_decisions") or []),
            "approved_scope": list(approval_state.get("approved_scope") or []),
            "ready_for_execution": bool(approval_state.get("ready_for_execution")),
        },
        "needs": [
            "顾问式澄清",
            "深度检索报告确认",
            "主线资料本地可得",
            "章节/页码级学习定位",
            "阅读/练习/项目/复盘联合检验",
        ],
    }



def render_planning_profile(profile: dict[str, Any]) -> str:
    user_model = profile.get("user_model") or {}
    goal_model = profile.get("goal_model") or {}
    planning_state = profile.get("planning_state") or {}
    clarification_state = profile.get("clarification_state") or {}
    preference_state = profile.get("preference_state") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    approval_state = profile.get("approval_state") or {}
    lines = [
        f"- 学习主题：{profile['topic']}",
        f"- 学习目的：{profile['goal']}",
        f"- 当前水平：{profile['level']}",
        f"- 时间/频率约束：{profile['schedule']}",
        f"- 学习偏好：{profile['preference']}",
        f"- 主题 family：{profile['family']}",
        f"- 当前 workflow mode：{profile.get('mode')}",
        "- 用户模型：",
        f"  - 画像：{user_model.get('profile')}",
        *[f"  - 约束：{item}" for item in user_model.get("constraints", [])],
        *[f"  - 偏好：{item}" for item in user_model.get("preferences", [])],
        *[f"  - 已知优势：{item}" for item in user_model.get("strengths", [])],
        *[f"  - 已知薄弱点：{item}" for item in user_model.get("weaknesses", [])],
        "- 目标层级：",
        f"  - 主线目标：{goal_model.get('mainline_goal')}",
        *[f"  - 支撑能力：{item}" for item in goal_model.get("supporting_capabilities", [])],
        *[f"  - 增强模块：{item}" for item in goal_model.get("enhancement_modules", [])],
        "- planning state：",
        f"  - 澄清状态：{planning_state.get('clarification_status')}",
        f"  - deepsearch 状态：{planning_state.get('deepsearch_status')}",
        f"  - 诊断状态：{planning_state.get('diagnostic_status')}",
        f"  - 偏好确认状态：{planning_state.get('preference_status')}",
        f"  - 计划状态：{planning_state.get('plan_status')}",
        "- 顾问式澄清状态：",
        *[f"  - 已确认：{item}" for item in clarification_state.get("resolved_items", [])],
        *[f"  - 待确认：{item}" for item in clarification_state.get("open_questions", [])],
        *[f"  - 假设：{item}" for item in clarification_state.get("assumptions", [])],
        *[f"  - 非目标：{item}" for item in clarification_state.get("non_goals", [])],
        "- 学习风格与练习方式：",
        *[f"  - 学习风格：{item}" for item in preference_state.get("learning_style", [])],
        *[f"  - 练习方式：{item}" for item in preference_state.get("practice_style", [])],
        *[f"  - 交付偏好：{item}" for item in preference_state.get("delivery_preference", [])],
        *[f"  - 待确认偏好：{item}" for item in preference_state.get("pending_items", [])],
        "- 诊断摘要：",
        *[f"  - 诊断维度：{item}" for item in diagnostic_profile.get("dimensions", [])],
        *[f"  - 观察到的优势：{item}" for item in diagnostic_profile.get("observed_strengths", [])],
        *[f"  - 观察到的薄弱点：{item}" for item in diagnostic_profile.get("observed_weaknesses", [])],
        *( [f"  - 推荐起步层级：{diagnostic_profile.get('recommended_entry_level')}"] if diagnostic_profile.get("recommended_entry_level") else [] ),
        "- 计划确认状态：",
        f"  - 审批状态：{approval_state.get('approval_status')}",
        *[f"  - 待确认决策：{item}" for item in approval_state.get("pending_decisions", [])],
        *( [f"  - 可进入执行：{approval_state.get('ready_for_execution')}"] if approval_state else [] ),
        "- 当前规划要求：",
        *[f"  - {item}" for item in profile.get("needs", [])],
    ]
    return "\n".join(lines)



def render_planning_constraints(profile: dict[str, Any]) -> str:
    lines = [
        "- 主线资料必须优先可落地到本地；无法本地化的在线材料只能作为候选或备注。",
        "- 学习路线必须从当前水平出发，不能直接套用零基础模板。",
        "- 每个阶段必须细化到可执行阅读定位：至少到章节；若资料存在稳定页码信息，则进一步细到页码。",
        "- 每个阶段必须明确掌握标准，并能被 /learn-today 精确拆成当天计划。",
        f"- 当前主题将以 `{profile['family']}` family 为默认 seed；若后续检索结论与默认模板冲突，应以检索结论为准。",
    ]
    return "\n".join(lines)



def build_plan_report(profile: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any]:
    goal_model = profile.get("goal_model") or {}
    planning_state = profile.get("planning_state") or {}
    research_plan = profile.get("research_plan") or {}
    research_report = profile.get("research_report") or {}
    diagnostic_profile = profile.get("diagnostic_profile") or {}
    approval_state = profile.get("approval_state") or {}
    mode = str(profile.get("mode") or "draft")
    mode_summary = {
        "draft": "当前输出的是候选规划草案，用于继续澄清、补研究或补诊断，不应直接视为正式主线计划。",
        "research-report": "当前输出的是研究摘要，用于确认要查什么、为什么查、查完后如何影响学习路线。",
        "diagnostic": "当前输出的是诊断摘要或最小验证方案，用于确认真实起点和薄弱点，而不是直接推进正式主线。",
        "finalize": "当前输出的是正式规划摘要；只有在顾问式澄清、研究决策、诊断与计划确认通过后，才应视为正式主线计划。",
    }
    stage_summaries = []
    for index, stage in enumerate(curriculum["stages"]):
        role_in_plan = "mainline" if index == 0 else ("supporting" if index == 1 else "optional")
        stage_summaries.append(
            {
                "name": stage["name"],
                "focus": stage["focus"],
                "goal": stage["goal"],
                "reading": stage.get("reading", []),
                "exercise_types": stage.get("exercise_types", []),
                "test_gate": stage.get("test_gate"),
                "role_in_plan": role_in_plan,
                "goal_alignment": goal_model.get("mainline_goal"),
                "capability_alignment": (goal_model.get("supporting_capabilities") or [])[:2],
            }
        )
    preference_state = profile.get("preference_state") or {}
    return {
        "summary": mode_summary.get(mode, mode_summary["draft"]),
        "must_master": list(research_report.get("must_master_capabilities") or [stage["focus"] for stage in curriculum["stages"]]),
        "stage_summaries": stage_summaries,
        "quality_gates": [
            "完成顾问式澄清",
            "必要时完成 deepsearch 并确认",
            "完成能力要求报告，并向用户清晰告知为达到目标需要掌握哪些能力",
            "完成最小水平诊断或明确跳过理由",
            "完成学习风格与练习方式确认",
            "主线资料可本地获得",
            "阶段资料可定位到章节/页码/小节",
            "每阶段存在掌握度检验方式",
            "长期路线可拆成 /learn-today 当日计划",
            "计划已通过确认 gate",
        ],
        "material_policy": "仅将可本地化资料作为正式主线；在线不可缓存资料仅作候选或备注。",
        "planning_state": planning_state,
        "research_questions": list(research_plan.get("research_questions") or []),
        "candidate_paths": list(research_report.get("candidate_paths") or []),
        "selection_rationale": list(research_report.get("selection_rationale") or []),
        "evidence_summary": list(research_report.get("evidence_summary") or []),
        "open_risks": list(research_report.get("open_risks") or []),
        "diagnostic_summary": {
            "baseline_level": diagnostic_profile.get("baseline_level"),
            "recommended_entry_level": diagnostic_profile.get("recommended_entry_level"),
            "confidence": diagnostic_profile.get("confidence"),
        },
        "preference_summary": {
            "status": preference_state.get("status"),
            "learning_style": list(preference_state.get("learning_style") or []),
            "practice_style": list(preference_state.get("practice_style") or []),
            "delivery_preference": list(preference_state.get("delivery_preference") or []),
            "pending_items": list(preference_state.get("pending_items") or []),
        },
        "approval_state": approval_state,
    }



def render_plan_report(report: dict[str, Any]) -> str:
    lines = [
        f"- 结论摘要：{report['summary']}",
        "- 为达到目标需要掌握：",
        *[f"  - {item}" for item in report.get("must_master", [])],
        "- 当前采用的资料策略：",
        f"  - {report['material_policy']}",
        "- 计划质量门槛：",
        *[f"  - {item}" for item in report.get("quality_gates", [])],
    ]
    if report.get("research_questions"):
        lines.extend([
            "- 当前 research questions：",
            *[f"  - {item}" for item in report.get("research_questions", [])],
        ])
    if report.get("summary") and "研究摘要" in str(report.get("summary")):
        lines.extend([
            "- 当前交付类型：",
            "  - 这是研究阶段的中间产物，用于确认要查什么、为什么查以及查完如何影响规划。",
            "  - 在完成研究确认与后续诊断前，不应直接进入正式执行。",
        ])
    if report.get("must_master"):
        lines.extend([
            "- 能力要求报告：",
            "  - 这一阶段应明确回答：为达到该学习目的，必须掌握哪些能力。",
        ])
    if report.get("mainline_capabilities"):
        lines.extend([
            "- 主线能力：",
            *[f"  - {item}" for item in report.get("mainline_capabilities", [])],
        ])
    if report.get("supporting_capabilities"):
        lines.extend([
            "- 支撑能力：",
            *[f"  - {item}" for item in report.get("supporting_capabilities", [])],
        ])
    if report.get("deferred_capabilities"):
        lines.extend([
            "- 可后置能力：",
            *[f"  - {item}" for item in report.get("deferred_capabilities", [])],
        ])
    if report.get("candidate_paths"):
        lines.extend([
            "- 候选路径：",
            *[f"  - {item}" for item in report.get("candidate_paths", [])],
        ])
    if report.get("selection_rationale"):
        lines.extend([
            "- 取舍理由：",
            *[f"  - {item}" for item in report.get("selection_rationale", [])],
        ])
    if report.get("evidence_summary"):
        lines.extend([
            "- 证据摘要：",
            *[f"  - {item}" for item in report.get("evidence_summary", [])],
        ])
    if report.get("open_risks"):
        lines.extend([
            "- 当前风险：",
            *[f"  - {item}" for item in report.get("open_risks", [])],
        ])
    diagnostic_summary = report.get("diagnostic_summary") or {}
    if diagnostic_summary:
        lines.extend([
            "- 诊断摘要：",
            *( [f"  - 基线水平：{diagnostic_summary.get('baseline_level')}"] if diagnostic_summary.get("baseline_level") else [] ),
            *( [f"  - 推荐起步层级：{diagnostic_summary.get('recommended_entry_level')}"] if diagnostic_summary.get("recommended_entry_level") else [] ),
            *( [f"  - 诊断置信度：{diagnostic_summary.get('confidence')}"] if diagnostic_summary.get("confidence") is not None else [] ),
        ])
        if report.get("summary") and "诊断摘要" in str(report.get("summary")):
            lines.extend([
                "- 当前交付类型：",
                "  - 这是诊断阶段的中间产物，用于确认真实起点、薄弱点和建议起步层级。",
                "  - 在完成确认 gate 前，不应直接把它当成正式执行计划。",
            ])
    preference_summary = report.get("preference_summary") or {}
    if preference_summary:
        lines.extend([
            "- 学习风格与练习方式确认：",
            *( [f"  - 偏好确认状态：{preference_summary.get('status')}"] if preference_summary.get("status") else [] ),
            *[f"  - 学习风格：{item}" for item in preference_summary.get("learning_style", [])],
            *[f"  - 练习方式：{item}" for item in preference_summary.get("practice_style", [])],
            *[f"  - 交付偏好：{item}" for item in preference_summary.get("delivery_preference", [])],
            *[f"  - 待确认偏好：{item}" for item in preference_summary.get("pending_items", [])],
        ])
    approval_state = report.get("approval_state") or {}
    if approval_state:
        lines.extend([
            "- 计划确认状态：",
            *( [f"  - 审批状态：{approval_state.get('approval_status')}"] if approval_state.get("approval_status") else [] ),
            *[f"  - 待确认：{item}" for item in approval_state.get("pending_decisions", [])],
        ])
    lines.append("- 阶段候选路线：")
    for stage in report.get("stage_summaries", []):
        lines.extend(
            [
                f"  - {stage['name']}：{stage['focus']}",
                f"    - 阶段目标：{stage['goal']}",
                f"    - 角色：{stage.get('role_in_plan')}",
                f"    - 目标对齐：{stage.get('goal_alignment')}",
                f"    - 支撑能力对齐：{'；'.join(stage.get('capability_alignment', []))}",
                f"    - 主线阅读：{'；'.join(stage.get('reading', []))}",
                f"    - 练习方式：{'；'.join(stage.get('exercise_types', []))}",
                f"    - 通过标准：{stage.get('test_gate')}",
            ]
        )
    return "\n".join(lines)



def render_mastery_checks(curriculum: dict[str, Any]) -> str:
    lines = [
        "### 阅读掌握清单",
        "- 每阶段至少列出 3 个“学完后应能解释/区分/实现”的检查点。",
        "- 若阅读材料有章节/页码，则检查点应能定位回具体段落。",
        "",
        "### session 练习/测试",
        "- 每阶段都应有对应的概念题、代码题或阶段测试。",
        "- 正确率只能作为证据之一，不能单独代表真正掌握。",
        "",
        "### 小项目 / 实作",
        "- 关键阶段至少安排 1 个小项目或真实任务，用于验证能否迁移应用。",
        "- 若项目未完成，不应直接判定为阶段完全掌握。",
        "",
        "### 口头 / 书面复盘",
        "- 每阶段结束后，需用自己的话解释核心概念、易错点与实际用途。",
        "- 若无法完成清楚复盘，应将相关内容加入后续复习池。",
        "",
        "### 质量判断规则",
        "- 阅读掌握清单 + session 表现 + 项目/实作 + 复盘，需要综合判断。",
        "- 只有做题表现，没有阅读理解与项目证据，不应判定为完全掌握。",
    ]
    return "\n".join(lines)



def render_today_generation_rules(curriculum: dict[str, Any]) -> str:
    lines = [
        "- /learn-today 默认先询问真实进度，再决定今日计划。",
        "- 若上次指定章节/页码/segment 未完成，优先补读与复习，不推进新内容。",
        "- 若阅读掌握清单未达标，应减少新知识比例，优先解释、复盘与巩固。",
        "- 若最近两次 session 与复盘稳定，才允许进入下一阶段。",
        "- 今日计划必须同时给出：复习内容、新学习内容、对应资料定位、练习重点、掌握标准。",
    ]
    if curriculum.get("daily_templates"):
        lines.append("- 当前默认 day 模板可作为 fallback，但不能替代真实进度 check-in。")
    return "\n".join(lines)



def build_plan_sections(topic: str, goal: str, level: str, schedule: str, preference: str, materials_dir: Path, materials_index: Path, *, clarification: dict[str, Any] | None = None, research: dict[str, Any] | None = None, diagnostic: dict[str, Any] | None = None, approval: dict[str, Any] | None = None, topic_profile: dict[str, Any] | None = None, mode: str = "draft") -> dict[str, str]:
    curriculum = build_curriculum(topic, level, preference, topic_profile=topic_profile)
    profile = build_planning_profile(topic, goal, level, schedule, preference, clarification=clarification, research=research, diagnostic=diagnostic, approval=approval, topic_profile=topic_profile, mode=mode)
    report = build_plan_report(profile, curriculum)
    return {
        "学习画像": render_planning_profile(profile),
        "规划假设与约束": render_planning_constraints(profile),
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
    existing = extract_section(original, heading)
    if existing is None:
        return default
    return existing


def render_plan(topic: str, goal: str, level: str, schedule: str, preference: str, sections: dict[str, str]) -> str:
    blocks = [
        "# Learn Plan",
        "",
        f"- 学习主题：{topic}",
        f"- 学习目的：{goal}",
        f"- 当前水平：{level}",
        f"- 时间/频率约束：{schedule}",
        f"- 学习偏好：{preference}",
        "",
    ]

    ordered_headings = [
        "学习画像",
        "规划假设与约束",
        "检索结论与取舍",
        "阶段总览",
        "阶段路线图",
        "资料清单与阅读定位",
        "掌握度检验设计",
        "今日生成规则",
        "每日推进表",
        "学习记录",
        "测试记录",
    ]
    for heading in ordered_headings:
        content = sections.get(heading)
        if content is None:
            continue
        blocks.append(f"## {heading}")
        blocks.append("")
        content = content.strip()
        if content:
            blocks.append(content)
            blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def group_topics_for_segments(focus_topics: list[str], *, chunk_size: int = 3) -> list[list[str]]:
    cleaned = [str(item).strip() for item in focus_topics if str(item).strip()]
    if not cleaned:
        return []
    return [cleaned[index:index + chunk_size] for index in range(0, len(cleaned), chunk_size)]



def build_reading_segments(entry: dict[str, Any], curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    recommended_stages = list(entry.get("recommended_stage") or [])
    focus_topics = list(entry.get("focus_topics") or [])
    topic_groups = group_topics_for_segments(focus_topics, chunk_size=3)
    segments: list[dict[str, Any]] = []

    if recommended_stages:
        for stage_index, stage_name in enumerate(recommended_stages[:3], start=1):
            groups = topic_groups or [[curriculum["topic"]]]
            for group_index, group in enumerate(groups[:2], start=1):
                section_label = " / ".join(group)
                label = f"{stage_name} / {entry.get('title', '材料')} / {section_label}"
                locator = {"chapter": stage_name, "pages": None, "sections": group}
                if entry.get("source_type") == "local":
                    locator["pages"] = f"待补充页码（优先定位到 {stage_name} 中与 {section_label} 对应的内容）"
                segments.append(
                    {
                        "segment_id": f"{entry.get('id', 'material')}-segment-{stage_index}-{group_index}",
                        "label": label,
                        "locator": locator,
                        "purpose": entry.get("use") or f"服务于 {curriculum['topic']} 学习",
                        "recommended_for": {"stage": stage_name, "days": entry.get("recommended_day") or []},
                        "estimated_minutes": 35 if len(group) <= 2 else 45,
                        "checkpoints": group,
                    }
                )
    if not segments:
        fallback_group = (topic_groups[0] if topic_groups else [curriculum["topic"]])[:3]
        segments.append(
            {
                "segment_id": f"{entry.get('id', 'material')}-segment-1",
                "label": f"{entry.get('title') or '未命名材料'} / {' / '.join(fallback_group)}",
                "locator": {"chapter": "待补充章节", "pages": None, "sections": fallback_group},
                "purpose": entry.get("use") or f"服务于 {curriculum['topic']} 学习",
                "recommended_for": {"stage": None, "days": entry.get("recommended_day") or []},
                "estimated_minutes": 45,
                "checkpoints": fallback_group,
            }
        )
    return segments



def build_default_material_entries(topic: str, domain: str, materials_dir: Path, curriculum: dict[str, Any], topic_profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    topic_profile = normalize_topic_profile(topic_profile or {}, topic)
    profile_materials = topic_profile.get("materials") if isinstance(topic_profile.get("materials"), list) else []
    family_config = TOPIC_FAMILIES.get(domain, TOPIC_FAMILIES["general-cs"])
    material_seed = profile_materials or family_config.get("materials", [])
    entries = []
    for item in material_seed:
        kind = item.get("kind") or "reference"
        safe_title = sanitize_filename(item.get("title") or item["id"])
        local_path = materials_dir / domain / kind / f"{item['id']}_{safe_title}"
        entry = enrich_material_entry(item, curriculum)
        entry["topic"] = topic
        entry["domain"] = domain
        seeded_local_path = str(entry.get("local_path") or "").strip()
        entry["local_path"] = seeded_local_path or str(local_path)
        seeded_artifact = entry.get("local_artifact") if isinstance(entry.get("local_artifact"), dict) else {}
        artifact_path = str(seeded_artifact.get("path") or entry["local_path"] or str(local_path)).strip()
        entry["exists_locally"] = Path(artifact_path).expanduser().exists() if artifact_path else False
        entry["local_artifact"] = {
            "path": artifact_path,
            "file_type": seeded_artifact.get("file_type") or (Path(artifact_path).suffix.lstrip(".") if artifact_path and Path(artifact_path).suffix else None),
            "downloaded_at": seeded_artifact.get("downloaded_at"),
        }
        entry["coverage"] = {
            "topic": topic,
            "stages": entry.get("recommended_stage") or [],
            "skills": entry.get("focus_topics") or [],
        }
        entry["goal_alignment"] = goal_alignment = topic
        entry["capability_alignment"] = (entry.get("focus_topics") or [topic])[:3]
        entry["role_in_plan"] = "optional"
        entry["usage_modes"] = ["reading", "reference"] if kind in {"book", "tutorial", "reference"} else ["reference"]
        entry["discovery_notes"] = "候选资料：当前无法直接落地到本地，仅作补充参考，不应直接进入主线。"
        entry["reading_segments"] = build_reading_segments(entry, curriculum)
        entry["mastery_checks"] = {
            "reading_checklist": entry.get("focus_topics") or [topic],
            "session_exercises": entry.get("exercise_types") or [],
            "applied_project": [f"围绕 {entry.get('title') or topic} 做 1 个小练习或小项目"],
            "reflection": [f"用自己的话解释 {entry.get('title') or topic} 的关键概念与实际用途"],
        }
        if entry["exists_locally"]:
            entry["cache_status"] = "cached"
            entry["cache_note"] = "已检测到本地缓存文件"
            entry["local_artifact"]["downloaded_at"] = time.strftime("%Y-%m-%d")
        entries.append(recompute_material_runtime_fields(entry, materials_dir=materials_dir))
    return entries


def merge_material_entries(existing_entries: list[dict[str, Any]], default_entries: list[dict[str, Any]], materials_dir: Path | None = None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    schema_critical_fields = {
        "role_in_plan",
        "goal_alignment",
        "capability_alignment",
        "reading_segments",
        "mastery_checks",
        "coverage",
        "usage_modes",
        "discovery_notes",
        "selection_status",
        "availability",
    }
    runtime_preferred_fields = {
        "cache_status",
        "cache_note",
        "exists_locally",
        "local_artifact",
        "cached_at",
        "last_attempt",
        "downloaded_at",
    }
    for item in existing_entries:
        if isinstance(item, dict) and item.get("id"):
            merged[item["id"]] = dict(item)
    for item in default_entries:
        current = merged.get(item["id"], {})
        merged_item = {**item, **current}
        for field in schema_critical_fields:
            if field in item:
                merged_item[field] = json.loads(json.dumps(item[field]))
        for field in runtime_preferred_fields:
            if field in current:
                merged_item[field] = json.loads(json.dumps(current[field]))
        merged_item["topic"] = item.get("topic")
        merged_item["domain"] = item.get("domain")
        merged_item["local_path"] = item.get("local_path")
        merged[item["id"]] = recompute_material_runtime_fields(merged_item, materials_dir=materials_dir)
    return list(merged.values())


def build_materials_index(topic: str, goal: str, level: str, schedule: str, preference: str, materials_dir: Path, plan_path: Path, existing: dict[str, Any], topic_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(existing) if existing else {}
    topic_profile = normalize_topic_profile(topic_profile or {}, topic)
    domain = infer_domain(topic, topic_profile)
    curriculum = build_curriculum(topic, level, preference, topic_profile=topic_profile)
    existing_pool = data.get("entries") or data.get("materials") or []
    existing_entries = [
        item
        for item in existing_pool
        if isinstance(item, dict) and item.get("domain") == domain
    ]
    default_entries = build_default_material_entries(topic, domain, materials_dir, curriculum, topic_profile=topic_profile)
    entries = merge_material_entries(existing_entries, default_entries, materials_dir=materials_dir)
    confirmed_entries = [item for item in entries if item.get("selection_status") == "confirmed" and item.get("role_in_plan") == "mainline"]
    candidate_entries = [item for item in entries if item.get("selection_status") != "confirmed" or item.get("role_in_plan") != "mainline"]
    data["topic"] = topic
    data["goal"] = goal
    data["level"] = level
    data["schedule"] = schedule
    data["preference"] = preference
    data["domain"] = domain
    data["updated_at"] = time.strftime("%Y-%m-%d")
    data["plan_path"] = str(plan_path)
    data["materials_dir"] = str(materials_dir)
    data["material_policy"] = "正式主线资料必须优先使用本地已存在或可直链下载到本地的材料。"
    data["entries"] = entries
    data["materials"] = entries
    data["confirmed_materials"] = confirmed_entries
    data["candidate_materials"] = candidate_entries
    data["sources"] = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "source_name": item.get("source_name"),
            "source_type": item.get("source_type"),
            "selection_status": item.get("selection_status"),
            "availability": item.get("availability"),
        }
        for item in entries
    ]
    data["local_materials"] = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "local_path": item.get("local_path"),
            "reading_segments": item.get("reading_segments") or [],
        }
        for item in entries
        if item.get("exists_locally") and item.get("local_path")
    ]
    data["notes"] = "当前版本要求主线资料优先本地可得，并为主线资料补充章节/页码/小节级阅读定位与掌握度检验信息。"
    return data


def validate_plan_quality(sections: dict[str, str], materials_data: dict[str, Any], *, profile: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required_sections = [
        "学习画像",
        "规划假设与约束",
        "检索结论与取舍",
        "阶段总览",
        "阶段路线图",
        "资料清单与阅读定位",
        "掌握度检验设计",
        "今日生成规则",
    ]
    for heading in required_sections:
        if not sections.get(heading, "").strip():
            issues.append(f"缺少关键区块：{heading}")

    planning_state = profile.get("planning_state") or {}
    approval_state = profile.get("approval_state") or {}
    clarification_status = str(planning_state.get("clarification_status") or "")
    deepsearch_status = str(planning_state.get("deepsearch_status") or "")
    diagnostic_status = str(planning_state.get("diagnostic_status") or "")
    plan_status = str(planning_state.get("plan_status") or "")
    if clarification_status not in {"confirmed", "captured"}:
        issues.append("顾问式澄清尚未完成")
    if deepsearch_status in {"needed-pending-plan", "approved-running"}:
        issues.append("deepsearch 尚未完成或尚未确认")
    research_report = profile.get("research_report") or {}
    if deepsearch_status == "completed" and not (research_report.get("must_master_capabilities") or research_report.get("mainline_capabilities") or research_report.get("evidence_summary")):
        issues.append("research 阶段尚未形成对用户可见的能力要求报告")
    research_report = profile.get("research_report") or {}
    if deepsearch_status == "completed" and not (research_report.get("must_master_capabilities") or research_report.get("mainline_capabilities") or research_report.get("evidence_summary")):
        issues.append("research 阶段尚未形成对用户可见的能力要求报告")
    if diagnostic_status in {"in-progress", "not-started"}:
        issues.append("诊断尚未完成或缺少最小水平验证")
    preference_status = str(planning_state.get("preference_status") or "")
    if preference_status in {"needs-confirmation", "not-started"}:
        issues.append("学习风格与练习方式尚未确认")
    current_mode = str(profile.get("mode") or "draft")
    if current_mode != "finalize":
        issues.append("当前仍处于非 finalize workflow mode，不能视为正式主线计划")
    if plan_status != "approved" and not approval_state.get("ready_for_execution"):
        issues.append("计划尚未通过确认 gate")

    entries = materials_data.get("entries") or []
    confirmed = [item for item in entries if item.get("selection_status") == "confirmed" and item.get("role_in_plan") == "mainline"]
    if not confirmed:
        issues.append("没有正式主线资料（selection_status=confirmed）")

    for item in confirmed:
        segments = item.get("reading_segments") or []
        if not segments:
            issues.append(f"主线资料缺少 reading_segments：{item.get('title') or item.get('id')}")
            continue
        first_segment = segments[0]
        locator = first_segment.get("locator") if isinstance(first_segment, dict) else {}
        if not isinstance(locator, dict) or not (locator.get("chapter") or locator.get("pages") or locator.get("sections")):
            issues.append(f"主线资料缺少章节/页码/小节定位：{item.get('title') or item.get('id')}")
        mastery_checks = item.get("mastery_checks") or {}
        if not mastery_checks:
            issues.append(f"主线资料缺少掌握度检验设计：{item.get('title') or item.get('id')}")

    return issues



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
    clarification: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    planning_state: dict[str, Any] | None = None,
    download_result: dict[str, Any] | None = None,
    auto_download_enabled: bool = True,
    quality_issues: list[str] | None = None,
) -> None:
    clarification = clarification or {}
    research = research or {}
    diagnostic = diagnostic or {}
    approval = approval or {}
    next_step_by_mode = {
        "draft": "继续完成澄清、研究、诊断或确认 gate，再进入 finalize",
        "research-report": "先确认研究计划/研究摘要，再决定是否进入诊断或 finalize",
        "diagnostic": "先完成最小水平验证并确认起步层级，再进入 finalize",
        "finalize": "/learn-today",
    }
    recommended_mode, routing_reasons, blocking_stage = recommend_workflow_mode(topic, goal, clarification, research, diagnostic, approval, mode)
    next_action = (
        f"switch_to:{recommended_mode}" if quality_issues else "enter:/learn-today"
    )
    should_continue_workflow = bool(quality_issues) or mode in {"draft", "research-report", "diagnostic"}
    summary = {
        "topic": topic,
        "requested_mode": requested_mode,
        "mode": mode,
        "recommended_mode": recommended_mode,
        "blocking_stage": blocking_stage,
        "routing_reasons": routing_reasons,
        "is_intermediate_product": mode in {"draft", "research-report", "diagnostic"},
        "should_continue_workflow": should_continue_workflow,
        "next_action": next_action,
        "workflow_loop_hint": "若 should_continue_workflow 为 true，则外层应继续下一轮澄清/research/diagnostic/approval；仅当 next_action = enter:/learn-today 时才退出 /learn-plan 工作流。",
        "plan_path": str(plan_path),
        "materials_dir": str(materials_dir),
        "materials_index": str(materials_index),
        "planning_state": planning_state or {},
        "next_step": next_step_by_mode.get(mode, "/learn-today"),
        "quality_issues": quality_issues or [],
    }
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
    if quality_issues:
        print("计划状态：草案 / 待确认 / 待补条件")
        print("阻塞原因：" + "；".join(quality_issues))
        print(f"下一步建议：先切换到 {recommended_mode} mode，继续补齐 gate")
        if mode in {"draft", "research-report", "diagnostic"}:
            print("当前交付：这是中间产物，不应直接当作正式主线计划执行")
    else:
        print("计划状态：可作为正式学习计划")
        print(f"下一步建议：{next_step_by_mode.get(mode, '/learn-today')}")
    if stdout_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


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
    clarification = load_workflow_json_with_fallback(args.clarification_json, plan_path.parent, "clarification.json", ".learn-plan-clarification.json")
    research = load_workflow_json_with_fallback(args.research_json, plan_path.parent, "research.json", ".learn-plan-research.json")
    diagnostic = load_workflow_json_with_fallback(args.diagnostic_json, plan_path.parent, "diagnostic.json", ".learn-plan-diagnostic.json")
    approval = load_workflow_json_with_fallback(args.approval_json, plan_path.parent, "approval.json", ".learn-plan-approval.json")
    topic_profile = load_topic_profile(plan_path, topic)
    recommended_mode, routing_reasons, blocking_stage = recommend_workflow_mode(topic, goal, clarification, research, diagnostic, approval, requested_mode if requested_mode != "auto" else "draft")
    mode = recommended_mode if requested_mode == "auto" else requested_mode

    materials_index = materials_dir / "index.json"

    original = read_text_if_exists(plan_path)
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
        topic_profile=topic_profile,
        mode=mode,
    )
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
        topic_profile=topic_profile,
        mode=mode,
    )
    sections = {
        "学习画像": base_sections["学习画像"],
        "规划假设与约束": base_sections["规划假设与约束"],
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
    materials_data = build_materials_index(topic, goal, level, schedule, preference, materials_dir, plan_path, existing_index, topic_profile=topic_profile)
    quality_issues = validate_plan_quality(sections, materials_data, profile=profile)
    sections = append_quality_warning(sections, quality_issues)

    rendered = render_plan(topic, goal, level, schedule, preference, sections)
    write_text(plan_path, rendered)
    write_json(materials_index, materials_data)

    download_result = None
    should_download = mode == "finalize" and not args.skip_material_download
    if should_download:
        download_result = process_materials(
            materials_dir,
            None,
            force=False,
            dry_run=False,
            timeout=args.download_timeout,
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
        clarification=clarification,
        research=research,
        diagnostic=diagnostic,
        approval=approval,
        planning_state=profile.get("planning_state") if isinstance(profile, dict) else {},
        download_result=download_result,
        auto_download_enabled=should_download,
        quality_issues=quality_issues,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
