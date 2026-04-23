# AI资讯早报监控面板 - 总体设计方案

> 版本：v2.0 | 日期：2026-04-10
> 目标读者：AI Agent（拿到此文档即可独立开发）

---

## 一、项目概述

### 1.1 背景

AI 资讯早报 v10 每天自动采集、过滤、生成早报推送至微信公众号。当前面临以下问题：
- 无法查看每个拦截器每天过滤了哪些新闻
- 配置分散在代码中，无法可视化修改
- 无历史数据积累和问题追溯能力
- 流程黑盒，难以及时发现异常

### 1.2 核心目标

| 目标 | 说明 |
|------|------|
| **可观测** | 每个拦截器每天过滤了哪些新闻，原因是什么 |
| **可配置** | 在线修改拦截器参数，保存后下次任务生效 |
| **可追溯** | 原始数据快照，历史任意回放 |
| **可分析** | 数据源质量监控，流程瓶颈识别 |

---

## 二、系统架构

### 2.1 核心理念：两个完全独立的系统，通过 SQLite 文件通信

```
┌──────────────────────────────────────────────────────────────────┐
│                       v10 项目（资讯收集）                         │
│                                                                   │
│   Scheduled Task                                                   │
│       │                                                            │
│       ▼                                                            │
│   main.py                                                          │
│       │                                                            │
│       ├── collect_all_news()        # 收集数据                     │
│       ├── process_interceptors()    # 拦截器管道                   │
│       └── 埋点钩子 ──────────────────────────────────────────────  │
│            │                                                      │
│            ▼                                                      │
│       MonitorDB.write_run(...)     # 直接写 SQLite（不需要任何服务）│
│       MonitorDB.write_raw_news(...)                               │
│       MonitorDB.write_step(...)                                  │
└──────────────────────────────────────────────────────────────────┘

                          写数据
                              │
                              ▼
                    ┌─────────────────────┐
                    │  ~/.openclaw/data/   │
                    │  ai-news-monitor/   │
                    │  monitor.db         │  ← SQLite 数据库文件
                    └─────────────────────┘
                              │
                          读数据
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     monitor 项目（管理面板）                        │
│                                                                   │
│   FastAPI 后端（只读不写）                                        │
│       │                                                            │
│       ▼                                                            │
│   GET /api/runs                                                   │
│   GET /api/raw-news                                               │
│   GET /api/removed                                                │
│   GET /api/config/...                                             │
│       │                                                            │
│       ▼                                                            │
│   Vue3 前端                                                       │
│       │                                                            │
│       ▼                                                            │
│   Dashboard / RawNews / Filtered / Config / Logs                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 两个项目的职责边界

| 项目 | 职责 | 启动方式 |
|------|------|---------|
| **v10** | 资讯采集、过滤、生成早报 | 定时任务自动执行 |
| **monitor** | 数据可视化、配置管理 | 想看的时候手动启动 |

**关键点：**
- v10 执行时**不需要 monitor 服务在跑**
- v10 直接写 SQLite 文件，就像写文件一样简单
- monitor 服务只在**你想看页面时才需要开**

### 2.3 数据流

```
[定时触发 / 手动执行 v10]
        │
        ▼
┌─────────────────────────────────────────┐
│  v10 main.py                             │
│                                          │
│  1. collect_all_news()                   │
│     └── MonitorDB.write_raw_news()       │
│                                          │
│  2. process_interceptors()               │
│     ├── time_filter                      │
│     │   └── MonitorDB.write_step()       │
│     ├── keyword_filter                   │
│     │   └── MonitorDB.write_step()       │
│     ├── bge_dedup                        │
│     │   └── MonitorDB.write_step()       │
│     ├── llm_classify                     │
│     │   └── MonitorDB.write_step()       │
│     └── llm_summary                      │
│         └── MonitorDB.write_step()       │
│                                          │
│  3. MonitorDB.finish_run()               │
└─────────────────────────────────────────┘
        │
        ▼
  SQLite 文件（monitor.db）
        │
        ▼（看页面时才开 monitor）
