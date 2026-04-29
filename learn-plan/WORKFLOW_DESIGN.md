# learn-plan skill 簇架构文档

本文档是整个 `/learn-plan` skill 簇的架构真相源，记录 2026-04-26 重构后的设计。

## 1. 核心设计理念

重构围绕一个核心判断：**内容深度 > 流程复杂度**。

- 流程由 agent 对话层编排，不过度依赖 Python 状态机
- LLM 负责专业内容（深挖追问、检索分析、课件生成、出题审题、复盘建议）
- Python 层负责稳定的运行时工具：session bootstrap、材料缓存/下载
- 正式状态和中间态分离：`learn-plan.md` 是主状态，中间报告明确标注"中间产物"

## 2. 系统入口（3 个核心 + 1 个工具）

| 入口 | 角色 | 核心产出 |
|---|---|---|
| `/learn-plan` | 学习顾问 | learn-plan.md + materials/index.json |
| `/learn-today` | 日常教师 | lesson.md + 练习题 + 复盘 |
| `/learn-test` | 阶段测试 | 测试题 + 测试复盘 |
| `/learn-download-materials` | 资料缓存工具 | 材料下载到本地（独立入口，/learn-plan 中已自动触发） |

更新回写不再作为独立入口暴露：今日学习回写由 `/learn-today` Step 6 负责，测试回写由 `/learn-test` Step 4 负责；底层 updater 脚本仍由主入口内部复用。

## 3. `/learn-plan`：三轮递进结构

```text
Phase 1: 深挖 + 分析
  ├── 顾问式深挖（9 个主题逐轮追问）
  └── 资料检索（子 Agent 并行）+ 目的分析
  → 产出：综合报告（HTML）

Phase 2: 起点检测（可选）
  ├── 网页 diagnostic session
  └── 诊断结论（水平、差距、推荐起点）

Phase 3: 出规划
  ├── 草案 + 用户确认（可多轮）
  └── 正式落盘 learn-plan.md + materials/index.json

动态调整：mini approval 流程，微调计划而不重跑整条链路
```

### 3.1 Phase 1 细节

**深挖主题**（逐主题，终端自然语言追问）：

| 主题 | 追问深度要求 |
|---|---|
| learning_purpose | 深挖到具体场景："哪个学校的考试？有没有真题？""看了哪些 JD？什么岗位？" |
| success_criteria | 量化的成功标准 |
| current_level | 具体背景，不可靠则 deferred 到 Phase 2 |
| constraints | 频率、时长、截止日 |
| teaching_preference | 概念推导式 / 情景案例式 / 混合（默认情景案例式） |
| practice_preference | 题量、题型、反馈方式 |
| materials | 自备资料评估 + 语言偏好 + 平台偏好 |
| assessment_budget | 最多几轮、每轮最多几题 |
| non_goals | 明确排除项 |

**资料评估 + 检索**：
- 先评估用户自备资料（覆盖度、深度、缺口）
- 不够时多个子 Agent 并行检索外部资料
- 检索不到：诚实告知，请用户补充——不编造
- 并行做目的分析检索（真题、岗位 JD、行业标准等）

**产出**：HTML 综合报告（目的分析 + 资料评估 + open risks）

### 3.2 Phase 2 细节

- 复用 /learn-test runtime（网页 session）
- 根据 Phase 1 的目标能力出诊断题
- 支持多轮诊断（用户在 clarify 阶段确定预算）
- 跳过时必须记录风险："起点基于自报，未经诊断验证"

### 3.3 Phase 3 细节

**草案必须包含**：
- 学习画像
- 能力指标与起点判断
- 阶段路线（目标、内容、资料、练习、掌握标准、产出证据）
- 资料清单与取舍说明
- material curation：结合目标分析与诊断结果，确认主线/辅助/候选/拒绝资料、采用片段、下载验证状态与 open risks
- **进度指针**（/learn-today 的定位锚点）
- 关键 tradeoff 与风险

**正式落盘**：用户确认计划草案与 material curation 后写 learn-plan.md + materials/index.json；写盘后自动下载只作为缓存动作，不替代材料策展确认。

## 4. `/learn-today`：六步教学流程

```text
Step 1: check-in（进度确认，强制）
  → Step 2: 定位今日内容 + 加载资料
  → Step 3: 生成课件 lesson.md（五部分强制结构）
  → Step 4: 生成练习题（双 Agent：出题 + 审题）
  → Step 5: 组装 session 并启动网页
  → Step 6: 学后复盘 → 更新 learn-plan.md + learner_model
```

### 4.1 课件强制结构

1. **今日定位**：学什么、为什么、在路线中的位置
2. **情景引入**：真实场景/故事 → 卡点 → "现有知识解决不了"
3. **知识讲解**：来龙去脉 → 用法 → 回到情景解决卡点 → 过程抛问题引导思考
4. **扩展与注意点**：常见误区、关联知识、进阶方向
5. **今日小结 + 参考资料**：标注来源 `[来源: 资料名, 章节X, P.Y]`

### 4.2 练习题双 Agent 机制

- **子 Agent A（出题）**：每题绑定知识点和来源，干扰项有真实迷惑性，难度梯度
- **子 Agent B（审题）**：独立审查，检查答案正确性、干扰项质量、覆盖度、表述清晰度
- 审题失败 → 修改 → 重审，直到通过
- 禁止使用内置题库或 fallback

