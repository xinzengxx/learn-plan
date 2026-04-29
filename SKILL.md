---
name: learn-plan
description: 生成长期学习计划文件 learn-plan.md，并以三轮递进方式衔接 /learn-today 和 /learn-test
---

# /learn-plan root entry

这是本机 Claude Code 的 `/learn-plan` skill 入口 shim。

实际实现位于：

```text
$HOME/.claude/skills/learn-plan/learn-plan/SKILL.md
```

执行 `/learn-plan` 时必须先读取并遵循该文件；所有实现脚本、文档、模板、测试与前端资源也都以：

```text
$HOME/.claude/skills/learn-plan/learn-plan
```

作为 skill 根目录。

不要把当前目录下的仓库顶层当作学习系统运行根；它只是发布仓库的多 skill 容器。

## 学习系统入口

当前学习系统共 3 个核心入口：

| 入口 | 职责 |
|---|---|
| `/learn-plan` | 三轮递进式学习顾问：深挖需求+检索资料 → 可选诊断 → 出规划 |
| `/learn-today` | 今日学习教师：课件 + 练习题 + 复盘，学完自动更新进度 |
| `/learn-test` | 阶段测试：出题 + 测试 + 复盘，测完自动更新 learner model |

更新回写已收口到主流程：
- 今日学习复盘 → `/learn-today` Step 6
- 测试复盘 → `/learn-test` Step 4

以下工具入口仍保留：
- `/learn-download-materials` → 独立材料缓存维护工具；日常流程中也会在 `/learn-plan` Phase 3 自动触发一次
