# learn-plan skill 簇契约文档

本文档定义整个 `/learn-plan` skill 簇的**稳定数据契约**。它不是实现细节文档，而是各脚本、skill prompt 与后续模块拆分时都要对齐的 schema 约束。

相关文档：
- 顶层 skill 协议：`../SKILL.md`
- clarification 阶段：`./clarification-stage.md`
- research 阶段：`./research-stage.md`
- diagnostic 阶段：`./diagnostic-stage.md`
- approval 阶段：`./approval-stage.md`
- finalize 阶段：`./finalize-stage.md`
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
   - `workflow_state.json`（派生路由缓存，可从 stage artifacts 重建）
2. **正式长期状态契约**
   - `learn-plan.md`
   - `reports/purpose-analysis.html`
   - `reports/plan-draft.html`
   - `knowledge-map.md`
   - `knowledge-state.json`
   - `materials/index.json`
3. **执行期 session 契约**
   - `questions.json`
   - `progress.json`
   - `interaction_events.jsonl`
   - `reflection.json`
4. **反馈与演进契约**
   - `.learn-workflow/session_facts.json`
   - `learner_model.json`
   - `curriculum_patch_queue.json`

原则：
- workflow 中间态用于推进 `/learn-plan`，**不能替代** 正式 `learn-plan.md`。
- `learn-plan.md` 是用户可读的正式 curriculum 主文档，**只允许** 在 `finalize` 或已批准 patch 落地时更新主体结构。
- `knowledge-map.md` 是用户审阅知识图谱的正式视图；`knowledge-state.json` 是底层知识点 mastery / confidence / evidence 的权威状态源。
- `progress.json` 记录 session 事实，不承担长期工作流状态职责。
- `interaction_events.jsonl` 记录终端学习交互证据，只保存结构化摘要和必要短摘录，不保存完整聊天。
- `reflection.json` 记录用户明确完成后的 update 前复盘结果；没有 completion signal 时不应生成最终 reflection。
- `learner_model.json` 保存能力证据与复习债，但不是新的正式 curriculum 主状态源，也不替代 `knowledge-state.json` 的知识点掌握度。

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
- runtime/session 产物：`questions.json`、`sessions/<date>/lesson.html` 对应的结构化 lesson payload
- session evidence 产物：`interaction_events.jsonl` 条目、`reflection.json`、`.learn-workflow/session_facts.json`
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

### 2.5 knowledge-map.md 与 knowledge-state.json

`/learn-plan` 在目标和路线足够明确后，必须与 `learn-plan.md` 同目录维护双文件知识状态层：

- `knowledge-map.md`：给用户审阅，展示当前知识图谱、核心叶子粒度、关键依赖、coverage report、DAG 校验和 diagnostic blueprint。
- `knowledge-state.json`：给 skill 精确读写，保存节点、边、mastery、confidence、required evidence、evidence log 与 history。

第一版 `knowledge-state.json` 顶层结构：

```json
{
  "contract_version": "learn-plan.knowledge-state.v1",
  "schema_version": "1.0",
  "goal": {},
  "status": "draft|confirmed|active|migrated",
  "nodes": [],
  "edges": [],
  "coverage_report": {},
  "dag_validation": {},
  "diagnostic_blueprint": {},
  "evidence_log": [],
  "history": []
}
```

当前兼容层仍可读取三层：`domain | topic | knowledge_point`。目标 schema 会迁移到五层：`domain | module | concept_cluster | concept | atomic_knowledge_point`。上层节点只允许展示只读 `derived_mastery`；只有底层 `knowledge_point` / `atomic_knowledge_point` 可以维护真实 `mastery`、`confidence`、`target_mastery`、`required_evidence_types`、`status_label`、`last_studied`、`last_tested` 与 `evidence_refs`。

