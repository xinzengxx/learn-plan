---
name: learn-download-materials
description: 从 materials/index.json 下载可直链获取的学习材料，并回写缓存状态
---

# learn-download-materials

这是“下载学习材料”的独立 skill 入口。

## 用途

读取 `materials/index.json`，筛选可下载条目并下载到本地，然后回写缓存状态、落盘路径与时间戳。

## 执行规则

1. 确认 `materials/` 目录或 `materials/index.json` 所在位置。
2. 必须复用：

```bash
python3 "$HOME/.claude/skills/learn-plan/material_downloader.py" --materials-dir "<materials目录路径>"
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

7. 终端只输出简短下载统计与结果。
