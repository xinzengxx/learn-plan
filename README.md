# learn-plan Skill

本地计算机学习工作流，支持更通用的计算机学习主题建模，可用于 Linux、LLM 应用开发、算法、数学、英语以及更广义的工程方向的学习计划、每日练习、阶段测试与材料管理。

## 命令结构说明

当前这套工作流采用“多个独立 skills 协同”的方式，而不是单个 skill 自动派生命令。

已提供的独立入口包括：
- `/learn-plan`：创建或更新长期学习计划
- `/learn-today`：生成并启动今日学习 session
- `/learn-today-update`：回写今日学习结果
- `/learn-test`：生成并启动测试 session
- `/learn-test-update`：回写测试结果
- `/learn-download-materials`：下载材料索引中可直链获取的材料

其中，`learn-plan` 目录仍是这套工作流的主要实现目录，其他 `learn-*` skills 作为轻量包装入口复用其中脚本。

## 快速开始

## 质量要求

`/learn-plan` 的目标不是快速生成一份模板，而是生成真正可执行、可验证、能落到每日学习的长期计划。

高质量学习计划至少要满足：
- 目标对齐：阶段安排必须服务用户真实目标
- 起点准确：从用户当前水平出发，不套默认零基础模板
- 资料可执行：主线资料可在本地获得
- 粒度够细：至少细到章节；有稳定页码时进一步细到页码
- 可检验：每阶段都能说明如何证明“真的掌握了”
- 可日拆：长期路线必须能被 `/learn-today` 精确拆成当天安排

出现以下情况，视为质量不合格：
- 只有路线，没有顾问式澄清与检索结论
- 主线资料大多无法本地获取
- 只有书名/链接，没有章节页码定位
- 阶段目标和用户目标脱节
- 没有掌握度检验方式
- `/learn-today` 无法据此产出具体当日计划

### 1. 创建学习计划

```bash
# 在你确认好的学习根目录下执行
cd ~/learning/algorithm

# 生成学习计划（默认写到当前根目录下的 learn-plan.md / materials / sessions）
/learn-plan
```

`/learn-plan` 不应再被理解为“一次性模板生成器”，而应按以下 workflow 工作：
1. 先做顾问式澄清
2. 判断是否需要 deepsearch
3. deepsearch 前先给用户研究计划并确认
4. 必要时做最小水平诊断
5. 在正式规划前确认学习偏好与练习方式
6. 诊断整合后生成正式计划草案
7. 通过确认 gate 后，才写正式 `learn-plan.md`
8. 若当前输出仍是 `draft / research-report / diagnostic`，应继续进入下一轮，而不是直接把结果当正式计划使用

因此，`learn_plan.py` 的执行 mode 也分为：
- `auto`：根据已有输入自动推荐并切换到合适阶段
- `draft`：候选规划状态 / 草案
- `research-report`：研究计划或研究摘要
- `diagnostic`：诊断摘要或最小验证方案
- `finalize`：正式落盘

推荐外层循环是：
1. 先用 `auto`
2. 读取脚本返回的 `recommended_mode / blocking_stage / should_continue_workflow / next_action`
3. 若仍是中间产物，则继续下一轮澄清 / research / diagnostic / approval
4. 只有当脚本明确返回可进入 `/learn-today` 时，才进入正式执行

更直接地说：
- `blocking_stage = clarification`：继续顾问式追问
- `blocking_stage = research`：继续研究计划 / 研究摘要确认
- `blocking_stage = diagnostic`：继续最小水平验证
- `blocking_stage = approval`：继续计划确认
- `blocking_stage = ready`：进入正式执行

Claude 在 `/learn-plan` 中至少应先询问并确认：
- 学习文件存放根目录
- 学习主题
- 学习目的 / 最终想达到什么能力
- 当前水平
- 时间/频率约束
- 学习偏好
- 希望如何检验是否真的掌握
- 是否已有本地资料可直接纳入主线

确认目录后，默认按以下结构生成：
- `<root>/learn-plan.md`：学习计划文件
- `<root>/materials/index.json`：材料索引
- `<root>/materials/`：材料存储位置
- `<root>/sessions/`：后续学习 session 目录

生成 `materials/index.json` 后，会自动尝试下载一遍可直链下载的材料。

