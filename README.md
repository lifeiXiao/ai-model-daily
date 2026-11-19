# 每日模型雷达 · AI Model Daily

[访问网站](https://lifeixiao.github.io/ai-model-daily/) · [运行记录](https://github.com/lifeiXiao/ai-model-daily/actions) · [原始数据](data/catalog.json)

自动追踪官方 AI 模型仓库与厂商动态，整理任务类型、功能说明、来源日期和原文链接，发布到 GitHub Pages。

## 完全由 GitHub 托管运行

- **每日北京时间 08:17**（UTC 00:17）由 GitHub Actions 自动采集、测试、构建、归档并部署。
- 使用 GitHub 托管的 Ubuntu runner；不使用 self-hosted runner，不依赖个人电脑、Codex 定时任务、Codex 会话或外部服务器。
- 不调用任何付费模型 API、不做模型推理、不下载模型权重。采集仅使用公开的 HTTPS API、RSS 与官方页面，不需要另配 API Key。
- 只使用 GitHub 自动提供的临时 GITHUB_TOKEN 提交数据和发布网站。Actions 固定到明确的提交版本。
- 收集程序只用 Python 3.12 标准库。首次发布、手动执行和代码变更时，在 GitHub 上额外运行 Chromium 桌面与手机界面测试；日常定时更新运行单元测试、数据检查与部署验证。

## 收录范围

配置见 [config/sources.json](config/sources.json)。

| 来源 | 用途 |
| --- | --- |
| Hugging Face 指定官方账号 | 新模型仓库、任务标签、功能、许可信息、下载量等元数据 |
| OpenAI 官方 RSS | 模型及相关产品动态 |
| Google DeepMind 官方 RSS | 模型及研究动态 |
| Anthropic 官方 News | 带日期的模型相关动态 |

当前配置包括 OpenAI、Google、Qwen、DeepSeek、Meta、Mistral、Microsoft、NVIDIA、Black Forest Labs、Stability AI、月之暗面、MiniMax、智谱、北京智源、腾讯混元与 Hugging Face 的指定账号。

每个账号抓取最新 **30 个仓库**。首次导入最近 **90 天**的数据，后续增量合并，保留 **365 天**的记录。密集发布超过 30 个仓库的机构可能有遗漏，可调整配置中的 models_per_source。此项目不是全网模型全集。

## 信息含义

- **仓库创建时间**来自 Hugging Face 的 createdAt，不使用 lastModified 冒充新模型发布。它也不一定等于模型正式发布日期。
- **功能介绍**来自平台任务标签及明确能力标签的中文说明，不使用 AI 编造参数、评测或排名；详细功能以官方模型卡为准。
- **官方动态**按标题关键词筛选，包含已有模型和产品功能更新，不把所有公告当成新模型。英文摘要保留简短原文节选。
- **本日新发现**指首次采集到的条目，日期按北京时间计算。首次历史导入单独标识，不计为当日新增。
- 独立量化、预览、规格变体可能各占一个仓库，仓库数量不代表独立模型数量。
- 公开可见的模型不一定是开源，也不一定允许免费商用；请遵守原始模型许可和访问限制。

## 容错与可追溯性

- 网络请求有超时、有限重试和响应大小限制；最多 4 个并发请求。
- 按稳定 ID 去重，保留 first_seen_at，失败来源的历史内容不删除。
- 页面展示本次各来源同步结果；超过 36 小时未更新时显示提示。
- 若模型或公告某一类全部失败，流程失败并保留上次已发布站点，避免把空数据当成正常日报。
- 每日采集数据提交到 data/catalog.json；daily/YYYY-MM-DD.json 记录每日新发现和首次导入 ID。同日重跑合并记录。
- 发布后从公网检查 JSON 是否已更新到本次版本。失败记录可在 Actions 查看。

## 手动更新与维护

进入 **Actions → Daily AI models & Pages → Run workflow** 即可在 GitHub 上立即更新，无需本地执行任何脚本。

修改 config/sources.json 可增加账号、调整保留时间和单来源采集上限；修改 .github/workflows/daily.yml 中的 cron 可变更更新时间。GitHub 定时任务可能延迟，不是精确时间承诺。公开仓库连续 60 天没有活动时，GitHub 可能停用定时任务；正常运行会每日提交数据，若任务停用，可在 Actions 页面重新启用。

GitHub Pages 的发布来源设为 **GitHub Actions**，部署环境为 github-pages。

## 文件结构

| 路径 | 内容 |
| --- | --- |
| scripts/update.py | API、RSS、HTML 采集与归档 |
| scripts/build.py | 静态网站打包 |
| web/ | 响应式中文页面与筛选交互 |
| tests/ | 采集规则与浏览器测试 |
| data/catalog.json | 最新数据及来源状态（首次运行自动生成） |
| daily/ | 每日变化归档（首次运行自动生成） |
| .github/workflows/daily.yml | 全部自动化与 Pages 发布 |

## 参考文档

- [Hugging Face Hub API](https://huggingface.co/docs/hub/api)
- [GitHub Pages 自定义工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions 定时事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
