# learn-plan skill 簇工作流设计文档

## 1. 文档目的

本文档是整个 `/learn-plan` skill 簇的**架构真相源**，用于指导后续重构与实现。

覆盖范围：
- `/learn-plan`
- `/learn-today`
- `/learn-test`
- `/learn-today-update`
- `/learn-test-update`
- `/learn-download-materials`
- 共享脚本、状态文件、材料系统、session runtime 与文档体系

核心目标：把当前耦合在少数大脚本中的学习系统，重构为**由代码固定流程动作、由 LLM 负责专业内容生成**的多阶段学习工作流。

核心原则：
- **流程动作由代码固定**：阶段切换、gate、契约校验、正式计划落盘、session 产物校验、update 写回边界必须由代码控制。
- **专业细节由 LLM 生成**：问卷追问、research、能力指标细化、诊断题设计、批改、学习方案草案、讲课、出题、复盘建议由 LLM 负责。
- **正式状态和中间态分离**：workflow 中间 JSON 不能替代 `learn-plan.md`，session `progress.json` 不能替代 learner model。
- **不破坏现有 session runtime**：继续保留 `questions.json + progress.json + 题集.html + server.py` 的本地学习/测试模型。
- **整个 skill 簇统一演进**：`/learn-plan`、daily teacher、test、update、materials 不再作为松散脚本各自演化。

相关细化文档：
- 数据契约：`docs/contracts.md`
- 状态文件所有权：`docs/state-files.md`
- 运行时兼容边界：`docs/runtime-compatibility.md`
- 执行器规则：`docs/skill-operator-guide.md`

---

## 2. 本轮重构范围与非目标

## 2.1 范围

本轮目标是制定并逐步实施整个 skill 簇的重构方案，包括：

1. 重定义目标架构与职责边界。
2. 固化 workflow 中间态、正式计划、session 事实、learner model、patch queue 的状态分层。
3. 将 `learn_plan.py` 从大一统脚本改为 CLI facade + workflow/planning/materials 模块。
4. 将 `session_orchestrator.py` 从巨型 runtime 脚本改为 CLI facade + daily/test runtime pipeline。
5. 将 update 脚本从日志摘要器升级为 learner model 与 curriculum patch 建议器。
6. 将 materials 从模板列表升级为 capability-driven 材料系统。
7. 收口 `SKILL.md`、`README.md` 与 docs 的职责边界。

## 2.2 非目标

本轮不做：
- 不替换本地前端/后端 runtime 协议。
- 不把 `learn-plan.md` 改成纯 JSON 主状态。
- 不让 update 脚本未经用户确认直接重写长期 curriculum。
- 不强制旧项目一次性迁移到完整新 schema。
- 不默认读取 `PROJECT.md` 作为学习系统主链路输入；只有用户明确要求兼容或迁移旧记录时才读取。

---

## 3. 当前实现判断

## 3.1 已具备能力

当前系统已经具备：
- `/learn-plan` 的 `auto / draft / research-report / diagnostic / finalize` mode 雏形。
- `clarification / research / diagnostic / approval / ready` 的 gate 雏形。
- `learn-plan.md -> materials/index.json -> /learn-today|/learn-test -> progress.json -> update -> learn-plan.md` 的基本闭环。
- `questions.json + progress.json + 题集.html + server.py` 的本地 session runtime。
- `/learn-today` 与 `/learn-test` 共用 `session_orchestrator.py` / `session_bootstrap.py` 的机制。
- update 脚本已经能摘要 session 表现并追加学习/测试记录。
- materials 下载器已经能按 `materials/index.json` 的缓存字段工作。

## 3.2 主要结构问题

当前系统的主要债务不是单点 bug，而是边界不清：

