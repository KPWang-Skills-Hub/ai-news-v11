# AI资讯早报 v10 - 技术架构文档

> 本文档涵盖系统架构、数据源、拦截器流程、输出生成、技术配置。不含周报相关内容。

---

## 一、系统概览

AI资讯早报 v10 是一个**模块化的 AI 行业资讯收集与处理系统**，每天自动从多个数据源抓取 AI 相关新闻，经过多层过滤、语义去重、LLM 分类摘要后，生成微信公众号草稿。

### 核心特性

- **7 个数据源**：虎嗅、InfoQ、量子位、AIBase、HuggingFace、GitHub Trending、OpenRouter
- **5 层拦截器链**：时间过滤 → 关键词过滤 → BGE 语义去重 → LLM 分类 → LLM 摘要
- **自动分类**：国内AI / 国外AI / 智能硬件 / 其它科技
- **AI 生成摘要**：每条新闻自动生成 100-300 字中文摘要
- **AI 热点与洞察**：自动选择热点 + 生成 200-300 字今日洞察
- **多格式输出**：JSON + HTML + Markdown + 公众号草稿
- **表格图片**：GitHub / HuggingFace / OpenRouter 三张趋势榜图片

---

## 二、目录结构

```
ai-news-v10/
├── SKILL.md                          # 本文档（入口）
├── company_patterns.py               # 公司名识别正则配置
├── scripts/
│   ├── main.py                       # 主入口脚本
│   ├── config.py                     # 配置模块（已弃用，改用 ~/.openclaw/config.json）
│   ├── openrouter_scraper.py          # OpenRouter 独立抓取脚本（MonitorDB 写入）
│   ├── publish_wechat.py              # 微信公众号上传工具
│   ├── sources/                       # 数据源模块
│   │   ├── base.py                   # 基类：NewsSource、NewsItem
│   │   ├── __init__.py               # 自动注册所有数据源
│   │   ├── huxiu.py                  # 虎嗅（Playwright + NUXT_DATA 解析）
│   │   ├── infoq.py                  # InfoQ（curl + NUXT_DATA 解析）
│   │   ├── qbitai.py                 # 量子位（Playwright + BeautifulSoup）
│   │   ├── aibased.py                # AIBase（Playwright + BeautifulSoup）
│   │   ├── huggingface.py            # HuggingFace（API 直接请求）
│   │   ├── github.py                 # GitHub Trending（调用 ossinsight-github skill）
│   │   └── openrouter.py             # OpenRouter（从 MonitorDB 读取）
│   ├── interceptors/                  # 拦截器模块
│   │   ├── base.py                   # 基类：Interceptor、InterceptorResult
│   │   ├── __init__.py              # 自动注册所有拦截器
│   │   ├── logger.py                # 拦截器执行日志
│   │   ├── time_filter.py            # 时间过滤（保留 24h 内新闻）
│   │   ├── keyword_filter.py         # 关键词过滤（过滤政治/金融/招聘等）
│   │   ├── bge_dedup.py             # BGE 语义去重（阈值 0.8，跳过来源可配置）
│   │   ├── llm_classify.py          # LLM 分类（国内AI/国外AI/智能硬件/其它）
│   │   ├── llm_summary.py           # LLM 摘要（并行生成，每条 100-300 字）
│   │   ├── hot_insight.py           # AI 热点选择 + 洞察生成
│   └── templates/
│       └── github_trending.html     # GitHub 趋势榜 HTML 模板（Jinja2）
├── output/                           # 输出目录（JSON/HTML/MD/图片）
└── SKILL.md
```

---

## 三、数据源详解

### 3.1 数据源分类

