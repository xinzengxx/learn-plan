# learn-plan skill 簇契约文档

本文档定义整个 `/learn-plan` skill 簇的**稳定数据契约**。它不是实现细节文档，而是各脚本、skill prompt 与后续模块拆分时都要对齐的 schema 约束。

相关文档：
- 架构总览：`../WORKFLOW_DESIGN.md`
- 状态文件所有权：`./state-files.md`
- 运行时兼容边界：`./runtime-compatibility.md`

---

## 1. 契约分层

系统中的数据契约按 4 层划分：

1. **workflow 中间态契约**
   - `clarification.json`
   - `research.json`
   - `diagnostic.json`
   - `approval.json`
   - `workflow_state.json`
2. **正式长期状态契约**
   - `learn-plan.md`
   - `materials/index.json`
3. **执行期 session 契约**
   - `questions.json`
   - `progress.json`
4. **反馈与演进契约**
   - `learner_model.json`
   - `curriculum_patch_queue.json`

原则：
- workflow 中间态用于推进 `/learn-plan`，**不能替代** 正式 `learn-plan.md`。
- `learn-plan.md` 是用户可读的正式 curriculum 主文档，**只允许** 在 `finalize` 或已批准 patch 落地时更新主体结构。
- `progress.json` 记录 session 事实，不承担长期工作流状态职责。
- `learner_model.json` 保存能力证据与复习债，但不是新的正式 curriculum 主状态源。

---

## 2. 通用约定

### 2.1 版本字段

所有 JSON 契约都应包含版本字段：

```json
{
  "contract_version": "learn-plan.workflow.v2"
}
```

说明：
- `learn-plan.workflow.v2` 表示 skill 簇重构后的统一契约代。
- 后续若发生不兼容变更，应升级主版本号，而不是静默改字段含义。

### 2.2 状态字段命名

统一使用：
- `status`：当前对象生命周期状态
- `approved` / `ready_for_execution`：明确 gate 结果
- `open_questions` / `pending_decisions`：显式未决项
- `source_evidence` / `evidence`：保留结论依据
- `recommended_*`：建议动作，不等于已生效动作

### 2.3 契约设计原则

- 缺字段时应被 gate 明确阻塞，不允许静默通过。
- 数组字段优先使用空数组 `[]`，避免 `null`/缺失混用。
- 需要给用户解释的关键结论，都应保留依据字段。
- `plan_path`、`materials_index`、`session_dir` 等路径字段优先保存绝对路径或相对学习根目录的稳定路径，不使用临时工作目录语义。

### 2.4 统一质量 envelope

以下字段构成跨阶段统一质量契约，字段名必须保持完全一致：
- `generation_trace`
- `quality_review`
- `evidence`
- `confidence`
- `traceability`

适用范围：
- workflow 中间态：`clarification.json`、`research.json`、`diagnostic.json`、`approval.json`
- runtime/session 产物：`questions.json`、`lesson.md` 对应的结构化 lesson payload
- feedback 产物：`learner_model.json`、`curriculum_patch_queue.json` 的根对象，以及它们内部的 `evidence_log`、`patches`

语义约定：
- `generation_trace`：记录当前对象由谁、在哪个阶段、以什么状态生成；用于追溯生成链路，不承担业务放行。
- `quality_review`：记录 reviewer、valid、issues、warnings、confidence、evidence_adequacy、verdict；用于表达质量判断结果。
- `evidence`：当前对象可直接支撑结论的证据摘要，优先保留用户可解释的文本事实。
- `confidence`：`0.0-1.0` 的归一化置信度；低置信度不应被包装成 ready。
- `traceability`：当前对象与 session、material segment、question、profile、curriculum 等来源的关联指针。

边界约定：
- LLM 可以生成 candidate 与 reviewer 输入，但不能直接替代正式长期状态。
- deterministic gate 继续拥有最终放行权；`quality_review.valid=true` 不等于允许 `finalize`。
- 正式 `learn-plan.md` 只能由 renderer + gate 写出，不允许由 LLM 直接产出最终正文并绕过 gate。

---

## 3. workflow_state.json

`workflow_state.json` 是 workflow engine 的路由摘要，不是事实来源本体。

### 3.1 作用

- 告诉 orchestrator 当前卡在哪个阶段。
- 告诉 `/learn-plan` 下一轮要切到哪个 mode。
- 汇总 gate 缺项与质量问题。

### 3.2 建议结构

