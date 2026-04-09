---
name: learn-today
description: 基于 learn-plan.md 生成并启动今日学习 session，复用 learn-plan 目录下的 session_orchestrator.py 与 session_bootstrap.py
---

# learn-today

这是“开始今日学习”的独立 skill 入口。

## 用途

基于当前目录下的 `learn-plan.md`（若存在）与已有 session 历史，先生成当天的教师型学习安排文件 `lesson.md`，再根据当天类型决定是继续/新建学习 session，还是仅输出教学计划。

## 关键约束

- 必须复用 `$HOME/.claude/skills/learn-plan/session_orchestrator.py` 与 `$HOME/.claude/skills/learn-plan/session_bootstrap.py`
- 不重写新的 session 运行时
- 输出结构必须继续使用：`questions.json`、`progress.json`、`题集.html`、`server.py`
- 若当日 session 已通过完整性校验，应继续该 session，而不是重建

## 执行规则

1. 确认学习根目录与 session 保存目录（默认 `./sessions/YYYY-MM-DD/`）。
2. 优先读取当前目录下的 `learn-plan.md`；若存在 `PROJECT.md` 也一并参考。
3. 默认先做一次进度 check-in，再决定今天学什么。至少应确认：
   - 上次计划中的阅读内容完成了多少
   - 哪些章节/页码/资料段落已完成，哪些未完成
   - 当前最大的卡点是什么
   - 今天大概有多少时间
   - 是否更想优先复习、推进新内容、还是先解决卡点
4. `/learn-today` 的默认主产物是当天教学计划文件：`lesson.md`。该文件必须至少包含：
   - 今日定位
   - 今日具体学习任务（细到书名/章节/页码/小节或 repo 目录）
   - 今日讲解摘要
   - 阅读指导
   - 今日练习安排
   - 今日完成标准
   - 学完后反馈
5. 今日安排不能只机械读取最后一个 day block，而应综合：
   - `learn-plan.md` 中的长期路线与今日生成规则
   - 历史 `progress.json`
   - 用户刚刚反馈的真实进度
   - 当天 selected segments 对应的资料内容与讲解需求
6. 若 session 目录中以下文件都存在，且 `questions.json` / `progress.json` 结构校验通过，则视为完整 session：
   - `题集.html`
   - `questions.json`
   - `progress.json`
   - `server.py`
6. 完整 session 直接继续；否则调用：

```bash
python3 "$HOME/.claude/skills/learn-plan/session_orchestrator.py" --session-dir "<session目录>" --topic "<学习主题>" --plan-path "<learn-plan.md路径>" --session-type today
```

7. 若已有 `questions.json` 但缺运行时文件，也可调用：

```bash
python3 "$HOME/.claude/skills/learn-plan/session_bootstrap.py" --session-dir "<session目录>" --questions "<questions.json路径>"
```

8. 执行后至少校验：
   - `questions.json`
   - `progress.json`
   - `题集.html`
   - `server.py`
9. 必须启动服务并打开浏览器。
   - 若遇到 8080 端口占用，不要只报失败。
   - 应先探测当前占用进程（至少给出 PID/命令或已运行 session 信息）。
   - 先告知用户当前是什么占用了 8080，并询问是否需要协助停掉后再启动学习服务。
10. 终端只做简短输出：
   - session 目录
   - 关键文件路径
   - 浏览器地址
   - 手动停服命令
   - 是否检测到 `learn-plan.md` / `PROJECT.md`
   - 载入的材料条目数
