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

分层边界必须保持清晰：`question-scope.json` 和 `question-plan.json` 是薄规划层，只决定范围、题型、数量、目标难度和 planned item；`question-artifact.json` 是厚题目层，逐题保存考察思想、题型用途、选项/断言/测试点级知识覆盖和难度；`question-review.json` 是审题层，保存四维审查与 repair plan；`questions.json` 是 runtime 展示层，可以携带 metadata 供追踪和复盘，但不要把审题长报告塞进学习者可见题干。

---

## 0.1 厚题目 metadata（新 artifact 必填）

新生成题目只要进入 `question-artifact.json`，每题都必须包含以下字段；旧历史题缺失时 runtime 可兼容，但不作为新出题标准。

| 字段 | 类型 | 说明 |
|---|---|---|
| `planned_item_id` | string | 对齐 `question-plan.planned_items[].item_id`；若 plan 顺序与题目顺序一致也建议显式填写 |
| `assessment_intent` | string | 本题考察思想：想验证什么、为什么这样设置、答错能诊断什么 |
| `knowledge_scope` | object | 题目整体知识范围，含 `knowledge_point_ids`、`prerequisite_ids`、`misconception_ids` 和 source/evidence |
| `question_type_rationale` | object | 为什么选择该题型，以及该题型如何服务 `assessment_intent` |
| `coverage_units` | array[object] | 细到选项、判断断言、边界反例、测试点、子任务或 rubric item 的覆盖单元 |
| `difficulty_profile` | object | 题目级和 unit 级难度，含目标难度、实际难度、难度理由和预期失败模式 |

最小示例：

```json
{
  "planned_item_id": "plan-item-1",
  "assessment_intent": "检查学习者是否能区分 Python 赋值与相等比较，并能解释错选 `==` 暴露的误区。",
  "knowledge_scope": {
    "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
    "prerequisite_ids": [],
    "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
    "source_trace": {"question_source": "agent-injected"}
  },
  "question_type_rationale": {
    "type": "single_choice",
    "reason": "需要在多个相似符号中识别唯一正确项。",
    "assessment_fit": "错选项可诊断赋值、比较与符号语义混淆。"
  },
  "coverage_units": [
    {
      "unit_type": "option",
      "option_index": 0,
      "claim": "`=` 是 Python 赋值符号。",
      "diagnostic_role": "correct_concept",
      "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
      "difficulty_level": "basic",
      "diagnostic_value": "验证正向概念识别。"
    },
    {
      "unit_type": "option",
      "option_index": 1,
      "claim": "`==` 是相等比较符号，不是赋值符号。",
      "diagnostic_role": "distractor",
      "knowledge_point_ids": [{"id": "kp-python-assignment", "relevance": "primary", "confidence": 0.9}],
      "misconception_ids": [{"id": "mc-assignment-vs-equality", "confidence": 0.8}],
      "difficulty_level": "basic",
      "distractor_rationale": "常见误区是把赋值和比较混在一起。",
      "diagnostic_value": "错选可触发赋值/比较区分追问。"
    }
  ],
  "difficulty_profile": {
    "target_difficulty_level": "basic",
    "difficulty_level": "basic",
    "difficulty_reason": "只考一个符号语义，但通过干扰项暴露常见误区。",
    "expected_failure_mode": "混淆赋值与相等比较。",
    "coverage_units": [
      {"option_index": 0, "difficulty_level": "basic"},
      {"option_index": 1, "difficulty_level": "basic"}
    ]
  }
}
```

`coverage_units` 按题型有额外约束：

- `single_choice` / `multiple_choice`：每个选项都必须有一个 unit，含 `option_index`、`diagnostic_role`、知识点、unit 难度；干扰项必须写 `distractor_rationale` 或误区 rationale。
- `true_false`：必须至少包含 `statement`、`truth_rationale`、`boundary_or_counterexample` 三类 unit。判断题应用来考边界、限定条件、反例或概念适用范围，禁止退化成一眼术语判断。
- `code` / `sql`：必须至少包含 `subtask`、`test` / `public_test` / `hidden_test`、`rubric` / `rubric_item` 中的核心 unit，说明每个测试点覆盖的知识点、难度和诊断价值。

---

## 0.2 四维 question-review.json 契约

严格审题必须输出顶层 `dimension_reviews`，并且必须在 `question_reviews[]` 中逐题覆盖 `question-artifact.json` 里的全部题目 id。四个维度固定为：

| 维度 | 审查内容 |
|---|---|
| `description_completeness` | 题面、选项、输入输出、约束、答案格式、示例是否完整且可判定 |
| `knowledge_coverage_match` | 是否覆盖 `question-scope` / `question-plan` 的目标知识点、planned item 和来源依据 |
| `difficulty_correctness` | `difficulty_level`、`difficulty_dimensions`、coverage-unit 难度和干扰项/测试点复杂度是否一致 |
| `type_fitness` | 题型是否服务 `assessment_intent`；choice 干扰项是否有诊断价值；true_false 是否过浅 |