```json
{
  "contract_version": "learn-plan.workflow.v2",
  "workflow_type": "light|diagnostic-first|research-first|mixed",
  "current_mode": "draft",
  "recommended_mode": "research-report",
  "blocking_stage": "research",
  "should_continue_workflow": true,
  "is_intermediate_product": true,
  "next_action": "switch_to:research-report",
  "missing_requirements": [],
  "quality_issues": [],
  "artifacts": {
    "clarification_json": "<root>/.learn-workflow/clarification.json",
    "research_json": "<root>/.learn-workflow/research.json",
    "diagnostic_json": "<root>/.learn-workflow/diagnostic.json",
    "approval_json": "<root>/.learn-workflow/approval.json",
    "workflow_state_json": "<root>/.learn-workflow/workflow_state.json",
    "learner_model_json": "<root>/.learn-workflow/learner_model.json",
    "curriculum_patch_queue_json": "<root>/.learn-workflow/curriculum_patch_queue.json",
    "plan_path": "<root>/learn-plan.md",
    "materials_index": "<root>/materials/index.json"
  }
}
```

### 3.3 必需语义

- `blocking_stage` 只能取：`clarification | research | diagnostic | approval | ready`
- `next_action` 只能取：
  - `switch_to:draft`
  - `switch_to:research-report`
  - `switch_to:diagnostic`
  - `switch_to:finalize`
  - `enter:/learn-today`
- `should_continue_workflow = false` 时，必须同时满足：
  - `is_intermediate_product = false`
  - `blocking_stage = ready`
  - `next_action = enter:/learn-today`

---

## 4. clarification.json

### 4.1 作用

保存顾问式 intake 的结构化结果。

### 4.2 关键字段

```json
{
  "contract_version": "learn-plan.workflow.v2",
  "questionnaire": {
    "topic": "",
    "goal": "",
    "success_criteria": [],
    "current_level_self_report": "",
    "background": [],
    "time_constraints": {
      "frequency": "",
      "session_length": "",
      "deadline": "",
      "routine_constraints": []
    },
    "learning_preferences": {
      "style": [],
      "sequence": "先讲后练|先测后讲|边讲边练|混合",
      "exercise_types": [],
      "feedback_style": ""
    },
    "mastery_preferences": {
      "preferred_checks": [],
      "acceptable_evidence": [],
      "assessment_depth_preference": "simple|deep|undecided"
    },
    "existing_materials": [],
    "non_goals": [],
    "constraints": []
  },
  "clarification_state": {
    "status": "needs-more|confirmed",
    "resolved_items": [],
    "open_questions": [],
    "assumptions": [],
    "constraints_confirmed": [],
    "non_goals": []
  },
  "preference_state": {
    "status": "needs-confirmation|confirmed",
    "learning_style": [],
    "practice_style": [],
    "delivery_preference": [],
    "pending_items": []
  }
}
```

### 4.3 gate 最低要求

- `questionnaire.topic` 非空
- `questionnaire.goal` 非空
- `questionnaire.success_criteria` 非空
- `questionnaire.current_level_self_report` 非空
- `questionnaire.time_constraints.frequency` 或 `session_length` 至少一项非空
- `questionnaire.mastery_preferences.assessment_depth_preference` 必须为 `simple` 或 `deep`，不能停留在 `undecided`
- `preference_state.pending_items` 为空
- `clarification_state.open_questions` 为空或只剩非阻塞项

补充说明：
- `/learn-plan` 必须在 clarification 阶段显式让用户选择“简单测评 / 深度测评”。
- 若该字段仍为 `undecided`，workflow 必须继续停留在 clarification，不得默认走 simple。

---

## 5. research.json

### 5.1 作用

保存 deepsearch / capability modeling 的结构化结果。

### 5.2 关键字段

```json
{
  "contract_version": "learn-plan.workflow.v2",
  "deepsearch_status": "not-needed|plan-pending|completed",
  "research_plan": {
    "status": "proposed|approved|completed",
    "research_questions": [],
    "source_types": [],
    "selection_criteria": []
  },
  "research_report": {
    "report_status": "missing|completed",
    "goal_level_definition": "",
    "capability_metrics": [
      {
        "id": "cap-001",
        "name": "",
        "layer": "mainline|supporting|deferred",
        "target_level": "",
        "observable_behaviors": [],
        "quantitative_indicators": [
          {
            "metric": "",
            "threshold": "",
            "measurement_method": ""
          }
        ],
        "diagnostic_methods": [],
        "learning_evidence": [],
        "source_evidence": [],
        "material_implications": [],
        "priority": "must|should|optional"
      }
    ],
    "mainline_capabilities": [],
    "supporting_capabilities": [],
    "deferred_capabilities": [],
    "candidate_materials": [],
    "selection_rationale": [],
    "evidence_summary": [],
    "open_risks": []
  }
}
```

