---
name: learn-plan
description: 生成长期学习计划文件 learn-plan.md，并与 learn-today / learn-test / learn-download-materials 等独立 skills 协同工作
---

你是 learn-plan skill 的执行器。目标：把现有本地刷题骨架扩展为面向计算机学习的本地学习工作流，但仍复用当前 `questions.json + progress.json + 题集.html + server.py` 的 session/web 模型，不重写新系统。

# 相关独立 skills

当前学习工作流的独立入口包括：
- `/learn-plan`
- `/learn-today`
- `/learn-today-update`
- `/learn-test`
- `/learn-test-update`
- `/learn-download-materials`

当前真实主流程为：
- `/learn-plan`：顾问式澄清 → 判断是否需要 deepsearch → deepsearch 前先给用户计划并确认 → 诊断整合 → 生成正式 `learn-plan.md`
- `/learn-today` / `/learn-test`：生成 `lesson.md + session`，复用既有 `questions.json + progress.json + 题集.html + server.py` 链路
- `/learn-today-update` / `/learn-test-update`：把 session 结果回流为 `learning_state / progression / update_history`，供下一轮编排消费

兼容说明：
- 旧的 `/learn-code` 可以视为兼容别名，但当前长期计划入口为 `/learn-plan`。
- 当前学习主题建模已扩展为可配置 family，默认支持 `linux / llm-app / backend / frontend / database / algorithm / math / english / python / git / general-cs`；同时支持通过 `topic-profile.json` 或 `.learn-plan-topic-profile.json` 以 topic profile 优先覆盖 family 默认模板。
- 若主题未命中更具体 family，则回退到 `general-cs`；若存在 topic profile，则优先使用 profile 中的阶段、材料与 daily 模板。当前 `backend / frontend / database / git` 在 session 题库层可先复用 `general-cs` 通用工程题库。

# 总体原则

1. 优先最小改动，尽量复用现有本地 session 运行时。
2. `/learn-today` 与 `/learn-test` 都必须生成完整 session，并自动启动本地服务、打开页面。
3. 题目类型第一版收敛为：
   - 单选题
   - 多选题
   - 判断题
   - 编程题
   - 解答题（图片上传 + LLM 判题，暂定，仅预留字段与流程位）
4. 材料层第一版先保证“计划文件 → `materials/index.json` → session `questions.json.materials`”的元数据闭环，但正式主线资料必须优先满足“可落地到本地”的要求：
   - 主线资料优先使用已在本地或可直链下载到本地的材料
   - 若本地已存在缓存文件，则在索引中标记 `cached`
   - 无法本地化的在线资料只能作为候选或备注，不应作为正式主线阅读材料
5. 服务器必须向用户展示手动停服命令。
6. 不实现“空闲超时自动停服”。停服方式以：
   - 用户手动停服命令
   - 前端显式结束流程后的用户手动关闭
   - 可选页面关闭通知
   为主。
7. `/learn-plan` 的目标不是快速生成一份“看起来完整”的模板，而是产出可执行、高质量、能落到每日学习的长期计划。
8. 高质量学习计划必须同时满足：
   - 目标对齐：每个阶段都能解释其对用户最终目标的价值
   - 起点准确：难度从用户当前水平出发，而不是套默认零基础模板
   - 资料可执行：主线资料可本地获得
   - 粒度够细：至少细到章节；若资料有稳定页码信息，应进一步细到页码
   - 可检验：每阶段必须有明确掌握标准
   - 可日拆：长期路线必须能被 `/learn-today` 精确拆成当天安排

# 质量红线

出现以下任一情况，视为计划质量不合格，不应直接交付为正式 `learn-plan.md`：
- 只有大方向描述，没有顾问式澄清结果
- 只有路线，没有“为什么这么安排”的检索结论与取舍说明
- 主线资料大多不能落地到本地
- 只给资料名或链接，不给章节/页码/小节定位
- 阶段目标与用户目标脱节，或明显是 family 模板直接套壳
- 没有明确掌握度检验方式
- 计划内容无法被 `/learn-today` 拆成具体当日任务

# 质量验收清单

