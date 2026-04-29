---
name: learn-download-materials
description: 从 materials/index.json 下载可直链获取的学习材料，并回写缓存状态（已集成到 /learn-plan Phase 3）
---

# learn-download-materials

本 skill 保留为独立工具入口，但**在 /learn-plan 流程中已自动触发**。

## 用途

读取 `materials/index.json`，筛选可下载条目并下载到本地，然后回写缓存状态、落盘路径与时间戳。

## 执行规则

1. 确认 `materials/` 目录或 `materials/index.json` 所在位置。
2. 必须直接调用核心下载模块 `learn_materials.downloader`：

```bash
PYTHONPATH="$HOME/.claude/skills/learn-plan/learn-plan" python3 -m learn_materials.download_cli --materials-dir "<materials目录路径>"
```

3. 可选参数：
   - 指定材料：`--material-id "<材料ID>"`
   - 强制重下：`--force`
   - 模拟运行：`--dry-run`
   - 超时设置：`--timeout <秒数>`

4. 只下载以下条目：
   - `downloadable: true`
   - 或 URL 为直接文件链接（如 `.pdf`、`.md`、`.txt`、`.json`、`.csv`、`.html`）

5. 排除：
   - 需要认证的网站
   - 动态页面
   - 视频或交互式内容

6. 执行后应更新 `materials/index.json` 中的：
   - `cache_status`
   - `local_path`
   - `cached_at`
   - 失败时可记录 `download-failed` 与 `last_attempt`

## 注意

此入口主要用于**独立重新下载**或**手动维护资料缓存**的场景。日常学习流程中，资料下载会在 `/learn-plan` Phase 3 正式落盘后自动执行。
