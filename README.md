# learn-plan skills

面向 Claude Code 的多-skill 本地学习工作流。

这个仓库不是单个 skill，而是一整套协同工作的 skills。安装完成后，你会得到这些命令：

- `/learn-plan`
- `/learn-today`
- `/learn-today-update`
- `/learn-test`
- `/learn-test-update`
- `/learn-download-materials`

其中：
- `learn-plan/` 是主实现目录，包含 Python 脚本、模板和 Monaco 编辑器资源
- 其他 `learn-*` 目录是独立 skill 入口，复用 `learn-plan/` 下的脚本

## 仓库结构

```text
learn-plan-skills/
├── README.md
├── learn-plan/
│   ├── SKILL.md
│   ├── README.md
│   ├── learn_plan.py
│   ├── session_orchestrator.py
│   ├── session_bootstrap.py
│   ├── learn_today_update.py
│   ├── learn_test_update.py
│   ├── material_downloader.py
│   ├── templates/
│   └── node_modules/monaco-editor/
├── learn-today/
│   └── SKILL.md
├── learn-today-update/
│   └── SKILL.md
├── learn-test/
│   └── SKILL.md
├── learn-test-update/
│   └── SKILL.md
└── learn-download-materials/
    └── SKILL.md
```

## 环境要求

- Claude Code
- Python 3.8+
- `conda`，且可执行 `conda run -n base python ...`
- macOS 推荐使用（当前自动开浏览器走 `open`）
- 如需自动下载材料，需要网络访问

说明：
- 当前服务启动命令固定为 `conda run -n base python server.py`
- 当前自动打开浏览器使用 macOS `open`
- 如果你在 Linux/Windows 上使用，可能需要自行调整 `learn-plan/session_bootstrap.py`

## 安装方式

### 方式一：推荐，使用 symlink

```bash
mkdir -p ~/.claude/skills
cd ~
git clone https://github.com/BDLab-XZ/learn-plan.git learn-plan-skills

ln -s ~/learn-plan-skills/learn-plan ~/.claude/skills/learn-plan
ln -s ~/learn-plan-skills/learn-today ~/.claude/skills/learn-today
ln -s ~/learn-plan-skills/learn-today-update ~/.claude/skills/learn-today-update
ln -s ~/learn-plan-skills/learn-test ~/.claude/skills/learn-test
ln -s ~/learn-plan-skills/learn-test-update ~/.claude/skills/learn-test-update
ln -s ~/learn-plan-skills/learn-download-materials ~/.claude/skills/learn-download-materials
```

### 方式二：直接复制目录

```bash
mkdir -p ~/.claude/skills
cd ~
git clone https://github.com/BDLab-XZ/learn-plan.git learn-plan-skills

cp -R ~/learn-plan-skills/learn-plan ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-today ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-today-update ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-test ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-test-update ~/.claude/skills/
cp -R ~/learn-plan-skills/learn-download-materials ~/.claude/skills/
```

## 重要安装约束

- `learn-plan` 目录名不能改。wrapper skills 通过固定路径调用：`$HOME/.claude/skills/learn-plan/...`
- Claude Code 识别的是 `~/.claude/skills/<skill-name>/SKILL.md`
- 只安装 `learn-plan/` 不等于完整安装。若你还想直接使用 `/learn-today`、`/learn-test` 等命令，必须连同其他 skill 目录一起安装

## 最小验收流程

在一个空学习目录里执行：

```bash
mkdir -p ~/learning/algorithm
cd ~/learning/algorithm
```

然后在 Claude Code 中依次运行：

1. `/learn-plan`
2. `/learn-today`
3. `/learn-today-update`
4. `/learn-test`
5. `/learn-test-update`
6. `/learn-download-materials`（可选）

预期至少会出现这些运行时产物：

```text
learn-plan.md
materials/index.json
sessions/YYYY-MM-DD/lesson.md
sessions/YYYY-MM-DD/questions.json
sessions/YYYY-MM-DD/progress.json
sessions/YYYY-MM-DD/题集.html
sessions/YYYY-MM-DD/server.py
sessions/YYYY-MM-DD-test/questions.json
sessions/YYYY-MM-DD-test/progress.json
sessions/YYYY-MM-DD-test/题集.html
sessions/YYYY-MM-DD-test/server.py
```

## 功能说明

### `/learn-plan`
创建或更新长期学习计划，输出 `learn-plan.md`，并生成 `materials/index.json`。

### `/learn-today`
基于 `learn-plan.md` 生成当日学习 session，主产物是 `lesson.md`，同时生成并启动：
- `questions.json`
- `progress.json`
- `题集.html`
- `server.py`

### `/learn-today-update`
读取当日 session 的 `progress.json`，把学习结果回写到 `learn-plan.md`。

### `/learn-test`
生成阶段测试 session，支持：
- `general`
- `weakness-focused`
- `mixed`

### `/learn-test-update`
读取测试 session 的 `progress.json`，更新当前水平判断、薄弱项和后续建议。

### `/learn-download-materials`
从 `materials/index.json` 下载可直链获取的学习材料，并回写缓存状态。

## Monaco 编辑器资源

仓库已自带 `learn-plan/node_modules/monaco-editor`，安装后 `session_bootstrap.py` 会优先复制仓库内置资源，不再依赖你本机历史学习目录中的旧文件。

## 已知边界

- 本工具是本地单用户学习工具，不提供安全沙箱
- 代码题会在本机 Python 环境执行，只适用于可信题目数据
- 大部分默认材料是在线资源元数据，不支持自动下载
- 若 8080 端口已被占用，session 启动会失败并提示占用信息

## 开发说明

主实现都在 `learn-plan/` 目录下：
- 扩展材料库：编辑 `learn-plan/learn_plan.py`
- 调整 session 编排：编辑 `learn-plan/session_orchestrator.py`
- 调整运行时落地与启动：编辑 `learn-plan/session_bootstrap.py`
- 调整前端模板：编辑 `learn-plan/frontend/src/`（Vue SPA）

## License

个人学习工具，不提供任何担保。使用者自行承担风险。