生成正式计划前，必须逐项自检：
- 是否已完成顾问式澄清，并形成结构化用户画像
- 是否已形成深度检索报告，并允许用户确认/修改
- 是否清楚说明“选哪些资料 / 不选哪些资料 / 为什么”
- 主线资料是否满足本地可用要求
- 每个阶段是否都有：目标、资料、阅读定位、练习方式、掌握标准
- 是否至少包含 4 类掌握度检验中的合理组合：
  - 阅读掌握清单
  - session 练习/测试
  - 小项目/实作
  - 口头/书面复盘
- `learn-plan.md` 是否具备供 `/learn-today` 读取的明确规则，而不是只有散文式说明

# 场景识别

## 1. /learn-plan

用途：把 `/learn-plan` 作为教练型 orchestrator 使用，而不是一次性模板生成器。最终目标仍是生成长期学习计划文件 `learn-plan.md`，但必须先经过顾问式澄清、研究决策、必要诊断与确认 gate。

处理顺序：
0. 先做 Intake / 场景识别：判断当前是 `light / diagnostic-first / research-first / mixed` 哪种 workflow mode。
   - `light`：目标和水平都清楚，且 family 模板与目标基本一致
   - `diagnostic-first`：目标相对清楚，但当前水平不可靠，必须先做最小诊断
   - `research-first`：目标涉及职业标准 / 岗位能力要求 / 材料取舍，必须先研究
   - `mixed`：既要研究也要诊断，不能直接落正式计划
   - 进入 `/learn-plan` 后，默认先按 `--mode auto` 理解当前阶段，而不是先假设最终一定要 `finalize`
1. 确认学习文件存放路径：
   - 学习根目录
   - `learn-plan.md` 路径
   - `materials/` 目录路径
   - 默认建议结构为：`<root>/learn-plan.md`、`<root>/materials/index.json`、`<root>/sessions/`
2. 先做顾问式澄清，至少收集并确认：
   - 学习主题
   - 学习目的 / 最终想达到什么能力
   - 当前水平
   - 时间/频率约束
   - 是否偏题海 / 偏讲解 / 偏测试
   - 希望如何检验是否真的掌握
   - 是否已有本地资料可直接纳入主线
   - 非目标 / 暂不进入主线的部分
3. 判断是否需要 deepsearch：
   - 若目标涉及职业标准、岗位能力要求、材料取舍不明确、family 模板可能与目标冲突，则必须先进入 deepsearch gate
4. deepsearch 前必须先给用户研究计划并确认。研究计划至少包含：
   - 计划回答哪些问题
   - 准备查看哪些类型的来源
   - 这些结果将如何影响学习路线与资料取舍
5. 完成 research 阶段后，必须单独交付一份“能力要求报告”，至少包含：
   - 为达到该学习目的需要掌握哪些能力
   - 哪些是主线能力、哪些是支撑能力、哪些可以后置
   - 为什么这么判断
   - 依据了哪些来源 / 证据
   - 这些结论会如何影响后续测试与规划
6. 必要时做最小水平诊断，而不是只信任用户自报：
   - 口头解释题 / 小测试 / 小代码题 / 基于经历反推的验证动作，至少满足一种
6. 在正式规划前，必须确认学习偏好与练习方式，而不是只问学习目标：
   - 偏讲解 / 偏练习 / 偏项目 / 混合
   - 更接受先讲后练、边讲边练，还是先测后讲
   - 更偏选择判断、小代码题、小项目、阅读复盘中的哪几类
   - 更看重速度、扎实度、项目产出还是求职匹配
7. 诊断整合后，才生成正式规划草案。草案至少应包含：
   - 用户画像
   - 规划假设与约束
   - 检索结论与取舍
   - 阶段路线
   - 资料角色划分（mainline / supporting / optional）
   - 掌握标准
8. 仅当计划通过“质量验收清单”且通过确认 gate 后，才写出正式 `learn-plan.md`
   - **禁止**在以下情况直接进入 `finalize`：
     - 仍有开放澄清问题
     - 缺少职业导向目标对应的 research 结论
     - 当前水平仍主要依赖用户自报，尚未做最小验证
     - 学习风格与练习方式尚未确认
     - 计划尚未被用户确认
9. `learn_plan.py` 的 mode 约定：
   - `auto`：根据已有输入自动推荐并切换到合适阶段
   - `draft`：仅生成候选规划状态 / 草案
   - `research-report`：输出研究问题、候选资料与取舍方向
   - `diagnostic`：输出诊断摘要或最小验证方案
   - `finalize`：仅在前置 gate 满足时写正式计划
   - 若用户当前输入仍存在开放问题、缺研究结论、缺诊断结果、缺确认结果，则应优先选择更早的 mode，而不是强行进入 `finalize`
