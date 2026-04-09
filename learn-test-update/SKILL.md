---
name: learn-test-update
description: 基于测试 session 的 progress.json 更新当前水平判断与后续学习建议，并回写到 learn-plan.md
---

# learn-test-update

这是“测试完成后更新计划”的独立 skill 入口。

## 用途

读取测试 session 的 `progress.json`，分析测试结果，并更新 `learn-plan.md` 中的当前水平判断、薄弱项和后续学习建议；如果项目明确使用 `PROJECT.md` 跟踪学习，也可同步更新。

## 执行规则

1. 确认测试 session 目录。
2. 优先读取当前目录下的 `learn-plan.md`；若有项目级学习跟踪，也可读取 `PROJECT.md`。
3. 必须复用：

```bash
python3 "$HOME/.claude/skills/learn-plan/learn_test_update.py" --session-dir "<session目录>" --plan-path "<learn-plan.md路径>"
```

4. 若需要同步项目记录，可追加：

```bash
--project-path "<PROJECT.md路径>"
```

5. 输出至少覆盖：
   - 本次测试覆盖范围
   - 总体表现
   - 薄弱项
   - 是否应回退复习
   - 是否可以进入下一阶段

6. 终端只输出简短摘要。
