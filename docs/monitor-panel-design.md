# AI资讯早报监控面板设计方案

> 用于监控 AI 资讯采集全流程，直观查看每个拦截器每天过滤了哪些新闻、配置管理、智能分析。
> 版本：v1.0 | 日期：2026-04-10

---

## 一、项目概述

### 1.1 核心目标

将 AI 资讯采集流程（黑盒）改造成白盒，实现：
- **可观测**：每个拦截器每天过滤了哪些新闻，原因是什么
- **可配置**：在线修改拦截器参数，无需改代码
- **可分析**：LLM 生成优化建议，识别流程瓶颈
- **可追溯**：历史数据任意回放

### 1.2 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | Python 原生，异步，自动化 Swagger 文档 |
| 数据库 | SQLite | 零配置，文件级，本地部署无需安装 MySQL |
| ORM | SQLModel | 类型安全，支持 Pydantic v2 |
| 前端框架 | Vue3 + Vite | 开发效率高，组件化强 |
| UI 组件库 | Element Plus | 企业级后台组件丰富，自带暗黑模式 |
| 图表库 | ECharts | 漏斗图、折线图、饼图成熟稳定 |
| HTTP 客户端 | Axios | 对接 FastAPI |
| 包管理 | pnpm | 比 npm 快，推荐用 pnpm |

---

## 二、项目结构

```
ai-news-v10/
├── scripts/
│   ├── monitor/                  # 监控后端模块
│   │   ├── __init__.py
│   │   ├── models.py             # 数据模型（SQLModel）
│   │   ├── database.py           # 数据库读写封装
│   │   ├── events.py             # 事件发射器（埋点钩子）
│   │   └── api.py                # FastAPI 路由定义
│   └── frontend/                  # 前端
│       ├── src/
│       │   ├── api/              # API 调用层
│       │   │   └── index.ts
│       │   ├── views/            # 页面
│       │   │   ├── Dashboard.vue  # 概览页
│       │   │   ├── Filtered.vue   # 过滤明细页
│       │   │   ├── Config.vue     # 配置管理页
│       │   │   └── Logs.vue       # 日志中心页
│       │   ├── components/        # 公共组件
│       │   │   ├── FunnelChart.vue
│       │   │   ├── MetricCard.vue
│       │   │   └── NewsTable.vue
│       │   ├── router/
│       │   │   └── index.ts
│       │   ├── App.vue
│       │   └── main.ts
│       ├── package.json
│       ├── vite.config.ts
│       └── tsconfig.json
└── main.py                       # 改造：加入监控埋点
```

---

## 三、数据库设计

### 3.1 ER 图

```
daily_runs (每日任务)
    │
    └── 1:N ── interceptor_steps (拦截器步骤)
                   │
                   └── 1:N ── removed_items (被过滤的新闻)
```

### 3.2 表结构

#### `daily_runs` — 每日任务记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| date | TEXT UNIQUE | 日期 20260410 |
| started_at | TEXT | 开始时间 ISO8601 |
| finished_at | TEXT | 结束时间 ISO8601 |
| status | TEXT | success / failed / running |
| duration_seconds | REAL | 总耗时（秒） |
| total_collected | INTEGER | 总采集数（HTML来源） |
| total_output | INTEGER | 最终输出数 |
| token_used | INTEGER | Token 消耗估算 |

#### `interceptor_steps` — 拦截器执行步骤

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| run_id | INTEGER FK | 关联 daily_runs.id |
| step | TEXT | 拦截器名称（time_filter / keyword_filter 等） |
| input_count | INTEGER | 输入新闻数 |
| output_count | INTEGER | 输出新闻数 |
| removed_items | TEXT | JSON 格式，被过滤的新闻列表 |

#### `removed_items` — 被过滤的新闻明细

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| step_id | INTEGER FK | 关联 interceptor_steps.id |
| title | TEXT | 新闻标题 |
| source | TEXT | 来源（huxiu / infoq / 量子位） |
| reason | TEXT | 过滤原因（简述） |
| reason_detail | TEXT | 详细原因（如命中的关键词、相似度分数） |
| category | TEXT | LLM 分类结果（如有） |