┌─────────────────────────────────────────┐
│  monitor 前端 ← FastAPI 后端 ← SQLite    │
└─────────────────────────────────────────┘
```

---

## 三、目录结构

### 3.1 monitor 项目（新建）

```
~/.openclaw/workspace/skills/ai-news-monitor/
├── backend/                     # FastAPI 后端（只读数据库）
│   ├── __init__.py
│   ├── models.py               # SQLModel 数据模型
│   ├── database.py             # 数据库读取封装（供 API 使用）
│   ├── reader.py               # 读取器（供 API 调用）
│   └── api.py                  # FastAPI 路由（全部 GET）
│
├── frontend/                   # Vue3 前端
│   ├── src/
│   │   ├── api/              # API 调用层
│   │   ├── views/            # 页面组件
│   │   ├── components/       # 公共组件
│   │   ├── router/
│   │   ├── stores/
│   │   └── App.vue
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── scripts/                    # monitor 自己的脚本
│   ├── __init__.py
│   └── migrate.py             # 历史数据迁移脚本
│
├── v10_wrapper.py             # v10 埋点包装器（v10 导入这个来写数据库）
│   └── MonitorDB 类在这里
│
└── docs/                     # 设计文档
    ├── 01-overall-design.md
    ├── 02-backend-design.md
    └── 03-frontend-design.md
```

### 3.2 v10 项目（保持不变）

v10 完全不动原有的定时任务和代码逻辑。只需要在 `main.py` 里加几行埋点代码：

```python
# v10 的 main.py 改造（只改这一处）
import sys
sys.path.insert(0, "/path/to/ai-news-monitor")
from v10_wrapper import MonitorDB

db = MonitorDB()  # 写数据到 monitor.db

# 任务开始
run_id = db.start_run(today)

# 收集阶段
for src, items in sources.items():
    db.write_raw_news(run_id, src, items)

# 拦截器阶段
for name in interceptors:
    before = len(news)
    news = interceptor.process(news)
    after = len(news)
    db.write_step(run_id, name, before, after, removed)

# 任务结束
db.finish_run(run_id, "success", total_output)
```

### 3.3 数据目录

```
~/.openclaw/data/ai-news-monitor/
├── monitor.db                  # SQLite 数据库文件
└── config.json                # monitor 自己的配置文件（可选）
```

**重要：数据目录和代码目录完全分离，代码目录里没有 .db 文件。**

---

## 四、数据库设计

### 4.1 ER 关系图

```
daily_runs (每日任务)
    │
    ├── 1:N ── raw_news (原始数据快照)
    │
    ├── 1:N ── interceptor_steps (拦截器步骤)
    │              │
    │              └── 1:N ── removed_items (被过滤的新闻明细)
    │
    └── 1:N ── config_snapshots (配置快照)
```

### 4.2 表结构

共 5 张表：

| 表名 | 说明 |
|------|------|
| `daily_runs` | 每日任务记录 |
| `raw_news` | 各数据源原始采集数据快照 |
| `interceptor_steps` | 每个拦截器的执行记录 |
| `removed_items` | 被过滤的新闻明细 |
| `config_snapshots` | 配置变更快照 |

详见 `02-backend-design.md`。

---

## 五、启动方式

### 5.1 v10 资讯收集（定时任务，完全不变）

```bash
# 和现在一样执行，不需要 monitor 服务在跑
python3 scripts/main.py
# 执行时自动把数据写入 ~/.openclaw/data/ai-news-monitor/monitor.db
```

### 5.2 monitor 管理面板（想看的时候才开）

```bash
# 终端1：启动 FastAPI 后端
cd ~/.openclaw/workspace/skills/ai-news-monitor
uvicorn backend.api:app --reload --port 8000 --host 127.0.0.1