说明：
- 当前主题识别改为可扩展 family，已内置支持 `linux / llm-app / backend / frontend / database / algorithm / math / english / general-cs`。
- 若主题未命中更具体 family，会回退到 `general-cs`，不再默认落入 `algorithm`。
- 目前 `linux / llm-app / algorithm / math / english / general-cs` 已有专用或通用 session 题库；`backend / frontend / database` 在 session 层暂回退到 `general-cs` 工程通识题库。
- `/learn-plan` 默认会在索引生成后自动执行一次材料下载；若没有可直链下载条目，会正常显示跳过统计。

### 2. 开始每日学习

```bash
/learn-today
```

自动生成当日学习 session，包含：
- `lesson.md` 教学讲义
- 复习题（基于历史错题与薄弱点）
- 新知识题（按计划推进）
- 本地服务器自动启动
- 浏览器自动打开学习界面

### 3. 完成学习后更新计划

```bash
/learn-today-update
```

自动分析本次学习表现，更新 `learn-plan.md` 的学习记录，包括：
- 高频错误点
- 下次复习重点
- 下次新学习建议

### 4. 阶段测试

```bash
/learn-test
```

生成阶段测试 session，支持三种模式：
- `general`：全面测试
- `weakness-focused`：针对薄弱项
- `mixed`：混合模式

### 5. 测试后更新计划

```bash
/learn-test-update
```

分析测试结果，给出：
- 薄弱项诊断
- 是否应回退复习
- 是否可进入下一阶段

### 6. 下载学习材料（可选）

```bash
/learn-download-materials
```

下载 `materials/index.json` 中可直接下载的材料。

注意：
- 大部分默认材料是在线资源元数据，不支持自动下载。
- 只有 `downloadable: true` 或 URL 本身是直接文件链接时，下载器才会实际下载。

## 完整工作流示例

```bash
# 第一天：创建计划
cd ~/learning/algorithm
/learn-plan
# 回答问题：算法基础、准备面试、有基础但不系统、每天1小时、混合

# 第二天：开始学习
/learn-today
# 在浏览器中完成题目
# 完成后在终端执行：
/learn-today-update

# 第三天：继续学习
/learn-today
# 完成后更新
/learn-today-update

# 一周后：阶段测试
/learn-test
# 完成后更新
/learn-test-update

# 如果你在 materials/index.json 中额外加入了可下载材料：
/learn-download-materials

# 根据测试结果决定：
# - 如果薄弱项明显 → 继续 /learn-today 巩固
# - 如果表现稳定 → 进入下一阶段主题
```

## 目录结构

```text
learning/topic/
├── learn-plan.md              # 学习计划
├── materials/                 # 材料目录
│   ├── index.json             # 材料索引
│   ├── linux/                 # Linux / Shell / 系统类材料
│   ├── llm-app/               # LLM 应用开发材料
│   ├── algorithm/             # 算法材料
│   ├── math/                  # 数学材料
│   ├── english/               # 英语材料
│   └── general-cs/            # 通用计算机基础/工程材料
└── sessions/                  # 学习 session 目录
   ├── 2026-04-02/            # 每日学习 session
   │   ├── lesson.md
   │   ├── questions.json
   │   ├── progress.json
   │   ├── 题集.html
   │   └── server.py
   └── 2026-04-02-test/       # 测试 session
       ├── lesson.md
       ├── questions.json
       ├── progress.json
       ├── 题集.html
       └── server.py
```

说明：
- 学习系统默认以 `learn-plan.md` 作为唯一主状态源。
- `PROJECT.md` 不再作为学习系统主链路输入；仅在用户明确要求兼容旧项目记录时，才作为可选参考。
- `learn_plan.py` 会先在 `materials/index.json` 中写入与下载器规则一致的 `local_path` 占位路径。
- 真正下载完成后，`material_downloader.py` 会把实际落盘路径与缓存状态写回索引。

## 题型支持

- **单选题**：概念理解、知识点辨析
- **多选题**：综合判断、多维度考察
- **判断题**：快速检验基础认知
- **编程题**：函数实现、算法应用
- **解答题**：（预留，暂未实现）

## 材料管理

### 默认材料库

当前材料库按 topic family 组织，已内置：

