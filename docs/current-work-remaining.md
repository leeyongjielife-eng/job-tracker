# Current Work Remaining

## 当前状态

- LinkedIn 已经是默认主数据层
- 每周刷新流程已经建立，但仍是半手动
- 发布窗口已经统一改成滚动 `60` 天
- 每周运行一次代表“更新频率”，不再代表“只看最近 7 天发布的岗位”
- 当前 `60` 天候选池已从 `11` 条升到 `12` 条
- 当前最近一周新增样本里，已有 `3` 条可以稳定保留
- 当前 `60` 天候选池里：
  - `11` 条已经补到真实页面摘要
  - `1` 条为可见页面证据已捕获，但详细 JD 仍部分受登录墙限制
- 当前已补做 LinkedIn 中间层来源追踪字段：
  - `source_task_id`
  - `source_task_name`
  - `source_query`
  - `source_region`
- 当前候选池已单独整理在：
  - `data/linkedin_curated_candidates.json`
- 下一批优先补的 LinkedIn 新样本已整理在：
  - `docs/next-linkedin-refresh-targets.md`

## 最新复跑结果

- `python3 job_tracker.py --dry-run --skip-analysis --lookback-days 60`
  - `processed_jobs = 12`
- 当前默认建议不再把 `7` 天当成主发布窗口。
- 如果只做“最近一周新增样本诊断”，当前可保留的新增岗位是：
  - `平安健康保险股份有限公司 / 高级产品经理 / 深圳`
  - `翔傲信息科技（上海）有限公司 / 产品经理-AI方向 / 上海市`
  - `沃尔玛(中国)投资有限公司 / AI智能体与低代码平台 产品负责人 / 深圳`
- 最近一次排查也确认：
  - 之前出现的 `7d = 0` 有一部分是因为并行执行时主脚本先读到了旧版 `linkedin_jobs.json`
  - 串行重建中间层后再复跑，结果已恢复为 `7d = 1`

## 当前候选池

### 高优先

- `Confidential / AI Product Manager - AI Router / 上海`
- `Kong / Senior Product Manager, AI Gateway / 上海`
- `上海瑞霖贸易有限公司 / Gen-AI产品经理 / 广州`
- `RayNeo / AI Product Manager / 深圳`
- `Wing Assistant / Product Manager, AI Solutions / 上海`
- `WuXi Biologics/药明生物 / Agent AI Product Manager / 上海`
- `翔傲信息科技（上海）有限公司 / 产品经理-AI方向 / 上海`
- `平安健康保险股份有限公司 / 高级产品经理 / 深圳`
- `ShopBack / Product Lead, AI-Native (Special Projects) / 深圳`

### 观察

- `沃尔玛(中国)投资有限公司 / AI智能体与低代码平台 产品负责人 / 深圳`
- `通用汽车 / Staff Product Manager – CIX / 上海`
- `Metaprise / AI Engineer / 深圳`

当前核实清单位于：

- `docs/curated-candidate-review-checklist.md`
- `data/linkedin_curated_review_packets.json`

## 剩余工作

### 1. 提高样本真实性

- 当前阶段已完成：
  - `60` 天候选池里的 `12` 条已完成首轮核实
  - 其中 `11` 条有真实页面摘要，`1` 条有可见页面证据
- 下一步重点已经从补 `60` 天摘要，转为补强“最近一周新增样本”的质量：
  - 优先补最近命中的岗位卡片 `location`
  - 优先补最近命中的岗位卡片 `summary`
  - 尤其优先处理这些搜索项：
    - `linkedin-agent-product-cn`
    - `linkedin-genai-product-cn`
    - `linkedin-ai-platform-product-cn`
    - `linkedin-applied-ai-engineer-cn`

### 2. 稳定每周刷新

- 每周更新 `sources/<task-id>.browser_export.json`
- 至少保证主池搜索项稳定刷新：
  - `linkedin-ai-product-manager-cn`
  - `linkedin-genai-product-cn`
  - `linkedin-ai-platform-product-cn`
  - `linkedin-agent-product-cn`
- 每次刷新后运行：

```bash
python3 linkedin_ingest.py --mode refresh_bundle
```

### 3. 继续收敛观察池

- 当前观察池已基本定型：
  - `通用汽车 / Staff Product Manager – CIX / 上海` 继续保留观察
  - `Metaprise / AI Engineer / 深圳` 继续保留为少量工程补充观察
- 后续如需继续收缩，再决定是否从这两条里再删一条

### 4. 再恢复 Gemini

- 等候选池质量稳定后，再恢复 Gemini 做：
  - `Keywords`
  - `Relevance Score`
  - `Mentions Agent`
  - `Mentions AI Native`
- 这样 API 调用会更省，也更有意义

### 5. 再决定正式落库

- Notion 作为主落库目标已经确定
- 但更适合在候选池质量稳定后再正式写入，以免把测试样本一起落库

## 当前最推荐下一步

- 优先刷新最近有命中但字段不完整的 LinkedIn 搜索项
- 目标不是继续扩大数量，而是让“滚动 60 天主池 + 每周新增样本”这套节奏稳定下来