# 浏览器打开
http://localhost:8000
```

### 5.3 数据库路径配置

```python
# monitor 的后端和 v10_wrapper 都通过环境变量读取数据库路径
import os
MONITOR_DB_PATH = os.environ.get(
    "MONITOR_DB_PATH",
    "/Users/wangkaipeng/.openclaw/data/ai-news-monitor/monitor.db"
)
```

---

## 六、v10 改造方案（最小改动）

### 6.1 改造原则

**不改现有 v10 的任何逻辑，只在 main.py 里加埋点调用。**

### 6.2 改造位置

在 `main.py` 的以下位置加钩子：

1. **任务开始**：`monitor.start_run()`
2. **收集阶段**：`monitor.write_raw_news()` — 每收集完一个数据源写一次
3. **拦截器阶段**：`monitor.write_step()` — 每个拦截器执行完写一次
4. **任务结束**：`monitor.finish_run()`

### 6.3 过滤原因记录规范

| 拦截器 | reason 字段记录内容 |
|--------|------------------|
| time_filter | `"超过48小时（2026-04-08 10:30发布）"` |
| keyword_filter | `"命中关键词：[投资, 融资]"` |
| bge_dedup | `"与「Muse Spark...」相似度 0.87"` |
| llm_classify | `"分类为「其它科技资讯」，超出该分类上限"` |
| llm_summary | `"生成摘要失败（API超时）"` |

---

## 七、实施检查清单

### 第一阶段：monitor 后端基础设施（0.5天）
- [ ] 创建 `backend/` 目录
- [ ] 实现 `models.py`（5张表的 SQLModel 模型）
- [ ] 实现 `database.py`（只读封装）
- [ ] 实现 `reader.py`（查询逻辑）
- [ ] 实现 `api.py`（全部 GET 路由）
- [ ] 验证 API 正常

### 第二阶段：v10 埋点改造（0.5天）
- [ ] 创建 `v10_wrapper.py`（MonitorDB 类）
- [ ] 改造 v10 `main.py`，在收集和拦截器阶段加埋点
- [ ] 跑一次任务，验证数据正确写入数据库

### 第三阶段：monitor 前端（1.5天）
- [ ] 初始化 Vite + Vue3 项目
- [ ] 安装依赖：element-plus, echarts, vue-echarts, axios, pinia, vue-router
- [ ] 搭建 5 个页面
- [ ] 实现 ECharts 漏斗图
- [ ] 对接所有 API

### 第四阶段：历史数据迁移（0.5天）
- [ ] 编写 `scripts/migrate.py`
- [ ] 执行迁移
- [ ] 验证历史数据可查询

### 第五阶段：收尾（0.5天）
- [ ] 整理文档
- [ ] 写启动脚本封装
- [ ] 整体测试

---

## 八、技术选型

| 层级 | 技术选型 | 理由 |
|------|---------|------|
| 数据库 | SQLite + SQLModel | 零配置，文件级，无需服务进程 |
| 后端框架 | FastAPI + Uvicorn | Python 原生，异步，自动化 Swagger 文档 |
| 前端框架 | Vue3 + Vite | 组件化，生态成熟，开发效率高 |
| UI 组件库 | Element Plus | 企业级后台组件丰富，自带暗黑模式 |
| 图表库 | ECharts + vue-echarts | 漏斗图、折线图成熟稳定 |
| 包管理 | pnpm | 比 npm 快 |

---

## 九、依赖清单

### monitor 后端 Python 依赖

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlmodel>=0.0.14
pydantic>=2.0
```

### monitor 前端 Node 依赖

```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.6.0",
    "echarts": "^5.5.0",
    "vue-echarts": "^6.6.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vue-tsc": "^2.0.0"
  }
}
```

---

## 十、命名规范

### 数据库表名（snake_case，复数）

| 表名 | 说明 |
|------|------|
| `daily_runs` | 每日任务记录 |
| `raw_news` | 原始数据快照 |
| `interceptor_steps` | 拦截器步骤 |
| `removed_items` | 被过滤的新闻 |
| `config_snapshots` | 配置快照 |

### API 路由（RESTful，snake_case）

```
GET  /api/runs
GET  /api/runs/{date}
GET  /api/runs/{date}/funnel
GET  /api/raw-news
GET  /api/removed
GET  /api/config/current
GET  /api/config/history
POST /api/config
```

### 拦截器标识符（与 v10 现有代码一致）

```
time_filter
keyword_filter
bge_dedup
llm_classify
llm_summary
```

### 数据源标识符

```
huxiu      # 虎嗅
infoq      # InfoQ
量子位      # 量子位
huggingface # HuggingFace
github     # GitHub
openrouter  # OpenRouter
```
