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
├── knowledge-map.md
├── knowledge-state.json
├── reports/
│   ├── purpose-analysis.html
│   └── plan-draft.html
├── materials/
│   └── index.json
├── sessions/
│   ├── YYYY-MM-DD/
│   │   ├── lesson.html
│   │   ├── questions.json
│   │   ├── progress.json
│   │   ├── interaction_events.jsonl
│   │   ├── reflection.json
│   │   ├── 题集.html
│   │   └── server.py
│   └── YYYY-MM-DD-test/
│       ├── questions.json
│       ├── progress.json
│       ├── interaction_events.jsonl
│       ├── reflection.json
│       ├── 题集.html
│       └── server.py
└── .learn-workflow/
    ├── clarification.json
    ├── research.json
    ├── diagnostic.json
    ├── approval.json
    ├── workflow_state.json
    ├── session_facts.json
    ├── learner_model.json
    └── curriculum_patch_queue.json
```

---

## 2. 状态文件职责表

| 文件 | 类型 | 主要写入者 | 主要读取者 | 允许用户直接编辑 | 职责 |
| --- | --- | --- | --- | --- | --- |
| `learn-plan.md` | 正式长期状态 | `/learn-plan finalize`、已批准 patch | `/learn-today`、`/learn-test`、update | 可以 | 用户可读长期 curriculum 主文档 |
| `knowledge-map.md` | 知识图谱视图 | `/learn-plan finalize`、已批准 graph diff | 用户、`/learn-plan`、`/learn-today`、`/learn-test` | 可以提出意见，不直接改 mastery | 用户可读的 2–3 层知识图谱、关键依赖、coverage 和 DAG 校验摘要 |
| `knowledge-state.json` | 知识点状态 | `/learn-plan finalize`、`/learn-today` update、`/learn-test` update、已批准 graph diff | `/learn-today`、`/learn-test`、update | 不建议；禁止手动改 mastery | 底层知识点 mastery、confidence、target、required evidence、evidence log 与 history 权威源 |
| `materials/index.json` | 材料状态 | planning/materials/downloader | runtime/materials/downloader | 谨慎 | 材料索引、角色、segment、缓存状态 |
| `reports/purpose-analysis.html` | 用户可见报告 | `/learn-plan` Phase 1 | 用户、`/learn-plan` | 可作为阅读产物，不作为机器状态编辑 | 目的分析、资料评估与 open risks 的 canonical HTML |
| `reports/plan-draft.html` | 用户可见报告 | `/learn-plan` Phase 3 | 用户、`/learn-plan` | 可作为阅读产物，不作为机器状态编辑 | 计划草案与 tradeoff 的 canonical HTML |
| `sessions/*/questions.json` | session 输入 | runtime | 前端/server/update | 不建议 | 题目、上下文、材料引用 |
| `sessions/*/progress.json` | session 事实 | 前端/server/bootstrap/update/evidence CLI | update/runtime | 不建议 | 答题历史、统计、课前复习、完成信号、复盘摘要、掌握判断 |
| `sessions/*/interaction_events.jsonl` | session 证据日志 | 主 agent / evidence CLI | update/feedback | 不建议 | 终端学习交互、提问、误解、反馈、纠偏与自我总结摘要 |
| `sessions/*/reflection.json` | session 复盘产物 | 主 agent / evidence CLI | update/feedback | 不建议 | 用户明确完成后的 update 前多轮复盘与 mastery judgement |
| `.learn-workflow/clarification.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | 用户画像、目标、偏好、约束 |
| `.learn-workflow/research.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | research plan、能力要求、材料取舍依据 |
| `.learn-workflow/diagnostic.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine/planning | 不建议 | 诊断题、答案、评估、起点判断 |
| `.learn-workflow/approval.json` | workflow 中间态 | `/learn-plan` orchestrator | workflow engine | 不建议 | 计划草案确认、tradeoff、风险接受 |
| `.learn-workflow/workflow_state.json` | 派生路由摘要 | workflow engine | skill prompt/CLI | 不建议 | 当前 blocking stage 与 next action；可重建缓存，不保存用户可见 HTML 或权威 planning artifact |
| `.learn-workflow/session_facts.json` | 反馈事实快照 | update/feedback | learner_model/patch queue/debug | 不建议 | 最近一次 session 的 performance、interaction、reflection、feedback 事实汇总 |
| `.learn-workflow/learner_model.json` | 反馈状态 | update/feedback | runtime/update | 不建议 | 能力估计、证据、复习债、偏好候选与提示后掌握状态 |
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
- `当前教学/练习微调`：题目难度、题型比例、讲解方式、节奏、例子风格、反馈方式等低风险微调

