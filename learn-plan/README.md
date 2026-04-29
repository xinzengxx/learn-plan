# learn-plan Skill 簇

`learn-plan` 是一套本地学习工作流，用于从长期学习计划到每日学习、阶段测试、结果回写和材料管理。

它不是单个脚本，而是一组协同 skills：
- `/learn-plan`：创建或更新长期学习计划
- `/learn-today`：生成并启动今日学习 session，并在 Step 6 回写学习结果
- `/learn-test`：生成并启动测试 session，并在 Step 4 回写测试结果
- `/learn-download-materials`：下载材料索引中可直链获取的材料

共享实现目录：`~/.claude/skills/learn-plan/`

---

## 1. 这套系统解决什么

目标是把学习过程拆成一个稳定闭环：

```text
顾问规划
-> 能力建模
-> 起始测试（收口到 /learn-test Step 4 的测试后复盘）
-> 正式 learn-plan.md
-> 每日教师型学习 session
-> 阶段测试
-> 学习反馈与计划调整建议
```

核心产物：
- `learn-plan.md`：长期学习计划
- `materials/index.json`：材料索引与缓存状态
- `learn-today-YYYY-MM-DD.md`：today 唯一正式讲解文件
- `sessions/*/questions.json`：题目与 session 上下文
- `sessions/*/progress.json`：练习/测试事实记录
- `sessions/*/题集.html`：本地学习页面
- `sessions/*/server.py`：本地服务

---

## 2. 快速开始

### 2.1 创建学习计划

在你选择的学习根目录中运行：

```bash
/learn-plan
```

`/learn-plan` 会按多轮 workflow 工作：
1. 顾问式澄清学习目标、当前水平、时间约束与偏好
2. 必要时先做 research，形成能力要求报告
3. 必要时做最小水平诊断
4. 生成计划草案并让你确认关键取舍
5. 通过 gate 后写出正式 `learn-plan.md` 与 `materials/index.json`

默认目录结构：

```text
learning/topic/
├── learn-plan.md
├── materials/
│   └── index.json
├── sessions/
└── .learn-workflow/
```

说明：`.learn-workflow/` 存放 workflow 中间状态，普通使用时不需要手动编辑。

阶段细则已拆分到独立文档：
- clarification：`docs/clarification-stage.md`
- research：`docs/research-stage.md`
- diagnostic：`docs/diagnostic-stage.md`
- approval：`docs/approval-stage.md`
- finalize：`docs/finalize-stage.md`

### 2.2 开始每日学习

```bash
/learn-today
```

它会基于 `learn-plan.md`、材料索引、历史 progress 和你的当天反馈生成学习 session，通常包含：
- `<root>/learn-today-YYYY-MM-DD.md`：唯一正式讲解材料，固定为四部分：你阅读了哪些材料 / 今日重点要掌握哪些知识 / 项目驱动的知识点讲解和相关扩展 / 建议复习
- `questions.json`：网页练习题载荷，不写入 markdown
- `progress.json`
- `题集.html`
- `server.py`

同时会在 payload/context 中保留 `today_teaching_brief`、`lesson_review`、`question_review`、`lesson_focus_points`、`project_tasks`、`project_blockers`、`review_targets`，供人工审查与后续 update 复用。

并启动本地服务、打开浏览器。

### 2.3 完成后更新学习记录

学习记录回写已合并到 `/learn-today` 的 Step 6。完成本次 session 后，主流程会读取 `progress.json`，汇总表现并回写 `learn-plan.md` 的学习记录区块，同时更新 `.learn-workflow/learner_model.json`，并将课程调整建议写入 `.learn-workflow/curriculum_patch_queue.json`。这些 patch 只会进入待确认队列，不会自动改长期路线。

说明：如果这是由 `/learn-plan` diagnostic gate 触发的起始测试 session，完成作答后会优先自动停服、自动运行内部 `learn_test_update.py` 回写流程，再自动重新进入 `/learn-plan`；若自动续跑失败，再手动运行页面展示的整条命令。

### 2.4 阶段测试

```bash
/learn-test
```

支持测试模式：
- `general`：通用测试
- `weakness-focused`：针对薄弱项
- `mixed`：混合模式

测试后的记录回写已合并到 `/learn-test` 的 Step 4。它会更新测试记录、`learner_model.json` 与 `curriculum_patch_queue.json`。patch 默认先进入待确认队列；当 approval/finalize gate 放行后，`/learn-plan` 会消费已批准 patch 并写回正式计划。

### 2.5 下载学习材料

```bash
/learn-download-materials
```

只会下载：
- `downloadable: true` 的条目
- 或 URL 本身是直接文件链接的条目（例如 `.pdf`、`.md`、`.txt`、`.json`、`.csv`、`.html`）

需要认证、动态页面、视频或交互式内容不会被自动下载。

---

## 3. 质量标准

一份合格的 `learn-plan.md` 至少应满足：
- **目标对齐**：阶段安排服务用户真实目标
- **起点准确**：从当前水平出发，不套默认模板
- **能力明确**：把目标转成可观察、可诊断、可检验的能力指标
- **资料可执行**：主线资料可本地获得或稳定定位
- **粒度够细**：至少细到章节/小节；有页码时细到页码
- **掌握可检验**：每阶段有明确掌握标准
- **可日拆**：能被 `/learn-today` 拆成具体当天任务

不合格情况：
- 只有路线，没有澄清、research 或诊断依据
- 只有资料名/链接，没有阅读定位
- 主线资料大多无法执行
- 当前水平仍只是自报，没有任何验证动作
- 计划无法产出具体每日学习 session

### 3.1 质量保障边界