#### `config_snapshots` — 配置快照

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| date | TEXT | 日期 |
| config_json | TEXT | 完整配置 JSON |
| created_at | TEXT | 创建时间 |

### 3.3 索引策略

```sql
CREATE INDEX idx_runs_date ON daily_runs(date);
CREATE INDEX idx_steps_run_id ON interceptor_steps(run_id);
CREATE INDEX idx_removed_step_id ON removed_items(step_id);
```

---

## 四、后端实现

### 4.1 依赖

```txt
# requirements-monitor.txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlmodel>=0.0.14
pydantic>=2.0
```

### 4.2 API 接口

#### 运行记录

```
GET  /api/runs
     → 返回最近30天的每日任务列表
     Query: ?days=30&page=1&page_size=20

GET  /api/runs/{date}
     → 返回单日完整数据（包含所有拦截器步骤）
     → 200: { run, steps[], removed_items{} }

GET  /api/runs/{date}/funnel
     → 返回漏斗图数据
     → 200: { steps: [{name, input, output}], total_collected, total_output }
```

#### 过滤明细

```
GET  /api/removed
     → 被过滤的新闻列表（全局，支持筛选）
     Query: ?date=20260410&step=keyword_filter&source=huxiu&page=1&page_size=50
     → 200: { items: [{title, source, step, reason, reason_detail}], total }
```

#### 配置管理

```
GET  /api/config/current
     → 返回当前生效配置（从 config.json 读取）

GET  /api/config/history
     → 返回配置变更历史快照列表

POST /api/config
     Body: { config: {...} }
     → 写入 config.json，重启后生效
     → 同时写入 config_snapshots 表
```

#### 日志

```
GET  /api/logs/{date}
     → 返回指定日期的运行日志
     → 200: { logs: [{timestamp, level, message}] }
```

#### WebSocket（实时进度）

```
WS   /ws/live
     → 任务运行时推送实时进度
     → 消息格式: { type: "progress", step: "llm_summary", progress: 45 }
```

### 4.3 事件埋点机制

在 `monitor/events.py` 中实现事件发射器，提供钩子函数供 `main.py` 调用：

```python
class Monitor:
    def __init__(self, db_path: str):
        self.db = Database(db_path)

    def start_run(self) -> int:
        """开始一次任务，返回 run_id"""
        run = DailyRun(date=today, status="running", started_at=now())
        self.db.save_run(run)
        return run.id

    def emit_step(self, run_id: int, step: str, before: int, after: int,
                  removed: List[NewsItem], reason_fn=None):
        """发射拦截器步骤事件"""
        step_record = InterceptorStep(
            run_id=run_id, step=step,
            input_count=before, output_count=after,
            removed_items=json.dumps(removed_titles)
        )
        step_id = self.db.save_step(step_record)

        # 逐条写入被过滤的新闻明细
        for item in removed:
            reason = reason_fn(item) if reason_fn else ""
            self.db.save_removed(step_id, item, reason)

    def finish_run(self, run_id: int, status: str, total_output: int, duration: float):
        """结束任务"""
        self.db.update_run(run_id, status=status,
                          total_output=total_output,
                          duration_seconds=duration)
```

### 4.4 main.py 改造（最小改动原则）

**不改现有拦截器代码**，只在 `main.py` 的关键节点调用埋点：

```python
# main.py 改造
from monitor.events import Monitor

def main():
    monitor = Monitor(db_path="monitor.db")

    # 1. 任务开始
    run_id = monitor.start_run()
    monitor.emit_collect("huxiu", len(huxiu_news))
    monitor.emit_collect("infoq", len(infoq_news))

    # 2. 拦截器阶段（改这一处）
    before_total = len(html_news)
    for name in config["interceptors"]:
        interceptor = get_interceptor(name)
        before = len(news_list)

        news_list = interceptor.process(news_list)

        after = len(news_list)
        removed = [item for item in html_news if item not in news_list]

        # 获取过滤原因（不同拦截器原因不同）
        if name == "keyword_filter":
            reason_fn = lambda i: get_keyword_reason(i)  # 命中的关键词
        elif name == "bge_dedup":
            reason_fn = lambda i: get_similarity_reason(i)  # 相似度分数
        else:
            reason_fn = None

        monitor.emit_step(run_id, name, before, after, removed, reason_fn)

    # 3. 任务结束
    monitor.finish_run(run_id, status="success",
                      total_output=len(all_output),
                      duration=time.time() - start_ts)
```

