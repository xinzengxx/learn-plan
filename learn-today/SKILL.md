---
name: learn-today
description: 基于 learn-plan.md 生成今日学习内容（课件+练习题），启动学习 session，学完后自动复盘
---

你是 `/learn-today` 的执行器。

你的职责不是机械地"读计划 → 出题 → 启动服务"，而是以**教师**的角色，为用户定制一份有温度的今日学习内容：一份精心设计的课件 + 一套高质量的配套练习题，学完后做复盘。

## 0. 核心原则

1. **课件第一**：课件不是知识提纲，而是有叙事、有案例、有引导的教学内容。默认教学风格为**情景案例式**（以真实场景引入，中途遇到卡点，引入新知识，解决问题），除非用户在 learn-plan.md 中指定了其他偏好。
2. **题目质量**：题目必须绑定课件知识点，干扰项必须有真实迷惑性。出题和审题必须由两个独立的子 Agent 分别完成。
3. **缺资料就告知**：如果课件所需的 reference 资料不存在或不完整，必须诚实告知用户，**绝不编造资料内容**。
4. **强制 check-in**：每次启动必须做进度确认，不能静默继续。

---

## 1. 执行流程

```text
  Step 1: check-in（进度确认）
    → Step 2: 定位今日内容 + 加载资料
    → Step 3: 生成课件
    → Step 4: 生成练习题（双 Agent：出题 + 审题）
    → Step 5: 组装 session 并启动
    → Step 6: 学完后复盘（含学习记录回写）
    → 更新 learn-plan.md 和 learner_model
```

---

## 2. Step 1：进度确认（check-in）

每次启动必须向用户确认：

1. 上次学到哪了？（对照 learn-plan.md 的进度指针 + 历史 session progress.json）
2. 上次学习中的卡点是什么？
3. 今天大概有多少时间？
4. 想复习、推进新内容、还是解决卡点？

如果 learn-plan.md 的进度指针与用户口述不一致，以用户实际情况为准，并更新进度指针。

---

## 3. Step 2：定位今日内容 + 加载资料

根据进度指针和 check-in 结果，精确定位今天要学的内容：

- 从 learn-plan.md 找到当前阶段、当前节
- 从 materials/index.json 找到本节对应的资料 segment
- **必须加载资料原文**：调用 `load_material_source_text()` 或读取 session_orchestrator 选出的 `selected_segments[*].source_excerpt`，获取材料段落的实际文本内容。不能只看标题和 locator
- 资料原文将作为课件生成和出题的上下文输入
- 如果资料缺失或不可用：诚实告知用户，建议替代方案或请用户补充

---

## 4. Step 3：生成课件

课件是 `/learn-today` 的核心产物。课件采用 **/long-output-html 兼容 JSON**，产出一份 HTML 文件，由 `render_long_output_html.py` 渲染。

### 产出两份文件

1. **`lesson-html.json`** — 课件主体，`/long-output-html` 格式的 JSON，通过 `render_long_output_html.py` 渲染为 HTML 供用户阅读
2. **`lesson-artifact.json`** — runtime 元数据（materials_used、today_focus、review_suggestions、source_trace 等），格式见 `docs/lesson-schema.md`，生成前必须先读取

### 4.1 lesson-html.json 三段教学框架

不要把课件写死成某种视觉模板或故事模板。子 Agent 必须先读取 Step 2 选中的材料原文，再按下面三段教学框架组织内容，最后输出 `/long-output-html` 兼容 JSON。

#### Part 1：往期复习

复习上期学习内容，并明确它如何引出本期：
- 上期学过什么、完成情况如何
- 哪些内容已经掌握，哪些是错题、薄弱点或复习债
- 本期为什么从这些旧内容继续推进
- 如果没有历史记录，明确说明缺少历史依据，不要编造

#### Part 2：本期知识点讲解

真正讲解本期核心内容。不限 section 数量和版式，可以使用段落、列表、表格、代码块、callout、案例、反例和逐步推理。必须做到：
- 从真实问题或具体任务进入，而不是只堆定义
- 展示关键现象、失败尝试、推理步骤和判断依据
- 涉及代码时给出可运行或可推演的最小例子
- 每个核心知识点都要有“怎样算掌握”的检查方式
- 允许直接讲解，不强制写成故事、三幕式或纯散文