1. `learn_plan.py` 同时承担 CLI、topic family、workflow route、profile、renderer、materials index、quality check 与落盘。
2. `/learn-plan` 的 route 仍偏启发式关键词判断，不是真正 contract-based state machine。
3. `draft / research-report / diagnostic` 与 `finalize` 的中间态/正式态边界不够硬。
4. `session_orchestrator.py` 同时承担计划解析、历史进度、材料选择、lesson grounding、LLM/fallback 出题、payload 组装与 bootstrap 调用。
5. update 脚本主要是日志摘要器，还不是 learner model / curriculum patch 层。
6. materials planning 主要由 family 模板与 metadata 驱动，还不是 capability metrics 驱动。
7. 文档之间重复较多，且原设计文档中“Daily Teacher 下一阶段”的表述已不符合当前整个 skill 簇的重构范围。

## 3.3 目标转变

目标不是让 `/learn-plan` “更会写计划”，而是让整个 skill 簇成为：

```text
顾问规划 -> 能力建模 -> 起始测试（复用 /learn-test 与 /learn-test-update） -> 草案确认 -> 正式计划
        -> Daily Teacher 执行 -> Test 评估 -> Feedback 更新 learner model / patch 建议
```

---

## 4. 目标架构：六个子系统

建议将 `/Users/xinyuan/.claude/skills/learn-plan` 作为共享实现包，其它 `/learn-*` skills 保持轻量入口。

## 4.1 Conversation Orchestrator

**承载位置**：各入口 `SKILL.md` 与 Claude Code 对话层。

**本质**：LLM 对话编排层。

**负责**：
- 与用户对话。
- 追问目标、水平、约束、偏好。
- 解释 workflow 阶段与 gate。
- 设计 research plan 并等待用户确认。
- 执行 research 并形成能力要求报告。
- 设计诊断题、批改答案、解释起点判断。
- 生成学习方案草案并收集修改意见。
- daily teacher 阶段做 check-in、讲课、解释题目、复盘建议。

**不负责**：
- 绕过 gate 直接 finalize。
- 把模糊回答当确认事实。
- 把草案当正式 `learn-plan.md`。
- 未经确认就把 patch 应用到长期计划主体。

**输入**：
- 用户自然语言需求。
- workflow engine route summary。
- 已存在的中间态 JSON。
- 正式计划、材料索引、progress、learner model。

**输出**：
- 用户可见解释、追问、报告、题目、反馈。
- 可写入中间态 JSON 的结构化内容。
- 对 CLI facade 的调用指令。

**完成条件**：
- 当前阶段所需 JSON 或正式产物满足 gate。
- 或明确阻塞在某阶段，并向用户说明下一步需要提供什么。

## 4.2 Workflow Engine

**承载位置**：目标模块 `learn_workflow/`。

**本质**：代码状态机与 gate 校验层。

**负责**：
- 读取 `.learn-workflow/*.json`。
- 判断当前 stage / blocking stage。
- 输出 `recommended_mode / next_action / missing_requirements / quality_issues`。
- 只有全部 gate 通过时允许 `finalize`。
- 写入 `workflow_state.json`。

**不负责**：
- 追问。
- research。
- 出题。
- 批改开放式回答。
- 生成正式计划正文。

**输入**：
- `clarification.json`
- `research.json`
- `diagnostic.json`
- `approval.json`
- 目标 topic/goal/level/schedule/preference 的 CLI 参数

**输出**：
- `workflow_state.json`
- `--stdout-json` route summary

**完成条件**：
- `blocking_stage = ready`
- `should_continue_workflow = false`
- `is_intermediate_product = false`
- `next_action = enter:/learn-today`

## 4.3 Planning System

**承载位置**：目标模块 `learn_planning/`。

**本质**：正式长期学习计划生成与验证层。

**负责**：
- 从 workflow JSON 构建 learner profile。
- 从 research 结果构建 capability model。
- 从 diagnostic 结果确定起点。
- 构建阶段 curriculum。
- 构建 materials plan。
- 渲染正式 `learn-plan.md`。
- 验证正式计划是否能被 `/learn-today` 日拆。

**不负责**：
- 与用户对话。
- 直接启动 session。
- 根据一次 session 自动改长期路线。

**输入**：
- 四类 workflow JSON。
- 旧 `learn-plan.md` 中需要保留的记录区块。
- 材料可用性与候选材料。