---

## 五、前端实现

### 5.1 技术栈

- **Vue3** (Composition API + `<script setup>`)
- **TypeScript**
- **Vite** (构建工具)
- **Vue Router 4** (路由)
- **Pinia** (状态管理)
- **Element Plus** (UI 组件)
- **ECharts** + **vue-echarts** (图表)
- **Axios** (HTTP 客户端)

### 5.2 页面设计

#### Dashboard 概览页（`/`）

```
┌─────────────────────────────────────────────────────────────┐
│  🕐 今日概览                              [2026-04-10] ▼   │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────┤
│ 采集总数  │ 最终输出  │  过滤率   │  总耗时   │ Token消耗 │状态 │
│   45     │    24    │   46%    │  127s    │   3200   │ ✅  │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────┘

┌──────────────────────────────┐ ┌──────────────────────────────┐
│ 📊 数据流转漏斗图             │ │ 📈 近7天过滤趋势             │
│                              │ │                              │
│  采集 45 ────────────────── │ │  [折线图: 各拦截器每日过滤量] │
│    ↓ time_filter (-12)      │ │                              │
│  33 ─────────────────────── │ │                              │
│    ↓ keyword_filter (-8)    │ └──────────────────────────────┘
│  25 ─────────────────────── │
│    ↓ bge_dedup (-1)         │
│  24 ─────────────────────── │
│    ↓ llm_classify (0)       │
│  24 ─────────────────────── │
│    ↓ llm_summary (0)       │
│  最终输出 24 ───────────────│
└──────────────────────────────┘

┌──────────────────────────────┐
│ ⚡ 各拦截器耗时排行          │
│ 1. llm_summary  45s         │
│ 2. bge_dedup    12s          │
│ 3. llm_classify 8s          │
└──────────────────────────────┘
```

#### 过滤明细页（`/filtered`）

```
┌────────────────────────────────────────────────────────────────┐
│ 筛选条件                                                        │
│ [拦截器 ▼] [来源 ▼] [日期 ▼]           [🔍 搜索标题]            │
├────────────────────────────────────────────────────────────────┤
│  [全部 25条] [time_filter 12条] [keyword_filter 8条] [bge 1条]  │
├────┬────────┬──────────────────────┬────────┬─────────────────┤
│ 状态 │  来源  │        标题          │拦截器  │    过滤原因      │
├────┼────────┼──────────────────────┼────────┼─────────────────┤
│ 🔴 │ 虎嗅   │ 亚马逊计划在密西西比州..│keyword │ 命中: [投资,..] │
│ 🔴 │ 虎嗅   │ AI短剧低至百元就能买..  │keyword │ 命中: [短剧]     │
│ 🔴 │ InfoQ  │ OpenAI推出ChatGPT..   │keyword │ 命中: [美元]     │
│ 🔴 │ InfoQ  │ Gemini推出更长音乐..   │bge_ded│ 相似: Muse S..  │
└────┴────────┴──────────────────────┴────────┴─────────────────┘
        ◀ 上一页    第 1/3 页    下一页 ▶
```

- 点击行可展开查看完整标题和摘要
- 悬停"过滤原因"显示详情（如命中的完整关键词列表）

#### 配置管理页（`/config`）