### 5.3 gate 最低要求

- 若需要 research：`research_plan.status` 必须为 `approved` 或 `completed`
- `research_report.report_status = completed`
- `capability_metrics` 非空
- 每个主线能力项至少有：
  - `observable_behaviors`
  - `diagnostic_methods`
  - `learning_evidence`
- 有 `source_evidence` 或 `evidence_summary`

---

## 6. diagnostic.json

### 6.1 作用

保存最小诊断设计、用户答案、批改与起点评估。

### 6.2 关键字段

```json
{
  "contract_version": "learn-plan.workflow.v2",
  "diagnostic_plan": {
    "target_capability_ids": [],
    "test_strategy": "口头解释|选择判断|小代码题|小项目|阅读复盘|混合",
    "assessment_depth": "simple|deep",
    "round_index": 1,
    "max_rounds": 1,
    "delivery": "web-session",
    "assessment_kind": "initial-test",
    "session_intent": "assessment",
    "estimated_time": "",
    "scoring_rubric": []
  },
  "diagnostic_items": [
    {
      "id": "diag-001",
      "capability_id": "cap-001",
      "type": "concept|code|design|reflection|project",
      "prompt": "",
      "expected_signals": [],
      "rubric": [
        {
          "level": "",
          "criteria": []
        }
      ]
    }
  ],
  "diagnostic_result": {
    "status": "not-started|answered|evaluated",
    "answers_summary": [],
    "scores": [
      {
        "item_id": "diag-001",
        "score": "",
        "observed_signals": [],
        "missing_signals": []
      }
    ],
    "capability_assessment": [
      {
        "capability_id": "cap-001",
        "current_level": "",
        "target_level": "",
        "gap": "",
        "confidence": "low|medium|high"
      }
    ],
    "observed_strengths": [],
    "observed_weaknesses": [],
    "recommended_entry_level": "",
    "follow_up_needed": false,
    "stop_reason": "enough-evidence|max-rounds|user-stop|undetermined",
    "plan_adjustments": []
  },
  "diagnostic_profile": {
    "status": "in-progress|validated",
    "assessment_depth": "simple|deep",
    "round_index": 1,
    "max_rounds": 1,
    "baseline_level": "",
    "dimensions": [],
    "observed_strengths": [],
    "observed_weaknesses": [],
    "evidence": [],
    "recommended_entry_level": "",
    "confidence": "low|medium|high"
  }
}
```

### 6.3 gate 最低要求

- `diagnostic_items` 非空
- `diagnostic_plan.assessment_depth` 非空
- `diagnostic_plan.round_index >= 1`
- `diagnostic_plan.max_rounds >= diagnostic_plan.round_index`
- `diagnostic_plan.delivery = web-session`
- `diagnostic_plan.assessment_kind = initial-test`，历史 `plan-diagnostic` 仍应兼容读取
- `diagnostic_plan.session_intent = assessment`，历史 `plan-diagnostic` 仍应兼容读取
- `diagnostic_result.status = evaluated`
- `capability_assessment` 非空
- `recommended_entry_level` 非空
- `confidence` 非空
- 若 `assessment_depth = deep` 且证据仍不足，应显式写出 `follow_up_needed` 与 `stop_reason`

补充说明：
- diagnostic 题目应通过网页 session 四件套交付，用户先作答，再由 `/learn-plan` 诊断语义消费结果。
- 新生成的起始测试应写为 `assessment_kind = initial-test`、`session_intent = assessment`，并保留 `plan_execution_mode = diagnostic`；历史 `plan-diagnostic` 只读兼容。
- 不得把前置起点诊断改写成普通 `stage-test` 结论；虽然更新入口统一走 `/learn-test-update`，但输出语义仍应是“起步层级判断”，不是阶段通过/回退。

---

## 7. approval.json

### 7.1 作用

保存计划草案确认状态与关键 tradeoff 的接受结果。

### 7.2 关键字段

```json
{
  "contract_version": "learn-plan.workflow.v2",
  "approval_state": {
    "approval_status": "draft|needs-revision|approved",
    "ready_for_execution": false,
    "approved_scope": [],
    "pending_decisions": [],
    "requested_changes": [],
    "accepted_tradeoffs": [],
    "confirmed_material_strategy": false,
    "confirmed_daily_execution_style": false,
    "confirmed_mastery_checks": false,
    "risk_acknowledgements": []
  }
}
```

### 7.3 gate 最低要求

