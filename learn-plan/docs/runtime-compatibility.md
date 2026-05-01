# learn-plan skill 簇运行时兼容边界

本文档定义整个 `/learn-plan` skill 簇在重构过程中的**兼容性底线**：哪些运行时行为必须保持稳定，哪些能力允许逐步演进，哪些地方可以重写但不能破坏用户现有使用方式。

相关文档：
- 架构总览：`../WORKFLOW_DESIGN.md`
- 契约文档：`./contracts.md`
- 状态文件：`./state-files.md`

---

## 1. 兼容目标

当前重构不是推倒重来，而是在保留用户可用性的前提下，把 skill 簇从一组耦合脚本重构为稳定的多层系统。

因此兼容目标分三层：

1. **入口兼容**：用户仍通过原有 skills 使用系统
2. **产物兼容**：现有 session 运行时仍认 `questions.json + progress.json + 题集.html + server.py`
3. **计划兼容**：现有 `learn-plan.md` 和 `materials/index.json` 仍能继续被消费

---

## 2. 必须保持兼容的外部接口

## 2.1 skill 入口名

以下 user-facing skills 名称必须保持不变：
- `/learn-plan`
- `/learn-today`
- `/learn-test`
- `/learn-download-materials`

今日学习回写与测试回写不再作为独立 slash skill 暴露，分别收口到 `/learn-today` Step 6 与 `/learn-test` Step 7。

## 2.2 CLI facade 文件

以下脚本文件名应尽量保留，作为外部入口 facade：
- `learn_plan.py`
- `session_orchestrator.py`
- `session_bootstrap.py`
- `learn_today_update.py`
- `learn_test_update.py`
- `learn_materials/downloader.py`

说明：
- 这些脚本内部可以逐步瘦身并委托到新模块。
- 但不应在重构早期直接删掉或改名，否则会破坏 skill prompt 中已写死的调用方式。

---

## 3. 必须保持兼容的正式产物

## 3.1 learn-plan.md

`learn-plan.md` 必须继续被视为正式长期计划文件。

重构期间必须保证：
- `/learn-today` 可以读取它
- `/learn-test` 可以读取它
- `/learn-today` Step 6 与 `/learn-test` Step 4 可以继续向 `学习记录` / `测试记录` 追加内容

允许变化：
- 可以新增 `能力指标与起点判断` 等区块
- 可以优化 section 内内容表达

不允许破坏：
- 删除 `今日生成规则`
- 删除 `学习记录`
- 删除 `测试记录`
- 让 runtime 只能依赖新 JSON 而无法处理已有 plan

## 3.2 materials/index.json

`materials/index.json` 必须继续存在，并继续承担材料索引职责。

重构期间必须保证：
- `/learn-download-materials` 能继续读写它
- runtime 能继续从中拿到材料条目
- 旧索引即使没有 `segments` 或 source excerpts，也不会导致 `/learn-today` / `/learn-test` 失败

允许变化：
- 新增 `segments`
- 新增 `selection_rationale`
- 新增预处理与缓存字段

不允许破坏：
- 只允许把 `entries` 作为当前 canonical 根数组，同时兼容读取旧 `items` / `materials`
- 让 downloader 覆盖掉规划层字段

## 3.3 session 目录结构

session 目录仍必须采用：

```text
sessions/YYYY-MM-DD/
sessions/YYYY-MM-DD-test/
```

