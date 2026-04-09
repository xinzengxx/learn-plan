---
name: learn-today-update
description: 基于当日 session 的 progress.json 汇总学习结果，并回写到 learn-plan.md
---

# learn-today-update

这是“完成今日学习后更新计划”的独立 skill 入口。

## 用途

读取当日 session 的 `progress.json`，汇总本次学习结果，并将结果回写到 `learn-plan.md` 的学习记录区块；如果当前项目明确使用 `PROJECT.md` 维护学习日志，也可同步更新。

## 执行规则

1. 确认要汇总的 session 目录。
2. 优先读取当前目录下的 `learn-plan.md`；若存在 `PROJECT.md` 且项目明确使用它维护学习记录，也可同步写回。
3. 必须复用：

```bash
python3 "$HOME/.claude/skills/learn-plan/learn_today_update.py" --session-dir "<session目录>" --plan-path "<learn-plan.md路径>"
```

4. 若需要同步项目记录，可追加：

```bash
--project-path "<PROJECT.md路径>"
```

5. 汇总至少包含：
   - 主题
   - 总题数
   - 已练习题数
   - 正确/通过题数
   - 高频错误点
   - 下次复习重点
   - 下次新学习建议

6. 终端只输出简短摘要，不展开长报告。