9. 写出/更新 `materials/index.json` 后，仅在 `finalize` mode 且未跳过下载时自动执行一次材料下载器：
   - 默认执行：`python3 "$HOME/.claude/skills/learn-plan/material_downloader.py" --materials-dir "<materials目录路径>"`
10. 终端简短输出：
   - 学习主题
   - workflow mode
   - 计划文件路径
   - 材料缓存目录 / 索引路径
   - 自动下载结果摘要（如有）
   - 当前计划状态与下一步建议

执行入口：
- 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/learn_plan.py" --topic "<学习主题>" --goal "<学习目的>" --level "<当前水平>" --schedule "<时间/频率约束>" --preference "<偏题海|偏讲解|偏测试|混合>" --plan-path "<确认目录>/learn-plan.md" --materials-dir "<确认目录>/materials" --mode "<auto|draft|research-report|diagnostic|finalize>"`
- 可选中间状态输入：
  - `--clarification-json`
  - `--research-json`
  - `--diagnostic-json`
  - `--approval-json`
- 如需跳过自动下载，可追加：`--skip-material-download`

输出约定：
- `draft / research-report / diagnostic` mode 可以生成草案或中间状态，但不应视为正式主线计划
- 对于 `research-report / diagnostic`，应明确告知用户：当前交付的是中间产物，用于继续确认与判断，而不是直接进入正式执行
- `research-report` 的用户可见交付物必须是一份“能力要求报告”，而不仅仅是几条搜索结论或路线草案
- 没有完成能力要求报告时，不允许进入测试协商、能力测试或正式规划
- `research-report` 的用户可见交付物必须是一份“能力要求报告”，而不仅仅是几条搜索结论或路线草案
- 没有完成能力要求报告时，不允许进入测试协商、能力测试或正式规划
- 只有 `finalize` mode 且通过 gate 后，才固定写出正式 `learn-plan.md`
- 必须保留 `学习记录` 与 `测试记录` 区块，供 update 命令追加
- 当脚本输出 `推荐 mode` 与当前 mode 不一致时，skill 外层应优先采纳推荐 mode，而不是继续强推当前 mode
- skill 外层应把 `/learn-plan` 当作多轮工作流，而不是单轮命令：若当前输出仍是草案 / 中间产物，应继续下一轮澄清 / research / diagnostic，而不是直接结束
- 推荐的外层执行循环应为：
  1. 先用 `--mode auto` 运行 `learn_plan.py`
  2. 读取 `--stdout-json` 输出中的 `should_continue_workflow / next_action / blocking_stage / recommended_mode`
  3. 若 `should_continue_workflow = true`：
     - 根据 `blocking_stage` 继续澄清 / research / diagnostic / approval
     - 再次调用 `learn_plan.py`
  4. 只有当 `next_action = enter:/learn-today` 时，才退出 `/learn-plan` 工作流并进入执行阶段
- 外层决策树（建议强约束执行）：
  - `blocking_stage = clarification`：继续追问目标、成功标准、已有基础、非目标，不进入 research / diagnostic / finalize
  - `blocking_stage = research`：先产出研究计划并确认，再补 research 结论，不直接 finalize
  - `blocking_stage = diagnostic`：先做最小水平验证，不直接 finalize
  - `blocking_stage = approval`：先让用户确认计划草案与资料取舍，不直接 finalize
  - `blocking_stage = ready`：才允许进入 `finalize`
- 停止条件（必须同时满足）：
  - `should_continue_workflow = false`
  - `is_intermediate_product = false`
  - `next_action = enter:/learn-today`
- 若 `--stdout-json` 输出中：
  - `should_continue_workflow = true`：说明本轮不能结束，应继续进入下一轮 workflow
  - `next_action = switch_to:<mode>`：说明下一轮应切换到对应 mode
  - `next_action = enter:/learn-today`：说明当前已满足正式执行条件，可进入 `/learn-today`

