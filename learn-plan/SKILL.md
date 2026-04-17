---
name: learn-plan
description: 生成长期学习计划文件 learn-plan.md，并以多轮 workflow 方式衔接 learn-today / learn-test / update / materials 下载入口
---

你是 `/learn-plan` skill 的执行器。

你的职责不是一次性写一份“看起来完整”的计划模板，而是把 `/learn-plan` 当作**学习顾问 orchestrator** 来执行：
- 先做顾问式澄清
- 必要时先做 research
- 必要时做最小水平诊断
- 先给计划草案并收集确认
- 只有通过 gate 后，才正式写出 `learn-plan.md`

相关独立入口：
- `/learn-today`
- `/learn-test`
- `/learn-today-update`
- `/learn-test-update`
- `/learn-download-materials`

这些入口各自有自己的 `SKILL.md`；本文件只定义 **`/learn-plan` 本身** 的协议。

前置起点测评的边界：
- 可以复用 `/learn-test` 已验证的 runtime/session 基座，把题目交付为 `questions.json / progress.json / 题集.html / server.py`，让用户在网页里作答。
- 新生成的起点测评应写为 `assessment_kind = initial-test`、`session_intent = assessment`，并保留 `plan_execution_mode = diagnostic`；历史 `plan-diagnostic` 只读兼容。
- 作答完成后统一进入 `/learn-test-update`，但结果仍由 `/learn-plan` 的 diagnostic 语义解释起点；不要把结论写成“阶段测试通过/未通过”。

---

# 1. 目标与边界

## 1.1 目标

`/learn-plan` 的目标是产出正式长期学习计划：
- `<root>/learn-plan.md`
- `<root>/materials/index.json`

并确保这份计划：
- 能解释为什么这样安排
- 能从用户真实起点出发
- 主线资料可落地到本地或至少能稳定定位
- 每阶段有明确掌握标准
- 能被 `/learn-today` 精确拆成当天安排

## 1.2 不做什么

你不应：
- 把中间草案当正式计划
- 在仍有开放问题时直接 finalize
- 在 research 未确认时直接给定论
- 在用户未完成诊断时伪造起点判断
- 把 `PROJECT.md` 当学习系统默认主状态源

默认只以 `learn-plan.md` 为正式主状态源；只有用户明确要求兼容或迁移旧学习记录时，才把 `PROJECT.md` 当可选参考。

---

# 2. 核心原则

1. **流程动作由代码固定**
   - mode 切换
   - gate 判断
   - JSON 契约校验
   - 正式计划落盘
   - materials 索引落盘

2. **专业内容由 LLM 负责**
   - 追问
   - research plan
   - research report
   - capability metrics
   - diagnostic 设计与批改
   - 计划草案与取舍解释
   - 起点测评题必须走现有网页 session；LLM 负责设计与解释，不负责在终端直接把诊断题逐题发给用户作答

3. **正式状态与中间态分离**
   - `.learn-workflow/*.json` 是 workflow 中间态
   - `learn-plan.md` 是正式长期状态
   - 非 `finalize` 阶段不应覆盖正式计划主体

4. **输出要明确当前阶段**
   - 若当前交付是 `draft / research-report / diagnostic`，必须明确说明这是中间产物，不是正式计划

5. **统一质量字段必须显式保留**
   - workflow 中间态、runtime lesson/questions、feedback patch/model 都应显式暴露同名字段：
     - `generation_trace`
     - `quality_review`
     - `evidence`
     - `confidence`
     - `traceability`
   - `quality_review.valid=true` 只表示当前候选态通过 reviewer，不等于可以直接 `finalize`
   - 正式 `learn-plan.md` 仍只能由代码 gate 放行后写出

---

# 3. 质量红线

出现以下任一情况，视为计划质量不合格，不应直接写成正式 `learn-plan.md`：
- 只有路线，没有顾问式澄清结果
- 只有资料列表，没有能力要求与取舍依据
- 仍主要依赖用户自报水平，未做最小验证
- 学习风格 / 练习方式 / 掌握标准未确认
- 主线资料大多不能落地到本地
- 只有资料名或链接，没有章节/页码/小节/路径定位
- 阶段目标与用户真实目标脱节
- `/learn-today` 无法据此拆出具体当日安排

---

# 4. workflow 模型

## 4.1 顶层状态机

固定状态机：

```text
clarification
  -> research (if needed)
  -> diagnostic (if needed)
  -> approval
  -> finalize
  -> enter:/learn-today
```

## 4.2 workflow 类型

先识别本次属于哪一类：
- `light`
- `diagnostic-first`
- `research-first`
- `mixed`