**输出**：
- `<root>/learn-plan.md`
- `<root>/materials/index.json`
- plan validation result

**完成条件**：
- 正式计划包含稳定 section。
- 每阶段都有目标、资料定位、练习、掌握标准、产出证据。
- `学习记录` / `测试记录` 可继续追加。

## 4.4 Materials System

**承载位置**：目标模块 `learn_materials/`。

**本质**：能力驱动的材料索引、缓存与预处理层。

**负责**：
- 将 capability metrics 映射到材料角色。
- 维护 `materials/index.json`。
- 维护 mainline/supporting/optional/candidate 分类。
- 下载可直链材料。
- 预处理 PDF/html/md/txt 等文本来源。
- 维护 segment cache / source excerpt / key points。

**不负责**：
- 决定学习长期路线是否改动。
- 生成 lesson 或题目。

**输入**：
- capability model。
- curriculum 阶段目标。
- 候选材料与本地材料。
- `materials/index.json` 旧状态。

**输出**：
- 更新后的 `materials/index.json`。
- 本地缓存文件。
- segment/source excerpt 缓存。

**完成条件**：
- 主线材料可执行，至少有章节/小节/路径级定位。
- 下载失败不阻断 runtime，能回退 metadata-only。

## 4.5 Execution Runtime / Daily Teacher

**承载位置**：目标模块 `learn_runtime/`，CLI facade 仍由 `session_orchestrator.py` 提供。

**本质**：today/test session 生成与启动管线。

**负责**：
- 读取正式 `learn-plan.md`。
- 读取 `materials/index.json`。
- 读取最近 `progress.json` 与 `learner_model.json`。
- 结合用户 check-in 生成 session plan。
- 生成 `lesson.md` 与 daily/test lesson plan。
- 做 material grounding。
- 生成题目并保证题目可追踪到 lesson / capability / segment。
- 组装 `questions.json`。
- 调用 `session_bootstrap.py` 生成/继续 session。

**不负责**：
- 修改 workflow 中间态。
- 未经批准改长期 curriculum 主体。
- 替换前端/server 协议。

**输入**：
- `learn-plan.md`
- `materials/index.json`
- `learner_model.json`
- recent `sessions/*/progress.json`
- 用户 check-in

**输出**：
- `lesson.md`
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`
- 浏览器学习/测试 session

**完成条件**：
- session 四件套存在且结构有效。
- 服务启动或给出明确端口占用/手动处理说明。

## 4.6 Feedback / Learner Model

**承载位置**：目标模块 `learn_feedback/`。

**本质**：session 结果 -> learner model -> patch 建议层。

**负责**：
- 读取 `questions.json` 与 `progress.json`。
- 形成客观事实摘要。
- 更新 `learner_model.json` 的能力估计、证据、复习债。
- 生成 `curriculum_patch_queue.json` 中的 proposed patch。
- 向 `learn-plan.md` 追加学习/测试记录。

**不负责**：
- 未经用户确认直接改长期路线主体。
- 把单次表现夸大成稳定能力结论。

**输入**：
- `questions.json`
- `progress.json`
- `learn-plan.md`
- `learner_model.json`

**输出**：
- 更新后的 `learner_model.json`
- 更新后的 `curriculum_patch_queue.json`
- `learn-plan.md` 的记录区块追加

**完成条件**：
- facts / model_update / curriculum_patch 三层分开。
- 正式计划主体未被未批准 patch 改写。

---

## 5. 目标目录结构

当前结构：

```text
/Users/xinyuan/.claude/skills/learn-plan/
├── SKILL.md
├── README.md
├── WORKFLOW_DESIGN.md
├── docs/
│   ├── contracts.md
│   ├── state-files.md
│   ├── runtime-compatibility.md
│   └── skill-operator-guide.md
├── learn_plan.py
├── session_orchestrator.py
├── session_bootstrap.py
├── learn_today_update.py
├── learn_test_update.py
├── material_downloader.py
├── learn_core/
│   ├── __init__.py
│   ├── io.py
│   ├── markdown_sections.py
│   ├── text_utils.py
│   ├── plan_parser.py
│   ├── topic_family.py
│   └── llm_json.py
├── learn_workflow/
│   ├── __init__.py
│   ├── contracts.py
│   ├── state_machine.py
│   ├── gates.py
│   └── workflow_store.py
├── learn_planning/
│   ├── __init__.py
│   ├── learner_profile.py
│   ├── capability_model.py
│   ├── curriculum_builder.py
│   ├── plan_renderer.py
│   ├── plan_validator.py
│   └── section_preserver.py
├── learn_materials/
│   ├── __init__.py
│   ├── planner.py
│   ├── segments.py
│   ├── merge.py
│   ├── index_schema.py
│   ├── downloader.py
│   ├── preprocessing.py
│   └── segment_cache.py
├── learn_runtime/
│   ├── __init__.py
│   ├── plan_source.py
│   ├── session_history.py
│   ├── material_selection.py
│   ├── source_grounding.py
│   ├── lesson_builder.py
│   ├── question_generation.py
│   ├── question_banks.py
│   ├── question_validation.py
│   └── payload_builder.py
└── learn_feedback/
    ├── __init__.py
    ├── progress_summary.py
    ├── learner_model.py
    ├── curriculum_patch.py
    ├── plan_update_renderer.py
    └── update_history.py
