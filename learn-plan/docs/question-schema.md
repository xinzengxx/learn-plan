# 题目 JSON Schema（Agent 出题必读）

出题 Agent 生成的 `question-artifact.json` 必须通过 `question_validation.py` 的校验。本文件是 Schema 与 Runtime 之间的契约。

---

## 1. 顶层结构（11 个必填字段）

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

## 4. 禁止的题目类型

以下类型在 test-grade 模式下**自动被拒绝**：

| 被禁止的类型 | 错误信息 |
|---|---|
| `"open"` | `question.open_not_allowed_by_default` |
| `"written"` | `question.open_not_allowed_by_default` |
| `"short_answer"` | `question.open_not_allowed_by_default` |
| `"free_text"` | `question.open_not_allowed_by_default` |

**不要生成简答题/开放题**。使用 single_choice / multiple_choice / true_false / code 替代。

---

## 5. question_role（内容生成题必需）

当 tags 包含 `"content-derived"` 或 `"lesson-derived"` 时，必须填写 `question_role`：

| question_role | 适用场景 |
|---|---|
| `"learn"` | 普通学习题 |
| `"project_task"` | 项目/诊断题 |
| `"review"` | 复习题 |

---

## 6. 题目自包含要求（硬约束）

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

## 7. 干扰项质量（硬约束）

每个选择题的干扰项必须有真实迷惑性——必须来自常见误区、典型错误理解或易混淆概念。

- **迷惑性检验**：去掉正确选项后，剩余选项中是否仍有至少 2 个看起来 plausible？如果答案可以被不具备该知识的人轻易排除（如 3 个选项明显荒谬），则该题不通过
- **干扰项来源**：必须来自常见误区（如把浅拷贝当深拷贝、把引用当复制、混淆 sort 和 sorted）、典型错误写法（如忘记 return、用错参数顺序）、或易混淆概念（如 is vs ==、append vs extend）
- **禁止凑数选项**：不能出现"以上都不对""以上都对""都有可能"等无信息量的选项（除非它们确实是正确答案且有具体理由）

## 8. 排版约束

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

## 9. 基础校验清单（出题后自查）

生成 JSON 后，确认：
- [ ] 每题含完整 difficulty 元数据：difficulty_level、difficulty_label、difficulty_score、difficulty_reason、expected_failure_mode
- [ ] 每个概念题含 scoring_rubric、capability_tags、explanation
- [ ] 每个代码题含全部 8 个必填字段 + hidden_tests
- [ ] answer 类型正确：单选=int，多选=list[int]，判断=bool
- [ ] 每个代码题的 solution_code 在本地执行正确
- [ ] hidden_tests 的 argument contract 与 function_signature 一致
- [ ] 所有题含 source_trace 或 source_segment_id
- [ ] 无 open/written/short_answer 类型
- [ ] 无重复 id