| 数据源 | 类型 | 抓取方式 | 数据内容 | 备注 |
|--------|------|---------|---------|------|
| 虎嗅 | HTML | Playwright | AI 资讯列表 | 解析 NUXT_DATA JSON |
| InfoQ | HTML | curl | AI 快讯列表 | 解析 NUXT_DATA JSON |
| 量子位 | HTML | Playwright | 资讯列表 | 只保留作者为"量子位"的条目 |
| AIBase | HTML | Playwright | 资讯列表 | BeautifulSoup 解析 |
| HuggingFace | API | requests | 模型热度榜 | HF API，sort=trendingScore |
| GitHub | API | subprocess | AI 项目趋势榜 | 调用 ossinsight-github skill |
| OpenRouter | DB | SQL | 模型调用量榜单 | 从 MonitorDB raw_news 表读取 |

### 3.2 数据结构 `NewsItem`

```python
@dataclass
class NewsItem:
    title: str           # 标题
    desc: str = ""       # 描述/摘要
    link: str = ""       # 原文链接
    source: str = ""     # 来源名称
    time_ago: str = ""   # 相对时间
    category: str = ""   # 分类（国内AI资讯/国外AI资讯/智能硬件/其它科技资讯）
    summary: str = ""    # AI 摘要
    content: str = ""    # 正文内容（部分数据源需要抓取详情页）
    extra: dict = field(default_factory=dict)  # 额外字段（downloads/stars/rank等）
    llm_description: str = ""  # LLM 生成的中文介绍（仅 GitHub 项目）
```

### 3.3 数据源实现要点

#### 虎嗅（huxiu）
- 使用 Playwright 绕过 WAF，获取完整 HTML
- 从页面 `__NUXT_DATA__` 标签中提取 `aiNewsList` 数据
- Nuxt 序列化格式：`[["ShallowReactive", idx], {field: value_idx}, ...values]`
- publish_time 存储为时间戳（毫秒），从 `extra.publish_time` 读取

#### InfoQ（infoq）
- 使用 curl 替代 Playwright（更轻量）
- 从 `__NUXT_DATA__` 中提取 `aibriefsList.list`
- 注意：original_link 是 Twitter 链接，不采集
- 时间戳格式与虎嗅相同（毫秒级）

#### 量子位（qbitai）
- Playwright 快速抓列表页（不进入详情页，节省时间）
- **关键过滤**：只保留 `author == "量子位"` 的条目（过滤转载内容）
- 时间格式：`昨天 18:17` / `前天 18:17` / `N小时前`，在 `time_filter` 中处理

#### AIBase（aibased）
- Playwright 抓取列表页
- HTML 结构：`<div.grid><a href="/zh/news/xxx">标题|||摘要|||时间|||热度|||</a>`

#### HuggingFace（huggingface）
- 直接调用 HF API `https://hf-mirror.com/api/models`
- 参数：`limit=20&sort=trendingScore`
- 额外提取：downloads、likes、pipeline_tag、lastModified、参数规模（B/1B/7B等）

#### GitHub（github）
- 通过 subprocess 调用 `ossinsight-github` skill 的脚本
- 输出 `/tmp/github_ai_fetch.json`，包含 repo_name、description、stars、forks、total_score、language
- 无需解析 NUXT_DATA，直接读写 JSON

#### OpenRouter（openrouter）
- **不直接抓取**，从 MonitorDB `raw_news` 表读取
- 由独立的 `openrouter_scraper.py` 脚本预先抓取并写入数据库
- 从 `raw_extra` 字段解析 rank 和 change

---

## 四、拦截器链详解

### 4.1 执行顺序

```
time_filter → keyword_filter → bge_dedup → llm_classify → llm_summary
```

每个拦截器接收上一步的输出，返回 `InterceptorResult`。

### 4.2 时间过滤器（time_filter）

**功能**：只保留距执行时刻 24 小时内的新闻

**处理逻辑**：
1. 优先从 `extra.publish_time` 读取精确时间戳（毫秒）
2. 回退：从 `time_ago` 字符串解析（支持 `N分钟前` / `N小时前` / `N天前` / `昨天 HH:mm` / `前天 HH:mm`）
3. 时间戳转 datetime 后与阈值比较

### 4.3 关键词过滤器（keyword_filter）

