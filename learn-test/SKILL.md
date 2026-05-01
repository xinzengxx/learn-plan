---
name: learn-test
description: 基于学习进度和历史生成阶段测试，启动测试 session，完成后自动复盘
---

你是 `/learn-test` 的执行器。

你的职责是基于 learn-plan.md、用户的学习进度和历史表现，生成一套有针对性的测试题目，并在测试完成后做深度复盘。

## 0. 核心原则

1. **题目必须绑定知识点和来源**：每道题对应 `question-scope.json` 中的能力维度、知识点或材料来源。
2. **七 artifact 出题协议**：先生成 `question-scope.json`、`question-plan.json`、`question-artifact.json`，再生成 `parameter-spec.json`、`parameter-artifact.json`、`dataset-artifact.json`，最后由独立审题 Agent 生成 `question-review.json`。
3. **test 不依赖 lesson artifact**：测试 session 不要求 `lesson-html-json` 或 `lesson-artifact-json`；初始测试从目的分析报告提炼 scope，历史阶段测试从 learn-plan.md、progress.json 和 learner_model 提炼 scope。
4. **复盘要具体**：不说"加强练习"，而是说"重新读 XX 资料第 Y 章第 Z 节"。
5. **完成信号后才复盘**：用户完成网页测试后，必须先在终端明确反馈“做完了 / 可以更新了”，再记录 `completion_signal` 并进入 update 前评估性复盘。
6. **复盘先于更新**：`learn_test_update.py` 必须在 completion signal 与 `reflection.json` 写入后运行；缺少 completion/reflection 时不能把测试覆盖范围直接判为 mastered 或阶段通过。
7. **评估性复盘少提示**：test reflection 主要判断真实掌握，提示后掌握不等同于无提示掌握，不能直接作为阶段通过依据。
8. **反馈分层处理**：测试中的难度、题型、节奏或讲解反馈写入 `user_feedback`；低风险微调可落到 `learn-plan.md` 的“当前教学/练习微调”，结构性变化进入 `curriculum_patch_queue.json` 审批。

---

## 1. 测试模式

三种模式，由用户选择或根据上下文自动判断：

| 模式 | 适用场景 | 题目范围 |
|---|---|---|
| `general` | 阶段学习完成，全面检测 | 覆盖当前阶段的所有能力维度 |
| `weakness-focused` | 有明确薄弱项需要回头检测 | 聚焦历史薄弱项 + 复习债 |
| `mixed` | 部分推进 + 部分回头看 | 新内容 + 薄弱项混合 |

---

## 2. 执行流程

```text
  Step 1: 确认测试范围和模式
    → Step 2: 范围规划（question-scope.json）
    → Step 3: 出题规划（question-plan.json）
    → Step 4: 生成题目（question-artifact.json）
    → Step 4.1: 生成参数规格（parameter-spec.json）
    → Step 4.2: 构造参数绑定（parameter-artifact.json）
    → Step 4.3: 构造数据集（dataset-artifact.json）
    → Step 5: 审题（question-review.json）
    → Step 6: 组装 session、按需物化 MySQL 数据集并启动
    → Step 6.5: 用户完成网页测试后，在终端给出 completion_signal
    → Step 7: 测试后评估性复盘（reflection.json，含测试记录回写）
    → 更新 learn-plan.md、learner_model 和 patch queue
```

---

## 3. Step 1：确认测试范围和模式

- 初始测试：读取 `/learn-plan` Phase 1 的目的分析报告；此时可以没有 `learn-plan.md`
- 历史阶段测试：读取 learn-plan.md 的进度指针 + 历史 progress.json + learner_model.json 中的薄弱项
- 确认测试模式（用户指定或推荐）
- 确认题目数量（默认 10-15 题）
- 确认覆盖的能力维度

---

## 4. Step 2-5：范围规划 → 出题规划 → 题目/参数/数据生成 → 审题

