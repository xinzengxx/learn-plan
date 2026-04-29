# learn-plan skill 簇执行器指南

本文档定义 Claude Code 在执行 `/learn-plan` skill 簇时应该如何跟随 route summary、如何调用 CLI facade、以及哪些情况必须停在当前阶段而不能继续推进。

相关文档：
- 顶层 skill 协议：`../SKILL.md`
- clarification 阶段：`./clarification-stage.md`
- research 阶段：`./research-stage.md`
- diagnostic 阶段：`./diagnostic-stage.md`
- approval 阶段：`./approval-stage.md`
- finalize 阶段：`./finalize-stage.md`
- 架构总览：`../WORKFLOW_DESIGN.md`
- 契约文档：`./contracts.md`
- 状态文件：`./state-files.md`
- 兼容边界：`./runtime-compatibility.md`

---

## 1. 总原则

执行器不是一次性模板填充器，而是 workflow orchestrator。

必须遵守：
- 先识别当前 skill 入口。
- 对 `/learn-plan`，默认先按 `--mode auto` 或现有 route summary 理解当前阶段。
- 若脚本返回中间态，继续当前 workflow，不把中间产物当正式计划。
- 只有 workflow engine 允许 `finalize` 时才写正式 `learn-plan.md`。
- `/learn-today`、`/learn-test` 只从正式计划与反馈状态生成 session，不改 workflow 中间态。
- update 只追加记录和提出 patch，不在未批准时重写长期路线主体。

---

## 2. `/learn-plan` 执行循环

推荐外层循环：

```text
1. 确认学习根目录与目标。
2. 调用 learn_plan.py --mode auto --stdout-json。
3. 读取 stdout JSON：
   - should_continue_workflow
   - is_intermediate_product
   - blocking_stage
   - recommended_mode
   - next_action
   - missing_requirements
   - quality_issues
   - stage_exit_contract
   - stage_exit_missing_values
   - stage_exit_user_visible_next_step
4. 根据 blocking_stage 执行 selective subagent strategy。
   - 主 agent 负责澄清、编排、字段映射、小范围修复和 CLI 验证。
   - subagent 负责检索、出题、严格审题、语义审查、planning candidate 和需要独立上下文的第二意见；当前主会话不得直接调用 WebSearch/WebFetch 或直接撰写这些重语义 artifact 来替代 subagent。
   - 若已拿到合法 JSON，优先通过 `--stage-candidate-json` / `--stage-review-json` / `--planning-candidate-json` / `--planning-review-json` 注入 `learn_plan.py`；Python 只消费 artifact、推进 gate 与落盘状态。
5. 写入或更新对应 .learn-workflow/*.json。
6. 再次调用 learn_plan.py --mode auto 或推荐 mode。
7. 直到 next_action = enter:/learn-today。
```

---

## 3. route summary 决策表

| `blocking_stage` | 执行器动作 | 禁止动作 |
| --- | --- | --- |
| `clarification` | 在终端用自然语言围绕当前 consultation topic 做 1–3 个同主题开放追问；用户回答后再派 Agent 整理结构化 candidate patch | 不使用 `AskUserQuestion` / `UserQuestions` / 选择题控件；不跨主题批量问卷；不进入 research / diagnostic / finalize |
| `research` | 先给 research plan 并确认，再派发 Agent 生成 HTML 能力要求与达标水平报告 | 不直接诊断或规划；不把报告写成学习路线 |
| `diagnostic` | 启动现有网页 diagnostic session，等待用户在网页作答，再读取 progress.json 批改并写起点评估 | 不在终端直接文本出题；不伪造诊断结论 |
| `approval` | 生成计划草案与 material curation 报告，并让用户确认资料策略、tradeoff、执行节奏和掌握标准 | 不把草案写成正式计划；不在 material_curation 未确认时把 `confirmed_material_strategy` 置为 true |
| `planning` | 校验 planning candidate 与 review，清除 finalize 前的结构化计划阻塞项 | 不绕过 planning artifact 直接手写正式计划 |
| `ready` | 调用 `finalize`，检查正式产物 | 不再继续问非阻塞问题 |