每个维度的结构：

```json
{
  "status": "pass | warning | fail",
  "issues": [],
  "evidence": [],
  "suggestions": [],
  "repair_instruction": ""
}
```

任一维度 `fail` 或 `needs_revision`，总 `valid` 必须为 `false`，`verdict` 必须为 `needs-revision`，并在 `repair_plan` 中给出可执行修复动作。缺失四维审查时 runtime 会保留兼容 warning；缺失逐题 `question_reviews` 或未覆盖全部题目 id 时，新运行时会判定 `strict review` 无效。

`repair_plan` 不由 runtime 自动执行。真实闭环是：strict review 失败 → runtime 阻断并标记 `review_loop_status=needs_external_repair` → 外部出题/审题 subagent 基于 `repair_plan` 重生成 `question-artifact.json` 和 `question-review.json` → 再注入 runtime 校验。

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
  "difficulty_target": {
    "allowed_levels": ["basic", "medium", "upper_medium", "hard"],
    "difficulty_boundaries": "basic=单点直接识别；medium=两个知识点或近迁移；upper_medium=三点以上组合/多步实现；hard=远迁移/状态性/复杂组合"
  },
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
  "planned_items": [
    {
      "item_id": "plan-item-1",
      "target_difficulty_level": "medium",
      "knowledge_point_ids": ["kp-assignment", "kp-comparison"],
      "combination_requirement": "combine",
      "difficulty_dimensions": {
        "knowledge_point_count": 2,
        "requires_concept_combination": true,
        "reasoning_steps": 2,
        "boundary_condition_count": 0,
        "transfer_distance": "near",
        "implementation_complexity": "none",
        "trap_density": "medium"
      },
      "difficulty_boundary_reason": "两个元知识点需要组合判断，因此最低为 medium。"
    }
  ],
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

每道题都必须显式声明难度。runtime 不直接从自然语言题干推断难度，但会基于 `difficulty_dimensions` 确定性推导最低难度，并校验 `difficulty_level` 与 question-plan 目标是否低估；旧题缺少 `difficulty_dimensions` 时保持兼容，但确定性难度覆盖会降低。

| 字段 | 类型 | 说明 |
|---|---|---|
| `difficulty_level` | string | 必须为 `basic` / `medium` / `upper_medium` / `hard` |
| `difficulty_label` | string | 必须与 level 对应：`基础题` / `中等题` / `中难题` / `难题` |
| `difficulty_score` | int | 必须与 level 对应：1 / 2 / 3 / 4 |
| `difficulty_reason` | string | 标注该难度的理由，必须非空 |
| `expected_failure_mode` | string 或 array | 预期学习者可能失败的方式，必须非空 |
| `difficulty_dimensions` | object | 维度化难度自评，包含知识点数、组合要求、推理步数、边界条件、迁移距离、实现复杂度、干扰项密度 |
| `difficulty_boundary_reason` | string | 说明为什么这些维度落在当前难度边界内 |
| `claimed_difficulty_level` | string | LLM 自评难度；若省略则等同于 `difficulty_level` |
| `planned_item_id` | string | 可选；生成题与 `question-plan.planned_items[].item_id` 的显式关联 |

`difficulty_level` 表示题目本体难度，不随学习者变化。同一道题对不同用户应保持同一难度；学习者适配应通过题组分布和入口选择处理，而不是改题目本体难度。

维度化判级边界：

| level | 典型边界 |
|---|---|
| `basic` | 单一元知识点；直接识别/复现；无组合要求；0–1 个简单边界 |
| `medium` | 两个元知识点；需要近迁移、2–3 步推理或多个边界条件 |
| `upper_medium` | 三个以上元知识点；需要组合应用、多步实现、较强干扰项或隐藏边界 |
| `hard` | 跨模块/跨抽象层组合；状态性或嵌套数据结构；复杂 SQL/实现策略；远迁移 |

runtime/确定性 reviewer 会用 `difficulty_dimensions` 推导最低难度。LLM 不能只凭感觉填写 `difficulty_level`；如果 `claimed_difficulty_level` 低于启发式最低难度，题目会被阻断并要求重写或修正 plan。

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

### 2.3 选项级诊断契约

`single_choice` / `multiple_choice` 必须为每个选项提供 `option_diagnostics`。该字段是练后诊断的候选证据，用于把错选、不确定项和漏选映射到元知识点；它不是直接扣分依据，后续 mastery 更新仍需结合练后追问与 evidence gate。

每个 entry 必须覆盖一个选项：