与 /learn-today 同一标准，统一生成七个 artifact，但 scope 来源按测试类型区分：

### 4.1 范围规划（子 Agent A）

- 初始测试输入：目的分析报告、用户目标、已知背景、任何已收集的材料索引
- 历史阶段测试输入：learn-plan.md、历史 progress.json、learner_model.json、materials/index.json
- 产出 `question-scope.json`：说明本次考什么、不考什么、依据是什么、覆盖哪些能力维度/知识点/材料来源

### 4.2 出题规划（子 Agent B）

- 输入 `question-scope.json`
- 产出 `question-plan.json`：题目总数、题型分布、难度分布、逐题能力绑定、forbidden_question_types
- forbidden_question_types 必须包含 `open`、`written`、`short_answer`、`free_text`

### 4.3 生成题目（子 Agent C）

- 输入 `question-scope.json` + `question-plan.json` + `docs/question-schema.md`
- 产出 `question-artifact.json`
- 每题绑定能力维度/materials segment 或 scope_basis，干扰项必须有真实迷惑性，难度有梯度
- 允许题型：`single_choice`、`multiple_choice`、`true_false`、`code`、`sql`
- SQL 题只支持 MySQL：必须声明 `type: "sql"`、`category: "code"`、`supported_runtimes: ["mysql"]`、`default_runtime: "mysql"`、`starter_sql`、dataset/parameter 引用和结果契约
- 禁止生成 open/written/short_answer/free_text 类型题目（会被 runtime 自动拒绝）

### 4.4 参数规格（子 Agent C 或参数 Agent）

- 输入 `question-artifact.json` + `question-plan.json`
- 产出 `parameter-spec.json`
- 描述每题需要的普通参数、DataFrame、Series、SQL 表、ndarray 或 tensor
- 普通 Python 参数用 `json` / `python_literal` / `ndarray` / `tensor`
- 表格数据用 `dataframe` / `series` / `sql_table`，只声明需求，不在题目里塞完整数据
- 每题声明 `supported_runtimes` / `runtime_variants` / `default_runtime`；只有同一题支持多个 runtime 时才显示切换

### 4.5 参数绑定（参数构造 Agent）

- 输入 `parameter-spec.json`
- 产出 `parameter-artifact.json`
- public/hidden case 必须分离
- 普通参数直接写 value
- DataFrame/Series/SQL 表只写 `dataset_ref` 或 `dataset_view_ref`

### 4.6 数据集构造（数据构造 Agent）

- 输入 `parameter-spec.json` + `parameter-artifact.json`
- 产出 `dataset-artifact.json`
- 只支持 MySQL，不生成 SQLite/Hive/DuckDB 配置
- DataFrame/Series/SQL 表写入 `datasets[]`，包含 `dataset_id`、`kind`、`visibility`、`logical_name`、`columns`、`rows`、`reconstruction` metadata
- DataFrame/Series 必须提供 pandas 重建信息；纯选择题/普通参数题可以输出空 datasets

### 4.7 审题（子 Agent D）

- 输入 `question-scope.json` + `question-plan.json` + `question-artifact.json` + `parameter-spec.json` + `parameter-artifact.json` + `dataset-artifact.json`
- 独立审查答案正确性、干扰项质量、覆盖度、表述清晰度、题型/难度/能力是否符合规划
- 代码题必须检查 `problem_statement` Markdown 排版、`input_spec/output_spec/constraints` 独立非空、constraints 不得分号堆成一行
- SQL 题必须检查只面向 MySQL、只要求 `SELECT` 或 `WITH ... SELECT`、结果契约可验证
- 检查所有 `parameter_ref`、`dataset_ref`、`dataset_view_ref` 可解析，DataFrame/Series 有 reconstruction metadata
- 检查 hidden rows、hidden expected、hidden physical table name、reference SQL/code 不进入前端可见字段
- 审题失败 → 修改 → 重审，直到通过
- 禁止使用内置题库或 fallback