```
┌─────────────────────────────────────────────────────────────┐
│  拦截器配置                                        [💾 保存] │
├─────────────────────────────────────────────────────────────┤
│  ┌─ time_filter ─────────────────────────────────────────┐  │
│  │  时间窗口: [48] 小时                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─ keyword_filter ───────────────────────────────────────┐  │
│  │  关键词列表:                                           │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 政治相关: 中美, 外交, 制裁, 关税, 政策, 政府...       │  │  │
│  │  │ 宏观经济: IPO, 上市, 股价, 市值, 融资...           │  │  │
│  │  │ [+] 添加关键词  [🗑️ 删除]                          │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─ bge_dedup ───────────────────────────────────────────┐  │
│  │  相似度阈值: [0.80] ────●──────────── 范围: 0.5~1.0   │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─ 分类数量上限 ─────────────────────────────────────────┐  │
│  │  国内AI资讯: [15]  国外AI资讯: [15]                    │  │
│  │  智能硬件: [5]  其它科技资讯: [5]                      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### 日志中心页（`/logs`）

```
┌─────────────────────────────────────────────────────────────┐
│  [2026-04-10 ▼]  [INFO ▼]  [🔍 搜索]                        │
├─────────────────────────────────────────────────────────────┤
│  10:32:25  [INFO]  ▶ keyword_filter                        │
│  10:32:25  [INFO]     → 26 条                              │
│  10:32:30  [WARN]  ⚠️ LLM调用失败(1/3): JSON解析错误       │
│  10:32:31  [INFO]  🤖 LLM分类: 保留25条                     │
│  10:33:10  [INFO]  ✅ 完成! 最终输出: 24条                   │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 组件封装

| 组件 | 说明 |
|------|------|
| `MetricCard.vue` | 指标卡片（标题 + 数值 + 趋势箭头） |
| `FunnelChart.vue` | 漏斗图（ECharts，支持点击下钻） |
| `TrendChart.vue` | 趋势折线图（近7天数据） |
| `NewsTable.vue` | 新闻列表（支持展开行、筛选、分页） |
| `ConfigForm.vue` | 配置表单（按拦截器分组） |
| `LogViewer.vue` | 日志查看器（分级着色、搜索高亮） |
| `StatusBadge.vue` | 状态标签（running/success/failed） |

---

## 六、历史数据迁移方案

### 6.1 现状

v10 已运行一段时间，日志文件保存在：
```
~/.openclaw/workspace/skills/ai-news-v10/scripts/output/logs/interceptors_YYYYMMDD.log
```

日志格式示例：
```
[2026-04-10 09:16:05] keyword_filter - INPUT: 33条
  - [huxiu][] 阿里巴巴领投...
  - [infoq][] OpenAI推出ChatGPT...
[2026-04-10 09:16:05] keyword_filter - OUTPUT: 25条 | 移除8条
```

### 6.2 迁移脚本

编写一个一次性脚本 `scripts/monitor/migrate.py`，解析历史日志文件，导入 SQLite：

```python
# migrate.py - 历史数据迁移脚本
import re
import json
from pathlib import Path
from datetime import datetime
from sqlmodel import Session, create_engine

from models import DailyRun, InterceptorStep, RemovedItem

def parse_log_file(log_path: Path) -> dict:
    """解析单个日志文件"""
    content = log_path.read_text(encoding="utf-8")
    date_match = re.search(r"interceptors_(\d{8})", log_path.name)
    date = date_match.group(1) if date_match else ""

    steps = []
    # 用正则解析 INPUT/OUTPUT 块
    pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\w+) - (INPUT|OUTPUT): (\d+)条'
    for match in re.finditer(pattern, content):
        timestamp, step, direction, count = match.groups()
        if direction == "INPUT":
            steps.append({"step": step, "input": int(count), "output": None, "removed": []})

    # 解析 OUTPUT 和被移除的条目
    # ...（解析逻辑，根据实际日志格式编写）

    return {"date": date, "steps": steps}

def migrate_logs(log_dir: Path, engine):
    """迁移所有历史日志"""
    log_files = sorted(log_dir.glob("interceptors_*.log"))

    with Session(engine) as session:
        for log_file in log_files:
            data = parse_log_file(log_file)
            if not data["date"]:
                continue

            run = DailyRun(date=data["date"], status="success", total_collected=0, total_output=0)
            session.add(run)
            session.flush()

            for step_data in data["steps"]:
                step = InterceptorStep(
                    run_id=run.id,
                    step=step_data["step"],
                    input_count=step_data["input"],
                    output_count=step_data["output"],
                    removed_items=json.dumps(step_data["removed"])
                )
                session.add(step)

            session.commit()
        print(f"✅ 已迁移 {len(log_files)} 个日志文件")

if __name__ == "__main__":
    engine = create_engine("sqlite:///monitor.db")
    # SQLModel 自动建表
    SQLModel.metadata.create_all(engine)

    log_dir = Path(__file__).parent.parent / "output" / "logs"
    migrate_logs(log_dir, engine)
```

