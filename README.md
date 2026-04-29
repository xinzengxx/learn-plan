# learn-plan 学习系统

面向 Claude Code 的本地学习工作流。

## 核心入口（3 个）

| 入口 | 做什么 |
|---|---|
| `/learn-plan` | 学习顾问：深挖需求 → 检索资料 → 诊断水平 → 定制长期计划 |
| `/learn-today` | 日常学习：课件生成 → 练习题 → 学习复盘，自动更新进度 |
| `/learn-test` | 阶段检测：出题 → 测试 → 复盘分析，自动更新 learner model |

## 仓库结构

```text
learn-plan-skills/
├── README.md
├── SKILL.md                          # 根 shim
├── learn-plan/                        # 主实现目录
│   ├── SKILL.md                       # /learn-plan 执行协议
│   ├── docs/                          # 阶段细化文档
│   │   ├── phase1-deepdive-analysis.md
│   │   ├── phase2-diagnostic.md
│   │   └── phase3-plan-generation.md
│   ├── learn_plan.py
│   ├── session_orchestrator.py
│   ├── session_bootstrap.py
│   ├── learn_today_update.py
│   ├── learn_test_update.py
│   ├── material_downloader.py
│   ├── learn_core/
│   ├── learn_workflow/
│   ├── learn_planning/
│   ├── learn_materials/
│   ├── learn_runtime/
│   ├── learn_feedback/
│   ├── frontend/                      # Vue SPA 源码
│   ├── templates/                     # 运行时模板
│   └── tests/
├── learn-today/
│   └── SKILL.md                       # /learn-today 执行协议
├── learn-test/
│   └── SKILL.md                       # /learn-test 执行协议
└── learn-download-materials/
    └── SKILL.md                       # 独立工具入口（/learn-plan 已自动触发）
```

## 环境要求

- Claude Code
- Python 3.8+
- `conda`，且可执行 `conda run -n base python ...`
- macOS 推荐使用（当前自动开浏览器走 `open`）
- 如需自动下载材料，需要网络访问

## 安装方式

### 方式一：推荐，使用 symlink

```bash
mkdir -p ~/.claude/skills
cd ~
git clone https://github.com/BDLab-XZ/learn-plan.git learn-plan-skills

ln -s ~/learn-plan-skills/learn-plan ~/.claude/skills/learn-plan
ln -s ~/learn-plan-skills/learn-today ~/.claude/skills/learn-today
ln -s ~/learn-plan-skills/learn-test ~/.claude/skills/learn-test
```

### 方式二：直接复制目录

```bash
mkdir -p ~/.claude/skills
cd ~
git clone https://github.com/BDLab-XZ/learn-plan.git learn-plan-skills

cp -R ~/learn-plan-skills/learn-plan ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-today ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-test ~/.claude/skills/
```

## 最小验收流程

在一个空学习目录里执行：

```bash
mkdir -p ~/learning/python
cd ~/learning/python
```

然后在 Claude Code 中依次运行：

1. `/learn-plan`   — 深挖需求 + 检索资料 + 出长期计划
2. `/learn-today`  — 生成课件 + 练习题 + 学后复盘
3. `/learn-test`   — 阶段测试 + 测试复盘

预期至少会出现这些运行时产物：

```text
learn-plan.md
materials/index.json
sessions/YYYY-MM-DD/lesson.md
sessions/YYYY-MM-DD/questions.json
sessions/YYYY-MM-DD/progress.json
sessions/YYYY-MM-DD/题集.html
sessions/YYYY-MM-DD/server.py
sessions/YYYY-MM-DD-test/questions.json
sessions/YYYY-MM-DD-test/progress.json
sessions/YYYY-MM-DD-test/题集.html
sessions/YYYY-MM-DD-test/server.py
```

## License

个人学习工具，不提供任何担保。使用者自行承担风险。