材料层补充说明：
- 默认材料库主要提供可消费的元数据索引，绝大多数默认条目并不支持自动下载。
- `learn_plan.py` 先生成与下载器规则一致的 `local_path` 占位路径；真正下载完成后，`material_downloader.py` 会按实际落盘结果回写 `cache_status`、`local_path`、`cached_at`。
- `/learn-plan` 在生成完 `materials/index.json` 后会默认自动跑一遍下载器；若当前没有可直链下载条目，会显示跳过统计。
- 用户可手动向 `materials/index.json` 追加自定义可下载材料。

## 2. /learn-today

用途：基于 `learn-plan.md` 或当前上下文，生成当日学习 session。

处理顺序：
1. 确认 session 保存路径（默认建议当前目录下 `sessions/YYYY-MM-DD/`）
2. 读取主状态源：默认只读取 `learn-plan.md`。
   - `PROJECT.md` 不再作为学习系统主链路输入
   - 仅在用户明确要求做旧项目迁移时，才作为兼容参考
3. 提取今日应学习的：
   - 复习内容
   - 新学习内容
   - 相关材料元数据
   - 练习重点
4. 若当日 session 已通过完整性校验（`题集.html`、`questions.json`、`progress.json`、`server.py` 存在，且 `questions.json` / `progress.json` 结构有效），则进入“继续今日学习”
5. 否则生成：
   - `questions.json`
   - `progress.json`
   - `题集.html`
   - `server.py`
6. 生成完 `questions.json` 后，必须实际执行以下命令将 session 落地并启动，而不是只在终端口头说明：
   - 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" --session-dir "<session目录>" --topic "<学习主题>" --plan-path "<learn-plan.md路径>" --session-type today`
   - 若已单独生成 `questions.json`，也可直接调用：`python3 "$HOME/.claude/skills/learn-plan/session_bootstrap.py" --session-dir "<session目录>" --questions "<questions.json路径>"`
7. 执行后至少校验以下文件已存在：
   - `questions.json`
   - `progress.json`
   - `题集.html`
   - `server.py`
8. 启动本地服务并打开浏览器
7. 终端固定输出：
   - session 目录
   - `题集.html` / `questions.json` / `progress.json` / `server.py` 路径
   - 启动命令
   - 手动停服命令
   - 浏览器访问地址
   - 当前是否检测到 `learn-plan.md`
   - 当前载入的材料条目数

## 3. /learn-today-update

用途：基于当日 session 的 `progress.json` 汇总学习结果，并回写学习记录。

汇总至少包括：
- 主题
- 总题数
- 已练习题数
- 正确/通过题数
- 高频错误点
- 下次复习重点
- 下次新学习建议

执行入口：
- 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/learn_today_update.py" --session-dir "<session目录>" --plan-path "<learn-plan.md路径>"`

写回目标优先级：
1. `learn-plan.md` 中的学习记录 / 进度区块
2. 只有当用户明确要求兼容旧项目记录时，才额外同步更新 `PROJECT.md`

终端只输出简短摘要。

## 4. /learn-test

用途：基于当前学习进度生成测试 session。形式与 `/learn-today` 基本一致，但内容聚焦测试与复习。

支持测试模式：
- `general`：通用测试
- `weakness-focused`：针对薄弱项测试
- `mixed`：通用 + 薄弱项混合

处理顺序：
1. 确认 session 保存路径（默认建议当前目录下 `sessions/YYYY-MM-DD-test/` 或其他不冲突目录）
2. 读取 `learn-plan.md` 与历史 session 结果；仅在用户明确要求兼容旧项目时再读取 `PROJECT.md`
3. 判断测试范围：
   - 已学核心内容
   - 最近薄弱项
   - 需要回炉的概念与题型
4. 若测试 session 已通过完整性校验（`题集.html`、`questions.json`、`progress.json`、`server.py` 存在，且 `questions.json` / `progress.json` 结构有效），则进入“继续测试”
5. 否则生成：
   - `questions.json`
   - `progress.json`
   - `题集.html`
   - `server.py`
   - 如需额外元信息，可补充 `test.json`，但不能替代主文件
6. 生成完 `questions.json` 后，必须实际执行以下命令将 session 落地并启动，而不是只在终端口头说明：
   - 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" --session-dir "<session目录>" --topic "<学习主题>" --plan-path "<learn-plan.md路径>" --session-type test --test-mode "<general|weakness-focused|mixed>"`
   - 若已单独生成 `questions.json`，也可直接调用：`python3 "$HOME/.claude/skills/learn-plan/session_bootstrap.py" --session-dir "<session目录>" --questions "<questions.json路径>" --session-type test --test-mode "<general|weakness-focused|mixed>"`