```

说明：
- `learn_plan.py`、`session_orchestrator.py`、update 脚本和 downloader 先保留为 CLI facade。
- 新模块分阶段抽出，避免一次性破坏外部入口。
- `session_bootstrap.py` 相对稳定，优先保持对外语义不变。

---

## 6. 状态文件与数据流

## 6.1 正式长期状态

继续保留：

```text
<root>/learn-plan.md
<root>/materials/index.json
<root>/sessions/*/progress.json
```

职责：
- `learn-plan.md`：用户可读的正式 curriculum 主文档。
- `materials/index.json`：材料索引、角色、segment、缓存状态。
- `progress.json`：session 事实记录与交互进度。

## 6.2 workflow 中间态

正式启用：

```text
<root>/.learn-workflow/
├── clarification.json
├── research.json
├── diagnostic.json
├── approval.json
└── workflow_state.json
```

职责：
- `clarification.json`：用户画像、目标、约束、偏好、非目标、未决问题。
- `research.json`：research plan、能力要求报告、来源摘要、材料取舍依据。
- `diagnostic.json`：题目、回答、批改结果、起点判断、置信度。
- `approval.json`：用户确认、待决项、风险接受、`ready_for_execution`。
- `workflow_state.json`：当前 stage、blocking stage、推荐动作、上次 route 摘要。

## 6.3 learner model 与 patch 状态

新增：

```text
<root>/.learn-workflow/learner_model.json
<root>/.learn-workflow/curriculum_patch_queue.json
```

职责：
- `learner_model.json`：跨 session 的能力掌握度、证据、复习债、偏好变化。
- `curriculum_patch_queue.json`：update 层提出的计划调整建议，等待 approval 后再应用到正式计划。

## 6.4 主数据流

```text
/learn-plan:
用户输入 -> workflow JSON -> workflow gate -> planning/materials -> learn-plan.md + materials/index.json

/learn-today|/learn-test:
learn-plan.md + materials/index.json + learner_model.json + progress history + check-in
-> session plan -> lesson.md -> questions.json -> progress.json -> runtime

/learn-today-update|/learn-test-update:
questions.json + progress.json
-> facts summary -> learner_model update -> patch proposal -> learn-plan.md 记录追加

/learn-download-materials:
materials/index.json -> download/cache/preprocess -> materials/index.json 缓存字段回写
```

---

## 7. `/learn-plan` 工作流设计

## 7.1 状态机

固定状态机：

```text
clarification
  -> research (if needed)
  -> diagnostic (if needed)
  -> approval
  -> finalize
  -> enter:/learn-today
```

说明：
- `research` 可跳过，但必须记录理由。
- `diagnostic` 原则上不完全跳过；若用户坚持跳过，必须在 `approval.json` 中记录风险接受。
- `finalize` 只能由 workflow engine gate 放行。

## 7.2 workflow 类型

LLM 在 intake 后先判断类型：

| 类型 | 适用条件 | 路径 |
| --- | --- | --- |
| `light` | 目标清楚、水平可信、不明显需要外部标准 | clarification -> diagnostic(minimal) -> approval -> finalize |
| `diagnostic-first` | 目标清楚但当前水平不可靠 | clarification -> diagnostic -> approval -> finalize |
| `research-first` | 目标涉及岗位/职业/材料取舍/复杂实践标准 | clarification -> research -> diagnostic -> approval -> finalize |
| `mixed` | research 与 diagnostic 都不可跳过 | clarification -> research -> diagnostic -> approval -> finalize |

## 7.3 mode 映射

| 概念阶段 | CLI mode | 说明 |
| --- | --- | --- |
| intake / clarification | `draft` | 问卷、偏好、目标确认 |
| research / capability modeling | `research-report` | 研究计划、能力要求报告 |
| diagnostic | `diagnostic` | 出题、作答、批改、起点判断 |
| plan draft / approval | `draft` | 草案、取舍说明、确认 |
| finalize | `finalize` | 正式落盘 |
| route | `auto` | 自动判断 blocking stage，不代表业务阶段 |

## 7.4 统一质量 contract 与放行边界

所有阶段共享同一套质量字段：
- `generation_trace`
- `quality_review`
- `evidence`
- `confidence`
- `traceability`

统一边界：
- LLM 负责生成 candidate 内容，也可以生成 reviewer 所需的候选分析，但不直接拥有放行权。
- reviewer 负责输出 `quality_review`，说明当前 candidate 是否 ready、缺什么、证据是否充分。
- deterministic gate 负责读取中间态与 `quality_review`，决定 `blocking_stage`、`quality_issues`、`next_action`。
- `finalize` 只消费已通过 gate 的结构化状态，并由 renderer 写正式 `learn-plan.md`；LLM 不直接写最终正式计划正文。
- runtime / feedback 也继承同一套字段，保证 lesson、questions、learner model、patch queue 能沿统一 traceability 审计。

## 7.5 各阶段 LLM 具体职责

### Phase 1：Clarification

**触发**：首次 `/learn-plan`、`blocking_stage=clarification|preference`。

**输入**：用户需求、旧计划画像、已有 `clarification.json`、材料路径、时间约束。

**LLM 工作**：
1. 追问学习主题、目标、成功标准。
2. 追问当前水平、背景、学习频率、单次时长、deadline。
3. 追问学习偏好、练习偏好、反馈偏好、掌握证据偏好。
4. 收集已有资料与非目标。
5. 将模糊信息记录为 assumption，不当作确认事实。
6. 产出可写入 `clarification.json` 的结构化内容。

**用户可见输出**：画像确认、未决问题、下一阶段说明。

**机器输出**：`clarification.json`。

**完成条件**：topic/goal/success criteria/current level/time constraints/preferences 均明确，阻塞问题为空。

### Phase 2：Research / Capability Modeling

**触发**：职业/岗位/求职/复杂技术栈/材料取舍依赖外部标准，或 `blocking_stage=research`。

**输入**：`clarification.json`、用户确认的 research plan、检索结果、本地资料摘要。

**LLM 工作**：
1. 先生成 research plan，并等待用户确认。
2. research 回答目标水平、能力集合、主线/支撑/后置能力。
3. 将目标转成可观察行为、量化指标、诊断方法、学习证据。
4. 解释材料取舍：选哪些、不选哪些、为什么。
5. 记录 source evidence 与 open risks。
6. 产出 `research.json`。

**用户可见输出**：research plan、能力要求报告。

**机器输出**：`research.json`。

**完成条件**：research plan 已批准或完成，capability metrics 非空，主线能力有诊断和证据，来源依据清晰。

### Phase 3：Diagnostic

**触发**：research 后需要判断真实起点、用户自报不可靠，或 `blocking_stage=diagnostic`。

**输入**：`clarification.json`、`research.json.capability_metrics`、用户背景、题型偏好。

**LLM 工作**：
1. 选择优先诊断的能力项。
2. 设计最小诊断题组。
3. 每题绑定 capability、expected signals、rubric。
4. 收到答案后批改，指出证据、缺口与误判风险。
5. 汇总 capability assessment、recommended entry level、confidence。
6. 产出 `diagnostic.json`。

**用户可见输出**：诊断题、批改反馈、起点判断摘要。

**机器输出**：`diagnostic.json`。

**完成条件**：题已答并 evaluated，有能力维度评估、推荐起点和置信度。

### Phase 4：Plan Draft & Approval

**触发**：clarification 完成，必要 research/diagnostic 完成，或 `blocking_stage=approval`。

**输入**：四类 workflow JSON、材料可用性、候选材料、旧计划记录区块。

**LLM 工作**：
1. 生成计划草案，不直接 finalize。
2. 解释为什么从这个起点开始。
3. 解释为什么这样分阶段、每阶段服务哪个 capability。
4. 每阶段给出资料、章节/页码/路径定位、练习方式、掌握标准、产出证据。
5. 明确后置内容与 tradeoff。
6. 收集用户确认或修改意见。
7. 产出 `approval.json`。

**用户可见输出**：计划草案、待确认决策、关键 tradeoff。

**机器输出**：`approval.json`。

**完成条件**：用户明确 approved，资料策略、daily execution style、mastery checks 均确认，pending decisions 为空。

### Phase 5：Finalize

**触发**：workflow engine 返回 `blocking_stage=ready` 或所有 gate 通过。

**输入**：四类 workflow JSON、用户最终确认、学习根目录。

**LLM 工作**：
1. 调用 `learn_plan.py --mode finalize`，不手写正式计划绕过 gate。
2. 检查 `quality_issues`。
3. 若有问题，回退到对应阶段。
4. 告知正式计划路径、材料索引路径、下一步 `/learn-today`。

**代码输出**：`learn-plan.md`、`materials/index.json`、可选下载结果。

**完成条件**：`next_action=enter:/learn-today`。

---

## 8. Daily Teacher / Runtime 设计

## 8.1 触发入口

- `/learn-today`
- `/learn-test`

## 8.2 输入

- `learn-plan.md`
- `materials/index.json`
- `.learn-workflow/learner_model.json`（若存在）
- 最近 `sessions/*/progress.json`
- 用户 check-in：真实进度、卡点、今日时间、复习/推进偏好

## 8.3 LLM 具体职责

Daily Teacher 阶段的 LLM 不是重新规划长期路线，而是做当天教学：

1. **进度解释**：结合长期计划、历史 progress、用户 check-in 判断今天应复习/推进/回炉什么。
2. **讲课**：围绕当天 capability / material segment 生成 `lesson.md`。
3. **阅读指导**：明确资料、章节、页码、小节或 repo 目录。
4. **出题**：题目绑定 lesson section、capability、material segment 或 source excerpt。
5. **测试聚焦**：`/learn-test` 时根据测试模式选择覆盖范围与薄弱点。
6. **质量校验**：代码侧对 `questions.json` 执行 deterministic validation，检查 schema、答案/解析、来源标记、fallback 比例与 traceability。
7. **失败回退**：LLM 不可用或 JSON 校验失败时，回退 source excerpt 题，再回退内置题库。

## 8.4 Runtime pipeline

```text
plan parser
-> progress reader
-> session plan
-> material grounding
-> lesson planner
-> question generation
-> question validation
-> runtime payload
-> session_bootstrap.py
```

## 8.5 完成条件

必须生成或继续完整 session：
- `lesson.md`
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`