单个 session 目录中，以下文件仍是完整 session 的最低判定：
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`

允许新增：
- `learn-today-YYYY-MM-DD.md`
- `test.json`
- `lesson_review` / `question_review` 等 advisory 产物
- 其他调试/中间产物

但新增文件不能替代上述最低四件套。

---

## 4. 必须保持兼容的 session 契约

## 4.1 questions.json

必须继续满足：
- 有统一顶层字段：`date/topic/mode/session_type/session_intent/assessment_kind/test_mode/plan_source/materials/questions`
- 每题有唯一 `id`
- 概念题 / 代码题的基本字段形状稳定

允许变化：
- 在题目级增加 capability、lesson section、segment trace 字段
- 引入开放题预留字段
- 增加 `runtime_context` 作为 server-side 字段，承载 parameter/dataset/materialized/mysql 元数据
- 增加 `sql` 题型、`supported_runtimes`、`default_runtime`、`starter_sql`、DisplayValue 等 runtime 字段

不允许破坏：
- 前端或 server 无法识别现有题型
- 移除代码题 `starter_code` / `solution_code` / `test_cases`
- 将 `runtime_context`、hidden dataset、hidden expected、physical table name、reference SQL/code 暴露给浏览器

## 4.2 progress.json

必须继续满足：
- 保留 `summary.total / attempted / correct`
- 保留 `questions.<id>.stats`
- 保留 `questions.<id>.history`
- 保留 `session.status / started_at / finished_at`

允许变化：
- 补充 learner model 所需的摘要字段
- 增加更细的 mastery/material alignment 信号

不允许破坏：
- 页面无法继续记录答题历史
- update 脚本无法读取既有统计字段

---

## 5. `/learn-plan` 工作流兼容边界

重构后 `/learn-plan` 的核心变化是：
- 从启发式单脚本生成器，升级为 contract-based workflow
- 正式启用 `.learn-workflow/*.json`

但必须保持以下兼容性：

### 5.1 用户入口行为

用户仍然只需要运行 `/learn-plan`，而不是自己管理一堆 JSON。

### 5.2 mode 兼容

以下 mode 仍应保留：
- `auto`
- `draft`
- `research-report`
- `diagnostic`
- `finalize`

允许变化：
- `auto` 更严格地只做路由而不是直接落正式计划
- `draft/research-report/diagnostic` 改为只产出中间态和 preview
- 执行器在调用 `learn_plan.py` 前，必须先派发 Agent subagent 生成 search/research、stage candidate、planning candidate 与 semantic review，再通过 JSON 文件参数注入脚本

不允许破坏：
- skill prompt 仍按这些 mode 工作，但脚本却删除这些 mode
- 让 Python runtime 默认依赖“当前主会话上下文句柄”；注入接口只接收显式 JSON 文件，不假设 Python 子进程可直接调用当前会话 Agent 工具层

### 5.3 旧 plan 兼容

若用户已有旧 `learn-plan.md`，但没有 `.learn-workflow/*.json`：
- `/learn-plan auto` 不应直接失败
- 应尽量从旧正式状态推断可继续的阶段，或从最近一次用户输入开始恢复中间态

---

## 6. `/learn-today` / `/learn-test` 兼容边界

## 6.0 题目与 runtime artifact 兼容

`/learn-today` 与 `/learn-test` 的题目生成链路已从四 artifact 扩展为七 artifact：
- `question-scope.json`
- `question-plan.json`
- `question-artifact.json`
- `parameter-spec.json`
- `parameter-artifact.json`
- `dataset-artifact.json`
- `question-review.json`

兼容原则：
- 旧的普通选择题和 Python 函数题继续可用。
- `parameter-*` 与 `dataset-*` 是新增增强层；普通题可以使用空 `dataset-artifact.json`。
- SQL runtime 第一阶段只支持 MySQL，不引入 SQLite/Hive/DuckDB 兼容分支。
- Agent 不直接写库；MySQL 数据写入由 deterministic materializer 完成。
- `materialized-dataset.json` 是 runtime 生成物，不要求出题 Agent 手写。
- Python DataFrame/Series 题从 MySQL 重建 pandas 对象；SQL 题直接查询 MySQL。
- `/run` 只运行 public cases，用作调试反馈；hidden 数据只在 `/submit` server-side 使用。

## 6.1 session_bootstrap.py 保持稳定

`session_bootstrap.py` 是相对稳定的运行时适配层。重构期间应尽量不动其对外语义：
- 若 session 已完整，允许继续使用现有目录
- 若已有 `questions.json` 但缺前端/runtime 文件，可以补齐
- 启动服务并打开浏览器的职责保留

## 6.2 session_orchestrator.py 可重构但不能破坏出参

`session_orchestrator.py` 可以拆分成多个模块，但对外仍必须：
- 能读 `learn-plan.md`
- 能读 `materials/index.json`
- 能参考最近 `progress.json`
- 能接收 `question-scope-json`、`question-plan-json`、`question-artifact-json`、`question-review-json`
- 能接收新增的 `parameter-spec-json`、`parameter-artifact-json`、`dataset-artifact-json`、`materialized-dataset-json`、`mysql-config-json`、`skip-materialize`
- 能在需要时把非空 `dataset-artifact.json` 物化到 MySQL 并写出 `materialized-dataset.json`
- 能写出合法 `questions.json`
- 能在 today 主路径产出/复用 canonical `learn-today-YYYY-MM-DD.md`
- 能调用 bootstrap 落地 session

## 6.3 daily teacher 一等化但不重写 runtime 前端

允许：
- 先做 check-in
- 在生成新课前做课前历史复习，并保存 `progress.pre_session_review`
- 先生成教师型 daily lesson
- 题目和材料/lesson 更强绑定
- session 启动后由主 agent 在终端继续答疑、追问和记录学习交互到 `interaction_events.jsonl`
- 用户明确完成后、update 前生成 `reflection.json` 与 `mastery_judgement`

不允许：
- 抛弃当前 `questions.json + progress.json + 题集.html + server.py` 模型
- 引入另一套全新前端/后端协议导致旧 session 不可用
- 为 SQL 题引入 SQLite/Hive/DuckDB 分支，第一阶段只保留 MySQL
- 让浏览器看到 hidden rows、hidden expected、hidden physical table name、server-side `runtime_context`、reference SQL/code
- 把复盘面板或掌握判断搬到前端 UI；本轮掌握判断属于 skill / agent workflow

---

## 7. update 脚本兼容边界

内部 `learn_today_update.py` 与 `learn_test_update.py` 可以继续作为 learner model / patch queue 更新器复用，但必须保留两件事：

1. 继续可从现有 `progress.json` 工作
2. 继续把摘要写回 `learn-plan.md` 的记录区块
3. 优先消费 `interaction_events.jsonl`、`reflection.json`、`completion_signal`、`pre_session_review` 与 `user_feedback`，但缺这些新增文件时不得破坏旧 session 的基本记录回写

补充边界：由 `/learn-plan` diagnostic gate 触发的新起始测试 session，应优先收口到内部 `learn_test_update.py` 回写流程；`learn_today_update.py` 仅保留 today 主路径与 legacy `plan-diagnostic` 兼容。

允许新增：
- `interaction_events.jsonl`
- `reflection.json`
- `.learn-workflow/session_facts.json`
- `learner_model.json` 更新
- `curriculum_patch_queue.json` 提案
- 更细的掌握度证据
- `pending-evidence` patch 与 `quality_review` 等质量 gate 字段
- `learn-plan.md` 的“当前教学/练习微调”区块，用于低风险反馈默认生效

不允许破坏：
- 只写新 JSON，不再更新 `learn-plan.md`
- 在缺 completion signal / reflection 时把 covered scope 直接判为 mastered
- 未经用户确认就改长期阶段路线、目标、材料、时间预算或学习频率
- 不强依赖 `PROJECT.md`

---

## 8. materials 系统兼容边界

## 8.1 downloader 职责不变

`learn_materials/downloader.py` 仍负责：
- 读取 `materials/index.json`
- 下载可直链材料
- 回写缓存状态

允许变化：
- 内部逻辑迁移到 `learn_materials/downloader.py`
- 增加 preprocessing / segment cache 支持

不允许破坏：
- 下载器开始改 curriculum 逻辑
- 旧索引结构一律报错

## 8.2 source grounding 是增强层

materials preprocessing、segment cache、source excerpt 都属于增强能力。

兼容原则：
- 有则优先使用
- 没有则回退 metadata-only 或条目级材料选择
- 预处理失败不能阻断 today/test session

---

## 9. 文档兼容边界

重构时文档职责要重新划分，但文档数量增加不应导致真相源混乱。

目标分工：
- `WORKFLOW_DESIGN.md`：整个 skill 簇架构真相源
- `docs/contracts.md`：schema 与契约
- `docs/state-files.md`：状态文件职责与边界
- `docs/runtime-compatibility.md`：兼容底线
- `SKILL.md`：`/learn-plan` 入口协议
- `README.md`：用户视角快速指南
- 其他 `/learn-*` 入口 `SKILL.md`：各自的轻量协议

不允许继续维持：
- 架构、协议、快速开始、实现细节在多个文档里大量重复且互相冲突

---

## 10. 分阶段迁移时的兼容检查清单

### 阶段 0：文档冻结
- `WORKFLOW_DESIGN.md` 是否已成为整个 skill 簇真相源
- contracts/state-files/runtime-compatibility 是否齐备

### 阶段 1：shared core 抽取
- `learn_plan.py`、update 脚本行为是否保持一致

### 阶段 2：workflow engine 上线
- `auto` 是否仍可用
- 非 finalize 是否不再覆盖正式 plan
- 旧 plan 是否仍可继续工作

### 阶段 3：planning/materials 拆分
- `learn-plan.md` 与 `materials/index.json` 是否仍兼容 today/test

### 阶段 4：runtime 拆分
- `/learn-today` 与 `/learn-test` 是否仍能生成完整 session
- `session_bootstrap.py` 是否仍可继续已有 session

### 阶段 5：feedback 升级
- `learn-plan.md` 记录区块是否仍正常追加
- `learner_model.json` / `curriculum_patch_queue.json` 是否只增量增强
- 无 evidence 的 patch 是否进入 `pending-evidence` 而不是被当作已就绪提案

### 阶段 6：materials preprocessing
- 预处理失败是否能安全回退

### 阶段 7：清理旧逻辑
- CLI facade 是否仍稳定
- 文档是否收口完毕

---

## 11. 最重要的不变量

1. 用户入口不变。
2. session 四件套不变。
3. 正式主计划文件不变。
4. 中间态 workflow 与 learner model 是新增层，不是替换层。
5. 所有增强能力都必须可回退。

---

## 12. 一句话原则

**内部可以重构到模块化，但外部要继续像同一套工具一样工作。**
