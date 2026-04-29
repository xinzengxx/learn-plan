# finalize stage

本文件只描述 `/learn-plan` 在 finalize 阶段的执行要求。

## 1. 目标

finalize 的目标是仅在所有 gate 放行后，正式写出长期学习计划与材料索引。

## 2. 前置条件

只有满足以下条件才允许正式写盘：
- clarification 完成
- 必要 research 完成
- diagnostic 完成
- approval 完成
- material curation 已确认：主线/辅助/候选/拒绝资料、片段范围、下载验证状态与 open risks 已经由用户确认
- 通过质量验收清单

## 3. 正式产物

正式输出包括：
- `learn-plan.md`
- `materials/index.json`
- 可选自动下载结果摘要

## 4. 执行规则

- 应调用 `learn_plan.py --mode finalize`。
- 只有代码 gate 能放行正式写盘。
- 生成 `materials/index.json` 后，仅在 finalize 且未跳过下载时执行一次材料下载。

## 5. 输出

终端只保留：
- 正式产物路径
- 自动下载摘要
- 下一步 `/learn-today` 提示

## 6. 禁止事项

- 不要手写正式 `learn-plan.md` 绕过 gate。
- 不要把中间态直接当正式计划。
- 不要在 `blocking_stage != ready` 时强推 finalize。