底层知识点 mastery 标签固定为：`0=未学习`，`1-59=不熟悉`，`60-79=已了解`，`80-99=已熟悉`，`100=已熟练掌握`。用户不能直接修正 mastery；所有 mastery 更新必须来自学习、测试、交互或复盘证据，并追加 evidence。`knowledge-state.json` 处于 `draft` 时不得回写 mastery/evidence；只有用户确认到 `confirmed` 或 `active` 后，且题目显式绑定合法 `knowledge_point_ids` 与 `evidence_types`，update 脚本才可写入知识点状态。

边结构至少包含：`from`、`to`、`type=hard|soft|recommended|diagnostic`、`reason`、`source`、`confidence`。DAG 校验必须覆盖节点唯一、parent 合法、edge 指向存在、无环、底层知识点有 required evidence、上层节点不写真实 mastery。

初始图谱采用“核心叶子”粒度：主线内容拆到底层可学习、可测试、可更新 mastery 的核心叶子；边缘 API 参数、罕见选项和细碎题型先保留为 `expandable_subpoints` / `notes`，只有目标强相关、用户反馈缺漏、测试暴露问题或学习中反复卡住时才升级为独立底层节点。

#### lesson target slice

`/learn-today` 应根据 plan pointer 与 `knowledge-state.json` 生成本节 `lesson_target_slice`：

```json
{
  "session_goal": "",
  "plan_pointer": {"stage": "", "topic": ""},
  "primary_points": [],
  "prerequisite_points": [],
  "review_points": [],
  "bridge_points": [],
  "blocked_points": [],
  "evidence_targets": [],
  "material_segments": [],
  "readiness": {}
}
```

进入新知识点前必须做 prerequisite readiness check：`mastery 达标 + confidence 足够 + required evidence 类型足够 + 最近无明显反证`。hard prerequisite 不足时应局部补前置；soft prerequisite 可边学边补；diagnostic prerequisite 不阻塞但需要小题校准。

#### test coverage slice

`/learn-test` 应根据测试目的、轮次和题量预算生成 `test_coverage_slice`：

```json
{
  "test_goal": "",
  "coverage_budget": {"rounds": 2, "questions_per_round": 5},
  "selected_points": [],
  "excluded_points": [],
  "question_mapping": [],
  "evidence_types": [],
  "expected_confidence_update": {}
}
```

测试题必须绑定 `knowledge_point_ids`、`evidence_types`、`rubric_by_knowledge_point` 与 `source_trace`。测试结束后按知识点拆分 evidence，不只看整题总分。

图谱漏项、依赖错误、前置缺口、节点过粗/过细或阶段过快/过慢，不允许被 `/learn-today` 或 `/learn-test` 静默重写长期计划；必须先记录 evidence，再生成图谱 diff 或 curriculum patch，经用户确认后写入。

---

## 3. workflow_state.json

`workflow_state.json` 是 workflow engine 的路由摘要，不是事实来源本体。

### 3.1 作用

- 告诉 orchestrator 当前卡在哪个阶段。
- 告诉 `/learn-plan` 下一轮要切到哪个 mode。
- 汇总 gate 缺项与质量问题。

### 3.2 建议结构

`workflow_type` 表示 intake 阶段判定出的首次路由类型，不表示当前所处阶段。它在首次写入后应保持冻结，后续 workflow 推进只更新 `blocking_stage / recommended_mode / next_action`，不应随当前 gate 重算。

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
  "stage_entry_contract": {},
  "stage_exit_contract": {
    "required_artifacts": [],
    "required_values": [],
    "user_visible_next_step": ""
  },
  "stage_exit_missing_values": [],
  "stage_exit_required_artifacts": [],
  "stage_exit_user_visible_next_step": "",
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