若端口占用，不能只抛 traceback；应告知占用并询问是否协助处理。

---

## 9. Feedback / Update 设计

## 9.1 触发入口

- `/learn-today-update`
- `/learn-test-update`

## 9.2 输入

- session 目录
- `questions.json`
- `progress.json`
- `learn-plan.md`
- `learner_model.json`（若存在）

## 9.3 LLM/代码具体职责

update 输出分三层：

1. **facts**：客观事实
   - 总题数、已做题数、正确/通过数
   - 高频错误点
   - 未完成材料/题目
   - 测试覆盖范围

2. **model_update**：学习者模型更新
   - capability 级别的掌握证据
   - 置信度变化
   - 弱点与复习债
   - 下次优先级

3. **curriculum_patch**：课程调整建议
   - 是否建议回炉
   - 是否建议推迟某阶段
   - 是否建议更换/补充材料
   - 是否建议增加某类练习
   - evidence / confidence 是否足够进入 `proposed`

## 9.4 写回边界

允许直接写：
- `learner_model.json`
- `curriculum_patch_queue.json` 中的 `proposed` / `pending-evidence` patch
- `learn-plan.md` 的 `学习记录` / `测试记录` 追加

不允许直接写：
- 未经用户确认的长期阶段路线主体
- 未批准的材料主线重排