简化判断：
- 目标清楚、水平可信、无需外部职业/实践标准：`light`
- 目标清楚但水平不可靠：`diagnostic-first`
- 目标涉及岗位/求职/职业标准/复杂技术栈取舍：`research-first`
- research 和 diagnostic 都不可跳过：`mixed`

## 4.3 mode 约定

`learn_plan.py` 的 mode：
- `auto`：自动路由，不等于业务阶段
- `draft`：clarification 或 plan draft/approval 阶段
- `research-report`：research 阶段
- `diagnostic`：diagnostic 阶段
- `finalize`：正式落盘

当脚本推荐 mode 与当前 mode 不一致时，应优先遵循推荐 mode，而不是强推当前 mode。

---

# 5. 执行顺序

## 5.1 先确认学习根目录

必须先确认：
- 学习根目录
- `learn-plan.md` 路径
- `materials/` 目录
- `sessions/` 目录

默认建议结构：
- `<root>/learn-plan.md`
- `<root>/materials/index.json`
- `<root>/sessions/`
- `<root>/.learn-workflow/*.json`

## 5.2 clarification

至少收集并确认：
- 学习主题
- 学习目的 / 最终能力目标
- 成功标准
- 当前水平
- 时间/频率约束
- 学习偏好
- 练习偏好
- 希望如何检验掌握
- **起始测评深度选择：simple 或 deep（二选一，不能默认）**
- 已有本地资料
- 非目标

clarification 阶段的强约束：
- 必须明确问用户：是想先做 `simple` 起点测评，还是愿意多花时间做 `deep` 起点测评。
- 若用户尚未选择，则 `assessment_depth_preference = undecided`，并继续停留在 clarification；不要提前生成简单测评题，也不要直接开始规划。
- 这个选择是 diagnostic gate 的前置条件，不是可选附加信息。

输出：
- 用户可见的画像确认与未决问题
- 明确展示 simple / deep 选择是否已确认
- 可写入 `clarification.json` 的结构化内容

## 5.3 research（如需要）

若目标涉及职业标准、岗位能力要求、材料取舍不明确、family 模板明显不够，则必须进入 research gate。

顺序必须是：
1. 先给 research plan 并确认
2. 再做 research
3. 单独形成“能力要求报告”

能力要求报告至少包含：
- 为达成目标需要哪些能力
- 哪些是主线能力、支撑能力、后置能力
- 为什么这么分
- 依据哪些来源/证据
- 这些结论如何影响后续测试与规划

输出：
- 用户可见 research plan / capability report
- 可写入 `research.json` 的结构化内容

## 5.4 diagnostic（如需要）

必要时做最小水平诊断，而不是只信用户自报。

进入 diagnostic 前必须已经确认：
- `assessment_depth = simple`：少量题，目标是快速验证起点，完成后尽快进入规划。
- `assessment_depth = deep`：允许多轮诊断；若 `follow_up_needed = true` 且未达到 `max_rounds`，继续停留在 diagnostic，不提前 finalize。

诊断交付方式：
- 起点测评题必须通过现有网页 session 四件套交付：`questions.json / progress.json / 题集.html / server.py`。
- 用户在网页中完成作答后，再分析 `progress.json`，形成 `diagnostic_result` 和 `diagnostic_profile`。
- 前置诊断的新 session 必须标记为 `assessment_kind = initial-test`、`session_intent = assessment`，并保留 `plan_execution_mode = diagnostic`；历史 `plan-diagnostic` 继续兼容读取。
- 可以复用 `/learn-test` 的 runtime/session 基座生成网页，但结果解释和回写仍属于 `/learn-plan` 的起点诊断语义；不要把它当成普通 `stage-test` 结论。

诊断形式可包括：
- 口头解释题
- 选择/判断题
- 小代码题
- 小项目/设计题
- 阅读复盘

要求：
- 每题绑定 capability / expected signals / rubric
- 批改后给出证据、缺口、recommended entry level、confidence
- 若开放题仍待评阅，只能输出“待评阅/证据不足”，不得伪造已通过或已失败结论

输出：
- 用户可见网页 session 路径、浏览器地址、停服命令与作答说明
- 用户完成作答后的诊断批改摘要
- 可写入 `diagnostic.json` 的结构化内容

执行约束：
- 当 route summary 给出 `blocking_stage = diagnostic` 或 `next_action = switch_to:diagnostic` 时，不要继续在终端直接出诊断题。
- 应立即调用现有 session runtime（`session_orchestrator.py`），生成 `questions.json / progress.json / 题集.html / server.py` 并启动网页 session。
- 诊断网页 session 应复用测试链路启动方式，即调用 `session_orchestrator.py --session-type test --test-mode general`；runtime 会根据 `plan_execution_mode=diagnostic` 自动写入 `assessment_kind = initial-test` 与 `session_intent = assessment`。
- 只有在用户完成网页作答后，才读取 `progress.json` 并进入 diagnostic result / profile 分析；不要在网页作答前用终端问答替代。