- **linux**：Linux Journey、The Linux Command、ArchWiki、DigitalOcean Community（以元数据索引为主）
- **llm-app**：Anthropic Docs、LangChain Docs、LangGraph Docs、LlamaIndex Docs、Prompting Guide、RAG/评测相关公开资料
- **algorithm**：LeetCode Study Plan、OI Wiki、NeetCode Roadmap、VisuAlgo
- **math**：Khan Academy Math、Paul's Online Math Notes、OpenStax、3Blue1Brown
- **english**：Cambridge Dictionary、Grammarly Handbook、Purdue OWL、VOA Learning English
- **general-cs**：MDN HTTP、Git 官方文档、Docker Docs、Postman Learning Center 等工程通识材料

说明：
- `backend / frontend / database` 当前在计划与材料层可独立识别。
- 若 session 题库暂未为这些 family 单独建模，会先回退到 `general-cs` 通用工程题库，而不是算法题。

### 材料下载

大部分默认材料为在线资源（需认证、动态页面或交互式内容），不支持自动下载。

下载器的规则是：
- 只下载 `downloadable: true` 的材料，或 URL 本身就是直接文件链接（如 `.pdf`、`.md`、`.txt`、`.json`）
- 排除认证站点与动态内容
- 成功后回写 `cache_status`、`local_path`、`cached_at`

如需添加可下载材料，在 `materials/index.json` 中添加：

```json
{
  "id": "custom-material",
  "title": "自定义材料",
  "kind": "tutorial",
  "url": "https://example.com/material.pdf",
  "downloadable": true,
  "tags": ["algorithm", "tutorial"]
}
```

然后执行 `/learn-download-materials` 下载。

## 服务器管理

### 启动服务

`/learn-today` 和 `/learn-test` 会自动启动本地服务器（端口 8080）。

### 手动停服

```bash
# 方式 1：在服务器终端按 Ctrl+C

# 方式 2：查找并终止进程
pkill -f 'server.py'

# 方式 3：查看端口占用并终止
lsof -ti:8080 | xargs kill
```

### 端口占用

如果端口 8080 已被占用，服务器会提示并退出。先停止已有服务再重新启动。

## 常见问题

### Q: 如何切换学习主题？

A: 在新目录下执行 `/learn-plan` 创建新计划，或在现有 `learn-plan.md` 中手动修改主题后继续使用。

### Q: 学习系统还会默认读 PROJECT.md 吗？

A: 不会。当前学习系统默认只以 `learn-plan.md` 为主状态源。只有你明确要求兼容旧项目记录时，才会额外使用 `PROJECT.md`。

### Q: 如何重置学习进度？

A: 删除 `sessions/` 目录，保留 `learn-plan.md` 和 `materials/`，重新开始 `/learn-today`。

### Q: 如何自定义题目？

A: 暂不支持手动添加题目。题目由 Claude 根据学习计划和历史表现动态生成。

### Q: 材料下载失败怎么办？

A: 先确认该材料是否真的是直接文件链接；如果不是，通常需要手动下载。手动下载后可放入对应 `materials/{domain}/{kind}/` 目录，并更新 `index.json` 的 `local_path` 字段。

### Q: Linux、LangChain 或更广义的计算机主题能直接走这个 skill 吗？

A: 可以。当前已支持 topic family 识别：`linux / llm-app / backend / frontend / database / algorithm / math / english / general-cs`。若主题未命中更具体 family，会回退到 `general-cs`，不会再默认落到算法题路径。

### Q: 如何备份学习数据？

A: 备份整个学习目录即可，包含计划、材料索引和所有 session 数据。

## 技术栈

- **后端**：Python 3.8+，标准库 HTTP 服务器
- **前端**：原生 HTML/CSS/JavaScript，Monaco Editor
- **数据**：JSON 文件存储
- **判题**：本地 Python 执行（仅适用于可信代码）

## 安全提示

- 本工具在本地执行用户代码，仅适用于自己信任的题目数据
- 不实现安全沙箱，不适合运行不可信代码
- 建议在隔离环境（如虚拟机或容器）中使用

## 开发与扩展

### 添加新题型

编辑 `session_orchestrator.py` 的题库生成函数，添加新的题目模板。

### 自定义前端样式

编辑 `templates/题集模板.html` 的 CSS 变量部分。

### 扩展材料库

优先编辑 `learn_plan.py` 中的 `TOPIC_FAMILIES` 配置，为对应 family 补充：
- `keywords`
- `stages`
- `materials`

若只想补充本地项目自己的材料，也可以直接编辑 `materials/index.json`。

## 许可

本 skill 为个人学习工具，不提供任何担保。使用者自行承担风险。
