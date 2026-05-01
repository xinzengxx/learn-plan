# 题目 JSON Schema（Agent 出题必读）

出题 Agent 生成的 `question-artifact.json` 必须通过 `question_validation.py` 的校验。本文件是 Schema 与 Runtime 之间的契约。

题目生产链路统一分为七个 Agent artifact、一个可选物化产物和一个 runtime payload：

1. `question-scope.json`：范围规划。说明本次练/考什么、不练/不考什么、依据是什么、覆盖哪些能力维度、知识点和材料来源。
2. `question-plan.json`：出题规划。说明题目总数、题型分布、难度分布、逐题要求、能力覆盖、runtime 需求和 `forbidden_question_types`。
3. `question-artifact.json`：题目候选。只包含题面、starter、runtime 声明、参数/数据引用和结果契约，不负责实际构造二维数据。
4. `parameter-spec.json`：参数规格。描述每题需要哪些普通参数、DataFrame、Series、SQL 表、ndarray 或 tensor。
5. `parameter-artifact.json`：参数绑定。构造 public/hidden case 的普通参数值，或绑定 `dataset_ref` / `dataset_view_ref`。
6. `dataset-artifact.json`：数据集声明。描述需要物化到 MySQL 的 DataFrame、Series、SQL 表数据及 pandas reconstruction metadata；无二维数据时允许空 datasets。
7. `question-review.json`：严格审题结果。审查题目正确性、scope/plan 一致性、排版、参数/数据引用、MySQL runtime 契约和 hidden 安全。
8. `materialized-dataset.json`：可选物化产物。由 deterministic materializer 写出，记录 MySQL physical table、列、行数、visibility 和 reconstruction metadata。
9. `questions.json`：runtime 最终 payload。由 `session_orchestrator.py` 组装，写入 `plan_source`、`selection_context`、scope/plan 快照、最终题目和 server-side `runtime_context`。前端 `/questions.json` 响应会过滤 `runtime_context` 与 hidden 信息。

`today` 与 `test` 的差异只在 `question-scope.json` 的来源：today 来自课件和材料原文；初始测试来自目的分析报告；历史阶段测试来自 `learn-plan.md`、历史 `progress.json` 和 learner model。`test` 不要求 `lesson-html-json` 或 `lesson-artifact-json`。

---

## 1. question-scope.json（范围规划）

最小结构：

```json
{
  "schema_version": "learn-plan.question_scope.v1",
  "scope_id": "scope-...",
  "source_profile": "today-lesson | initial-diagnostic | history-stage-test",
  "session_type": "today | test",
  "session_intent": "learning | assessment",
  "assessment_kind": null,
  "test_mode": null,
  "topic": "...",
  "language_policy": {"user_facing_language": "zh-CN"},
  "scope_basis": [],
  "target_capability_ids": [],
  "target_concepts": [],
  "review_targets": [],
  "lesson_focus_points": [],
  "project_tasks": [],
  "project_blockers": [],
  "source_material_refs": [],
  "difficulty_target": {},
  "minimum_pass_shape": {"required_open_question_count": 0},
  "exclusions": [],
  "evidence": [],
  "generation_trace": {"status": "ok"}
}
```

`source_profile` 约束：
- `today-lesson`：`session_type=today`，必须有 `lesson_focus_points` 或 `target_concepts`。
- `initial-diagnostic`：`session_type=test`，`assessment_kind=initial-test`，scope 来源是目的分析报告。
- `history-stage-test`：`session_type=test`，`assessment_kind=stage-test`，scope 来源必须含历史进度、learn-plan 或 learner model 证据。

---

## 2. question-plan.json（出题规划）

最小结构：

```json
{
  "schema_version": "learn-plan.question_plan.v1",
  "plan_id": "plan-...",
  "scope_id": "scope-...",
  "source_profile": "today-lesson | initial-diagnostic | history-stage-test",
  "session_type": "today | test",
  "session_intent": "learning | assessment",
  "assessment_kind": null,
  "test_mode": null,
  "topic": "...",
  "question_count": 8,
  "question_mix": {"single_choice": 4, "multiple_choice": 1, "true_false": 1, "code": 1, "sql": 1},
  "difficulty_distribution": {"basic": 1, "medium": 6, "hard": 1},
  "planned_items": [],
  "coverage_matrix": [],
  "minimum_pass_shape": {"required_open_question_count": 0},
  "forbidden_question_types": ["open", "written", "short_answer", "free_text"],
  "generation_guidance": [],
  "review_checklist": [],
  "evidence": [],
  "generation_trace": {"status": "ok"}
}
```