这套系统不是让 LLM 直接写“看起来完整”的最终计划，而是把质量判断做成一等公民：
- LLM 负责生成澄清、research、诊断、规划、讲解、出题等候选内容
- reviewer 与 deterministic gate 负责判断是否可推进
- 正式 `learn-plan.md` 只在 `finalize` 且 gate 放行时由代码写出

跨阶段统一质量字段：
- `generation_trace`
- `quality_review`
- `evidence`
- `confidence`
- `traceability`

这些字段会出现在：
- workflow 中间态
- `questions.json` 与结构化 lesson payload
- `learner_model.json` 的 `evidence_log`
- `curriculum_patch_queue.json` 的 patch proposal

因此系统可以明确回答三类问题：
- 这份内容是谁、在哪个阶段生成的
- 为什么它被判定为可推进或需要阻断
- 它具体能追溯到哪些 session、资料段落或诊断证据

---

## 4. 状态文件说明

### 4.1 正式长期状态

```text
learn-plan.md
materials/index.json
sessions/*/progress.json
```

含义：
- `learn-plan.md` 是正式长期 curriculum 主文档
- `materials/index.json` 是材料索引与缓存状态
- `progress.json` 是单次 session 的事实记录

### 4.2 workflow 中间状态

```text
.learn-workflow/
├── clarification.json
├── research.json
├── diagnostic.json
├── approval.json
├── workflow_state.json
├── learner_model.json
└── curriculum_patch_queue.json
```

普通用户通常不需要手动维护这些文件。

其中：
- `clarification.json`：目标、水平、偏好、约束
- `research.json`：能力要求报告与材料取舍依据
- `diagnostic.json`：诊断题、批改、起点判断
- `approval.json`：计划草案确认与风险接受
- `workflow_state.json`：当前 workflow route 摘要
- `learner_model.json`：跨 session 能力证据、复习债与当前掌握度估计
- `curriculum_patch_queue.json`：待确认的课程调整建议；当前只会写入 `proposed` / `pending-evidence` patch，不会自动改主线计划

---

## 5. 目录结构示例

```text
learning/topic/
├── learn-plan.md
├── learn-today-2026-04-02.md
├── materials/
│   ├── index.json
│   └── ...
├── sessions/
│   ├── 2026-04-02/
│   │   ├── questions.json
│   │   ├── progress.json
│   │   ├── 题集.html
│   │   └── server.py
│   └── 2026-04-02-test/
│       ├── questions.json
│       ├── progress.json
│       ├── 题集.html
│       └── server.py
└── .learn-workflow/
    ├── clarification.json
    ├── research.json
    ├── diagnostic.json
    ├── approval.json
    ├── workflow_state.json
    ├── learner_model.json
    └── curriculum_patch_queue.json
```

---

## 6. 支持主题

当前主题识别采用可扩展 family，默认支持：
- `linux`
- `llm-app`
- `backend`
- `frontend`
- `database`
- `algorithm`
- `math`
- `english`
- `general-cs`

若主题未命中更具体 family，会回退到 `general-cs`。

说明：部分 family 在 session 题库层可能暂时复用通用工程题库；后续会逐步增强。

---

## 7. session 与服务器管理

`/learn-today` 和 `/learn-test` 会复用本地 session runtime：
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`

若 session 已完整，会继续该 session，而不是重建。

服务默认使用端口 `8080`。如果端口占用，应先确认占用进程，再决定是否停止旧服务。

手动停服方式：

```bash
# 方式 1：在服务器终端按 Ctrl+C

# 方式 2：向本地服务发送 shutdown 请求（若服务可访问）
# 或按运行时输出的手动停服命令执行
```

---

## 8. 材料管理

`materials/index.json` 记录：
- 材料标题、类型、URL
- mainline / supporting / optional / candidate 角色
- 阅读定位
- cache 状态
- 本地路径
- 后续可用的 segment / source excerpt 信息

默认材料中很多是在线资源元数据，不代表都能自动下载。

如果要添加自己的材料，可以直接向 `materials/index.json` 添加条目，例如：

```json
{
  "id": "custom-material",
  "title": "自定义材料",
  "kind": "tutorial",
  "url": "https://example.com/material.pdf",
  "downloadable": true,
  "tags": ["algorithm", "tutorial"]
}
```

然后运行：

```bash
/learn-download-materials
```

---

## 9. 与 PROJECT.md 的关系

学习系统默认不读取 `PROJECT.md`。

默认主状态源是：
- `learn-plan.md`
- `materials/index.json`
- `sessions/*/progress.json`
- `.learn-workflow/*.json`

只有当你明确要求兼容旧项目记录或迁移旧学习日志时，才把 `PROJECT.md` 当作可选参考。

---

## 10. 开发文档

如果要继续重构或扩展这套 skill 簇，优先阅读：
- `WORKFLOW_DESIGN.md`：整体架构与迁移计划
- `docs/contracts.md`：JSON / Markdown section 契约
- `docs/state-files.md`：状态文件读写边界
- `docs/runtime-compatibility.md`：兼容底线
- `docs/skill-operator-guide.md`：执行器行为规则

当前技术栈：
- Python 3.8+
- 本地 JSON 文件
- 原生 HTML/CSS/JavaScript
- 本地 Python HTTP server

---

## 11. 安全提示

本工具会在本地执行题目中的代码，仅适用于你信任的题目数据。

它不是安全沙箱；不要用它运行不可信代码。

---

## 12. 一句话总结

`learn-plan` skill 簇是一套本地学习系统：先用 `/learn-plan` 做顾问式长期规划，再用 `/learn-today` 和 `/learn-test` 执行学习与评估，最后用 update 入口把结果回流为后续学习依据。