- `blocking_stage` 只能取：`clarification | research | diagnostic | approval | planning | ready`
- 其中 `planning` 表示 formal plan 尚未可写，但前序 gate 已基本满足、系统正在等待或生成 `plan_candidate`；它是 `finalize` 前的过渡态，不表示 workflow 回退到更早阶段。
- `stage_exit_contract` 必须展示当前阻塞阶段的退出契约，包括 required artifacts、required values 与用户可见下一步。
- `stage_exit_missing_values` 只能列当前阶段缺口；未来阶段缺口应放入 reference missing，不应用来诱导当前阶段手补未来 artifact。
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
      "max_assessment_rounds_preference": 1,
      "questions_per_round_preference": 5,
      "question_mix_preference": []
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
  },
  "consultation_state": {
    "status": "needs-more|confirmed",
    "current_topic_id": "learning_purpose",
    "topic_order": ["learning_purpose", "exam_or_job_target", "success_criteria", "current_level", "constraints", "teaching_preference", "practice_preference", "materials", "assessment_scope", "non_goals"],
    "topics": [
      {
        "id": "learning_purpose",
        "label": "学习目的",
        "status": "not-started|in-progress|resolved|deferred",
        "required": true,
        "exit_criteria": [],
        "confirmed_values": {},
        "open_questions": [],
        "assumptions": [],
        "ambiguities": [],
        "evidence": [],
        "last_user_answer_summary": ""
      }
    ],
    "thread": [
      {
        "turn_id": "",
        "topic_id": "",
        "question": "",
        "user_answer_summary": "",
        "interpretation": "",
        "status": "resolved|ambiguous|needs-follow-up|assumed|deferred",
        "next_question": ""
      }
    ],
    "open_questions": [],
    "assumptions": []
  },
  "language_policy": {
    "user_facing_language": "zh-CN|en|auto",
    "detected_from": "current-conversation|explicit-user-choice|fallback",
    "localization_required": true,
    "source_language_policy": "sources-may-be-original-language",
    "quote_policy": "preserve-source-quotes-with-local-explanation",
    "code_identifier_policy": "preserve-code-identifiers"
  }
}
```

### 4.3 gate 最低要求

- `questionnaire.topic` 非空
- `questionnaire.goal` 非空
- `questionnaire.success_criteria` 非空
- `questionnaire.current_level_self_report` 非空，或 `consultation_state.topics[current_level]` 明确 deferred 到 diagnostic
- `questionnaire.time_constraints.frequency` 或 `session_length` 至少一项非空，或有明确 routine/deadline 约束
- `questionnaire.mastery_preferences.max_assessment_rounds_preference >= 1`
- `questionnaire.mastery_preferences.questions_per_round_preference >= 1`
- `consultation_state` 存在并包含 `current_topic_id`、`topics`、`topic_order`
- required topics 必须是 `resolved` 或合规 `deferred`，否则必须保留当前主题的 follow-up question
- 若存在 `preference_state`，则 `preference_state.pending_items` 在归一化后应为空，或只剩非阻塞/后置项
- `preference_state` 本身可为空；此时 runtime 从 `user_model` / `planning_state.preference_status` 回填兼容视图
- `clarification_state.open_questions` 为空或只剩非阻塞项

兼容口径：
- gate / reviewer 最终认定的 canonical 字段是：
  - `questionnaire.success_criteria`
  - `questionnaire.time_constraints`
  - `questionnaire.mastery_preferences.max_assessment_rounds_preference`
  - `questionnaire.mastery_preferences.questions_per_round_preference`
  - `clarification_state.open_questions`
  - `preference_state.pending_items`
- 兼容输入字段可以被归一化回上述 canonical 视图，包括但不限于：
  - `clarification_state.success_criteria.confirmed`
  - `schedule.time_constraints_confirmed`
  - `clarification_state.constraints_confirmed`
  - `user_model.constraints`
- `clarification_state.open_questions` 允许保存 deferred / non-blocking 项，但 gate 只消费 blocking 子集；明确 deferred_to_diagnostic 或已 resolved 的问题不应继续阻塞 clarification。
- `preference_state.pending_items` 也允许暂存偏好细化项；当 `preference_state.status` 已是 `confirmed` 或 `partially_confirmed` 时，只有真正阻塞当前阶段的问题才应继续保留在 blocking 子集里。

补充说明：
- `/learn-plan` 必须在 clarification 阶段显式确认“最多接受几轮起始测评、每轮最多接受多少题”。
- 默认先按“每轮总题数”理解；只有用户主动在意题型比例时，再额外记录 `question_mix_preference`。
- 若上述预算仍未确认，workflow 必须继续停留在 clarification，不得默认进入任意诊断预算或轮次结构。

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
    "report_type": "capability-level-report",
    "goal_level_definition": "",
    "required_level_definition": "",
    "goal_target_band": "",
    "must_master_core": [],
    "evidence_expectations": [],
    "research_brief": "",
    "user_facing_report": {
      "format": "html",
      "language": "zh-CN|en",
      "title": "",
      "summary": [],
      "html": "",
      "sections": []
    },
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
    "open_risks": [],
    "diagnostic_scope": {
      "target_goal_band": "",
      "target_capability_ids": [],
      "target_capabilities": [],
      "scope_rationale": [],
      "evidence_expectations": [],
      "scoring_dimensions": [],
      "gap_judgement_basis": [],
      "non_priority_items": []
    }
  },
  "language_policy": {
    "user_facing_language": "zh-CN|en|auto",
    "detected_from": "current-conversation|explicit-user-choice|fallback",
    "localization_required": true,
    "source_language_policy": "sources-may-be-original-language",
    "quote_policy": "preserve-source-quotes-with-local-explanation",
    "code_identifier_policy": "preserve-code-identifiers"
  }
}
```