### 6.3 迁移执行

```bash
cd ~/.openclaw/workspace/skills/ai-news-v10/scripts
python3 -m monitor.migrate
# 输出: ✅ 已迁移 30 个日志文件
```

---

## 七、实施步骤

### 第一阶段：基础设施（0.5天）

1. 创建 `scripts/monitor/` 目录结构
2. 安装后端依赖：`pip3 install fastapi uvicorn sqlmodel`
3. 初始化 SQLite 数据库和表结构
4. 验证数据库读写正常

### 第二阶段：事件埋点（0.5天）

5. 实现 `monitor/events.py` 事件发射器
6. 改造 `main.py`，在收集阶段和每个拦截器步骤加入埋点
7. 跑一次今日采集，验证数据正确写入数据库
8. 确认每个被过滤的新闻都有 `reason_detail`（关键词过滤要包含命中的关键词列表）

### 第三阶段：FastAPI 后端（0.5天）

9. 实现所有 API 接口（runs / removed / config / logs）
10. 测试 Swagger 文档（浏览器访问 `http://localhost:8000/docs`）
11. 验证分页、筛选、排序功能正常

### 第四阶段：Vue3 前端（1.5天）

12. 初始化 Vite + Vue3 项目，安装依赖
13. 搭建页面框架：Dashboard / Filtered / Config / Logs
14. 对接 API，实现数据展示
15. 实现 ECharts 漏斗图（支持点击下钻到明细）
16. 页面样式调整（暗黑模式适配）

### 第五阶段：历史数据迁移（0.5天）

17. 编写 `migrate.py` 解析历史日志
18. 执行迁移脚本
19. 在前端"日志中心"验证历史数据可查询

### 第六阶段：收尾（0.5天）

20. 配置热更新（修改 config 后无需重启）
21. 启动脚本封装（`python3 -m monitor.api`）
22. 文档整理

---

## 八、启动方式

### 方式A：独立服务（推荐）

```bash
# 终端1：启动 Web 服务
cd ~/.openclaw/workspace/skills/ai-news-v10/scripts
uvicorn monitor.api:app --reload --port 8000 --host 127.0.0.1

# 终端2：运行采集任务
python3 scripts/main.py

# 浏览器访问
http://localhost:8000
```

### 方式B：集成启动

在 `main.py` 末尾，任务完成后启动 Web 服务：

```python
if __name__ == "__main__":
    main()
    # 任务完成后启动 Web 服务
    import uvicorn
    uvicorn.run("monitor.api:app", host="127.0.0.1", port=8000)
```

---

## 九、需确认事项

在开始实施前，需要你确认以下几点：

1. **API 数据源是否纳入监控？**
   - HuggingFace / GitHub / OpenRouter 这类 API 来源不经过拦截器，直接生成表格图片
   - 漏斗图是只展示 HTML 来源（虎嗅/InfoQ/量子位），还是把 API 来源也加进去？

2. **token_used 统计是否需要？**
   - 当前 `llm_summary.py` 的 `_generate_summary` 方法没有统计 Token 消耗
   - 要改造为每次 API 调用后累加写入数据库吗？（需要从 API 响应中提取 usage 字段）

3. **启动端口有偏好吗？**
   - 默认用 8000，如果被占用可以换其他端口

4. **配置修改热更新如何生效？**
   - 方案A：保存后立即生效（拦截器在内存中重新加载配置）
   - 方案B：保存后下次任务生效（只记录快照）