---

## 10. Materials 设计

## 10.1 输入

- research capability metrics
- curriculum stage goals
- 用户已有材料
- family 默认材料
- 旧 `materials/index.json`

## 10.2 具体职责

1. **材料规划**：将 capability 映射到 mainline/supporting/optional/candidate 材料。
2. **阅读定位**：尽量细到章节、小节、页码或 repo 路径。
3. **缓存管理**：下载可直链材料并回写 cache 状态。
4. **预处理**：提取文本、segment、key points、examples、pitfalls。
5. **runtime grounding**：为 daily/test 题目和 lesson 提供 source excerpt。

## 10.3 失败回退

- 材料下载失败：标记 `download-failed`，不阻断计划。
- 预处理失败：回退 metadata-only。
- source excerpt 缺失：题目生成回退到 lesson 内容，再回退内置题库。

---

## 11. 文档分工

目标分工：

| 文档 | 职责 |
| --- | --- |
| `WORKFLOW_DESIGN.md` | 整个 skill 簇架构真相源 |
| `docs/contracts.md` | JSON / Markdown section 契约 |
| `docs/state-files.md` | 状态文件职责、读写边界、迁移规则 |
| `docs/runtime-compatibility.md` | 保持用户可用性的兼容底线 |
| `docs/skill-operator-guide.md` | skill 外层执行器该如何跟随 route summary 行动 |
| `SKILL.md` | `/learn-plan` 入口协议 |
| `README.md` | 用户视角快速指南 |
| 其它 `/learn-*` 的 `SKILL.md` | 各自轻量入口协议 |