### 5.3 gate 最低要求

- 若需要 research：`research_plan.status` 必须为 `approved` 或 `completed`
- `research_report.report_status = completed`
- `research_brief` 非空
- `goal_target_band` 非空
- `required_level_definition` 非空
- `must_master_core` 非空
- `evidence_expectations` 非空
- `user_facing_report.format = html`
- `user_facing_report.html` 非空，或结构化字段完整到可由 deterministic renderer 生成 HTML
- `user_facing_report.summary` 非空，且内容是能力要求与达标水平报告摘要，不是学习路线安排
- `diagnostic_scope.target_capability_ids` 非空
- `diagnostic_scope.scoring_dimensions` 非空
- `diagnostic_scope.gap_judgement_basis` 非空
- `capability_metrics` 非空
- 每个主线能力项至少有：
  - `observable_behaviors`
  - `quantitative_indicators`
  - `diagnostic_methods`
  - `learning_evidence`
  - `source_evidence`
- 有 `source_evidence` 或 `evidence_summary`
- `language_policy.user_facing_language` 非空；用户可见报告语言必须遵守该策略，代码标识符、命令、路径和原文引用可保留原语言

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
    "round_index": 1,
    "max_rounds": 1,
    "questions_per_round": 5,
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
    "round_index": 1,
    "max_rounds": 1,
    "questions_per_round": 5,
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
- `diagnostic_plan.round_index >= 1`
- `diagnostic_plan.max_rounds >= diagnostic_plan.round_index`
- `diagnostic_plan.questions_per_round >= 1`
- `diagnostic_plan.delivery = web-session`
- 新链路以 `round_index / max_rounds / questions_per_round / follow_up_needed / stop_reason` 为唯一诊断预算与推进字段，不再要求 `assessment_depth`
- `diagnostic_plan.assessment_kind = initial-test`，历史 `plan-diagnostic` 仍应兼容读取
- `diagnostic_plan.session_intent = assessment`，历史 `plan-diagnostic` 仍应兼容读取
- `diagnostic_result.status = evaluated`
- `capability_assessment` 非空
- `recommended_entry_level` 非空
- `confidence` 非空
- 应显式写出 `follow_up_needed` 与 `stop_reason`