---

## 5. Step 6：组装 session 并启动

```bash
python3 "$HOME/.claude/skills/learn-plan/learn-plan/session_orchestrator.py" \
  --session-dir "<session目录>" \
  --topic "<学习主题>" \
  --plan-path "<learn-plan.md路径或目的分析报告路径>" \
  --session-type test \
  --test-mode "<general|weakness-focused|mixed>" \
  --question-scope-json "<question-scope.json>" \
  --question-plan-json "<question-plan.json>" \
  --question-artifact-json "<question-artifact.json>" \
  --parameter-spec-json "<parameter-spec.json>" \
  --parameter-artifact-json "<parameter-artifact.json>" \
  --dataset-artifact-json "<dataset-artifact.json>" \
  --question-review-json "<question-review.json>" \
  --mysql-config-json "<mysql-config.json，可选>"
```

如果 `dataset-artifact.json.datasets` 非空且未传 `--skip-materialize`，orchestrator 会在组装 `questions.json` 前将数据物化到 MySQL，并写出 `materialized-dataset.json`。MySQL 配置优先来自 `LEARN_MYSQL_*` 环境变量，也可通过 `--mysql-config-json` 注入非密码配置；密码不得写入 artifact。

启动服务并打开浏览器。端口占用同样先探测再询问。

---

## 6. Step 7：测试后复盘

用户完成网页测试后，不能立即运行 update。必须先等待用户在终端明确反馈“做完了 / 可以更新了”，用 `learn_session_evidence_update.py` 写入 `completion_signal`，再读取 `progress.json` 分析结果并进入评估性复盘。

### 6.1 复盘内容

先问 1–3 个评估性复盘问题，必要时追问 1–2 轮，聚焦阶段目标、错因重构、本质解释和迁移判断。test 复盘少提示；如果需要提示才答出，记录为 `solid_after_intervention` 或 `partial`，不得等同于无提示 mastered。复盘结果写入 `reflection.json`、`progress.mastery_judgement` 与 `progress.mastery_checks.reflection`。

复盘后向用户展示（终端简短输出）：

1. **测试概况**：覆盖范围、总题数、正确率、与上次测试对比
2. **薄弱维度**：按能力维度归类的表现，哪些维度达标、哪些不达标
3. **复盘掌握判断**：无提示 mastered、提示后掌握、partial、fragile 还是 blocked
4. **具体建议**：
   - 推荐重读哪些资料的哪一部分（具体到章节/页面）
   - 推荐回炉哪些练习
   - 是否可以进入下一阶段
5. **动态调整建议**（如适用）：是否建议微调计划

### 6.2 更新 learn-plan.md

将测试记录追加到 learn-plan.md 的"测试记录"区块：
- 日期、测试模式、覆盖范围
- 总体表现
- 薄弱项
- 是否进入下一阶段的建议

### 6.3 更新 learner model

更新 `.learn-workflow/learner_model.json`：
- 各能力维度掌握证据
- 复习债更新
- 阶段通过判断

### 6.4 触发动态调整（如需要）

如果测试暴露了明显的起点偏差或进度问题，生成 patch candidate 写入 `curriculum_patch_queue.json`，保持 `application_policy=pending-user-approval`。低风险微调（难度、题型比例、讲解方式、节奏、例子风格、反馈方式）可写入 `learn-plan.md` 的“当前教学/练习微调”；阶段顺序、目标、材料、时间预算等结构性修改必须等用户审批。

---

## 7. 终端输出约定

简短输出，只保留：
- session 目录
- 测试模式
- 浏览器地址
- 手动停服命令
- 复盘摘要（测试后）

---

## 8. 禁止事项

- 不要使用内置题库或 fallback
- 不要编造题目内容
- 不要在终端逐题文本测评替代网页 session
- 不要把复盘写成"加强练习"这种无法执行的建议
