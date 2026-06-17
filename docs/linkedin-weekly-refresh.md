# LinkedIn Weekly Refresh

## 目标

把 LinkedIn 保持为 `job-tracker` 的主数据层，同时把每周刷新动作固定成可重复执行的最小流程。

## 当前边界

- 当前支持的是“半手动刷新”
- 浏览器抓取仍需要你在 LinkedIn 页面中执行
- 抓取后的汇总、标准化、freshness 检查已经脚本化
- GitHub Actions 周跑只消费已经刷新的 `data/linkedin_jobs.json`

## 每周步骤

1. 打开 `sources/linkedin_search_tasks.json`
2. 逐项访问其中的 LinkedIn 搜索 URL
3. 每个搜索项分别更新对应文件：
   - `sources/<task-id>.browser_export.json`
   - 如果职位卡片上能看到一句简介、标签或能力描述，尽量写入 `summary`
   - 尤其是泛 PM 岗位，若卡片里出现 `agent / copilot / AI tools / model platform / workflow / multimodal / prompt / RAG / inference` 等字样，必须写入 `summary`
   - 中文搜索层也要同步刷新，例如：
     - `AI产品经理`
     - `Gen-AI产品经理`
     - `AIGC产品经理`
     - `大模型产品经理`
     - `智能体产品经理`
     - `AI平台产品经理`
4. 在项目目录运行：

```bash
python3 linkedin_ingest.py --mode refresh_bundle
```

5. 检查输出：
   - `sources/linkedin_jobs_browser_export_grouped.json`
   - `data/linkedin_jobs.json`
   - `data/linkedin_refresh_report.json`
6. 如需本地验证本周会留下哪些岗位，再运行：

```bash
python3 job_tracker.py --lookback-days 7 --skip-analysis --dry-run --output data/job-tracker-weekly-preview.json
```

## 通过标准

- `data/linkedin_refresh_report.json` 中没有关键主池任务缺失
- 英文主池与中文主池至少大部分已刷新
- 尤其要覆盖 `AI Product Manager / Agent Product Manager / GenAI Product Manager / AI Platform Product Manager`
- 以及 `AI产品经理 / Gen-AI产品经理 / AIGC产品经理 / 大模型产品经理 / 智能体产品经理 / AI平台产品经理`
- 没有明显过旧样本充当本周输入
- 主池搜索项里的泛 PM 岗位尽量不是空 `summary`

## 失败信号

- 某些 `*.browser_export.json` 文件不存在
- 文件存在但 `jobs` 为空
- 大量泛 PM 岗位 `summary` 为空，导致弱 AI 信号规则无法生效
- freshness report 显示主池任务最新发布时间早于 7 天
- `job_tracker.py --lookback-days 7` 输出为 0，且提示最近记录全部被规则筛掉

## 当前定位

- LinkedIn：主层
- Greenhouse / Lever / 官网：补充层，默认关闭
- Applied AI Engineer 等工程岗：补充池，不压过 PM 主池