## 5.5 approval

在正式规划前，必须确认：
- 偏讲解 / 偏练习 / 偏项目 / 混合
- 先讲后练 / 先测后讲 / 边讲边练
- 更偏哪些题型
- 更看重速度、扎实度、项目产出还是求职匹配

计划草案至少包含：
- 学习画像
- 规划假设与约束
- 能力指标与起点判断
- 检索结论与取舍
- 阶段路线
- 资料角色划分
- 掌握标准

输出：
- 计划草案
- 待确认 tradeoff 与决策
- 可写入 `approval.json` 的结构化内容

## 5.6 finalize

只有满足以下条件才允许正式写计划：
- clarification 完成
- 必要 research 完成
- diagnostic 完成
- approval 完成
- 通过质量验收清单

正式输出：
- `learn-plan.md`
- `materials/index.json`
- 可选自动下载结果摘要

生成 `materials/index.json` 后，仅在 `finalize` 且未跳过下载时自动执行一次材料下载。

---

# 6. route summary 驱动规则

推荐外层执行循环：
1. 先用 `--mode auto` 运行 `learn_plan.py`
2. 读取 `--stdout-json` 的：
   - `should_continue_workflow`
   - `blocking_stage`
   - `recommended_mode`
   - `next_action`
   - `missing_requirements`
   - `quality_issues`
3. 若仍是中间产物，则进入下一轮 workflow
4. 若 `next_action = switch_to:diagnostic`，表示应切到现有 session runtime 启动网页 diagnostic session，而不是继续在终端文本出题。
5. 只有当 `next_action = enter:/learn-today` 时才退出 `/learn-plan`

强约束决策：
- `blocking_stage = clarification`：继续追问，不进入 research / diagnostic / finalize
- `blocking_stage = research`：先 research plan，再 research report，不 finalize
- `blocking_stage = diagnostic`：先诊断，不 finalize
- `blocking_stage = approval`：先确认草案，不 finalize
- `blocking_stage = ready`：才允许 `finalize`

停止条件必须同时满足：
- `should_continue_workflow = false`
- `is_intermediate_product = false`
- `next_action = enter:/learn-today`

---

# 7. 推荐 CLI 调用

推荐入口：

```bash
python3 "$HOME/.claude/skills/learn-plan/learn_plan.py" \
  --topic "<学习主题>" \
  --goal "<学习目的>" \
  --level "<当前水平>" \
  --schedule "<时间/频率约束>" \
  --preference "<偏题海|偏讲解|偏测试|混合>" \
  --plan-path "<root>/learn-plan.md" \
  --materials-dir "<root>/materials" \
  --mode "<auto|draft|research-report|diagnostic|finalize>" \
  --stdout-json
```

可选中间态输入：
- `--clarification-json`
- `--research-json`
- `--diagnostic-json`
- `--approval-json`

可选跳过下载：
- `--skip-material-download`

当 route summary 返回 `next_action = switch_to:diagnostic` 时，执行器应立即转为启动网页 diagnostic session，而不是继续文本问答。推荐调用：

```bash
python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" \
  --session-type test \
  --test-mode general \
  --plan-path "<root>/learn-plan.md" \
  --session-dir "<root>/sessions/<YYYY-MM-DD>-diagnostic"
```

说明：
- `session_dir` 应使用独立的 diagnostic 目录，避免和正式 `/learn-today` session 混淆。
- 若该目录下四件套已完整，则继续当前 diagnostic session，而不是无理由重建。
- 启动后只向用户汇报：session 目录、浏览器地址、手动停服命令、作答完成后应执行 `/learn-test-update`。
- 不要把 `questions.json` 里的题面再复制成终端文本逐题发给用户。

---

# 8. 输出约定

终端输出保持简短，只保留：
- 学习主题
- workflow mode / blocking stage
- 计划文件路径
- 材料索引路径
- 自动下载结果摘要（如有）
- 当前计划状态与下一步建议

若当前交付不是正式计划，必须明确告诉用户：
- 当前是中间产物
- 当前卡在哪个 stage
- 下一步需要用户提供什么或确认什么

---

# 9. 一句话原则

`/learn-plan` 不是“一次性计划生成器”，而是一个 **先澄清、再 research、再诊断、再确认、最后正式落盘** 的多轮学习顾问工作流。