补充说明：
- diagnostic 题目应通过网页 session 四件套交付，用户先作答，再由 `/learn-plan` 诊断语义消费结果。
- 新生成的起始测试应写为 `assessment_kind = initial-test`、`session_intent = assessment`，并保留 `plan_execution_mode = diagnostic`；历史 `plan-diagnostic` 只读兼容。
- `questions_per_round` 默认表示“每轮总题数”，不是分题型配额；只有用户明确提出题型比例偏好时，才进一步细化。
- 不得把前置起点诊断改写成普通 `stage-test` 结论；虽然回写统一走内部 `learn_test_update.py` 流程，但输出语义仍应是“起步层级判断”，不是阶段通过/回退。

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
    "approved_patch_ids": [],
    "rejected_patch_ids": [],
    "pending_decisions": [],
    "requested_changes": [],
    "accepted_tradeoffs": [],
    "confirmed_material_strategy": false,
    "confirmed_daily_execution_style": false,
    "confirmed_mastery_checks": false,
    "risk_acknowledgements": []
  },
  "material_curation": {
    "schema_version": "learn-plan.material-curation.v1",
    "status": "draft|needs-user-confirmation|confirmed",
    "learner_fit_summary": {
      "entry_level": "",
      "observed_weaknesses": [],
      "goal_requirements": [],
      "constraints": [],
      "preferences": []
    },
    "strategy_summary": {
      "mainline_strategy": "",
      "supporting_strategy": "",
      "download_strategy": "",
      "rejected_strategy": ""
    },
    "materials": [
      {
        "id": "",
        "title": "",
        "role": "mainline|required-support|optional-candidate|rejected",
        "selection_status": "confirmed|candidate|rejected",
        "availability": "cached|downloadable|local-downloadable|metadata-only|download-failed|validation-failed|requires-user-upload",
        "cache_status": "cached|not-cached|download-failed|validation-failed|metadata-only",
        "curation_reason": "",
        "risks": [],
        "download": {
          "should_download": false,
          "validation_status": "valid|invalid|skipped|unknown"
        },
        "excerpt_briefs": []
      }
    ],
    "open_risks": [],
    "user_confirmation": {
      "required": true,
      "confirmed": false,
      "pending_questions": [],
      "requested_changes": [],
      "confirmed_by_user_text": ""
    }
  }
}
```

补充说明：
- `approved_patch_ids` / `rejected_patch_ids` 用于把 approval 阶段对 `curriculum_patch_queue.json` 中 patch 的决策显式写回 workflow。
- `approved_patch_ids` 对应的 patch 在 finalize 成功写正式计划后转为 `applied`；`rejected_patch_ids` 对应 patch 进入终态，不再阻塞 gate。

### 7.3 gate 最低要求

- `approval_status = approved`
- `ready_for_execution = true`
- `pending_decisions` 为空
- `confirmed_material_strategy = true`
- `material_curation.status = confirmed`
- `material_curation.user_confirmation.confirmed = true`
- 至少存在一个 `role = mainline` 且 `selection_status = confirmed` 的资料，或明确记录无主线资料的风险并由用户确认
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
  "prompted_mastery_scope": [],
  "preferences": {},
  "preference_candidates": {},
  "learning_behaviors": [],
  "last_updated": ""
}
```

### 8.3 使用边界

- 根对象与 `evidence_log` 条目都应保留统一质量 envelope；根对象表达“当前 learner model 状态”，条目表达“单次 session 证据”。
- 可被 `/learn-today`、`/learn-test`、update 脚本消费。
- 不应直接替代 `learn-plan.md` 中的长期路线图。
- 只能表达“当前估计”和“证据”；正式阶段切换仍以计划与 approval 为准。
- `mastered_scope` 必须 evidence-gated：只有 completion signal 已收到、`reflection.json` 完成、`mastery_judgement.status=mastered` 且 prompting level 为 none/unprompted/unknown 时才可加入。
- `solid_after_intervention` 必须进入 `prompted_mastery_scope` 或 learning behaviors，并保留 spaced review 信号；`partial` / `fragile` / `blocked` 不得加入 `mastered_scope`。
- 单次用户反馈先进入 `preference_candidates`；多次稳定反馈或用户明确“以后都这样”才进入稳定 `preferences`。

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
      "patch_type": "review-adjustment|advance-proposal|entry-level-adjustment|next-session-reinforcement|reinforcement-proposal|pre-session-review-adjustment|difficulty-adjustment|teaching-style-adjustment|stage-restructure-proposal|goal-scope-adjustment|material-strategy-review",
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
- 单次卡点优先进入 `review_debt` 或 `next-session-reinforcement`；连续同类 evidence 或影响阶段目标时才生成结构性 patch。
- 缺少 interaction/reflection/pre-session review evidence 的结构性 patch 应降级为 `pending-evidence`。

