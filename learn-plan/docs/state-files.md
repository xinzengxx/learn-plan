# learn-plan skill 簇状态文件所有权

本文档定义整个 `/learn-plan` skill 簇中各状态文件的职责、所有者、读写边界与迁移规则。

相关文档：
- 架构总览：`../WORKFLOW_DESIGN.md`
- 数据契约：`./contracts.md`
- runtime 兼容边界：`./runtime-compatibility.md`

---

## 1. 状态分层总览

目标学习根目录 `<root>/` 下建议形成以下结构：

```text
<root>/
├── learn-plan.md
├── learn-today-YYYY-MM-DD.md
├── materials/
│   └── index.json
├── sessions/
│   ├── YYYY-MM-DD/
│   │   ├── questions.json
│   │   ├── progress.json
│   │   ├── 题集.html
│   │   └── server.py
│   └── YYYY-MM-DD-test/
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

## 2. 状态文件职责表

| 文件 | 类型 | 主要写入者 | 主要读取者 | 允许用户直接编辑 | 职责 |
| --- | --- | --- | --- | --- | --- |
| `learn-plan.md` | 正式长期状态 | `/learn-plan finalize`、已批准 patch | `/learn-today`、`/learn-test`、update | 可以 | 用户可读长期 curriculum 主文档 |
| `materials/index.json` | 材料状态 | planning/materials/downloader | runtime/materials/downloader | 谨慎 | 材料索引、角色、segment、缓存状态 |
| `sessions/*/questions.json` | session 输入 | runtime | 前端/server/update | 不建议 | 题目、上下文、材料引用 |
| `sessions/*/progress.json` | session 事实 | 前端/server/bootstrap/update | update/runtime | 不建议 | 答题历史、统计、session 状态 |
| `.learn-workflow/clarification.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | 用户画像、目标、偏好、约束 |
| `.learn-workflow/research.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | research plan、能力要求、材料取舍依据 |
| `.learn-workflow/diagnostic.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | 诊断题、答案、评估、起点判断 |
| `.learn-workflow/approval.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine | 不建议 | 计划草案确认、tradeoff、风险接受 |
| `.learn-workflow/workflow_state.json` | 路由摘要 | workflow engine | skill prompt/CLI | 不建议 | 当前 blocking stage 与 next action |
| `.learn-workflow/learner_model.json` | 反馈状态 | update/feedback | runtime/update | 不建议 | 能力估计、证据、复习债 |
| `.learn-workflow/curriculum_patch_queue.json` | patch 队列 | update/feedback | `/learn-plan` approval/finalize | 不建议 | 待批准的长期计划调整建议 |

---

## 3. 正式长期状态

## 3.1 learn-plan.md

### 职责

`learn-plan.md` 是系统中最重要的正式长期状态源。它必须同时满足：
- 用户可读
- 可由 `/learn-today` 拆成当日计划
- 可被 update 脚本追加学习/测试记录

### 写入规则

允许写入主体结构的场景：
1. `/learn-plan` 的 `finalize` 阶段通过所有 gate。
2. `curriculum_patch_queue.json` 中 patch 已经过用户确认，并进入 approved/applied 流程。

不允许写入主体结构的场景：
- 仍处于 clarification/research/diagnostic 中间阶段
- 只是生成了计划草案
- 只是 update 发现薄弱项但尚未获得计划调整确认

update 脚本可以追加：
- `学习记录`
- `测试记录`
- 简短后续建议

但不应在未批准时重写长期阶段路线。

### 必须保留的 section

- `学习画像`
- `规划假设与约束`
- `能力指标与起点判断`
- `检索结论与取舍`
- `阶段总览`
- `阶段路线图`
- `资料清单与阅读定位`
- `掌握度检验设计`
- `今日生成规则`
- `每日推进表`
- `学习记录`
- `测试记录`

## 3.2 materials/index.json

### 职责

`materials/index.json` 是材料层正式状态，负责：
- 记录材料条目
- 标注 mainline/supporting/optional/candidate 角色
- 记录章节/页码/segment 定位
- 记录下载缓存状态
- 为 runtime grounding 提供 source hints

### 写入规则

允许写入者：
- planning/materials planner：生成与更新材料策略
- downloader：只更新下载与缓存相关字段（`cache_status`、`local_path`、`cached_at`、`last_attempt`、`download_validation`）；`cache_note`、`exists_locally`、`local_artifact` 仅 legacy 只读兼容
- preprocessing：只更新 source excerpt、segment cache、预处理状态字段

不允许：
- runtime 为了临时 session 随意重排主线材料
- downloader 改写 `availability`、`selection_status`、`role_in_plan`、`goal_alignment`、`reading_segments`、`mastery_checks` 等 planner 字段
- update 未经批准直接删除主线资料

---

## 4. workflow 中间态

## 4.1 共同原则

workflow 中间态保存在：

```text
<root>/.learn-workflow/
```

共同原则：
- 用于中断恢复与 gate 校验
- 不直接展示为正式学习计划
- 可以被脚本反复读取、校验、补齐
- 缺字段时应阻塞到相应阶段，而不是尝试猜测
- `clarification.json` / `research.json` / `diagnostic.json` / `approval.json` 是事实载体，`workflow_state.json` 只是 route summary，不反向充当事实源
- `learn_plan.py` 负责 merge / route，`learn_workflow/state_machine.py` 负责 gate 缺口判定，`learn_workflow/stage_review.py` 负责阶段质量审查

## 4.2 clarification.json

写入时机：
- 用户完成或部分完成顾问式澄清后
- 用户修改目标、约束、偏好后

拥有信息：
- topic
- goal
- success criteria
- self-reported level
- schedule/time constraints
- learning preferences
- mastery preferences
- existing materials
- non-goals
- assumptions/open questions

阻塞条件：
- 目标不清
- 成功标准不清
- 当前水平没有任何描述
- 时间/频率完全缺失
- 学习偏好仍有阻塞项

## 4.3 research.json

写入时机：
- research plan 生成后
- 用户批准 research plan 后
- research 完成并形成能力报告后

拥有信息：
- research plan
- source types
- capability metrics
- source evidence
- material selection rationale
- open risks

阻塞条件：
- 职业/岗位/复杂技术目标需要 research，但 research plan 未确认
- 没有 capability metrics
- 没有把目标水平转成可观察行为与诊断方式

## 4.4 diagnostic.json

写入时机：
- 诊断题组生成后
- 用户回答后
- 批改与起点评估后

拥有信息：
- diagnostic items
- expected signals
- rubric
- answers summary
- capability assessment
- recommended entry level
- plan adjustments

阻塞条件：
- 未答题就下结论
- 只有总分，没有能力维度判断
- 没有推荐起点或置信度

## 4.5 approval.json

写入时机：
- 计划草案生成后
- 用户提出修改意见后
- 用户明确批准草案和关键 tradeoff 后

拥有信息：
- approval status
- pending decisions
- accepted tradeoffs
- material strategy confirmation
- material curation：主线/辅助/候选/拒绝资料、片段范围、下载验证状态、open risks 与用户确认痕迹
- daily execution style confirmation
- mastery check confirmation
- risk acknowledgements

阻塞条件：
- 关键决策未确认
- 资料策略未确认
- material_curation 缺失、未确认、无主线资料且未说明风险，或主线资料全部下载/验证失败且没有替代策略
- 掌握标准未确认
- 用户只给模糊认可但仍有核心分歧

## 4.6 workflow_state.json

写入时机：
- 每次 workflow engine route/gate 运行后

职责：
- 保存最新 `blocking_stage`
- 保存 `recommended_mode`
- 保存 `next_action`
- 保存缺项和质量问题

注意：
- 它是 route summary，不是事实来源。
- 如果它与四类中间态 JSON 冲突，应重新计算，以四类中间态为准。

---

## 5. session 状态

## 5.1 questions.json

职责：
- 保存一次 session 的题目与上下文。
- 支持前端、server、update 重放与审计。

写入者：
- `session_orchestrator.py`
- `learn_runtime/payload_builder.py`（由 `session_orchestrator.py` facade 调用）

不应承担：
- 长期计划状态
- workflow gate 状态
- 跨 session learner model

## 5.2 progress.json

职责：
- 保存 session 事实记录。
- 包括答题历史、正确率、开始/结束状态、材料与计划来源。

写入者：
- `session_bootstrap.py`
- 前端/server
- update 脚本在汇总时可补充结构化状态

不应承担：
- workflow 中间态
- 长期课程路线
- 已批准计划调整

---

## 6. feedback 状态

## 6.1 learner_model.json

职责：
- 汇总跨 session 的能力证据。
- 保存当前能力估计、置信度、弱信号、复习债、下一步建议。

边界：
- 它可以影响 `/learn-today` 的选题和复习优先级。
- 它不能单独决定长期阶段路线改写。

## 6.2 curriculum_patch_queue.json

职责：
- 保存 update 层提出的计划调整建议。
- 支持后续由 `/learn-plan` 或用户确认后正式落地。

patch 状态：
- `pending-evidence`：证据或置信度不足，暂不能进入正式审批
- `proposed`：证据齐备，等待用户确认
- `approved`：用户确认可改
- `rejected`：用户拒绝
- `applied`：已写入正式计划

当前 update 写入的 patch 必须保持 `application_policy = pending-user-approval`，并附带 `quality_review`。

---

## 7. 读写数据流

## 7.1 `/learn-plan`

```text
用户输入
-> clarification/research/diagnostic/approval JSON
-> workflow engine gate
-> planning system
-> finalize
-> learn-plan.md + materials/index.json
```

只有 `finalize` 通过 gate 后才写正式主产物。

## 7.2 `/learn-today` / `/learn-test`

```text
learn-plan.md
+ materials/index.json
+ learner_model.json
+ recent sessions/*/progress.json
+ 用户 check-in
-> session plan
-> learn-today-YYYY-MM-DD.md（today 主路径）
-> questions.json
-> progress.json
-> 题集.html + server.py
```

运行时只能基于正式计划和反馈状态生成 session，不应修改 workflow 中间态。

## 7.3 复盘回写脚本

```text
questions.json + progress.json
-> facts summary
-> learner_model.json update
-> curriculum_patch_queue.json proposed patch
-> learn-plan.md 学习记录/测试记录追加
```

主体计划结构只有在 patch 被确认后才修改。

补充说明：若 session 属于 `/learn-plan` diagnostic gate 触发的起始测试，新链路应优先由内部 `learn_test_update.py` 回写流程消费；`learn_today_update.py` 仅保留 today 主路径与 legacy `plan-diagnostic` 兼容。

## 7.4 `/learn-download-materials`

```text
materials/index.json
-> downloader
-> local files
-> cache_status/local_path/cached_at 回写
```

下载器只维护材料缓存字段，不修改 curriculum 逻辑。

---

## 8. 迁移规则

### 8.1 从现有系统迁移

现有系统已经有：
- `learn-plan.md`
- `materials/index.json`
- `sessions/*/progress.json`

迁移时不要强制一次性生成所有 `.learn-workflow/*.json`。

推荐顺序：
1. 先读取现有正式状态。
2. 若缺 `.learn-workflow/`，在下一次 `/learn-plan` 或 update 时惰性创建。
3. `learner_model.json` 可由历史 `progress.json` 回填，也可从下一次 session 开始累积。
4. `curriculum_patch_queue.json` 初始为空队列即可。

### 8.2 兼容旧 plan

若旧 `learn-plan.md` 缺少 `能力指标与起点判断`：
- `/learn-today` 不应失败。
- `/learn-plan finalize` 或下一次计划修订时补齐。

若旧 `materials/index.json` 缺少 `segments`：
- runtime 回退到材料条目级定位。
- preprocessing 后再补 segment。

---

## 9. 不变量

1. `learn-plan.md` 是正式长期 curriculum 主文档。
2. `.learn-workflow/*.json` 是中间态，不替代正式计划。
3. `progress.json` 是 session 事实，不替代 learner model。
4. `learner_model.json` 是能力证据，不替代 curriculum。
5. `curriculum_patch_queue.json` 中的 proposed patch 未确认前不能改正式路线。
6. `materials/index.json` 的下载字段只能由下载/预处理层维护。

---

## 10. 一句话原则

**让每个状态文件只承担一个层级的责任：规划中间态、正式计划、执行事实、学习者模型、计划调整建议必须分开。**