`question_count` 必须等于 `question_mix` 与 `difficulty_distribution` 的数量总和。`question_mix` 应使用具体 runtime 题型：`single_choice`、`multiple_choice`、`true_false`、`code`、`sql`；不要把 `concept` 当作正式 mix 键。`sql` 题只支持 MySQL，不要规划 SQLite、Hive 或 DuckDB 题。

---

## 3. question-artifact.json / questions.json 顶层结构（11 个必填字段）

```json
{
  "date": "2026-04-27",
  "topic": "Python 变量与对象引用",
  "mode": "today-generated",
  "session_type": "today",
  "session_intent": "learning",
  "assessment_kind": null,
  "test_mode": null,
  "language_policy": {
    "user_facing_language": "zh-CN",
    "localization_required": true
  },
  "plan_source": { /* 由 runtime 填充，Agent 无需手动构造 */ },
  "materials": [],
  "questions": [ /* 题目列表 */ ]
}
```

| 字段 | 说明 | 常见值 |
|---|---|---|
| `date` | 日期字符串 | `"2026-04-27"` |
| `topic` | 学习主题 | `"Python 变量与对象引用"` |
| `mode` | session 模式 | `"today-generated"` / `"test-general"` |
| `session_type` | 类型 | `"today"` / `"test"` |
| `session_intent` | 意图 | `"learning"` / `"assessment"` |
| `assessment_kind` | 测试类型 | `null` (today) / `"initial-test"` / `"stage-test"` |
| `test_mode` | 测试模式 | `null` (today) / `"general"` / `"weakness-focused"` / `"mixed"` |
| `language_policy` | 语言策略 | `{"user_facing_language": "zh-CN", "localization_required": true}` |
| `plan_source` | 计划上下文 | 由 runtime 填充 |
| `materials` | 资料列表 | 由 runtime 填充 |
| `questions` | 题目数组 | **非空，每项必含 id** |

---

## 2. 难度元数据（每题必填）

每道题都必须显式声明难度，runtime 只做结构校验和枚举归一化，不会根据题干自动推断真实难度。

| 字段 | 类型 | 说明 |
|---|---|---|
| `difficulty_level` | string | 必须为 `basic` / `medium` / `upper_medium` / `hard` |
| `difficulty_label` | string | 必须与 level 对应：`基础题` / `中等题` / `中难题` / `难题` |
| `difficulty_score` | int | 必须与 level 对应：1 / 2 / 3 / 4 |
| `difficulty_reason` | string | 标注该难度的理由，必须非空 |
| `expected_failure_mode` | string 或 array | 预期学习者可能失败的方式，必须非空 |

难度映射：

| level | label | score |
|---|---|---:|
| `basic` | `基础题` | 1 |
| `medium` | `中等题` | 2 |
| `upper_medium` | `中难题` | 3 |
| `hard` | `难题` | 4 |

`difficulty` 是旧字段，只作为兼容 alias 保留；新 artifact 必须以 `difficulty_level` 为准。`easy`、`进阶`、`挑战` 等旧值可被归一化，但不能替代完整难度元数据。

---

## 3. 概念题（concept）

### 2.1 通用必填字段

所有概念题（single_choice、multiple_choice、true_false）必须包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 唯一标识，如 `"q-var-ref-01"` |
| `type` | string | `"single_choice"` / `"multiple_choice"` / `"true_false"` |
| `category` | string | 必须为 `"concept"` |
| `title` | string | 题目名称 |
| `prompt` | string | 题干（与 `question` 至少填一个） |
| `options` | array[string] | 至少 2 个选项（true_false 可为 0 或 2） |
| `explanation` | string | 解析（非空，concept 题强制） |
| `scoring_rubric` | array[object] | 评分标准（非空） |
| `capability_tags` | array[string] | 能力标签（非空） |

### 2.2 各类型 answer 约束

