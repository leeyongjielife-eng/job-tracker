# Job Tracker

这个项目已经从工作区根目录整理到独立目录：

- 项目目录：`projects/job-tracker/`
- 主脚本：`job_tracker.py`
- LinkedIn 中间层：`linkedin_ingest.py`
- 来源配置：`sources/`
- 运行产物：`data/`
- n8n 工作流：`n8n/`
- 项目日志：`logs/`

## 初始化

```bash
cd /Users/youngkit/Documents/codex_project/projects/job-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

脚本仍兼容读取工作区根目录旧 `.env`，这样现有本地配置不会立刻失效。

## 每周最短操作流程

如果你这周只想完成一次最小必要更新，按这个顺序做：

1. 打开你已经登录 LinkedIn 的专用 Chrome 会话。
2. 进入项目目录并运行：

```bash
cd /Users/youngkit/Documents/codex_project/projects/job-tracker
source .venv/bin/activate
python linkedin_browser_refresh.py --refresh-bundle
```

3. 确认这轮刷新已经生成：
   - `data/linkedin_jobs.json`
   - `data/linkedin_refresh_report.json`
4. 等 GitHub Actions 周跑，或者手动运行：

```bash
python job_tracker.py
```

补充说明：

- 如果 LinkedIn 个别搜索词临时失败，脚本会自动重试，并在必要时跳过失败项继续整轮刷新。
- 如果这周网络特别差，先完成 `linkedin_browser_refresh.py --refresh-bundle` 即可，等网络稳定后再补跑也可以。

## 桌面按钮

如果你不想每次手动打开终端，项目里已经准备了两个可双击运行的启动脚本：

- `scripts/run_linkedin_refresh.command`
- `scripts/run_full_weekly_update.command`

它们分别对应：

- 只刷新 LinkedIn 搜索数据
- 刷新 LinkedIn 数据后，再继续执行 `job_tracker.py`

每次运行的日志会保存到：

- `logs/launcher/`

## 常用命令

按默认滚动窗口抓取并同步岗位：

```bash
python3 job_tracker.py
```

当前默认行为：

- GitHub Actions 每周运行默认扫描最近 `7` 天发布的岗位
- `60` 天窗口保留给首次回填或手动补跑
- 因为同步到 Notion / 后续数据库时按 `Link` 去重且不会删除旧记录，所以周跑会在原有岗位库基础上补最近一周的新岗位

当前默认策略：

- `LinkedIn Middle Layer` 作为主数据层
- `Greenhouse / Lever / 官网` 默认不自动混入
- 如需重新打开补充源，设置 `JOB_TRACKER_INCLUDE_SUPPLEMENTAL_SOURCES=1`

手动指定滚动窗口：

```bash
python3 job_tracker.py --lookback-days 60
```

当前更推荐这样理解时间窗口：

- `7 天`：当前 GitHub 周跑默认发布窗口
- `60 天`：首次回填或手动补跑窗口
- `每周一次`：更新频率；周跑会在已有岗位库基础上补最近 7 天新增岗位

只抓取和去重，不调用 LLM 分析，也不写 Notion：

```bash
python3 job_tracker.py --dry-run --skip-analysis --output data/job-tracker-preview.json
```

先用 GLM 做小样本质量测试，不改主流程：

```bash
python3 glm_quality_test.py --limit 3
```

需要先在 `.env` 或工作区根目录 `.env` 里补：

```bash
GLM_API_KEY=...
GLM_BASE_URL=...
GLM_MODEL=glm-5.2
```

当前更稳的 GLM 周跑建议参数：

```bash
JOB_TRACKER_LLM_MAX_JOBS=2
JOB_TRACKER_GLM_REQUEST_INTERVAL_SECONDS=3
JOB_TRACKER_GLM_RETRY_BACKOFF_SECONDS=5
JOB_TRACKER_GLM_RATE_LIMIT_COOLDOWN_SECONDS=30
GLM_MODEL=glm-4.5-flash
```

这样即使接口偶发限流，脚本也会：

- 小批量调用 GLM
- 在请求之间主动等待
- 命中 `429` 后冷却并停止继续冲后续岗位
- 让剩余岗位自动退回 heuristics，保证整轮同步不中断

生成 LinkedIn 标准化中间层：

```bash
python3 linkedin_ingest.py --mode manual_json
```

按每周刷新流程，自动汇总各个 `*.browser_export.json`，并生成 grouped export、标准化中间层和 freshness 报告：

```bash
python3 linkedin_ingest.py --mode refresh_bundle
```

如果你想在本机直接自动打开浏览器刷新 LinkedIn 搜索结果，再接入现有中间层：

```bash
python3 linkedin_browser_refresh.py --refresh-bundle
```

如果你本机终端带了代理变量，建议在 `.env` 保留：

```bash
DISABLE_SYSTEM_PROXY=1
```

这样脚本连接本机 Chrome 调试端口 `127.0.0.1:9222` 时，不会误走系统代理。

当前本机刷新脚本还带有基础容错：

- LinkedIn 页面导航失败会自动重试
- 单个搜索项反复失败时会跳过并继续后续任务
- 最终失败项会出现在脚本输出里的 `failed_tasks`

详细说明见：

- `docs/linkedin-local-browser-automation.md`

用半手动纯文本输入生成 LinkedIn 标准化中间层：

```bash
python3 linkedin_ingest.py --mode manual_text --input sources/linkedin_jobs_manual_text.template.txt --output data/linkedin_jobs.json
```

默认输出位置已经调整为：

- `data/linkedin_jobs.json`

默认输入示例位于：

- `sources/linkedin_jobs_seed.example.json`

LinkedIn 搜索任务清单位于：

- `sources/linkedin_search_tasks.json`

它的作用不是直接作为岗位输入，而是把我们确认过的 LinkedIn 搜索词正式整理成可重复使用的浏览器搜索入口，供后续逐个搜索、导出、再送进 `linkedin_ingest.py`。

当前也已经有一份来自浏览器态 LinkedIn 搜索结果的真实输入样例：

- `sources/linkedin_jobs_browser_export.json`

LinkedIn 浏览器导出规范位于：

- `sources/linkedin_browser_export_spec.json`

LinkedIn 半手动文本模板位于：

- `sources/linkedin_jobs_manual_text.template.txt`
- `sources/linkedin_jobs_manual_text.sample.txt`

用真实浏览器导出输入重新生成中间层：

```bash
python3 linkedin_ingest.py --mode manual_json --input sources/linkedin_jobs_browser_export.json --output data/linkedin_jobs.json
```

主 job tracker 现在可以直接读取这个 LinkedIn 中间层：

- 开关：`JOB_TRACKER_INCLUDE_LINKEDIN_MIDDLE_LAYER=1`
- 路径：`JOB_TRACKER_LINKEDIN_JSON_PATH=data/linkedin_jobs.json`

因此主脚本会把 `data/linkedin_jobs.json` 当作一个正式输入源，并继续经过：

- 目标岗位过滤
- 地区过滤
- 去重
- 配额控制
- GLM / heuristics 分析

## LinkedIn 当前阶段说明

目前 LinkedIn 这条链路还不是“按全部搜索词自动批量抓取”，而是：

1. 先根据 `sources/linkedin_search_tasks.json` 打开某一个 LinkedIn 搜索 URL
2. 从浏览器页手动导出一批职位卡片
3. 保存为 `sources/linkedin_jobs_browser_export.json`
4. 再用 `linkedin_ingest.py` 规范化成 `data/linkedin_jobs.json`
5. 最后交给 `job_tracker.py` 做过滤和去重

所以之前看到的 `processed_jobs = 5`，含义是：

- 不是 LinkedIn 只搜到了 5 条
- 而是当前样本输入只覆盖了一个小批量浏览器导出
- 且这批输入在进入主流水线后，又经过了岗位类型、地区、去重与配额筛选
- 最终只保留了 5 条符合当前规则的岗位

## LinkedIn 浏览器导出规范

当前约定如下：

1. 每个 LinkedIn 搜索任务单独导出，再合并成一个 JSON 数组文件。
2. PM 核心搜索项每个目标抓 `20` 条，`AI Operations` 这种相邻岗位池先抓 `10` 条即可。
3. 首次补样和常规运行都优先覆盖最近 `60` 天；如果只是做局部验证，可以手动缩小窗口。
4. 导出字段固定为：
   - `title`
   - `company`
   - `location`
   - `summary`
   - `link`
   - `published_at`
   - `source`
   - `source_type`
5. `source` 固定写 `LinkedIn Browser Search`，`source_type` 固定写 `linkedin_manual`。

这一步的目标是先把样本结构和抓取规模固定住，避免后面因为字段不齐或不同搜索项抓取深度不一致，导致中间层和主流水线结果难比较。

## LinkedIn 每周刷新流程

当前约定的周刷新流程是：

1. 逐个打开 `sources/linkedin_search_tasks.json` 里的搜索 URL
2. 每个搜索项分别保存到对应的 `sources/<task-id>.browser_export.json`
3. 运行：

```bash
python3 linkedin_ingest.py --mode refresh_bundle
```

4. 脚本会自动产出：
   - `sources/linkedin_jobs_browser_export_grouped.json`
   - `data/linkedin_jobs.json`
   - `data/linkedin_refresh_report.json`
5. 再运行主脚本或等待 GitHub Actions 周跑消费最新的 `data/linkedin_jobs.json`

`linkedin_refresh_report.json` 主要用于检查：

- 哪些搜索项本周没有导出文件
- 哪些搜索项文件为空
- 哪些搜索项最新发布时间已经明显陈旧，不利于本周增量更新

补充一个现在很重要的操作要求：

- 后续导出时，`summary` 需要尽量补齐
- 尤其是标题比较泛的 `Product Manager / Senior Product Manager / Product Owner`
- 如果卡片里出现 `agent / copilot / AI tools / model platform / workflow / prompt / RAG / multimodal / inference` 等弱 AI 信号，必须写入 `summary`
- 否则即使规则已经放松，这类岗位仍可能因为文本不足被过滤掉

## 自动化

GitHub Actions 已更新为从 `projects/job-tracker/` 运行。

当前需要注意一件事：

- GitHub Actions 可以自动运行 `job_tracker.py`
- 但不会自动生成新的 LinkedIn 浏览器导出
- 因此如果 `data/linkedin_jobs.json` 没有在周跑前被刷新，线上运行只能使用仓库里现成的静态 LinkedIn 样本
- 现有样本更适合用于规则验证和初始回填测试，不足以直接承担长期每周新数据输入
 
换句话说，LinkedIn 现在已经接入了“标准化输入层”和“半手动周刷新层”，但还没有接入“全自动浏览器采集层”。

n8n 工作流说明见：

- [n8n/README.md](/Users/youngkit/Documents/codex_project/projects/job-tracker/n8n/README.md)