**功能**：过滤掉政治、宏观经济、融资、招聘、会议活动等无关新闻

**过滤关键词**：
```
中美、外交、制裁、关税、政策、政府、国会、总统、总理
IPO、上市、股价、市值、并购、收购、融资、债务、投资、股权、估值
征稿、报名、参会、展位、博览会、Meetup、活动、论坛
医院、药物、捐赠、捐款、短剧、奖学金、AAAI、议题、拿地
高校、学院、校友、毕业、开学
招聘、求职、简历、面试、裁员、就业、招募、年薪
名创优品、持股
```

**注意**：AI 公司发布新产品/技术时的融资新闻应保留（通过判断 title 中是否同时包含融资关键词和 AI 技术关键词）。

### 4.4 BGE 语义去重（bge_dedup）

**功能**：使用 BGE 语义向量对新闻标题进行相似度计算，去除重复内容

**配置项**（`~/.openclaw/config.json` 中的 `ai-news-v10`）：
```json
{
  "bge_skip_sources": ["huggingface", "github", "openrouter"]
}
```
上述三个数据源不参与 BGE 去重（这些来源的标题是模型名/项目名，不会与 HTML 来源重复）

**模型**：`BAAI/bge-small-zh-v1.5`（轻量中文 embedding 模型）

**阈值**：`0.8`（余弦相似度 > 0.8 视为重复）

**去重流程**：
1. 过滤掉 skip_sources 中的数据
2. 加载 BGE 模型，计算所有标题的 embedding
3. 遍历每条新闻，计算与已有唯一新闻的相似度
4. 相似度 > 阈值 → 标记为重复；否则加入唯一列表

### 4.5 LLM 分类（llm_classify）

**功能**：对保留的新闻进行分类，同时过滤不适合的新闻

**分类类别**：
- 国内AI资讯（国内公司/模型/国内市场）
- 国外AI资讯（OpenAI、Anthropic、Google、Meta、Microsoft、NVIDIA 等）
- 智能硬件（智能眼镜、AI 眼镜、VR、AR、机器人、人形机器人等）
- 其它科技资讯

**过滤类型**：
- 纯融资、债务、投资、股权相关（AI 公司产品发布时的融资例外）
- 政治、宏观经济（关税、制裁、外交等）
- 纯招聘、裁员、求职
- 纯会议活动（征稿、报名、参会等）

**LLM 调用**：
- 模型：MiniMax-M2.5
- 超时：60s
- 最大重试：5 次（指数退避：1s → 2s → 4s → 8s → 16s）
- 输出格式：JSON `{filtered_indices: [...], categories: [...]}`

**并发控制**：信号量限制为 2 个并发请求（避免内存爆炸）

### 4.6 LLM 摘要（llm_summary）

**功能**：为每条新闻生成 100-300 字的中文摘要

**流程**：
1. **正文抓取**（仅配置了 `fetch_content_sources` 的数据源）：
   - 量子位需要抓取详情页（通过 Playwright）
   - 优先用 desc（列表页摘要）兜底，避免被验证码拦截
2. **并行生成摘要**：限制 2 个并发，LLM 调用超时 30s

**配置项**：
```json
{
  "fetch_content_sources": ["量子位"]
}
```

**并发优化**：
```python
_sem = threading.Semaphore(2)  # 信号量限制 2 个并发
ThreadPoolExecutor(max_workers=2)  # 线程池最多 2 个
ThreadPoolExecutor(max_workers=3)  # 正文抓取最多 3 个
```

---

## 五、热点与洞察生成

### 5.1 AI 选择热点（hot_insight.py）

**配置**：
```python
categories = {
    '国内AI资讯': 3,   # 取前3条
    '国外AI资讯': 2,  # 取前2条
    '智能硬件': 1     # 取前1条
}
# 共 6 条热点
```

**流程**：
1. 按分类汇总新闻（每个分类最多取 5 条）
2. 调用 MiniMax LLM，一次性输出 JSON `{hot_items: [...], insight: "..."}`
3. JSON 解析失败则最多重试 5 次
4. 重试全部失败 → 使用备用方案（直接取前 N 条）

