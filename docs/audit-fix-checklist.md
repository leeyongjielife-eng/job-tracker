# Audit Fix Checklist

## 已确认规则

- [x] Notion 中人工修改后的 `Status` 不能被脚本重置
- [x] 线上 GitHub 周跑窗口应为 `7` 天
- [x] `60` 天只用于首次建池或手动 backfill

## 审计问题清单

- [x] 修复 Notion 同步覆盖人工 `Status`
- [x] 收敛 `7 天 / 60 天` 配置与文档冲突
- [x] 让 LinkedIn 刷新在任务失败时显式暴露失败，而不是伪装整轮成功
- [x] 修复 `legacy_rss` 兼容路径失效
- [x] 让 LinkedIn `published_at` 缺失问题在报告中被显式暴露
- [x] 补上 `summary` 质量门槛，避免空摘要大量流入主流程
- [x] 修正文档中“全链路验证”与真实副作用不一致的问题
- [x] 修复 LinkedIn 中间层把原始浏览器卡片噪音直接写入 grouped / normalized JSON 的问题

## 本轮审计结论

- [x] 本地 `refresh_bundle` 已改为先标准化再聚合
- [x] 本地小样本审计确认：
  - `data/linkedin_jobs.json` 中 `location / summary` 不再残留 `几天前 / 几周前 / 正在招聘 / 抢先申请` 这类界面噪音
  - `sources/linkedin_jobs_browser_export_grouped.json` 也已同步变为清洗后版本
- [ ] 仍待完成：
  - 推送当前版本到 GitHub
  - 手动触发一次 `job-tracker` 线上运行
  - 复核 Notion 实际写入是否已完全体现“LinkedIn-only + Status 不重置”这版逻辑