| 类型 | answer 格式 | 示例 |
|---|---|---|
| `single_choice` | `int` (0-based index) | `"answer": 1` |
| `multiple_choice` | `array[int]` (非空) | `"answers": [0, 2]` |
| `true_false` | `bool` / `int` / `"true"` / `"false"` | `"answer": true` |

### 2.3 来源追溯

每道题必须携带来源信息（至少一种）：

- `source_trace.question_source`: 如 `"agent-injected"` / `"runtime-generated"`
- `source_segment_id`: 绑定到 materials segment
- `tags`: 含 `"content-derived"` / `"lesson-derived"` 时需配 `question_role`

### 2.4 完整示例

```json
{
  "id": "q-var-ref-01",
  "type": "single_choice",
  "category": "concept",
  "title": "变量引用 vs 复制",
  "prompt": "执行 a = [1,2,3]; b = a; b.append(4); print(a) 输出什么？",
  "options": ["[1,2,3]", "[1,2,3,4]", "报错", "None"],
  "answer": 1,
  "difficulty_level": "basic",
  "difficulty_label": "基础题",
  "difficulty_score": 1,
  "difficulty_reason": "只考察变量引用赋值后共享同一列表对象这一单点概念。",
  "expected_failure_mode": "把 b = a 误解为复制列表。",
  "explanation": "b = a 是引用赋值，a 和 b 指向同一列表对象。b.append(4) 修改了共享对象，所以 a 也变为 [1,2,3,4]。",
  "scoring_rubric": [
    {"metric": "概念理解", "threshold": "正确识别变量引用语义"}
  ],
  "capability_tags": ["python-core", "variable-reference"],
  "source_trace": {"question_source": "agent-injected"},
  "tags": ["lesson-derived"],
  "question_role": "learn"
}
```

---

## 3. 代码题（code）

### 3.1 8 个必填字段

代码题比概念题严格得多，以下每个字段都不能为空：

| 字段 | 说明 | 示例 |
|---|---|---|
| `title` | 题目标题 | `"实现列表过滤函数"` |
| `problem_statement` | 问题描述 | `"写一个函数，接收整数列表，过滤 None 和负数..."` |
| `input_spec` | 输入规格 | `"scores: list[int | None] — 可能含 None 的整数列表"` |
| `output_spec` | 输出规格 | `"list[int] — 只含非负整数的列表"` |
| `constraints` | 约束条件 | `"保持原顺序，不修改原列表"` |
| `examples` | 公开示例 | `[{"input": ..., "output": ..., "explanation": ...}]` |
| `hidden_tests` | 隐藏测试用例 | `[{"args": [...], "expected": ...}]` |
| `scoring_rubric` | 评分标准 | `[{"metric": ..., "threshold": ...}]` |
| `capability_tags` | 能力标签 | `["python-core", "iteration"]` |

### 3.2 其他必填字段

| 字段 | 说明 |
|---|---|
| `type` | 必须为 `"code"` |
| `category` | 必须为 `"code"` |
| `id` | 唯一标识 |
| `function_signature` | 函数签名，如 `"def filter_scores(scores: list) -> list:"` |
| `starter_code` | 给用户的初始代码 |
| `solution_code` | **正确解答**（会被 exec() 执行验证！） |
| `function_name` | 函数名（如果没有 function_signature） |

### 3.3 examples 格式（每个 example）

```json
{
  "input": {"scores": [100, None, -1, 0, 88]},
  "output": [100, 0, 88],
  "explanation": "None 和 -1 被过滤，保留 100, 0, 88，顺序不变。"
}
```

每个 example 必须含 `input`、`output`、`explanation`（非空）。

### 3.4 hidden_tests 格式与 argument contract

**关键**：`solution_code` 会被 runtime 实际执行。hidden_tests 的每个 case 必须满足以下规则：

#### argument contract 规则

每个测试 case 必须**恰好使用以下三种输入方式之一**：

| 方式 | 适用场景 | 格式 |
|---|---|---|
| `args` | 多参数函数 | `"args": [arg1, arg2, ...]`，长度必须匹配函数参数个数 |
| `kwargs` | 关键字参数 | `"kwargs": {"param1": val1, ...}`，keys 必须精确匹配参数名 |
| `input` | 单参数函数 | `"input": value`，仅适用于单个参数或 `single_object_input: true` |