---

## 10. materials/index.json

### 10.1 作用

保存材料索引、角色划分、segment 信息与缓存状态。它既服务 planning，也服务 runtime grounding。当前实现以 `entries` 为 canonical 根数组，同时兼容读取 legacy `items` / `materials`。

### 10.2 关键字段

```json
{
  "topic": "",
  "family": "linux|llm-app|backend|frontend|database|algorithm|math|english|general-cs",
  "generated_at": "",
  "entries": [
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

- `entries` 是当前 canonical 根数组；legacy `items` / `materials` 只读兼容
- 允许逐步增强 `segments`、`source_key_points` 等字段
- 下载器只允许维护缓存相关字段，不得改写 planner 语义字段
- 下载器必须继续维护：
  - `cache_status`
  - `local_path`
  - `cached_at`
  - `last_attempt`
- `cache_note`、`exists_locally`、`local_artifact`、`downloaded_at` 仅作 legacy 只读兼容，不再作为 canonical 缓存字段

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
11. `当前教学/练习微调`（可选，低风险 feedback 的当前生效策略）
12. `学习记录`
13. `测试记录`

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
- 对应 `lesson_focus_points`
- 对应 `project_tasks` / `project_blockers`
- 对应 `review_targets`

当前 runtime 还会写入 `question_quality`，至少覆盖：
- `valid`
- `issues`
- `warnings`
- `fallback_count`
- `source_markers`

`questions.json` 的 bootstrap hard requirement 除上述最低结构外，还要求顶层显式保留：
- `session_intent`
- `assessment_kind`

Today session 还应允许扩展以下 advisory 字段；它们不阻断 `questions.json` 生成，但 runtime/update 已消费：
- `plan_source.today_teaching_brief`
- `plan_source.lesson_review`
- `plan_source.question_review`
- `plan_source.lesson_focus_points`
- `plan_source.project_tasks`
- `plan_source.project_blockers`
- `plan_source.review_targets`

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
  "pre_session_review": {
    "status": "not_started|completed|skipped",
    "reviewed_items": [],
    "questions": [],
    "user_answers": [],
    "result": "unknown|passed|not_passed|partial",
    "passed": null,
    "weak_points": [],
    "agent_assessment": null,
    "user_decision": null,
    "next_step": null,
    "evidence": []
  },
  "interaction_evidence": [],
  "user_feedback": {
    "difficulty": null,
    "teaching_style": null,
    "pace": null,
    "question_design": null,
    "material_fit": null,
    "comments": [],
    "scope": "session"
  },
  "mastery_judgement": {
    "status": "unknown|mastered|solid_after_intervention|partial|fragile|blocked|not_observed",
    "confidence": 0.0,
    "evidence": [],
    "blocking_gaps": [],
    "next_session_reinforcement": [],
    "prompting_level": "unknown|none|unprompted|hinted|guided|heavy",
    "mastery_level": "not_observed|recognition|explanation|application|transfer|diagnosis"
  },
  "completion_signal": {
    "status": "not_received|received|completed|skipped_by_user",
    "source": null,
    "received_at": null,
    "user_message_summary": null
  },
  "questions": {}
}
```

`progress.json` 的 bootstrap hard requirement 至少包括：
- `session.type`
- `session.intent`
- `session.assessment_kind`
- `session.plan_execution_mode`
- `session.test_mode`
- `session.status`
- `session.started_at`
- `session.finished_at`
- `session.plan_path`
- `summary.total`
- `summary.attempted`
- `summary.correct`
- `pre_session_review.status`
- `interaction_evidence`
- `user_feedback.scope`
- `mastery_judgement.status`
- `completion_signal.status`