---

## 12. 分阶段迁移策略

## Phase 0：冻结架构与契约

目标：文档真相源定稿，不改变用户行为。

动作：
- 更新 `WORKFLOW_DESIGN.md`。
- 新增 `docs/contracts.md`。
- 新增 `docs/state-files.md`。
- 新增 `docs/runtime-compatibility.md`。
- 新增 `docs/skill-operator-guide.md`。
- 选择旧 `learn-plan.md` / `materials/index.json` / `questions.json` / `progress.json` 样本作为兼容验收样例。

## Phase 1：抽 shared core，不改行为

目标：先降低重复，避免后续拆分高风险。

动作：
- 抽 `learn_core/io.py`。
- 抽 `learn_core/markdown_sections.py`。
- 抽 `learn_core/topic_family.py`。
- 抽 `learn_core/plan_parser.py`。
- 让 `learn_plan.py` 与 update 脚本逐步共用这些函数。

## Phase 2：重建 workflow engine

目标：把 `/learn-plan` 从启发式路由改为契约驱动。

动作：
- 实现 `learn_workflow/contracts.py`。
- 实现 `learn_workflow/state_machine.py`。
- 实现 `learn_workflow/gates.py`。
- 实现 `learn_workflow/workflow_store.py`。
- 标准化 `--stdout-json`。
- 正式启用 `.learn-workflow/*.json`。
- 非 `finalize` 阶段不再覆盖正式 `learn-plan.md`。