每个 case 必须含 expected 字段：
- `"expected": value` — 普通返回值
- `"expected_code": "expr"` — 需要 eval 的期望值
- `"expected_output"` / `"expected_rows"` / `"expected_records"` — 特殊输出

#### 完整 hidden_test 示例

```json
{
  "hidden_tests": [
    {
      "args": [[100, None, -1, 0, 88]],
      "expected": [100, 0, 88]
    },
    {
      "args": [[None, None]],
      "expected": []
    },
    {
      "args": [[]],
      "expected": []
    }
  ]
}
```

### 3.5 preflight 检查

`solution_code` 会被 `preflight_code_question_tests()` 实际执行：
1. exec() 加载 solution_code
2. 对 `public_tests` 和 `hidden_tests` 的每个 case 调用函数
3. 比较返回值与 expected
4. 任何失败 = 题目被拒绝

### 3.6 完整示例

```json
{
  "id": "q-filter-scores",
  "type": "code",
  "category": "code",
  "title": "过滤列表中的无效值",
  "problem_statement": "实现 filter_scores 函数，接收可能含 None 和负数的整数列表，返回只含非负整数的列表，保持原顺序。",
  "input_spec": "scores: list[int | None]",
  "output_spec": "list[int]",
  "constraints": "不修改原列表；保持元素顺序；None 和负数被过滤",
  "function_signature": "def filter_scores(scores: list) -> list:",
  "function_name": "filter_scores",
  "starter_code": "def filter_scores(scores):\n    # TODO: 实现过滤逻辑\n    pass\n",
  "solution_code": "def filter_scores(scores):\n    return [x for x in scores if x is not None and x >= 0]\n",
  "difficulty_level": "medium",
  "difficulty_label": "中等题",
  "difficulty_score": 2,
  "difficulty_reason": "需要同时处理 None、负数、0、空列表，并保持原顺序。",
  "expected_failure_mode": "忘记保留 0，或直接修改原列表。",
  "examples": [
    {
      "input": {"scores": [100, None, -1, 0, 88]},
      "output": [100, 0, 88],
      "explanation": "None 被过滤，-1 被过滤，0 和正数保留，顺序不变。"
    }
  ],
  "hidden_tests": [
    {"args": [[100, None, -1, 0, 88]], "expected": [100, 0, 88]},
    {"args": [[None, None]], "expected": []},
    {"args": [[]], "expected": []}
  ],
  "scoring_rubric": [
    {"metric": "正确性", "threshold": "所有公开和隐藏测试通过"},
    {"metric": "边界处理", "threshold": "正确处理 None、负数、空列表"}
  ],
  "capability_tags": ["python-core", "list-comprehension", "edge-cases"],
  "source_trace": {"question_source": "agent-injected"},
  "question_role": "project_task"
}
```

---

## 4. SQL 题（MySQL-only）

SQL 题是 `category: "code"` 下的一类 runtime 题，但 `type` 必须为 `"sql"`。SQL runtime 只支持 MySQL，不支持 SQLite、Hive 或 DuckDB。

### 4.1 必填字段

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识 |
| `type` | 必须为 `"sql"` |
| `category` | 必须为 `"code"` |
| `title` | 题目标题 |
| `problem_statement` | 问题描述，必须说明业务背景和查询目标 |
| `input_spec` | 表结构、字段含义、public 数据说明 |
| `output_spec` | 期望输出列、排序要求、聚合口径 |
| `constraints` | SQL 限制，例如只写一条 SELECT/WITH 查询 |
| `starter_sql` | 给用户的初始 SQL |
| `supported_runtimes` | 必须包含且第一阶段只允许 `["mysql"]` |
| `default_runtime` | `"mysql"` |
| `parameter_spec_ref` 或 `dataset_refs` | 指向参数/数据集 artifact |
| `result_contract` | 可验证的列、行、排序或比较规则 |
| `scoring_rubric` | 评分标准 |
| `capability_tags` | 能力标签 |

### 4.2 SQL 安全边界

用户提交的 SQL 只允许单条查询：
- `SELECT ...`
- `WITH ... SELECT ...`