但不应在未批准时重写长期阶段路线。阶段顺序、目标、材料、时间预算、学习频率等结构性变化必须进入 `curriculum_patch_queue.json` 并等待用户确认。

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
- `当前教学/练习微调`（可选，低风险 session feedback 的当前生效策略）
- `学习记录`
- `测试记录`

## 3.2 knowledge-map.md 与 knowledge-state.json

### 职责

`knowledge-map.md` 与 `knowledge-state.json` 与 `learn-plan.md` 同目录，是正式长期知识状态层：

- `knowledge-map.md` 面向用户审阅，展示 2–3 层知识图谱、核心叶子粒度、关键依赖、coverage report、DAG 校验和 initial diagnostic blueprint。
- `knowledge-state.json` 面向 skill 精确读写，保存节点、边、底层知识点 mastery / confidence / target mastery / required evidence、evidence log 与 history。

### 写入规则

允许写入主体图谱的场景：
1. `/learn-plan finalize` 首次生成正式计划时同步生成初始知识图谱，状态为 `draft`。
2. 用户确认图谱后，状态可进入 `confirmed` / `active`。
3. 用户提出图谱缺漏、依赖错误或粒度问题时，skill 先生成 graph diff，经用户确认后归一化写入。
4. `/learn-today` 与 `/learn-test` 只能按 session evidence 更新底层知识点状态，不得静默重写图谱结构。

不允许：
- 用户直接覆盖 `mastery`。
- 上层 domain/topic 节点维护真实 `mastery`；只能展示由底层节点汇总出的 `derived_mastery`。
- update 脚本未经用户确认改阶段路线、材料主线或图谱结构。

### 迁移与 commit 边界

目标变更时，不支持多个并行目标；旧目标进入 `history`，保留已有底层 mastery 与 evidence，再重算新目标下的 relevance、target_mastery 与 required evidence。若学习根目录是 git repo，学习/测试 session 更新应按 session 原子提交相关状态变化；非 git 目录不报错，降级为 `evidence_log` 与 `history` 记录。

## 3.3 materials/index.json

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
- 保存 agent workflow 写入的课前复习、完成信号、交互摘要、用户反馈、复盘摘要与掌握判断。

写入者：
- `session_bootstrap.py`
- 前端/server
- `learn_session_evidence_update.py`：写入 `pre_session_review`、`completion_signal`、`interaction_evidence`、`user_feedback`、`reflection`、`mastery_judgement`
- update 脚本在汇总时可补充结构化状态

不应承担：
- workflow 中间态
- 长期课程路线
- 已批准计划调整

## 5.3 interaction_events.jsonl

职责：
- 追加式记录用户在终端与主 agent 的学习交互摘要。
- 记录用户提问、误解暴露、agent 纠偏、用户自我总结、难度/讲法/节奏反馈和 completion signal 相关事件。
- 只保存结构化摘要与必要短摘录，不保存完整聊天 transcript。

写入者：
- 主 agent 通过 `learn_session_evidence_update.py` 写入。

不应承担：
- 最终 mastery 判定；它提供 evidence，最终判断在 `reflection.json` / `mastery_judgement`。
- 长期偏好直接落盘；单次反馈先进入 session evidence。

## 5.4 reflection.json

职责：
- 保存用户明确完成学习/测试后的 update 前复盘产物。
- 记录多轮复盘问题、用户回答摘要、提示程度、agent 反馈、最终 `mastery_judgement`、learning path evidence、review debt 和 user feedback。

写入者：
- 主 agent 通过 `learn_session_evidence_update.py` 写入。

边界：
- `/learn-today` reflection 是教学性复盘，可提示和纠偏；`solid_after_intervention` 可推进但保留复习债。
- `/learn-test` reflection 是评估性复盘，提示要少；提示后掌握不等同无提示 mastered。
- 没有 completion signal 时不应生成最终 reflection；用户明确跳过时记录 skipped。

---

## 6. feedback 状态

## 6.1 learner_model.json

职责：
- 汇总跨 session 的能力证据。
- 保存当前能力估计、置信度、弱信号、复习债、下一步建议。
- 区分无提示 mastered 与提示后掌握；`solid_after_intervention` 进入提示后掌握/复习债，不直接进入 mastered scope。
- 保存偏好候选与稳定学习行为信号，例如迁移薄弱、课前复习不稳、需要提示后才能掌握。

边界：
- 它可以影响 `/learn-today` 的选题和复习优先级。
- 它不能单独决定长期阶段路线改写。

## 6.2 session_facts.json

