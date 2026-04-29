# approval stage

本文件只描述 `/learn-plan` 在 approval 阶段的执行要求。

## 1. 目标

approval 的目标是在正式写盘前，把计划草案、关键 tradeoff 和 patch 决策都确认清楚。

## 2. 需要确认的内容

至少确认：
- 偏讲解 / 偏练习 / 偏项目 / 混合
- 先讲后练 / 先测后讲 / 边讲边练
- 更偏哪些题型
- 更看重速度、扎实度、项目产出还是求职匹配

## 3. 草案最小结构

计划草案至少包含：
- 学习画像
- 规划假设与约束
- 能力指标与起点判断
- 检索结论与取舍
- 阶段路线
- material curation：主线/辅助/候选/拒绝资料、片段范围、能力用途、用户起点适配、下载验证状态和 open risks
- 资料角色划分
- 掌握标准

## 4. patch review

若 `curriculum_patch_queue.json` 中存在 proposed / pending patch：
1. 列出每条 patch 的 id、topic、patch_type、rationale、confidence
2. 逐条让用户批准或拒绝
3. 把决定写入 approval state
4. 再调用 patch 应用逻辑

## 5. 输出

用户可见输出应包含：
- 计划草案
- 材料策展报告：每份资料的功能、适配目标、适配当前水平、采用片段、下载状态与风险
- 待确认 tradeoff
- 风险说明

结构化输出应可写入 `approval.json`。

## 6. 禁止事项

- 不要把草案直接写成正式 `learn-plan.md`。
- 不要在仍有关键决策未确认时把 approval 标记成完成。
- 不要在 material_curation 未经用户确认时把 `confirmed_material_strategy` 置为 true。
- 不要手动改 approval JSON 来跳过用户确认。
