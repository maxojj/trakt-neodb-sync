# douban-neodb-sync

自动将豆瓣"看过/读过/听过"标记同步到 NeoDB，通过 GitHub Actions 每 6 小时运行一次。

## 原理

豆瓣每个用户都有公开的 RSS feed，每次标记"看过"等状态时会更新。本项目定时拉取该 RSS，解析新条目，通过 NeoDB API 写入标记（含评分和短评）。

已同步的条目 URL 记录在 `synced.json` 中，避免重复写入。

## 配置

在仓库 Settings → Secrets and variables → Actions 中添加两个 Secret：

| Secret 名称 | 说明 |
|------------|------|
| `DOUBAN_ID` | 豆瓣用户 ID（主页 URL 中 `people/` 后面的部分） |
| `NEODB_TOKEN` | NeoDB API Token（在 https://neodb.social/developer/ 生成） |

## 注意事项

- 豆瓣 RSS 每次只保留最近 10 条，所以 workflow 每 6 小时跑一次。如果某天集中标记很多，可在 Actions 页面手动触发。
- 豆瓣主页需设置为公开，RSS 才能被读取。
- NeoDB 中找不到对应条目的会跳过（部分冷门内容 NeoDB 可能尚未收录）。