- `approval_status = approved`
- `ready_for_execution = true`
- `pending_decisions` 为空
- `confirmed_material_strategy = true`
- `confirmed_daily_execution_style = true`
- `confirmed_mastery_checks = true`

---

## 8. learner_model.json

### 8.1 作用

保存跨 session 的学习者模型。它是 feedback 层的结构化状态，不是正式长期 curriculum 文档。

### 8.2 当前结构

```json
{
  "schema": "learn-plan.learner-model.v1",
  "contract_version": "learn-plan.workflow.v2",
  "evidence": [],
  "confidence": 0.0,
  "generation_trace": {
    "stage": "feedback",
    "generator": "learner-model-state",
    "status": "initialized|updated"
  },
  "traceability": [],
  "quality_review": {
    "reviewer": "learner-model-root-gate",
    "valid": true,
    "issues": [],
    "warnings": [],
    "confidence": 0.0,
    "evidence_adequacy": "partial|sufficient",
    "verdict": "ready"
  },
  "evidence_log": [
    {
      "update_type": "today|test|diagnostic",
      "date": "",
      "topic": "",
      "summary": "",
      "evidence": [],
      "session_dir": "",
      "confidence": 0.0,
      "generation_trace": {},
      "traceability": [],
      "quality_review": {}
    }
  ],
  "strengths": [],
  "weaknesses": [],
  "review_debt": [],
  "mastered_scope": [],
  "last_updated": ""
}
```

### 8.3 使用边界

- 根对象与 `evidence_log` 条目都应保留统一质量 envelope；根对象表达“当前 learner model 状态”，条目表达“单次 session 证据”。
- 可被 `/learn-today`、`/learn-test`、update 脚本消费。
- 不应直接替代 `learn-plan.md` 中的长期路线图。
- 只能表达“当前估计”和“证据”；正式阶段切换仍以计划与 approval 为准。

---

## 9. curriculum_patch_queue.json

### 9.1 作用

保存 update 层提出的课程调整建议，等待后续 gate/approval 决定是否改正式计划。

### 9.2 当前结构

```json
{
  "schema": "learn-plan.curriculum-patch-queue.v1",
  "contract_version": "learn-plan.workflow.v2",
  "evidence": [],
  "confidence": 0.0,
  "generation_trace": {
    "stage": "feedback",
    "generator": "curriculum-patch-queue",
    "status": "initialized|updated"
  },
  "traceability": [],
  "quality_review": {
    "reviewer": "patch-queue-root-gate",
    "valid": true,
    "issues": [],
    "warnings": [],
    "confidence": 0.0,
    "evidence_adequacy": "partial|sufficient",
    "verdict": "ready"
  },
  "patches": [
    {
      "id": "2026-04-14:today:Python",
      "status": "pending-evidence|proposed|approved|rejected|applied",
      "patch_type": "review-adjustment|advance-proposal|entry-level-adjustment",
      "topic": "",
      "created_at": "",
      "source_update_type": "today|test|diagnostic",
      "rationale": "",
      "evidence": [],
      "confidence": 0.0,
      "proposal": {
        "recommended_entry_level": "",
        "review_focus": [],
        "next_actions": [],
        "blocking_weaknesses": [],
        "deferred_enhancement": [],
        "can_advance": false,
        "should_review": true
      },
      "application_policy": "pending-user-approval",
      "generation_trace": {},
      "traceability": [],
      "quality_review": {
        "valid": false,
        "issues": [],
        "warnings": [],
        "reviewer": "deterministic-feedback-gate"
      }
    }
  ]
}
```

### 9.3 使用边界

- 根对象与 `patches` 条目都应保留统一质量 envelope；根对象表达“当前 patch queue 状态”，条目表达“单条 patch 建议”。
- queue 中的 patch 只是建议，不是已生效修改。
- `pending-evidence` 表示证据或 confidence 不足，只能等待补充，不应进入正式应用。
- `application_policy` 必须保持 `pending-user-approval`；update 不得直接改长期路线主体。
- `quality_review` 是 deterministic gate 结果，可用于阻断低质量 patch。
- `applied` 只能在正式计划完成更新后标记。

---

## 10. materials/index.json

### 10.1 作用

保存材料索引、角色划分、segment 信息与缓存状态。它既服务 planning，也服务 runtime grounding。

### 10.2 关键字段

