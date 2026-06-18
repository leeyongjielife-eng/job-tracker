# LinkedIn Local Browser Automation

这套方案用于在本机自动刷新 LinkedIn 搜索结果，再把结果送入现有的 `job-tracker` 流水线。

## 目标

本机自动化负责：

1. 打开 `sources/linkedin_search_tasks.json` 中的 LinkedIn 搜索 URL
2. 自动滚动并提取职位卡片
3. 写入 `sources/<task-id>.browser_export.json`
4. 可选自动运行 `linkedin_ingest.py --mode refresh_bundle`
5. 可选自动 `git commit / push`

GitHub Actions 继续负责：

1. 过滤
2. 去重
3. GLM / heuristics 分析
4. 写入 Notion

## 需要的本机环境

推荐：

- Python 3.11+
- Playwright
- Chromium 或本机 Chrome
- 一个已经登录 LinkedIn 的浏览器 profile

安装示例：

```bash
cd /Users/youngkit/Documents/codex_project/projects/job-tracker
source .venv/bin/activate
pip install playwright
```

如果你直接复用本机已安装的 Google Chrome，可以不下载 Playwright 自带 Chromium。

## 环境变量

至少需要：

```bash
DISABLE_SYSTEM_PROXY=1
LINKEDIN_BROWSER_USER_DATA_DIR=/path/to/your/browser-profile
```

可选：

```bash
LINKEDIN_BROWSER_EXECUTABLE=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
LINKEDIN_ATTACH_TO_EXISTING_BROWSER=1
LINKEDIN_REMOTE_DEBUGGING_URL=http://127.0.0.1:9222
JOB_TRACKER_REPO_PATH=/Users/youngkit/Documents/codex_project/projects/job-tracker
```

说明：

- 如果你的终端里带有 `http_proxy` / `https_proxy` / `all_proxy`，建议保留 `DISABLE_SYSTEM_PROXY=1`
- 这样脚本在连接本机 `127.0.0.1:9222` 的 Chrome 调试端口时，不会被本地代理错误拦截

## 推荐方式：连接你手动打开的 Chrome

如果你访问 LinkedIn 依赖浏览器扩展、代理或现有登录态，推荐不要让 Playwright 自己新开一个“净化版”Chrome，
而是让它连接到你手动启动的 Chrome。

先用下面的命令启动专用 Chrome：

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="/Users/youngkit/Documents/codex_project/projects/job-tracker/.browser-profile"
```

然后在 `.env` 里加：

```bash
LINKEDIN_ATTACH_TO_EXISTING_BROWSER=1
LINKEDIN_REMOTE_DEBUGGING_URL=http://127.0.0.1:9222
LINKEDIN_BROWSER_EXECUTABLE=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```

这条模式更适合：

- 你本机需要代理/扩展才能稳定打开 LinkedIn
- 你希望保留手动登录后的完整浏览器环境

## 首次运行建议

首次建议非无头运行，并暂停确认登录态：

```bash
python3 linkedin_browser_refresh.py \
  --pause-for-login \
  --task-id linkedin-ai-product-manager-cn \
  --task-id linkedin-ai-product-manager-zh-cn
```

如果确认抓取正常，再扩大任务范围。

如果你已经提前手动打开并登录了专用 Chrome，也可以先不加 `--pause-for-login`，直接做一个最小验证：

```bash
python3 linkedin_browser_refresh.py \
  --task-id linkedin-ai-product-manager-cn \
  --max-cards-per-task 5 \
  --scroll-rounds 1
```

## 完整刷新并汇总

```bash
python3 linkedin_browser_refresh.py --refresh-bundle
```

这会：

- 刷新 per-task `browser_export.json`
- 自动运行 `linkedin_ingest.py --mode refresh_bundle`
- 生成 `data/linkedin_jobs.json`

当前容错行为：

- 单个搜索任务如果遇到 LinkedIn 临时网络错误，脚本会先自动重试
- 如果重试后仍失败，该任务会被记录到 `failed_tasks`，但不会中断整轮刷新
- 因此大多数情况下你不需要因为一条搜索失败就整批重跑

## 刷新后自动提交

```bash
python3 linkedin_browser_refresh.py --refresh-bundle --git-push
```

默认 commit message：

- `Refresh LinkedIn browser exports`

## 当前限制

- 依赖本机登录态
- 页面结构变化后可能需要更新选择器
- 电脑需要开机
- 当前脚本主要提取搜索结果卡片，不保证每条都有完整 summary
- 若 LinkedIn 页面风格变化较大，建议先用 `--task-id` 小范围验证