禁止要求或鼓励：
- 多语句 SQL
- `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `CREATE` / `TRUNCATE` / `LOAD DATA`
- 依赖物理表名作答；题面只能暴露 logical table/view 名称

### 4.3 示例

```json
{
  "id": "q-sql-active-users",
  "type": "sql",
  "category": "code",
  "title": "统计活跃用户订单数",
  "problem_statement": "查询 `orders` 表中每个活跃用户的订单数量。",
  "input_spec": "`orders(user_id, status, created_at)`；只统计 `status = 'paid'` 的记录。",
  "output_spec": "返回 `user_id` 和 `paid_order_count` 两列，按 `user_id` 升序。",
  "constraints": ["只能写一条 MySQL SELECT 或 WITH 查询", "不得修改数据"],
  "starter_sql": "SELECT user_id, COUNT(*) AS paid_order_count\nFROM orders\nWHERE status = 'paid'\nGROUP BY user_id\nORDER BY user_id;",
  "supported_runtimes": ["mysql"],
  "default_runtime": "mysql",
  "dataset_refs": ["orders-public"],
  "parameter_spec_ref": "q-sql-active-users",
  "result_contract": {"columns": ["user_id", "paid_order_count"], "order_sensitive": true},
  "difficulty_level": "medium",
  "difficulty_label": "中等题",
  "difficulty_score": 2,
  "difficulty_reason": "需要理解过滤、分组聚合和排序。",
  "expected_failure_mode": "忘记过滤 paid 状态或输出列别名不一致。",
  "scoring_rubric": [{"metric": "SQL 正确性", "threshold": "public 和 hidden case 查询结果一致"}],
  "capability_tags": ["mysql", "group-by", "aggregation"]
}
```

---

## 5. 参数与数据集 artifact

### 5.1 parameter-spec.json

`parameter-spec.json` 描述每题需要什么参数或数据。普通参数直接由参数 Agent 构造；DataFrame、Series、SQL 表等二维数据只声明需求，由 `dataset-artifact.json` 承载数据。

最小结构：

```json
{
  "schema_version": "learn-plan.parameter_spec.v1",
  "questions": [
    {
      "question_id": "q-clean-sales",
      "supported_runtimes": ["python"],
      "default_runtime": "python",
      "parameters": [
        {"name": "df", "type": "dataframe", "dataset_ref_required": true},
        {"name": "min_amount", "type": "json"}
      ]
    }
  ]
}
```

允许的参数类型：`json`、`python_literal`、`dataframe`、`series`、`sql_table`、`ndarray`、`tensor`。

### 5.2 parameter-artifact.json

`parameter-artifact.json` 绑定 public/hidden case：

```json
{
  "schema_version": "learn-plan.parameter_artifact.v1",
  "cases": [
    {
      "question_id": "q-clean-sales",
      "case_id": "p1",
      "visibility": "public",
      "parameters": {
        "df": {"dataset_ref": "sales-public"},
        "min_amount": {"value": 100}
      },
      "expected": {"records": [{"region": "A", "amount": 120}]}
    }
  ]
}
```

规则：
- public/hidden case 必须明确分离。
- 普通参数用 `value`。
- DataFrame/Series/SQL 表用 `dataset_ref` 或 `dataset_view_ref`。
- hidden case 不得复制进前端可见字段。

### 5.3 dataset-artifact.json

`dataset-artifact.json` 描述需要物化到 MySQL 的二维数据：

```json
{
  "schema_version": "learn-plan.dataset_artifact.v1",
  "datasets": [
    {
      "dataset_id": "sales-public",
      "kind": "dataframe",
      "visibility": "public",
      "logical_name": "sales",
      "columns": [
        {"name": "region", "dtype": "object", "mysql_type": "VARCHAR(255)", "nullable": false},
        {"name": "amount", "dtype": "int64", "mysql_type": "BIGINT", "nullable": false}
      ],
      "rows": [
        {"region": "A", "amount": 120},
        {"region": "B", "amount": 80}
      ],
      "reconstruction": {"index": {"kind": "range"}}
    }
  ]
}
```

规则：
- 只支持 MySQL。
- `kind` 可为 `dataframe`、`series`、`sql_table`。
- DataFrame/Series 必须有 `reconstruction`、`reconstruction_metadata` 或 `pandas_metadata`。
- 纯选择题或普通参数题使用空数据集：`{"schema_version": "learn-plan.dataset_artifact.v1", "datasets": []}`。
- Agent 不直接写 MySQL；真实建表和插入由 materializer 完成。

### 5.4 materialized-dataset.json

`materialized-dataset.json` 由 runtime 生成，不由 Agent 编写。它记录：
- `physical_table`
- `logical_name`
- `visibility`
- `columns`
- `row_count`
- `reconstruction`

前端永远不能看到 hidden physical table 或 hidden rows。

---

## 6. MySQL runtime 与结构化展示

### 6.1 Runtime 声明

每题可以声明：
- `supported_runtimes`: `"python"` / `"mysql"`
- `default_runtime`
- `runtime_variants`

单 runtime 题只显示语言标签；只有同一道题支持多个 runtime 时才显示切换。

### 6.2 Python tabular 题

Python DataFrame/Series 题仍写成 `type: "code"`：
- 题目提供 `function_signature`、`starter_code` 和题意。
- 参数规格声明 DataFrame/Series。
- `parameter-artifact.json` 用 `dataset_ref` 绑定 case。
- runtime 从 MySQL 查询 materialized table，根据 metadata 重建 pandas DataFrame/Series，再调用用户函数。

### 6.3 /run 调试反馈

`/run` 只运行 public cases，并返回：
- input
- expected
- actual return / query result
- stdout
- stderr
- traceback
- `DisplayValue` 结构化展示值

### 6.4 DisplayValue

结构化展示统一使用 `DisplayValue`：
- DataFrame / Series / SQL result：表格
- ndarray / tensor：shape、dtype、device、values preview 或 repr
- 普通 JSON / scalar / repr / error：对应轻量结构

---

## 7. Hidden 数据安全

以下内容不得进入前端可见 `/questions.json` 或 public run response：
- `runtime_context`
- hidden tests
- hidden rows
- hidden expected
- hidden dataset refs
- hidden physical table names
- `solution_code`
- `solution_sql`
- `reference_sql`

submit hidden failure 只返回安全摘要，例如 case id、`category: hidden`、failure type 和安全 message，不返回 hidden input/expected/actual。

---

## 8. 禁止的题目类型

以下类型在 test-grade 模式下**自动被拒绝**：

| 被禁止的类型 | 错误信息 |
|---|---|
| `"open"` | `question.open_not_allowed_by_default` |
| `"written"` | `question.open_not_allowed_by_default` |
| `"short_answer"` | `question.open_not_allowed_by_default` |
| `"free_text"` | `question.open_not_allowed_by_default` |

**不要生成简答题/开放题**。使用 single_choice / multiple_choice / true_false / code 替代。

---

## 9. question_role（内容生成题必需）

当 tags 包含 `"content-derived"` 或 `"lesson-derived"` 时，必须填写 `question_role`：

| question_role | 适用场景 |
|---|---|
| `"learn"` | 普通学习题 |
| `"project_task"` | 项目/诊断题 |
| `"review"` | 复习题 |

---

## 10. 题目自包含要求（硬约束）

**每道题必须独立可答。脱离课件后，题目文本必须提供所有作答所需信息。**

- 代码题：`problem_statement` 必须完整描述输入/输出/行为。禁止写"阅读课件中的 xx 函数"或"参考第三节的代码"。如果涉及特定函数，其签名和规格必须在题目中给出
- `starter_code` 禁止仅为 `pass` 占位（除非 `problem_statement` 已给出完整函数签名和 docstring）
- 概念题：禁止引用"课件中提到的 xx 概念"而不在题目中解释该概念
- 如果题目需要阅读一段代码才能作答，该代码必须在 `problem_statement` 或 `starter_code` 中完整给出

**反例（禁止）**：
- "阅读下面的函数定义，回答问题"——但没有给出函数定义
- "根据课件中的 clean_scores 函数，判断以下测试是否能覆盖关键边界"——题目不含 clean_scores 代码
- "参考第 3 节的代码实现"——题目没有复现那段代码

**正例**：
- "以下是 clean_scores 函数的实现：[代码]。判断以下哪个测试用例能覆盖边界条件 X。"——代码在题目中
- "实现一个函数 filter_positive(numbers)，接收整数列表，返回只含正数的新列表。签名：def filter_positive(numbers: list[int]) -> list[int]。"——签名和规格在题目中

---

## 11. 干扰项质量（硬约束）

每个选择题的干扰项必须有真实迷惑性——必须来自常见误区、典型错误理解或易混淆概念。

- **迷惑性检验**：去掉正确选项后，剩余选项中是否仍有至少 2 个看起来 plausible？如果答案可以被不具备该知识的人轻易排除（如 3 个选项明显荒谬），则该题不通过
- **干扰项来源**：必须来自常见误区（如把浅拷贝当深拷贝、把引用当复制、混淆 sort 和 sorted）、典型错误写法（如忘记 return、用错参数顺序）、或易混淆概念（如 is vs ==、append vs extend）
- **禁止凑数选项**：不能出现"以上都不对""以上都对""都有可能"等无信息量的选项（除非它们确实是正确答案且有具体理由）

## 12. 排版约束

- **概念题 `question` / `prompt` 字段必须使用 Markdown 排版**：代码用 ` ```python ``` ` 包裹，重点用 `**粗体**`，列表用 `- ` 或 `1. `。一段到底的纯文本不可接受。
- **代码题必须拆分为独立字段**：`problem_statement`（问题描述）、`input_spec`（输入规格）、`output_spec`（输出规格）、`constraints`（约束条件）各自独立填写，全部非空且有实质性内容。严禁把所有内容写成一大段只塞进 `problem_statement`。
- **代码题 `problem_statement` 必须可扫读**：使用空行、列表、粗体、inline code 或代码块组织题面；函数名、参数名、字段名用 inline code；多个条件、边界或步骤每条独立成行。
- **`constraints` 有多条规则时必须使用数组、Markdown bullet 或换行**，禁止用分号堆成一行。

**代码题正例**：
```json
{
  "problem_statement": "实现 `clean_records(records)`。

**目标**：清洗并过滤记录列表，返回一个新的列表。

每条记录可能包含：
- `name`
- `city`
- `score`

要求函数不修改输入列表。",
  "input_spec": "`records: list[dict]`，每个 dict 可能包含 `name: str`、`city: str`、`score: int | str`。",
  "output_spec": "`list[dict]`，只保留有效记录；每条记录包含标准化后的 `name`、`city`、`score`。",
  "constraints": [
    "`name` 为空则跳过该记录",
    "`city` 缺失或为空时填为 `'未知'`",
    "`score` 必须能转换为非负整数",
    "不得修改输入列表或原始记录对象"
  ]
}
```

**反例（会被拒绝）**：
```json
{
  "problem_statement": "实现 clean_records 函数，接收 records，清洗 name city score，name 为空跳过，city 为空未知，score 转整数，不能修改输入，返回列表。",
  "constraints": "不修改输入；name 为空则跳过；city 缺失/为空默认未知；score 必须 >= 0"
}
```

- `examples` 数组的每一项必须有 `input`/`output`/`explanation` 三个字段，不得省略任何字段
- `starter_code` 必须给出完整的函数签名（含参数名和类型标注），不能只是 `pass` 占位

## 13. 基础校验清单（出题后自查）

生成 JSON 后，确认：
- [ ] 每题含完整 difficulty 元数据：difficulty_level、difficulty_label、difficulty_score、difficulty_reason、expected_failure_mode
- [ ] 每个概念题含 scoring_rubric、capability_tags、explanation
- [ ] 每个代码题含全部 8 个必填字段 + hidden_tests
- [ ] 每个 SQL 题声明 `supported_runtimes: ["mysql"]`、`starter_sql`、dataset/parameter 引用和 `result_contract`
- [ ] answer 类型正确：单选=int，多选=list[int]，判断=bool
- [ ] 每个代码题的 solution_code 在本地执行正确；SQL 题不走 Python preflight
- [ ] hidden_tests 的 argument contract 与 function_signature 一致
- [ ] `parameter-spec.json`、`parameter-artifact.json`、`dataset-artifact.json` 均存在并通过基础校验
- [ ] 所有 `parameter_ref`、`dataset_ref`、`dataset_view_ref` 可解析
- [ ] DataFrame/Series dataset 含 reconstruction metadata
- [ ] hidden rows、hidden expected、hidden physical table name、reference SQL/code 不进入前端可见 payload
- [ ] 所有题含 source_trace 或 source_segment_id
- [ ] 无 open/written/short_answer 类型
- [ ] 无重复 id