**洞察要求**：200-300 字，基于当日新闻共同主题提炼

### 5.2 LLM 生成项目简介（GitHub）

**流程**：
1. 并行抓取 Top 10 项目的 README（24h 缓存 TTL）
2. 缓存路径：`~/.openclaw/workspace/ai-news/github_desc_cache.json`
3. 调用 MiniMax 生成 80-150 字纯中文介绍（禁止英文单词）
4. 缓存 TTL：5 天

**去重策略**：
- README 内容前 2500 字（按段落截断，保持语义完整）
- 结果中如无中文字符，回退使用 desc
- 句号（。）截断：确保不以残句结尾

---

## 六、输出生成

### 6.1 输出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| JSON | `output/news_YYYYMMDD.json` | 完整新闻数据（含分类、摘要） |
| HTML | `output/news_YYYYMMDD.html` | 公众号预览用 HTML |
| MD | `output/news_YYYYMMDD.md` | Markdown 格式备份 |

### 6.2 HTML 模板结构

```
🔥 今日热点（AI 选择的 6 条）
🔥 GitHub AI 项目趋势榜（截图）
🔥 HuggingFace 模型热度榜（截图）
🔥 OpenRouter 模型调用量榜单（截图）
🏷️ 国内AI资讯（最多 15 条）
🌍 国外AI资讯（最多 15 条）
📱 智能硬件（最多 5 条）
💡 其它科技资讯（最多 5 条）
💡 今日洞察（200-300 字）
```

**兜底模式**：如果 LLM 分类全部失败（每条新闻 `category` 均为空），所有新闻不分组，全量展示为一个无分类列表。

### 6.3 表格图片生成

#### GitHub 趋势榜
- 方式：Playwright + HTML 模板 + Jinja2 渲染 → 截图
- 模板：`templates/github_trending.html`
- 内容：Top 10 项目（排名、名称、语言、新增 star 数、中文介绍）

#### HuggingFace 模型热度榜
- 方式：PIL 绘制表格图片
- 内容：Top 10 模型（模型名、下载量、点赞数、类型、更新时间）

#### OpenRouter 模型榜单
- 方式：PIL 绘制表格图片
- 内容：Top 10 模型（排名、模型名、公司、Token 使用量、增长率）

---

## 七、微信公众号上传

### 7.1 流程

```
生成本地 HTML → 上传封面到微信素材 → 替换图片 URL 为微信 CDN URL → 提交草稿
```

### 7.2 图片处理

1. 上传图片到微信素材接口（返回 `url`）
2. 将 HTML 中的本地路径替换为微信 CDN URL
3. 图片格式：PNG/JPG，最大 2MB

### 7.3 封面处理

- 优先使用 `config.json` 中缓存的 `wechat_thumb_media_id`
- 如果不存在，上传 `cover.jpg` 获取 media_id
- 封面只上传一次，之后复用

### 7.4 草稿箱

- 使用草稿箱接口 `draft/add`
- 返回 `media_id` 即成功
- HTML 同时缓存到本地两份：
  - `output/wechat_draft_YYYYMMDD.html`
  - `~/.openclaw/workspace/ai-news/wechat_draft_YYYYMMDD.html`

---

## 八、配置管理

### 8.1 主配置文件

路径：`~/.openclaw/config.json`

```json
{
  "ai-news-v10": {
    "sources": [
      {"name": "huxiu", "enabled": true},
      {"name": "infoq", "enabled": true},
      {"name": "量子位", "enabled": true},
      {"name": "aibase", "enabled": true},
      {"name": "openrouter", "enabled": true},
      {"name": "huggingface", "enabled": true},
      {"name": "github", "enabled": true}
    ],
    "interceptors": [
      "time_filter",
      "keyword_filter",
      "bge_dedup",
      "llm_classify",
      "llm_summary"
    ],
    "bge_skip_sources": ["huggingface", "github", "openrouter"],
    "fetch_content_sources": ["量子位"],
    "limits": {
      "国内AI资讯": 15,
      "国外AI资讯": 15,
      "智能硬件": 5,
      "其它科技资讯": 5
    },
    "wechat_thumb_media_id": "OBa7s7v5pJj8C3xsRSuJHIpA0CnVzzikHstbq7wpg6b1PIl6_YmqTQiEm13GpoJ8"
  }
}
```

