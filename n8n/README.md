# n8n LinkedIn Job Tracker

这个目录放的是基于你原始 `Job Tracker.json` 重构后的 n8n 工作流，目标是让它更适合长期维护、复用和放到 GitHub 上管理。

## 文件

- `workflows/linkedin-job-tracker.optimized.json`

## 相比原始工作流的优化

1. 增加了 `Manual Trigger`，导入后可以先手动跑通，再启用定时器。
2. 保留你现有的 6 个 RSS 来源，但把后处理集中到一个 `Code` 节点里，减少后续改动时要改很多节点的问题。
3. 增加了链接规范化，会去掉常见 `utm_*` 和跟踪参数，降低同一岗位重复写入 Google Sheets 的概率。
4. 增加了基础打分逻辑，只保留更接近 AI PM / AI Ops / AI Project Manager 的职位。
5. 增加了 `company`、`location`、`keyword_tag`、`relevance_score`、`collected_at`、`unique_key` 等字段，后续筛选、排序、做看板会方便很多。
6. Google Sheets 从原来的 4 列扩展成完整的投递跟踪表结构，方便你后面手动维护 `status`、`applied_at`、`notes`。
7. 工作流默认 `active: false`，避免导入之后立刻自动执行。

## 建议的 Google Sheets 表头

在 `Jobs` 这个 sheet 里提前建好下面这些列：

- `Title`
- `Company`
- `Location`
- `Summary`
- `Job URL`
- `Source`
- `Keyword Tag`
- `Published At`
- `Days Old`
- `Relevance Score`
- `Status`
- `Applied At`
- `Notes`
- `Unique Key`
- `Collected At`

## 导入和配置

1. 打开 n8n，选择 `Import from file`
2. 导入 [workflows/linkedin-job-tracker.optimized.json](/Users/youngkit/Documents/codex_project/projects/job-tracker/n8n/workflows/linkedin-job-tracker.optimized.json)
3. 进入 `Append Or Update Sheet Row` 节点
4. 绑定你的 `Google Sheets OAuth2` 凭证
5. 把 `documentId` 改成你自己的 Google Sheets 地址
6. 确认目标工作表名是 `Jobs`
7. 先执行 `Manual Trigger` 测试一次
8. 确认写表正常后，再把 workflow 设为 `Active`

## 还可以继续增强的方向

- 增加 `HTTP Request + OpenAI` 节点，自动为岗位生成投递优先级和简短备注
- 增加 `Company blacklist` 或 `Location whitelist`
- 增加 Telegram / Slack / 邮件提醒，只推送高分岗位
- 把 RSS 来源改成单独配置表，用 `Loop` 方式动态扩展更多关键词

## GitHub 管理建议

建议把每次对 n8n 工作流的修改都导出回这个目录，然后走 Git 提交。这样有几个好处：

- 可以看到每次你改了哪些节点
- 可以回滚错误改动
- 可以在不同设备上同步工作流配置
- 后面如果你要加 CI 校验或团队协作，会更顺手