| 字段 | 类型 | 说明 |
|---|---|---|
| `index` | int | 选项 0-based index，必须覆盖全部选项且不重复 |
| `claim` | string | 该选项表达的可判定命题 |
| `diagnostic_role` | string | `correct_concept` / `distractor` / `edge_case` / `prerequisite_probe` / `wording_probe` / `question_quality` |
| `knowledge_point_ids` | array | 至少一个知识点映射；每项含 `id`、`relevance`、可选 `confidence` |
| `prerequisite_ids` | array | 可选前置知识点映射 |
| `misconception_ids` | array | 可选误区映射；干扰项应尽量提供 |
| `evidence_span` | string | 为什么该选项映射到这些知识点/误区 |
| `diagnostic_question` | string | 练后追问时可使用的问题 |
| `confidence` | number | 可选，0–1；低置信度表示需练后 reviewer 复核 |

`knowledge_point_ids[].relevance` 必须是 `primary` / `supporting` / `related`。`question_quality` 角色可以不提供知识点映射，用于标记题目措辞或选项本身的质量风险。

示例：

```json
"option_diagnostics": [
  {
    "index": 1,
    "claim": "`[1,2,3,4]` 正确表达 b.append 会修改共享列表对象。",
    "diagnostic_role": "correct_concept",
    "knowledge_point_ids": [{"id": "kp-variable-reference", "relevance": "primary", "confidence": 0.95}],
    "prerequisite_ids": [{"id": "kp-list-mutability", "confidence": 0.85}],
    "misconception_ids": [],
    "evidence_span": "该选项对应引用共享和 append 原地修改。",
    "diagnostic_question": "为什么 b.append(4) 会影响 a？"
  }
]
```

### 2.4 来源追溯

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
  "difficulty_dimensions": {
    "knowledge_point_count": 1,
    "requires_concept_combination": false,
    "reasoning_steps": 1,
    "boundary_condition_count": 0,
    "transfer_distance": "direct",
    "implementation_complexity": "none",
    "trap_density": "low"
  },
  "difficulty_boundary_reason": "单点引用语义直接识别，无组合推理，因此是 basic。",
  "option_diagnostics": [
    {
      "index": 0,
      "claim": "`[1,2,3]` 表示误以为 b = a 会复制列表。",
      "diagnostic_role": "distractor",
      "knowledge_point_ids": [{"id": "kp-variable-reference", "relevance": "primary", "confidence": 0.9}],
      "prerequisite_ids": [{"id": "kp-list-mutability", "confidence": 0.8}],
      "misconception_ids": [{"id": "mc-reference-as-copy", "confidence": 0.85}],
      "evidence_span": "该选项暴露引用赋值误解。",
      "diagnostic_question": "`b = a` 后 a 和 b 指向几个列表对象？"
    },
    {
      "index": 1,
      "claim": "`[1,2,3,4]` 正确表达 b.append 会修改共享列表对象。",
      "diagnostic_role": "correct_concept",
      "knowledge_point_ids": [{"id": "kp-variable-reference", "relevance": "primary", "confidence": 0.95}],
      "prerequisite_ids": [{"id": "kp-list-mutability", "confidence": 0.85}],
      "misconception_ids": [],
      "evidence_span": "该选项对应引用共享和 append 原地修改。",
      "diagnostic_question": "为什么 b.append(4) 会影响 a？"
    },
    {
      "index": 2,
      "claim": "该代码不会因为引用赋值或 append 报错。",
      "diagnostic_role": "distractor",
      "knowledge_point_ids": [{"id": "kp-variable-reference", "relevance": "supporting", "confidence": 0.8}],
      "prerequisite_ids": [],
      "misconception_ids": [{"id": "mc-list-append-error", "confidence": 0.6}],
      "evidence_span": "该选项检查是否理解 append 调用的合法性。",
      "diagnostic_question": "这段代码中哪一步可能报错？为什么？"
    },
    {
      "index": 3,
      "claim": "print(a) 输出列表内容，不会输出 None。",
      "diagnostic_role": "distractor",
      "knowledge_point_ids": [{"id": "kp-variable-reference", "relevance": "supporting", "confidence": 0.8}],
      "prerequisite_ids": [{"id": "kp-print-output", "confidence": 0.6}],
      "misconception_ids": [{"id": "mc-append-return-none", "confidence": 0.75}],
      "evidence_span": "该选项暴露把 append 返回值和 print 输出混淆。",
      "diagnostic_question": "append 的返回值和 print(a) 的输出有什么区别？"
    }
  ],
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

### 3.1 代码题必填字段

代码题比概念题严格得多，以下每个字段都不能为空：