---

## 4. `/learn-plan` 各阶段执行器职责

## 4.1 clarification

执行器应输出：
- 当前画像摘要。
- 当前聚焦的 `consultation_state.current_topic_id`。
- 为什么这一轮只追问这个主题。
- 当前主题已确认什么、还缺什么。
- 同一主题下 1–3 个问题；若回答仍模糊，下一轮继续同一主题。
- 起始测评预算是否已确认。

执行器不应一次抛出跨主题大问卷；若用户暂时答不出，应记录为 assumption / open question / deferred，而不是伪造确定事实。

执行器应写入：
- `.learn-workflow/clarification.json`

完成后再调用 route，不直接跳阶段。

## 4.2 research

执行器必须分两步：

1. research plan：
   - 计划回答哪些问题
   - 查哪些来源类型
   - 结果如何影响能力指标、材料取舍、诊断题
   - 等用户确认

2. research report：
   - HTML 能力要求与达标水平报告
   - 目标对应的达标带与 required level definition
   - 能力集合
   - 主线/支撑/后置能力
   - 可观察行为
   - 量化指标
   - 推荐诊断方法
   - 材料取舍依据
   - evidence / open risks

报告只回答“为了达成目标，需要掌握什么能力、到什么水平、用什么证据判断”；不要展开学习路线或阶段安排。

执行器应写入：
- `.learn-workflow/research.json`

禁止：
- 只有材料列表，没有能力指标。
- 没有来源证据就给确定性结论。

## 4.3 diagnostic

执行器应：
- 从 capability metrics 中选优先诊断项。
- 不在终端直接文本出题；而是调用现有 `session_orchestrator.py` 启动网页 diagnostic session。
- 复用现有 session 四件套：`questions.json / progress.json / 题集.html / server.py`。
- 诊断阶段应复用测试型 session 启动链：调用 `session_orchestrator.py --session-type test --test-mode general`，由 runtime 根据 `plan_execution_mode=diagnostic` 自动写入 `assessment_kind = initial-test` 与 `session_intent = assessment`；历史 `plan-diagnostic` 继续兼容读取。
- 等用户在网页完成作答后，再读取 `progress.json`。
- 批改时指出 observed signals / missing signals。
- 产出 capability assessment 和 recommended entry level。

执行器应写入：
- 启动后的 session 路径与浏览器地址
- 手动停服命令
- 用户完成作答后生成的 `.learn-workflow/diagnostic.json`

推荐启动配方：

```bash
python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" \
  --session-type test \
  --test-mode general \
  --plan-path "<root>/learn-plan.md" \
  --session-dir "<root>/sessions/<YYYY-MM-DD>-test" \
  --lesson-artifact-json "<Agent生成的lesson artifact>" \
  --question-artifact-json "<Agent生成的questions artifact>" \
  --question-review-json "<Agent生成的strict review artifact>"
```

执行器对用户的终端回报应只保留：
- `session_dir`
- 浏览器访问地址
- 手动停服命令
- “完成作答后会自动停服、自动运行内部 `learn_test_update.py` 回写流程，并自动重新进入 /learn-plan；若失败再手动运行页面展示的整条命令”

禁止：
- 用户没答就写 evaluated。
- 在终端继续逐题文本测评来替代网页 session。
- 只有总分，没有能力维度结论。

## 4.4 approval

执行器应：
- 生成计划草案。
- 生成 material curation 报告：主线/辅助/候选/拒绝资料、每份资料的能力用途、用户起点适配、采用片段、下载验证状态与 open risks。
- 明确每阶段目标、资料定位、练习、掌握标准、产出证据。
- 单独列出 tradeoff 和风险。
- 收集用户确认或修改意见；用户未确认 material curation 时不得把 `confirmed_material_strategy` 置为 true。

执行器应写入：
- `.learn-workflow/approval.json`