```json
{
  "topic": "",
  "family": "linux|llm-app|backend|frontend|database|algorithm|math|english|general-cs",
  "generated_at": "",
  "items": [
    {
      "id": "",
      "title": "",
      "role": "mainline|supporting|optional|candidate",
      "kind": "book|doc|tutorial|course|repo|article|reference",
      "domain": "",
      "url": "",
      "downloadable": false,
      "cache_status": "not-downloaded|cached|download-failed|unavailable",
      "local_path": "",
      "segments": [
        {
          "id": "seg-001",
          "title": "",
          "locator": "chapter/page/section/path",
          "summary": "",
          "capability_ids": [],
          "priority": "must|should|optional"
        }
      ],
      "source_key_points": [],
      "source_examples": [],
      "source_pitfalls": [],
      "selection_rationale": [],
      "updated_at": ""
    }
  ]
}
```

### 10.3 最低兼容要求

- 保留现有 runtime 依赖的 `items` 级材料列表语义
- 允许逐步增强 `segments`、`source_key_points` 等字段
- 下载器必须继续维护：
  - `cache_status`
  - `local_path`
  - `cached_at`
  - `last_attempt`

---

## 11. learn-plan.md

`learn-plan.md` 是正式长期计划，采用 Markdown section 契约而不是 JSON。

### 11.1 最低 section 契约

正式计划至少保留以下区块：

1. `学习画像`
2. `规划假设与约束`
3. `能力指标与起点判断`
4. `检索结论与取舍`
5. `阶段总览`
6. `阶段路线图`
7. `资料清单与阅读定位`
8. `掌握度检验设计`
9. `今日生成规则`
10. `每日推进表`
11. `学习记录`
12. `测试记录`

### 11.2 关键兼容要求

- `今日生成规则` 必须保留，供 `/learn-today` 消费。
- `学习记录`、`测试记录` 的标题必须稳定，供 update 追加。
- 新增 section 要尽量放在记录区块之前，避免破坏现有追加逻辑。

---

## 12. questions.json

### 12.1 作用

保存一次 today/test session 的题目载荷与上下文。

### 12.2 最低结构

```json
{
  "date": "",
  "topic": "",
  "mode": "",
  "session_type": "today|test",
  "session_intent": "learning|assessment|plan-diagnostic",
  "assessment_kind": "stage-test|initial-test|plan-diagnostic|null",
  "test_mode": "general|weakness-focused|mixed|null",
  "plan_source": {},
  "materials": [],
  "questions": []
}
```

### 12.3 题目级要求

每题必须有唯一 `id`。

概念题：
- `category: concept`
- `type: single | multi | judge`

代码题：
- `category: code`
- `type: function`
- `title`
- `prompt`
- `function_name`
- `params`
- `starter_code`
- `solution_code`
- `test_cases`

开放题预留：
- `category: open`
- `type: written`
- `prompt`
- `reference_points`
- `grading_hint`

### 12.4 可追踪性要求

题目应尽量保留：
- 对应 lesson section
- 对应 capability / mastery target
- 对应 material segment / source excerpt
- 明确来源标记或 fallback 标记

当前 runtime 还会写入 `question_quality`，至少覆盖：
- `valid`
- `issues`
- `warnings`
- `fallback_count`
- `source_markers`

---

## 13. progress.json

### 13.1 作用

保存 session 过程与结果事实。

### 13.2 最低结构

```json
{
  "date": "",
  "topic": "",
  "session": {
    "type": "today|test",
    "intent": "learning|assessment|plan-diagnostic",
    "assessment_kind": "stage-test|initial-test|plan-diagnostic|null",
    "plan_execution_mode": "normal|clarification|research|diagnostic|test-diagnostic|prestudy|null",
    "test_mode": "general|weakness-focused|mixed|null",
    "status": "active|finished",
    "started_at": "",
    "finished_at": "",
    "plan_path": "",
    "materials": []
  },
  "summary": {
    "total": 0,
    "attempted": 0,
    "correct": 0
  },
  "questions": {}
}
```

### 13.3 question 级要求

每个 `questions.<id>` 至少包含：
- `stats`
- `history`

代码题历史保留代码与运行结果；概念题历史只保留正确/错误与时间，不默认回填历史答案到页面。

---

## 14. 契约验收顺序

后续实现与重构时，按以下顺序验收：

1. workflow JSON 是否能被正常读写
2. `workflow_state.json` 是否正确给出 route summary
3. `learn-plan.md` 是否仍能被 `/learn-today` 消费
4. `questions.json` / `progress.json` 是否仍能驱动现有 runtime
5. `learner_model.json` / `curriculum_patch_queue.json` 是否只增量增强，不破坏旧链路

---

## 15. 一句话原则

**中间态要结构化，正式态要稳定，执行态要可追踪，反馈态要可演进。**
