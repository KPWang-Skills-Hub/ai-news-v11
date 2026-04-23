---
name: ai-news-v10
description: |
  AI资讯早报收集工具 v10。模块化架构，数据层与逻辑处理层分离。
  
  数据层：支持多个独立数据源（虎嗅、InfoQ、HuggingFace、GitHub Trending）
  逻辑层：拦截器链式处理（关键词过滤→BGE去重→LLM分类→LLM摘要）
  
  触发场景：
  (1) 用户要求生成AI资讯早报
  (2) 需要收集多个来源的AI资讯并处理
---

# AI资讯早报 v10

## 架构

```
ai-news-v10/
├── scripts/
│   ├── main.py              # 入口脚本
│   ├── config.py             # 配置
│   ├── sources/              # 数据源（可插拔）
│   │   ├── __init__.py
│   │   ├── base.py          # 数据源基类+数据结构
│   │   ├── huxiu.py         # 虎嗅
│   │   ├── infoq.py         # InfoQ
│   │   ├── huggingface.py   # HuggingFace
│   │   └── github.py        # GitHub Trending
│   └── interceptors/        # 拦截器（可配置顺序）
│       ├── __init__.py
│       ├── keyword_filter.py # 关键词过滤
│       ├── bge_dedup.py     # BGE去重
│       ├── llm_classify.py  # LLM分类
│       └── llm_summary.py    # LLM摘要
├── templates/                # HTML模板
└── SKILL.md
```

## 数据结构

```python
@dataclass
class NewsItem:
    title: str           # 标题
    desc: str = ""       # 描述
    link: str = ""       # 原文链接
    source: str = ""     # 来源
    time_ago: str = ""   # 相对时间
    category: str = ""   # 分类
    summary: str = ""    # AI摘要
    content: str = ""     # 正文内容
    extra: dict = field(default_factory=dict)  # 额外字段（如HF的stars等）
```

## 配置

在 `~/.openclaw/config.json` 中配置：
```json
{
  "ai-news-v10": {
    "sources": [
      {"name": "huxiu", "enabled": true},
      {"name": "infoq", "enabled": true},
      {"name": "huggingface", "enabled": true},
      {"name": "github", "enabled": true}
    ],
    "interceptors": [
      "keyword_filter",
      "bge_dedup", 
      "llm_classify",
      "llm_summary"
    ],
    "bge_skip_sources": ["huggingface", "github", "openrouter"],
    "fetch_content_sources": ["量子位"]
  }
}
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `bge_skip_sources` | string[] | `["huggingface", "github", "openrouter"]` | BGE语义去重跳过的数据源（这些来源的数据不需要去重） |
| `fetch_content_sources` | string[] | `["量子位"]` | 需要抓取正文的数据源（只有配置的数据源才会抓取详情页，其他用desc兜底） |

## 拦截器说明

| 拦截器 | 功能 | 可禁用 |
|--------|------|--------|
| keyword_filter | 关键词过滤，筛掉政治/金融/招聘等 | 是 |
| bge_dedup | BGE语义去重，阈值0.8（可配置跳过某些数据源） | 是 |
| llm_classify | LLM分类：国内AI/国外AI/智能硬件/其它科技 | 是 |
| llm_summary | LLM生成100-300字摘要（可配置只对特定数据源抓取正文） | 是 |

禁用拦截器：在配置中移除即可。

## 运行

```bash
python3 ~/.openclaw/workspace/skills/ai-news-v10/scripts/main.py
```