### 4.3 复盘

读取 progress.json 后的复盘维度：
- 本次概况（题数、正确率）
- 薄弱知识点（对应课件具体节、具体知识缺口）
- 具体建议（重读课件哪节、重读哪份资料哪一页）
- 下次预告
- 追加学习记录到 learn-plan.md，更新 learner_model

## 5. `/learn-test`：四步测试流程

```text
Step 1: 确认测试范围 + 模式（general / weakness-focused / mixed）
  → Step 2: 出题 + 审题（双 Agent，与 /learn-today 同标准）
  → Step 3: 组装 session 并启动网页
  → Step 4: 测试后复盘 → 更新 learn-plan.md + learner_model
```

三种模式：
- `general`：全阶段覆盖
- `weakness-focused`：聚焦历史薄弱项
- `mixed`：新内容 + 薄弱项混合

## 6. 核心约束

### 6.1 内容质量约束

- **课件不是知识提纲**：必须有叙事、有案例、有引导
- **题目不是凑数的**：每题绑定知识点、干扰项有迷惑性、难度有梯度
- **复盘不是泛泛而谈**：推荐具体到"XX 资料第 Y 章第 Z 页"
- **缺资料就诚实告知**：绝不编造

### 6.2 子 Agent 分工

| 任务 | 执行者 | 说明 |
|---|---|---|
| 顾问式追问 | 主 agent | 终端自然语言，不用 AskUserQuestion |
| 资料检索 / 目的分析 | 子 Agent | 多个可并行 |
| 课件正文 | 主 agent | 直接生成，不需要审课件 Agent |
| 出题 | 子 Agent A | 独立 |
| 审题 | 子 Agent B | 独立，不看出题 Agent 的内部推理 |
| 复盘分析 | 主 agent | 读取 progress.json，做分析 |

### 6.3 资料来源约束

- 所有引用外部资料的标注：`[来源: 资料名, 章节X, P.Y]`
- 无外部来源的教学组织内容标注：`[来源: 教学组织]`
- 检索不到资料：诚实告知，不编造

### 6.4 禁止事项（全局）

- 不要用 AskUserQuestion / 选择题控件做顾问式访谈
- 不要用内置题库或 fallback 替代出题+审题流程
- 不要编造资料内容或题目
- 不要在用户未确认时写正式 learn-plan.md
- 不要跳过 check-in 直接出题

## 7. 状态文件

### 正式长期状态

- `learn-plan.md`：用户可读的 curriculum 主文档（含进度指针）
- `materials/index.json`：材料索引
- `sessions/*/progress.json`：session 事实记录

### 学习者模型

- `.learn-workflow/learner_model.json`：跨 session 能力估计
- `.learn-workflow/curriculum_patch_queue.json`：计划调整建议

### 中间产物（Phase 1-2 阶段，明确标注"不是正式计划"）

- Phase 1 综合报告（HTML）
- Phase 2 诊断结论

## 8. 主数据流

```text
/learn-plan:
  用户输入 → Phase 1 深挖+检索 → Phase 2 可选诊断 → Phase 3 草案确认 → learn-plan.md + materials/index.json

/learn-today:
  learn-plan.md + materials/ + check-in → 课件 lesson.md → 练习题 questions.json → 网页 session → progress.json → 复盘 → learn-plan.md 记录追加 + learner_model 更新

/learn-test:
  learn-plan.md + learner_model + 历史 → 测试题 questions.json → 网页 session → progress.json → 复盘 → learn-plan.md 记录追加 + learner_model 更新
```

## 9. Python 层边界

| 保留 | 原因 |
|---|---|
| `session_bootstrap.py` | 生成网页 session，稳定工具 |
| `session_orchestrator.py` | session 组装入口 |
| `learn_materials/downloader.py` | 材料缓存下载与验证 |
| `learn_today_update.py` | learn-plan.md 记录追加 + learner_model 更新 |
| `learn_test_update.py` | learn-plan.md 记录追加 + learner_model 更新 |
| `learn_core/` | 共享工具（IO、plan parser、markdown 处理等） |

| 待精简 | 原因 |
|---|---|
| `learn_workflow/` (gate/state_machine) | 流程编排由 agent 对话层负责，不需要代码状态机 |
| `learn_planning/` (curriculum_builder/plan_validator) | 计划生成由 LLM 负责 |
| `learn_runtime/` (question_banks/question_validation) | 审题由审题 Agent 负责，不依赖代码级题库 |
| `learn_feedback/` (progress_summary/curriculum_patch) | 由复盘 Agent 逻辑承担 |

## 10. 兼容说明

- 旧阶段文档（clarification-stage.md 等）保留但不再作为主链路，新流程以 phase1/2/3 文档为准
- session runtime 协议不变（questions.json + progress.json + 题集.html + server.py）
- learn-plan.md 的 section 结构保持向后兼容，新增进度指针区块

## 11. 一句话总结

目标不是让每个 skill 更复杂，而是让每个 skill 的内容更深：深挖需求、情景化课件、双 Agent 审题、具体到页码的复盘——同时流程更短（5 阶段 → 3 阶段，6 入口 → 3 入口），Python 层更薄。
