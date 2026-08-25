# Trakt → NeoDB 同步

自动将 Trakt 的观影记录（电影和剧集）同步到 [NeoDB](https://neodb.social)，通过 GitHub Actions 定时运行。

## 功能

- 从 Trakt 拉取观影历史（电影和剧集）
- 自动在 NeoDB 标记为"看过"，并附带观看日期
- 增量同步：仅同步上次运行后的新记录，避免重复
- 支持电影（movie）和剧集（TV show）两种类型
- 单条记录失败不影响整体同步

## 配置步骤

### 1. 申请 Trakt API Key

1. 访问 [Trakt OAuth 应用管理](https://trakt.tv/oauth/applications)
2. 点击「新建应用」
3. 填写应用名称（随意），Redirect URI 填 `http://localhost`
4. 创建后记录以下信息：
   - **Client ID**（即 API Key）
   - 在应用页面生成 **Access Token**（OAuth 流程）

> 你需要记下 `TRAKT_CLIENT_ID`、`TRAKT_ACCESS_TOKEN` 和你的 `TRAKT_USERNAME`。

### 2. 获取 NeoDB Access Token

1. 访问 [NeoDB 开发者设置](https://neodb.social/settings/developer/)
2. 创建一个应用，获取 **Access Token**

### 3. 配置 GitHub Secrets

进入仓库的 **Settings → Secrets and variables → Actions**，添加以下四个 Secrets：

| Secret 名称 | 说明 |
|---|---|
| `TRAKT_CLIENT_ID` | Trakt 应用的 Client ID |
| `TRAKT_ACCESS_TOKEN` | Trakt 的 OAuth Access Token |
| `NEODB_ACCESS_TOKEN` | NeoDB 的 Access Token |
| `TRAKT_USERNAME` | 你的 Trakt 用户名 |

### 4. 手动触发

配置完成后，进入仓库的 **Actions** 页面：

1. 选择「Trakt to NeoDB Sync」工作流
2. 点击「Run workflow」手动触发首次同步
3. 之后将每 3 天自动运行一次

## 运行机制

- 同步脚本会记录上次同步的时间戳（通过 GitHub Actions Cache 持久化）
- 每次运行只拉取该时间戳之后的新观影记录
- 电影和剧集分别搜索 NeoDB 条目并标记为"看过"
- 剧集按剧名去重，同一部剧只标记一次
- 如果 NeoDB 中找不到对应条目，该条记录会被跳过并记录日志

## 项目结构

```
trakt-neodb-sync/
├── .github/
│   └── workflows/
│       └── sync.yml      # GitHub Actions 工作流
├── sync.py               # 同步脚本
├── requirements.txt      # Python 依赖
└── README.md             # 说明文档
```

## 注意事项

- Trakt Access Token 可能会过期，如同步失败请检查并更新 Token
- NeoDB 搜索基于标题匹配，可能存在匹配不准确的情况
- 同步是单向的（Trakt → NeoDB），不会反向同步