## Phase 3：拆 planning/materials renderer

目标：让长期计划生成真正模块化。

动作：
- 抽 learner profile / capability model / curriculum builder / renderer / validator / materials planner。
- 新增正式 section：`能力指标与起点判断`。
- 保持 `learn-plan.md` 和 `materials/index.json` 兼容 today/test。

## Phase 4：拆 runtime，Daily Teacher 一等化

目标：让 `/learn-today` 和 `/learn-test` 成为 teacher/runtime 管线。

动作：
- 拆 `session_orchestrator.py`。
- 新增 session plan / progress reader / lesson planner / material grounding / question generation / runtime payload。
- 保留 `session_bootstrap.py` 与现有前端/server。
- 让题目可追踪到 lesson / capability / segment。

## Phase 5：升级 feedback / learner model

目标：让 update 不只是记日志，而能更新 learner model 和提出 curriculum patch。

动作：
- 新增 progress summary / learner model / curriculum patch / plan update renderer。
- update 脚本写 learner model + patch queue + 用户可读日志。
- 长期计划主体修改走 patch approval。

## Phase 6：materials preprocessing 与 source grounding

目标：提升 lesson/题目来源对齐质量。

动作：
- 抽 downloader 核心到 `learn_materials/downloader.py`。
- 实现 preprocessing 与 segment cache。
- runtime 优先使用 cache 做 grounding，失败安全回退。

## Phase 7：清理旧逻辑与文档收口

目标：完成真正重构。

动作：
- 删除或瘦身已迁移的大块旧函数。
- 收口 README/SKILL/WORKFLOW_DESIGN 重复内容。
- 保留 CLI facade 文件名与 skill 入口兼容。

---

## 13. 验收与验证

按以下顺序验收：

1. **状态机验收**
   - `light / diagnostic-first / research-first / mixed` 是否正确分流。
   - `blocking_stage` 是否准确。

2. **契约验收**
   - 四类 workflow JSON 是否可读写。
   - 缺字段是否正确阻塞。
   - learner model 与 patch queue 是否不破坏旧链路。

3. **正式计划兼容性验收**
   - finalize 后的 `learn-plan.md` 是否仍可被 `/learn-today` 消费。
   - `学习记录 / 测试记录` 是否仍可追加。

4. **runtime 回归验收**
   - `/learn-today`、`/learn-test` 是否仍能生成完整 session。
   - `session_bootstrap.py` 与前端/server 是否不被破坏。

5. **feedback 验收**
   - update 是否能保留原日志输出。
   - learner model 是否正确更新。
   - curriculum patch 是否仅作为建议等待确认。

6. **materials 验收**
   - 下载、缓存、预处理失败是否安全回退。
   - source grounding 是否优先命中本地/segment cache。

7. **用户体验验收**
   - 用户能感知到：先顾问规划，再 daily teacher 执行，再反馈更新 learner model。
   - 用户能理解计划为什么适合自己。

---

## 14. 关键风险与控制

1. **中间态 JSON 与正式计划漂移**
   - 控制：只有 `finalize` 和 approved patch 可写 `learn-plan.md` 主体。

2. **runtime 拆分导致题目生成漂移**
   - 控制：第一轮只搬现有逻辑，保留 LLM -> content-derived -> bank fallback 顺序。

3. **learner model 变成第二个混乱主状态源**
   - 控制：learner model 只保存能力证据与复习债，正式 curriculum 仍以 `learn-plan.md` 为主。

4. **materials preprocessing 阻断学习**
   - 控制：预处理是增强层，失败回退 metadata-only。

5. **文档继续重复**
   - 控制：架构、契约、状态、兼容、入口协议、用户指南分别落到不同文档。

---

## 15. 一句话总结

目标不是单独增强 `/learn-plan`，而是把整个 `/learn-plan` skill 簇重构成一个 **代码负责流程与状态，LLM 负责专业教学内容，正式计划、运行时事实和学习者模型分层清晰** 的本地学习系统。