### 13.3 question 级要求

每个 `questions.<id>` 至少包含：
- `stats`
- `history`

代码题历史保留代码与运行结果；概念题历史只保留正确/错误与时间，不默认回填历史答案到页面。

Today session 的 `context` 应允许扩展以下字段：
- `today_teaching_brief`
- `lesson_review`
- `question_review`
- `lesson_focus_points`
- `project_tasks`
- `project_blockers`
- `review_targets`
- `lesson_path`
- `lesson_html_path`
- `lesson_artifact_path`
- `legacy_daily_plan_artifact_path`

其中：
- `lesson_path` 与 `lesson_html_path` 应指向 session 目录内的 canonical `lesson.html`；`legacy_daily_plan_artifact_path` 仅用于兼容旧调试产物，不得作为正式课件真相源。
- `lesson_review` / `question_review` 为 advisory reviewer 输出，只提供问题列表与建议，不替代 hard gate。

---

## 14. interaction_events.jsonl

每行是一条结构化学习事件。最低结构：

```json
{
  "timestamp": "",
  "session_type": "today|test",
  "phase": "pre_session_review|during_learning|post_completion_reflection",
  "source": "main_agent_interaction",
  "related_material": {},
  "knowledge_points": [],
  "user_event": {
    "type": "question|misconception_observed|instruction_intervention|self_explanation|feedback|completion_signal",
    "summary": "",
    "raw_excerpt": ""
  },
  "diagnostic_signal": {},
  "agent_response_summary": "",
  "follow_up_result": {},
  "recommended_action": ""
}
```

最低校验：必须有 `source`、`phase`、`user_event.summary`，并至少包含 `diagnostic_signal` 或 `follow_up_result`。只保存摘要和必要短摘录，不保存完整聊天 transcript。

---

## 15. reflection.json

`reflection.json` 是用户明确完成学习/测试后的 update 前复盘 artifact。最低结构：

```json
{
  "status": "completed|skipped_by_user|pending",
  "trigger": {
    "type": "user_completion_signal",
    "user_message_summary": "",
    "received_at": ""
  },
  "session_type": "today|test",
  "rounds": [],
  "mastery_judgement": {},
  "learning_path_evidence": [],
  "review_debt": [],
  "user_feedback": {},
  "next_actions": []
}
```

最低校验：必须有 `status`、`trigger`、`rounds`、`mastery_judgement`。today reflection 是教学性复盘，可提示和纠偏；test reflection 是评估性复盘，提示要少，提示后掌握不等同无提示 mastered。

---

## 16. session_facts.json

`.learn-workflow/session_facts.json` 保存最近一次 update 的事实快照，至少包含：

```json
{
  "update_type": "today|test|diagnostic",
  "date": "",
  "topic": "",
  "session_dir": "",
  "evidence": [],
  "pre_session_review_facts": {},
  "completion_signal_facts": {},
  "interaction_event_facts": [],
  "interaction_facts": [],
  "reflection_facts": {},
  "user_feedback_facts": {},
  "mastery_judgement_facts": {}
}
```

它只做事实聚合，不直接生成课程建议；learner model 和 patch proposal 消费它后再更新反馈状态。

---

## 17. 契约验收顺序

后续实现与重构时，按以下顺序验收：

1. workflow JSON 是否能被正常读写
2. `workflow_state.json` 是否正确给出 route summary
3. `learn-plan.md` 是否仍能被 `/learn-today` 消费
4. `questions.json` / `progress.json` 是否仍能驱动现有 runtime
5. `interaction_events.jsonl` / `reflection.json` 是否只增量增强，不破坏现有前端 runtime
6. `session_facts.json` / `learner_model.json` / `curriculum_patch_queue.json` 是否只增量增强，不破坏旧链路

---

## 18. 一句话原则

**中间态要结构化，正式态要稳定，执行态要可追踪，反馈态要可演进。**