禁止：
- 用户只说“差不多”但仍有主线材料、掌握标准或 daily style 争议时直接 approved。

## 4.5 finalize

执行器应：
- 调用 `learn_plan.py --mode finalize`。
- 检查 `quality_issues`。
- 汇报正式路径和下一步 `/learn-today`。

禁止：
- 手写正式 `learn-plan.md` 绕过脚本 gate。

---

## 5. `/learn-today` 执行器职责

执行器应：
1. 确认学习根目录和 session 目录。
2. 读取 `learn-plan.md`，默认不读 `PROJECT.md`。
3. 做简短 check-in：真实进度、卡点、今日时间、复习/推进偏好。
4. 调用 `session_orchestrator.py --session-type today`。
5. 校验 session 四件套。
6. 启动服务并打开浏览器。
7. 简短输出关键路径、浏览器地址、停服命令。

禁止：
- 重写长期计划主体。
- session 已完整时无理由重建题目。
- 端口占用时只报原始 traceback。

---

## 6. `/learn-test` 执行器职责

执行器应：
1. 确认测试模式：`general | weakness-focused | mixed`。
2. 确认 session 目录。
3. 读取 `learn-plan.md` 与历史 progress。
4. 调用 `session_orchestrator.py --session-type test --test-mode ...`。
5. 校验 session 四件套。
6. 启动服务并打开浏览器。

禁止：
- 缺出题/审题 artifact 时静默 fallback 到确定性内容题或内置题库。
- 未完成 session 就调用 test update。

---

## 7. 复盘回写职责

## 7.1 `/learn-today` Step 6

执行器应：
- 确认 today session 目录。
- 在主流程内调用内部 `learn_today_update.py`。
- 输出简短学习摘要。
- 确认 `.learn-workflow/learner_model.json` 已更新。
- 若生成 patch，确认它只写入 `proposed` 或 `pending-evidence` 队列，不直接应用到正式计划主体。

## 7.2 `/learn-test` Step 4

执行器应：
- 确认 test session 目录。
- 在主流程内调用内部 `learn_test_update.py`。
- 输出测试覆盖、薄弱项、是否回退/推进。
- 确认 `.learn-workflow/learner_model.json` 与 `curriculum_patch_queue.json` 已更新。
- 若生成 patch，确认它只写入 `proposed` 或 `pending-evidence` 队列，不直接应用。

禁止：
- 未经用户确认直接改长期路线主体。
- 默认不读也不同步 `PROJECT.md`。

---

## 8. `/learn-download-materials` 执行器职责

执行器应：
1. 确认 `materials/` 目录或 `materials/index.json`。
2. 调用 `python3 -m learn_materials.download_cli`。
3. 输出下载统计。
4. 明确失败材料状态，不把不可下载在线资料当作错误。

禁止：
- 下载需要认证或动态交互页面。
- 下载器修改 curriculum 规划逻辑。

---

## 9. 失败回退规则

| 失败点 | 回退 |
| --- | --- |
| clarification 信息不足 | 停留 clarification，继续问阻塞项 |
| research plan 未确认 | 不做 research report |
| research 证据不足 | 记录 open risks，不进入确定性规划 |
| diagnostic 未作答 | 不写 evaluated，不进入 approval |
| approval 未明确 | 保持 draft/needs-revision |
| finalize 质量校验失败 | 回到对应 blocking stage |
| 缺出题/审题 artifact | 阻断 session 启动，重新派发 subagent 生成或修复 artifact |
| materials 下载失败 | 标记失败，runtime 回退 metadata-only |
| preprocessing 失败 | 不阻断 session |

---

## 10. 终端输出风格

- 对用户输出保持简短。
- 中间阶段要说明“这是中间产物，不是正式计划”。
- 正式完成时只输出：
  - 生成/继续/完成结论
  - 关键路径
  - 下一步动作
  - 若启动服务，输出浏览器地址和停服命令

---

## 11. 一句话原则

**执行器跟随 route summary 推进，不凭感觉跳过 gate；LLM 负责内容质量，代码负责状态边界。**