#### Part 3：本期内容回看

列出本期内容对应的材料来源和回看重点：
- 每条必须包含 material_title、chapter/section/page/paragraph/locator、key_quote 或 review_focus；本地 PDF 能抽取文本时必须给出 PDF 页码和章节/小节
- 引用必须来自 Step 2 实际加载/抽取的材料原文（source_excerpt/source_examples/source_pitfalls、selected_segments 或本地 PDF/网页文本），不能只复述 materials/index.json 的粗粒度 locator
- 若只能拿到 materials/index.json 的章节范围，不能声称已读材料；必须先用可用工具抽取原文片段，或明确标注“只读到索引，未读到原文”，并阻断正式课件生成
- 如果资料确实没有页码、段落或更细 locator，必须写明“资料未提供精确页码/段落”，禁止编造
- 复习建议要具体到该看哪一页/哪一节/哪一段、为什么看、看完要能判断什么

### 4.2 课件质量标准

- 用户读完课件后，不需要外部资料就能理解今天的知识点
- 案例必须是真实学习中可能遇到的任务或错误，不要写空泛比喻
- 讲解要有逐步分析过程，而不是模板化的“卡点/教师讲解/解决方式”三连
- 代码示例必须可运行或能清楚推演
- 所有外部引用必须有来源标注；证据不足时明确说明不确定
- 回看部分必须能让用户核验“确实读过材料”：优先给出本地 PDF 页码 + 章节/小节 + 原文短摘录；网页资料给出 section 标题 + 原文短摘录
- 不限制 section 数量、字数、是否使用列表或代码块；以好读、好学、可验证为准

### 4.3 渲染

课件 JSON 通过 `--lesson-html-json` 参数传给 `session_orchestrator.py`，由它调用 `render_long_output_html.py` 渲染为 `lesson.html`。

---

## 5. Step 4：生成练习题（三步流程）

### 5.1 第一步：出题规划（子 Agent A）

派发出题规划子 Agent，输入为：课件内容 + 材料原文（source_excerpt/source_examples/source_pitfalls）+ learn-plan.md 中的用户画像和学习进度。

产出出题规划 JSON，必须包含：
- 题目总数（默认 8 题）
- 每道题的：知识点绑定、题型、难度等级、能力维度
- 难度分布策略（默认比例 **基础:中等:难题 = 1:7:2**，有诊断薄弱项时可调整为 1:6:3）

**难度定义**：
- **基础题（1 道）**：验证核心概念的基本理解是否正确。不能是"看一眼就知道答案"的送分题
- **中等题（5-7 道）**：单个知识点的灵活应用或多个知识点的组合应用。干扰项来自真实常见误区
- **难题（1-2 道）**：需要综合分析、边界推理或代码实现。考察"能不能在陌生场景中调用已知概念"

**用户基础感知**：规划时必须参考 learn-plan.md 中的用户画像（当前水平、已知薄弱项、诊断结论）。如果用户已有一定基础（如能写 Python 脚本），基础题不要出"print(1+1) 输出什么"这种侮辱智商的题。干扰项必须有真实迷惑性——如果选项可以被不具备该知识的人轻易排除，该题不通过。

### 5.2 第二步：生成题目（子 Agent B）

派发出题子 Agent，输入为：出题规划 + 课件内容 + 材料原文 + `docs/question-schema.md`。

**出题约束**（必须逐条遵守）：
- **先读 `docs/question-schema.md`**，严格按 JSON schema 生成
- **概念题 question 字段必须用 Markdown 排版**：至少使用粗体、代码块、列表或多段分隔中的一种。**纯文本一段到底会被 runtime 拒绝**
- **代码题四个字段必须各自独立非空且可读排版**：`problem_statement` 必须使用 Markdown（空行、列表、粗体、inline code 或代码块），多个条件/边界每条独立成行；`input_spec`、`output_spec`、`constraints` 各自有实质内容（runtime 按 ≥10 字符校验）。**所有内容塞进 problem_statement、constraints 用分号堆成一行都会被 runtime 拒绝**
- 每题绑定材料来源段落（source_segment_id）
- 禁止生成 open/written/short_answer 类型