### 8.2 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `sources` | array | 全部启用 | 数据源配置，enabled=false 跳过 |
| `interceptors` | array | 5 个全部 | 拦截器执行顺序，禁用则从数组中移除 |
| `bge_skip_sources` | string[] | hf/gh/or | BGE 去重跳过的来源 |
| `fetch_content_sources` | string[] | 量子位 | 需要抓取详情页的数据源 |
| `limits` | dict | 见上 | 每个分类的最大条数 |
| `wechat_thumb_media_id` | string | 无 | 微信公众号封面 media_id（避免重复上传） |

---

## 九、运行与调度

### 9.1 手动运行

```bash
/usr/local/bin/python3 ~/.openclaw/workspace/skills/ai-news-v10/scripts/main.py
```

### 9.2 调度配置

通过 OpenClaw cron job 定时触发，建议每天 08:00 执行：

```json
{
  "name": "ai-news-daily",
  "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
  "payload": {"kind": "agentTurn", "message": "运行 AI 资讯早报"},
  "sessionTarget": "isolated",
  "delivery": {"mode": "announce", "channel": "feishu"}
}
```

### 9.3 OpenRouter 独立抓取

```bash
/usr/local/bin/python3 ~/.openclaw/workspace/skills/ai-news-v10/scripts/openrouter_scraper.py
```

建议在早报执行前 10 分钟通过 cron 触发，MonitorDB 写入后供早报读取。

---

## 十、技术要点与注意事项

### 10.1 内存优化

LLM 和 Playwright 的并发数必须控制在较低水平：
- LLM 并发信号量：2
- LLM 摘要线程池：max_workers=2
- 正文抓取线程池：max_workers=3

过高并发会导致 macOS 机器被 OOM Killer 杀掉（SIGKILL）。

### 10.2 Playwright 重试

如果 `page.wait_for_selector` 超时（页面 WAF 拦截），等待 3-5 秒后重试。

### 10.3 微信公众号 IP 白名单

修改微信公众号后台 IP 白名单后，需要 **10-15 分钟** 才能生效，不要立即重试。

### 10.4 LLM JSON 解析容错

`llm_classify` 和 `hot_insight` 的 JSON 解析设置了重试机制：
- 最多 5 次重试（指数退避）
- 解析失败时不直接退出，而是继续处理或使用备用方案

### 10.5 GitHub README 缓存

README 内容缓存 24 小时，LLM 生成的中文介绍缓存 5 天，避免频繁调用 API 和 LLM。

### 10.6 公司名识别

`company_patterns.py` 中定义了正则模式，用于从新闻标题中提取公司名（用于 OpenRouter 榜单的公司列显示）。

---

## 十一、依赖与环境

### 11.1 Python 环境

- Python 3.9（使用 `/usr/local/bin/python3` 而非系统默认）
- 依赖包：
  - `playwright` - 浏览器自动化
  - `beautifulsoup4` / `bs4` - HTML 解析
  - `requests` - HTTP 请求
  - `sentence-transformers` - BGE 向量计算
  - `jinja2` - HTML 模板渲染
  - `sqlmodel` - MonitorDB ORM

### 11.2 Playwright 浏览器

需提前安装：
```bash
playwright install chromium
```

### 11.3 外部依赖

- `ossinsight-github` skill：GitHub Trending 数据源依赖
- `ai-news-monitor` skill：MonitorDB 写入/读取依赖
- `table-image-generator` skill：PIL 表格图片生成依赖

---

*文档版本：v1.0 | 更新日期：2026-04-21*