职责：
- 保存最近一次 update 聚合出的事实快照。
- 汇总三层证据：performance evidence（答题表现）、interaction evidence（学习中提问/误解/反馈/纠偏）、reflection evidence（完成后的复盘追问与掌握判断）。
- 为 learner model 与 patch proposal 提供同一份可追踪输入。

边界：
- 它是事实汇总，不直接生成课程建议。
- 它可被下一次 update 覆盖；长期历史应进入 `learner_model.evidence_log` 或 session 文件本身。

## 6.3 curriculum_patch_queue.json

职责：
- 保存 update 层提出的计划调整建议。
- 支持后续由 `/learn-plan` 或用户确认后正式落地。

patch 状态：
- `pending-evidence`：证据或置信度不足，暂不能进入正式审批
- `proposed`：证据齐备，等待用户确认
- `approved`：用户确认可改
- `rejected`：用户拒绝
- `applied`：已写入正式计划

当前 update 写入的 patch 必须保持 `application_policy = pending-user-approval`，并附带 `quality_review`。单次卡点优先进入 review debt 或 next-session reinforcement；连续同类证据或结构性影响才生成可审批 patch。缺 interaction/reflection/pre-session review 证据的结构性 patch 应降级为 `pending-evidence`。

---

## 7. 读写数据流

## 7.1 `/learn-plan`

```text
用户输入
-> clarification/research/diagnostic/approval JSON
-> workflow engine gate
-> planning system
-> finalize
-> learn-plan.md + knowledge-map.md + knowledge-state.json + materials/index.json
```

只有 `finalize` 通过 gate 后才写正式主产物。初始 `knowledge-state.json` 为 `draft`，进入初始 `/learn-test` 前需要用户确认 `knowledge-map.md`。

## 7.2 `/learn-today` / `/learn-test`

```text
learn-plan.md
+ knowledge-state.json
+ materials/index.json
+ learner_model.json
+ recent sessions/*/progress.json
+ 用户 check-in
-> lesson_target_slice 或 test_coverage_slice
-> session plan
-> sessions/<date>/lesson.html（today canonical 课件；根目录 learn-today-YYYY-MM-DD.md 仅 legacy/debug）
-> questions.json
-> progress.json
-> 题集.html + server.py
```

运行时只能基于正式计划、知识状态和反馈状态生成 session，不应修改 workflow 中间态。`/learn-today` 生成新课前必须做课前历史复习并保存 `pre_session_review`，并根据 plan pointer + `knowledge-state.json` 做 prerequisite readiness check；`/learn-test` 根据测试目的和题量预算生成 `test_coverage_slice`。session 启动后，终端学习交互写入 `interaction_events.jsonl`。

## 7.3 复盘回写脚本

```text
questions.json + progress.json
+ interaction_events.jsonl
+ reflection.json
-> performance / interaction / reflection facts summary
-> .learn-workflow/session_facts.json
-> learner_model.json update
-> knowledge-state.json evidence/mastery/confidence update
-> knowledge-map.md derived_mastery/coverage refresh
-> curriculum_patch_queue.json proposed|pending-evidence patch
-> learn-plan.md 学习记录/测试记录追加
-> learn-plan.md 当前教学/练习微调追加（仅低风险反馈）
```

最终 update 必须发生在用户 completion signal 与 reflection gate 之后。缺 completion/reflection 时，update 只能写事实记录和复习债，不能把 covered scope 直接判为 mastered。写入 `knowledge-state.json` 的 mastery/evidence 前，图谱状态必须为 `confirmed` 或 `active`，并且题目/练习必须显式绑定合法 `knowledge_point_ids` 与 `evidence_types`；`draft` 图谱和缺 evidence binding 的题目不得回写 mastery。主体计划结构只有在 patch 被确认后才修改。

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
2. `knowledge-state.json` 是知识点 mastery / confidence / evidence 的权威状态源；`learn-plan.md` 不承载底层 mastery。
3. `knowledge-map.md` 是用户审阅视图；图谱结构变更必须经用户确认。
4. `.learn-workflow/*.json` 是中间态，不替代正式计划。
5. `progress.json` 是 session 事实，不替代 learner model 或 knowledge state。
6. `learner_model.json` 是能力证据与复习债，不替代 curriculum 或 knowledge state。
7. `curriculum_patch_queue.json` 中的 proposed patch 未确认前不能改正式路线。
8. `materials/index.json` 的下载字段只能由下载/预处理层维护。

---

## 10. 一句话原则

**让每个状态文件只承担一个层级的责任：规划中间态、正式计划、执行事实、学习者模型、计划调整建议必须分开。**