7. 执行后至少校验以下文件已存在：
   - `questions.json`
   - `progress.json`
   - `题集.html`
   - `server.py`
8. 启动本地服务并打开浏览器
9. 终端固定输出：
   - session 目录
   - 关键文件路径
   - 测试模式
   - 启动命令
   - 手动停服命令
   - 浏览器访问地址

## 5. /learn-test-update

用途：基于测试 session 的 `progress.json` 更新当前水平判断与后续学习建议。

至少输出：
- 本次测试覆盖范围
- 总体表现
- 薄弱项
- 是否应回退复习
- 是否可以进入下一阶段

执行入口：
- 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/learn_test_update.py" --session-dir "<session目录>" --plan-path "<learn-plan.md路径>"`

写回目标：
- 默认只更新 `learn-plan.md` 中的进度、当前水平、后续建议
- 仅在用户明确要求兼容旧项目时，才同步更新 `PROJECT.md`

终端只输出简短摘要。

## 6. /learn-download-materials

用途：从 `materials/index.json` 下载可下载的材料到本地。

处理顺序：
1. 读取 `materials/index.json`
2. 筛选标记为可下载的材料（`downloadable: true` 或 URL 为直接文件链接）
3. 下载到 `materials/{domain}/{kind}/` 子目录
4. 更新 `index.json` 的缓存状态与本地路径
5. 输出下载统计

执行入口：
- 推荐入口：`python3 "$HOME/.claude/skills/learn-plan/material_downloader.py" --materials-dir "<materials目录路径>"`
- 指定材料：`--material-id "<材料ID>"`
- 强制重新下载：`--force`
- 模拟运行：`--dry-run`
- 超时设置：`--timeout <秒数>`

输出约定：
- 终端输出：下载进度、成功/失败消息、统计信息
- 更新 `materials/index.json` 的 `cache_status`、`local_path`、`cached_at` 字段
- 失败时记录 `download-failed` 状态与 `last_attempt` 时间

材料下载规则：
- 只下载 `downloadable: true` 或 URL 为直接文件链接（`.pdf`、`.md`、`.txt`、`.json`、`.csv`、`.html` 等）的材料
- 排除需要认证的站点（LeetCode、Khan Academy、Coursera 等）
- 排除动态内容（视频、交互式页面）
- 本地路径格式：`materials/{domain}/{kind}/{id}_{title}{ext}`

# 继续 session 规则

当以下文件同时存在，且 `questions.json` / `progress.json` 结构校验通过时，视为完整 session：
- `题集.html`
- `questions.json`
- `progress.json`
- `server.py`

行为：
- 直接调用 `session_bootstrap.py` 指向该 session 目录
- 启动该 session 下的 `server.py`
- 打开浏览器
- 不重新生成题目
- 当前运行时固定使用单一端口（默认 `8080`）；若已有其他 session 占用该端口，应先 `POST /shutdown` 或手动停服，再切换到新 session

若仅缺 `progress.json`：
- 允许使用模板重建空进度文件

若缺少 `题集.html` 或 `questions.json`：
- 视为 session 不完整
- 回退到“新建 session”场景并重建

# 文件与目录约定

skill 根目录：
- `~/.claude/skills/learn-plan/`

模板文件：
- `templates/server.py`
- `templates/progress_template.json`
- `templates/题集模板.html`

运行时目录：
- `sessions/YYYY-MM-DD/题集.html`
- `sessions/YYYY-MM-DD/questions.json`
- `sessions/YYYY-MM-DD/progress.json`
- `sessions/YYYY-MM-DD/server.py`

可选计划与缓存文件：
- `learn-plan.md`
- `materials/`
- `materials/index.json`

# 题目生成规则

## 概念题
数量：7-11 道
类型分布：
- 单选 3-5 道
- 多选 2-3 道
- 判断 2-3 道

要求：
- 围绕当日复习 + 新学习主题，或测试范围生成
- 题干清晰
- 有标准答案
- 有简短解析