| 字段 | 说明 | 示例 |
|---|---|---|
| `title` | 题目标题 | `"实现列表过滤函数"` |
| `problem_statement` | 问题描述 | `"写一个函数，接收整数列表，过滤 None 和负数..."` |
| `input_spec` | 输入规格：逐个参数说明类型、嵌套结构、底层元素所有可能类型与约束 | `"scores: list[int | None] — 可能含 None 的整数列表"` |
| `output_spec` | 输出规格：逐个说明返回字段/元素的类型、语义、结构、排序、精度、边界返回、取值范围或枚举 | `"返回 list[int]，每个元素是非负整数，取值范围 >= 0"` |
| `calculation_spec` | 计算说明：过滤、聚合、排序、比较、舍入和边界处理规则 | `"过滤 None 和负数，保留 0 与正整数，保持原顺序"` |
| `constraints` | 约束条件 | `"保持原顺序，不修改原列表"` |
| `examples` | 公开示例 | `[{"input": ..., "output": ..., "explanation": ...}]` |
| `public_tests` | 公开测试用例，用于运行预览和可见评测 | `[{"args": [...], "expected": ...}]` |
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
  "input_spec": "`scores: list[int | None]`，列表元素可能是 `int` 或 `None`；长度可为 0，`int` 元素可为负数、0 或正数。",
  "output_spec": "返回 `list[int]`，长度可为 0；每个元素都是来自输入 `scores` 的 `int`，语义为被保留的有效分数，取值范围为 `>= 0`；元素顺序必须与输入中出现顺序一致。",
  "calculation_spec": "从左到右遍历 `scores`；跳过 `None` 和负整数；保留 `0` 与正整数；不修改原列表。",
  "constraints": ["不修改原列表", "保持元素顺序", "None 和负数被过滤"],
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
  "public_tests": [
    {"args": [[100, None, -1, 0, 88]], "expected": [100, 0, 88]}
  ],
  "hidden_tests": [
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
        {"name": "min_amount", "type": "json", "schema": {"kind": "number", "min": 0}}
      ],
      "output_schema": {
        "kind": "object",
        "fields": {
          "error_code": {"kind": "int", "allowed_values": [0, 1, 2], "description": "0 表示成功，1 表示无匹配记录，2 表示输入非法。"},
          "records": {"kind": "list", "element": {"kind": "object", "fields": {"region": {"kind": "str", "description": "区域名称。"}, "amount": {"kind": "number", "min": 0, "description": "订单金额。"}}}, "description": "筛选后的记录列表。"}
        }
      }
    }
  ]
}
```

允许的参数类型：`json`、`python_literal`、`dataframe`、`series`、`sql_table`、`ndarray`、`tensor`。

`parameters[].schema` 是代码题输入的机器可读细类型契约。第一版支持：
- 标量：`int`、`float`、`number`、`bool`、`str`/`string`、`none`/`null`、`json`
- 容器：`list`/`array`（`element`）、`tuple`（`items`）、`dict`/`object`（`fields` 或 `key`/`value`）
- 联合类型：`union` + `any_of`
- 约束：`min`、`max`、`min_length`、`max_length`、`nullable`、`allowed_values`、`description`

所有 code 题都必须在 `runtime_context.parameter_spec.questions[]` 中有同 id 的规格；`parameters[].name` 必须覆盖 `function_signature` 中的所有参数；每个 code 题必须有 `output_schema`。`examples`、`public_tests`、`hidden_tests` 的参数值必须符合 `parameters[].schema`，expected output 必须符合 `output_schema`；`input_spec` 必须用自然语言覆盖每个参数名、关键容器类型、union 的所有基础类型和主要约束，`output_spec` 必须覆盖 `output_schema` 中每个返回字段/元素的名称、类型、语义、取值范围、长度约束或枚举值含义。输出字段若是 `error_code`、`status`、`label`、`score`、`id` 等状态/类别/数值标识，schema 必须提供 `description` 以及 `allowed_values` 或 `min/max` 等范围约束。

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
- **代码题必须拆分为独立字段**：`problem_statement`（题目详细描述）、`input_spec`（输入说明）、`output_spec`（输出说明）、`calculation_spec`（计算说明）、`examples`（示例）构成前端五段主展示；`constraints` 仍是边界限制契约字段，但不替代计算说明。各字段必须独立填写，全部非空且有实质性内容。严禁把所有内容写成一大段只塞进 `problem_statement`。
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
  "calculation_spec": "逐条扫描 `records`：`name` 为空跳过；`city` 缺失或为空时填为 `'未知'`；`score` 必须能转换为非负整数，否则跳过；返回新记录对象。",
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
- [ ] 每个代码题含完整题面契约字段：problem_statement、input_spec、output_spec、calculation_spec、constraints、examples、public_tests、hidden_tests、scoring_rubric、capability_tags
- [ ] 每个代码题在 runtime_context.parameter_spec 中有同 id 参数规格和 output_schema，且示例/public/hidden 参数值与 schema 一致，expected output 与 output_schema 一致
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
