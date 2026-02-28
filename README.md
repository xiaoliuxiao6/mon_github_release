# GitHub Release & Commit Monitor

自动监控指定 GitHub 仓库的最新 Release 和 Commit，通过 Discord Webhook 推送通知。

## 架构

```
GitHub Actions Workflow (每 5 分钟定时触发)
  └─ Python 脚本 (monitor.py)
       ├─ 读取 config.json 中的目标仓库列表
       ├─ 通过 GitHub API 查询最新 release / commit
       ├─ 对比 state.json 缓存记录（避免重复推送）
       ├─ 格式化为 Discord Embed 消息
       └─ 通过 Discord Webhook 推送通知
```

## 快速开始

### 1. Fork / Clone 本仓库

### 2. 配置目标仓库

编辑 `config.json`，修改 `repos` 列表为你想监控的仓库：

```json
{
  "repos": [
    "facebook/react",
    "vuejs/core",
    "vercel/next.js"
  ],
  "check_releases": true,
  "check_commits": true
}
```

- **check_releases** — 是否监控新 Release
- **check_commits** — 是否监控新 Commit（默认分支最新一条）

### 3. 配置 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|---|---|
| `DISCORD_WEBHOOK_URL` | Discord 频道的 Webhook URL |

> `GITHUB_TOKEN` 由 Actions 自动提供，无需手动配置。如果监控私有仓库，需要创建有 `repo` 权限的 PAT 并覆盖此 secret。

### 4. 获取 Discord Webhook URL

1. 打开 Discord → 目标频道 → 编辑频道 → 集成 → Webhook
2. 创建 Webhook，复制 URL
3. 粘贴到 GitHub Secret `DISCORD_WEBHOOK_URL`

### 5. 启用 Actions

推送代码到 GitHub 后，Workflow 会按 cron 计划自动运行。也可以在 **Actions** 页面手动触发 (`workflow_dispatch`)。

## 本地测试

```bash
export GITHUB_TOKEN="ghp_xxxx"          # 可选，提高 API 速率限制
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
pip install -r requirements.txt
python monitor.py
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `monitor.py` | 主脚本：查询 GitHub API → 对比状态 → 推送 Discord |
| `config.json` | 目标仓库列表及开关配置 |
| `state.json` | 运行时状态缓存（已 gitignore，Actions 中通过 cache 持久化） |
| `.github/workflows/monitor.yml` | GitHub Actions 工作流定义 |
| `requirements.txt` | Python 依赖 |

## 注意事项

- GitHub Actions 的 cron 调度**不保证精确**到 5 分钟，可能有 1-10 分钟的延迟。
- GitHub API 未认证速率限制为 60 次/小时，认证后为 5000 次/小时。10 个仓库每次约消耗 20-30 次请求，认证 token 足够使用。
- 状态通过 `actions/cache` 在 CI 运行间持久化，缓存最长保留 7 天（有活动时自动续期）。