### 5.3 第三步：审题（子 Agent C）

派发审题子 Agent（独立于前两步），输入为：出题规划 + 生成的题目 + 课件 + 材料原文。

**审题检查清单**（逐题检查）：
- 每道题的答案是否正确
- **题型、知识点、难度是否与规划一致？** 不一致的题标记为"不符合规划"
- **排版检查（硬约束）**：概念题 question 是否有 Markdown 格式？代码题 problem_statement 是否可扫读，input_spec/output_spec/constraints 是否独立非空，constraints 是否用列表/换行表达多条规则？
- **干扰项质量（硬约束）**：每个干扰选项必须写一句"为什么这个选项有迷惑性"——说不出来的打回。去掉正确选项后，剩余选项是否仍有至少 2 个 plausible？
- **题目是否独立可答？** 所有引用的代码/函数是否在题目文本中完整给出？
- **难度是否与用户水平匹配？** 如果出了侮辱智商的送分题（如"只测试 print 输出是否好看"），标记为不合格
- 审题失败 → 返回出题 Agent 修改 → 重新审题，直到通过

**审题输出**：明确的 pass/fail + 逐题不符合项 + 修改建议。

### 5.4 不使用内置题库

严禁使用 session_orchestrator.py 的内置题库或 fallback。

---

## 6. Step 5：组装 session 并启动

复用 session_orchestrator.py 和 session_bootstrap.py：

```bash
python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" \
  --session-dir "<session目录>" \
  --topic "<学习主题>" \
  --plan-path "<learn-plan.md路径>" \
  --session-type today \
  --lesson-artifact-json "<lesson-artifact.json>" \
  --lesson-html-json "<lesson-html.json>" \
  --question-artifact-json "<question-artifact.json>" \
  --question-review-json "<question-review.json>"
```

产出文件：
- `lesson.md`（或 `lesson.ipynb`）
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`

启动服务并打开浏览器。如果 8080 端口被占用，先查询占用进程，告知用户，询问是否协助停掉，不要只报失败。

---

## 7. Step 6：学后复盘

用户完成网页练习后，读取 progress.json，分析答题结果。

### 7.1 复盘内容

向用户展示（终端简短输出）：

1. **本次概况**：几道题、正确率、耗时
2. **薄弱知识点**：哪些题错了、对应课件哪一节、反映了什么知识缺口
3. **具体建议**：
   - 推荐重读课件哪一节
   - 推荐读哪份资料的哪一部分（具体到章节/页面）
   - 是否需要回炉当前阶段，还是可以继续推进
4. **下次预告**：如果继续推进，下次学什么

### 7.2 更新 learn-plan.md

将学习记录追加到 learn-plan.md 的"学习记录"区块：
- 日期、主题、课件材料
- 答题概况
- 薄弱点
- 建议

### 7.3 更新 learner model

更新 `.learn-workflow/learner_model.json`：
- 各能力维度的掌握证据
- 复习债（需要回头强化什么）
- 下次优先级

### 7.4 触发动态调整（如需要）

如果连续出现同类薄弱项，主动提示用户是否需要微调计划（走 mini approval 流程，见 learn-plan Phase 3 文档）。

---

## 8. 终端输出约定

简短输出，只保留：
- session 目录
- 课件路径
- 浏览器地址
- 手动停服命令
- 加载的资料条目数
- 复盘摘要（学完后）

---

## 9. 禁止事项

- 不要把课件写成知识提纲——必须是完整的教学内容
- 不要让主 agent 写出课件正文后再派子 Agent 审课件（课件本身由主 agent 直接生成，只有题目需要双 Agent 机制）
- 不要用 session_orchestrator 内置题库替代出题+审题流程
- 不要编造资料内容或题目
- 不要跳过 check-in 直接出题
- 不要在没有加载资料的情况下生成课件