## 代码题
数量：7-12 道
类型：第一版以 `function` 题为主，贴近 LeetCode 模式。
难度分布：
- easy 3-5 道
- medium 3-5 道
- project 1-2 道

要求：
- 给出固定函数名
- 给出 starter code
- 给出 test_cases
- test_cases 以函数调用参数和 expected 为主
- 可选保留 `script` 扩展字段，但第一版主流程按 `function` 生成

## 解答题（预留）
- 第一版允许在 schema 中预留字段
- 页面可暂不实现完整批改工作流
- 若生成，必须明确标注为实验能力

# questions.json 结构要求

必须生成统一结构，至少包含：
- `date`
- `topic`
- `mode`
- `session_type`：`today | test`
- `session_intent`：`learning | assessment | plan-diagnostic`
- `assessment_kind`：`stage-test | plan-diagnostic | null`
- `test_mode`：`general | weakness-focused | mixed | null`
- `plan_source`
- `materials`
- `questions`

每题必须有唯一 `id`。

概念题用：
- `category: concept`
- `type: single | multi | judge`

代码题用：
- `category: code`
- `type: function`
- `title`
- `prompt`
- `function_name`
- `params`
- `starter_code`
- `solution_code`
- `test_cases`

解答题预留可用：
- `category: open`
- `type: written`
- `prompt`
- `reference_points`
- `grading_hint`

# progress.json 结构要求

必须兼容可重复练习与历史记录，并保留 session 元信息：
- `date`
- `topic`
- `session`
- `summary.total`
- `summary.attempted`
- `summary.correct`
- `questions.<id>.stats`
- `questions.<id>.history`

推荐 `session` 字段：
- `type`: `today | test`
- `intent`: `learning | assessment | plan-diagnostic`
- `assessment_kind`: `stage-test | plan-diagnostic | null`
- `plan_execution_mode`: `normal | clarification | research | diagnostic | test-diagnostic | prestudy | null`
- `test_mode`: `general | weakness-focused | mixed | null`
- `status`: `active | finished`
- `started_at`
- `finished_at`
- `plan_path`
- `materials`

约束：
- 页面加载时只展示统计，不自动恢复历史答案或历史代码
- 历史详情通过记录面板查看
- 概念题历史记录不直接展示历史答案，只记录正确/错误与时间
- 代码题历史记录保存代码、结果、时间
- 显式结束 session 时，应把 `finished_at` / `status` 写回 `progress.json`

# 前端页面要求

模板页继续贴近 LeetCode 风格，但文案应从“刷题器”扩为“学习/测试 session”。

必须满足：
1. 首页仍是题目总览
2. 概念题页默认干净作答态
3. 概念题历史记录入口只显示正确/错误，不显示历史答案
4. 代码题页编辑区要更大
5. 代码区要有行号
6. 代码区要有关键字高亮
7. 提交记录页左侧列表、右侧详情
8. 保留深色主题，并支持浅色淡奶黄主题切换
9. `/learn-today` 与 `/learn-test` 共用同一套页面模板，只根据 `session_type` / `test_mode` 切换文案
10. 若属于长期训练项目，热力图应优先基于 `sessions/*/progress.json` 渲染真实多天数据
11. 页面要有显式结束入口：`结束今日学习` / `结束本次测试`

# 后端接口要求

复用并补齐：
- `GET /progress`
- `POST /progress`
- `POST /run`
- `POST /submit`
- `GET /server-info`
- `POST /heartbeat`
- `POST /finish`
- `POST /shutdown`

判题规则：
- `function` 题：执行用户代码，调用目标函数，比较 `expected`
- `script` 题：仅保留兼容能力

服务端行为补充：
- 页面加载后应有心跳机制
- 页面可在关闭时尝试通知服务端
- 不实现空闲超时自动停服
- 启动时必须向用户显示手动停服命令
- 端口占用时应输出友好提示，不直接抛原始 traceback

# 边界说明
- 这是本地单用户学习工具
- 代码会在本机 Python 环境执行
- 只适用于运行自己信任的题目数据
- 不需要实现安全沙箱

# 执行风格
- 优先最小改动
- 生成失败时先校验 JSON 结构，必要时重生成一次
- 最终终端输出保持简短：
  - 生成 / 继续 / 完成 的结论
  - 关键文件路径
  - 浏览器访问地址（若已启动）
  - 手动停服命令（若已启动）
