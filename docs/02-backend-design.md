# AI资讯早报监控面板 - 后端详细设计方案

> 版本：v2.0 | 日期：2026-04-10
> 目标读者：AI Agent（拿到此文档即可独立实现后端）

---

## 一、架构说明

### 1.1 职责划分

monitor 后端**只读不写**：
- **写操作**：由 v10 的 `MonitorDB` 类直接写 SQLite 文件
- **读操作**：由 monitor 的 FastAPI 后端读取 SQLite 文件，通过 HTTP API 提供给前端

```
v10 执行时：
    MonitorDB (v10_wrapper.py) ──写──▶ monitor.db

monitor 服务运行时：
    Vue3 前端 ──读──▶ FastAPI (GET 路由) ──读──▶ monitor.db
```

### 1.2 目录结构

```
backend/
├── __init__.py
├── models.py         # SQLModel 数据模型（写+读共用）
├── database.py       # 数据库基础连接（写+读共用）
├── writer.py         # 写入器（v10 用，MonitorDB 类）
├── reader.py         # 读取器（API 用）
└── api.py            # FastAPI 路由（全部 GET）
```

---

## 二、依赖安装

```bash
pip3 install fastapi uvicorn sqlmodel pydantic
```

---

## 三、数据模型（models.py）

```python
"""
backend/models.py

SQLModel 数据模型 — 所有表结构定义
读写共用，v10 和 monitor 后端都 import 这个文件
"""
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class DailyRun(SQLModel, table=True):
    """每日任务记录"""
    __tablename__ = "daily_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, unique=True, description="日期 20260410")
    started_at: str = Field(description="开始时间 ISO8601")
    finished_at: Optional[str] = Field(default=None, description="结束时间 ISO8601")
    status: str = Field(default="running", description="running / success / failed")
    duration_seconds: Optional[float] = Field(default=None, description="总耗时（秒）")
    total_collected: int = Field(default=0, description="HTML来源总采集数")
    total_output: int = Field(default=0, description="最终输出数")
    error_message: Optional[str] = Field(default=None, description="错误信息（如有）")

    raw_news: List["RawNews"] = Field(default_factory=list, sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    steps: List["InterceptorStep"] = Field(default_factory=list, sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    config_snapshots: List["ConfigSnapshot"] = Field(default_factory=list, sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class RawNews(SQLModel, table=True):
    """各数据源原始采集数据快照"""
    __tablename__ = "raw_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="daily_runs.id", index=True, description="关联 run_id")
    source: str = Field(index=True, description="来源")
    title: str = Field(description="标题")
    link: str = Field(default="", description="原文链接")
    time_ago: str = Field(default="", description="相对时间")
    desc: str = Field(default="", description="列表页描述")
    raw_extra: str = Field(default="{}", description="原始 extra JSON")
    collected_at: str = Field(description="采集时间 ISO8601")
    filtered_by: Optional[str] = Field(default=None, description="被哪个拦截器过滤")


class InterceptorStep(SQLModel, table=True):
    """每个拦截器的执行记录"""
    __tablename__ = "interceptor_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="daily_runs.id", index=True, description="关联 run_id")
    step: str = Field(index=True, description="拦截器名称")
    input_count: int = Field(description="输入新闻数")
    output_count: int = Field(description="输出新闻数")
    duration_seconds: Optional[float] = Field(default=None, description="该步骤耗时（秒）")
    removed_items: str = Field(default="[]", description="JSON：被过滤的新闻标题列表")

    removed_detail: List["RemovedItem"] = Field(default_factory=list, sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class RemovedItem(SQLModel, table=True):
    """被过滤的新闻明细"""
    __tablename__ = "removed_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    step_id: int = Field(foreign_key="interceptor_steps.id", index=True, description="关联 step_id")
    title: str = Field(description="新闻标题")
    source: str = Field(default="", description="来源")
    reason: str = Field(default="", description="过滤原因（简述）")
    reason_detail: str = Field(default="", description="过滤原因（详细）")
    category: str = Field(default="", description="LLM 分类结果")


class ConfigSnapshot(SQLModel, table=True):
    """配置变更快照"""
    __tablename__ = "config_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, description="日期")
    config_json: str = Field(description="完整配置 JSON")
    created_at: str = Field(description="创建时间 ISO8601")
```

---

## 四、数据库基础（database.py）

```python
"""
backend/database.py

数据库连接基础 — 读写共用
"""
import os
from sqlmodel import Session, create_engine, SQLModel

# 数据库路径从环境变量读取
DB_PATH = os.environ.get(
    "MONITOR_DB_PATH",
    "/Users/wangkaipeng/.openclaw/data/ai-news-monitor/monitor.db"
)


def get_engine():
    """获取数据库引擎"""
    # 确保目录存在
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    # 自动建表（如果不存在）
    SQLModel.metadata.create_all(engine)
    return engine
```

---

## 五、写入器（writer.py）— v10 用

```python
"""
backend/writer.py

写入器 — v10 的 main.py 导入这个模块来写数据库
v10 不需要知道数据库的读写细节，只需要调用这个模块

用法：
    import sys
    sys.path.insert(0, "/path/to/ai-news-monitor/backend")
    from writer import MonitorDB

    db = MonitorDB()
    run_id = db.start_run("20260410")
    db.write_raw_news(run_id, "huxiu", items)
    db.write_step(run_id, "keyword_filter", before=33, after=25, removed=removed_items)
    db.finish_run(run_id, status="success", total_output=24)
"""
import json
import time
from datetime import datetime
from typing import List, Optional

from .database import get_engine
from .models import DailyRun, RawNews, InterceptorStep, RemovedItem
from sqlmodel import Session


class MonitorDB:
    """
    监控数据库写入器

    v10 的 main.py 导入这个类来写数据。
    不需要知道数据库内部结构，只需要调用这几个方法。
    """

    def __init__(self, db_path: str = None):
        if db_path:
            import os
            os.environ["MONITOR_DB_PATH"] = db_path
        self.engine = get_engine()

    # -------------------------------------------------------------------------
    # 任务生命周期
    # -------------------------------------------------------------------------
    def start_run(self, date: str) -> int:
        """
        开始一次任务

        Args:
            date: 日期字符串，如 "20260410"

        Returns:
            run_id: 任务 ID
        """
        started_at = datetime.now().isoformat()
        with Session(self.engine) as session:
            run = DailyRun(date=date, started_at=started_at, status="running")
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def finish_run(self, run_id: int, status: str = "success",
                   total_output: int = 0, total_collected: int = 0,
                   error_message: str = None):
        """
        结束任务

        Args:
            run_id: 任务 ID
            status: "success" / "failed"
            total_output: 最终输出数
            total_collected: 总采集数
            error_message: 错误信息（如有）
        """
        finished_at = datetime.now().isoformat()

        # 计算耗时
        with Session(self.engine) as session:
            run = session.get(DailyRun, run_id)
            if run:
                try:
                    start = datetime.fromisoformat(run.started_at)
                    duration = (datetime.now() - start).total_seconds()
                except:
                    duration = 0.0
                run.status = status
                run.finished_at = finished_at
                run.duration_seconds = duration
                run.total_collected = total_collected
                run.total_output = total_output
                if error_message:
                    run.error_message = error_message
                session.commit()

    # -------------------------------------------------------------------------
    # 原始数据
    # -------------------------------------------------------------------------
    def write_raw_news(self, run_id: int, source: str, items: List):
        """
        写入原始采集数据

        Args:
            run_id: 任务 ID
            source: 数据源名称（huxiu / infoq / 量子位 等）
            items: NewsItem 列表
        """
        collected_at = datetime.now().isoformat()
        with Session(self.engine) as session:
            for item in items:
                raw = RawNews(
                    run_id=run_id,
                    source=source,
                    title=getattr(item, "title", ""),
                    link=getattr(item, "link", ""),
                    time_ago=getattr(item, "time_ago", ""),
                    desc=getattr(item, "desc", ""),
                    raw_extra=json.dumps(getattr(item, "extra", {}), ensure_ascii=False),
                    collected_at=collected_at,
                    filtered_by=None
                )
                session.add(raw)
            session.commit()

    # -------------------------------------------------------------------------
    # 拦截器步骤
    # -------------------------------------------------------------------------
    def write_step(self, run_id: int, step_name: str,
                   before: int, after: int,
                   removed: List = None,
                   reason_fn=None):
        """
        写入拦截器步骤

        Args:
            run_id: 任务 ID
            step_name: 拦截器名称
            before: 输入数量
            after: 输出数量
            removed: 被移除的 NewsItem 列表
            reason_fn: 函数，接收 item 返回过滤原因字符串（可选）
        """
        removed_titles_json = json.dumps(
            [getattr(r, "title", str(r)) for r in (removed or [])],
            ensure_ascii=False
        )

        with Session(self.engine) as session:
            step = InterceptorStep(
                run_id=run_id,
                step=step_name,
                input_count=before,
                output_count=after,
                removed_items=removed_titles_json
            )
            session.add(step)
            session.flush()

            # 写入被过滤的新闻明细
            if removed:
                for item in removed:
                    title = getattr(item, "title", str(item))
                    src = getattr(item, "source", "")
                    cat = getattr(item, "category", "")
                    reason = reason_fn(item) if reason_fn else ""

                    detail = RemovedItem(
                        step_id=step.id,
                        title=title,
                        source=src,
                        reason=reason,
                        reason_detail=reason,
                        category=cat
                    )
                    session.add(detail)

                # 标记 raw_news 中被过滤的新闻
                removed_titles = [getattr(r, "title", str(r)) for r in removed]
                raw_items = session.query(RawNews).filter(
                    RawNews.run_id == run_id,
                    RawNews.title.in_(removed_titles),
                    RawNews.filtered_by == None
                ).all()
                for raw in raw_items:
                    raw.filtered_by = step_name

            session.commit()
```

---

## 六、读取器（reader.py）— API 用

```python
"""
backend/reader.py

读取器 — FastAPI API 调用这个模块来查询数据库
只读不写
"""
import math
from typing import List, Optional, Tuple
from sqlmodel import Session, select

from .database import get_engine
from .models import DailyRun, RawNews, InterceptorStep, RemovedItem, ConfigSnapshot


class Reader:
    """数据库读取器（只读不写）"""

    def __init__(self):
        self.engine = get_engine()

    # -------------------------------------------------------------------------
    # DailyRun 查询
    # -------------------------------------------------------------------------
    def get_runs(self, days: int = 30, page: int = 1,
                 page_size: int = 20) -> Tuple[List[DailyRun], int]:
        """分页查询 run 列表"""
        with Session(self.engine) as session:
            total = session.query(DailyRun).count()
            offset = (page - 1) * page_size
            runs = session.query(DailyRun).order_by(
                DailyRun.date.desc()
            ).offset(offset).limit(page_size).all()
            return list(runs), total

    def get_run_with_steps(self, date: str) -> Optional[dict]:
        """获取 run 及所有关联数据"""
        with Session(self.engine) as session:
            run = session.query(DailyRun).filter(DailyRun.date == date).first()
            if not run:
                return None

            steps = session.query(InterceptorStep).filter(
                InterceptorStep.run_id == run.id
            ).all()

            raw_news = session.query(RawNews).filter(
                RawNews.run_id == run.id
            ).all()

            steps_with_removed = []
            for step in steps:
                removed = session.query(RemovedItem).filter(
                    RemovedItem.step_id == step.id
                ).all()
                steps_with_removed.append({"step": step, "removed": list(removed)})

            return {
                "run": run,
                "steps": steps_with_removed,
                "raw_news": list(raw_news)
            }

    def get_funnel_data(self, date: str) -> Optional[dict]:
        """获取漏斗图数据"""
        with Session(self.engine) as session:
            run = session.query(DailyRun).filter(DailyRun.date == date).first()
            if not run:
                return None

            steps = session.query(InterceptorStep).filter(
                InterceptorStep.run_id == run.id
            ).all()

            return {
                "run": run,
                "steps": [{
                    "step": s.step,
                    "input": s.input_count,
                    "output": s.output_count,
                    "removed": s.input_count - s.output_count,
                    "duration": s.duration_seconds
                } for s in steps]
            }

    # -------------------------------------------------------------------------
    # RawNews 查询
    # -------------------------------------------------------------------------
    def get_raw_news(self, date: str = None, source: str = None,
                     page: int = 1, page_size: int = 50) -> Tuple[List[RawNews], int]:
        """分页查询原始新闻"""
        with Session(self.engine) as session:
            query = session.query(RawNews)

            if date:
                sub = select(DailyRun.id).where(DailyRun.date == date)
                query = query.filter(RawNews.run_id.in_(sub))

            if source:
                query = query.filter(RawNews.source == source)

            total = query.count()
            offset = (page - 1) * page_size
            items = query.order_by(RawNews.id.desc()).offset(offset).limit(page_size).all()
            return list(items), total

    # -------------------------------------------------------------------------
    # RemovedItem 查询
    # -------------------------------------------------------------------------
    def get_removed(self, date: str = None, step: str = None,
                     source: str = None, page: int = 1,
                     page_size: int = 50) -> Tuple[List[tuple], int]:
        """
        分页查询被过滤的新闻

        Returns:
            [(RemovedItem, step_name, date), ...]
        """
        with Session(self.engine) as session:
            query = session.query(RemovedItem, InterceptorStep, DailyRun).join(
                InterceptorStep, RemovedItem.step_id == InterceptorStep.id
            ).join(DailyRun, InterceptorStep.run_id == DailyRun.id)

            if date:
                query = query.filter(DailyRun.date == date)
            if step:
                query = query.filter(InterceptorStep.step == step)
            if source:
                query = query.filter(RemovedItem.source == source)

            total = query.count()
            offset = (page - 1) * page_size
            results = query.order_by(
                DailyRun.date.desc()
            ).offset(offset).limit(page_size).all()

            return [(r[0], r[1].step, r[2].date) for r in results], total

    # -------------------------------------------------------------------------
    # Config 查询
    # -------------------------------------------------------------------------
    def get_latest_config_snapshot(self) -> Optional[ConfigSnapshot]:
        """获取最新配置快照"""
        with Session(self.engine) as session:
            return session.query(ConfigSnapshot).order_by(
                ConfigSnapshot.id.desc()
            ).first()

    def get_config_history(self, limit: int = 30) -> List[ConfigSnapshot]:
        """获取配置变更历史"""
        with Session(self.engine) as session:
            return list(session.query(ConfigSnapshot).order_by(
                ConfigSnapshot.id.desc()
            ).limit(limit).all())

    def save_config_snapshot(self, date: str, config_json: str):
        """保存配置快照（写操作，供 API 调用）"""
        with Session(self.engine) as session:
            snapshot = ConfigSnapshot(
                date=date,
                config_json=config_json,
                created_at=datetime.now().isoformat()
            )
            session.add(snapshot)
            session.commit()
```

---

## 七、API 路由（api.py）

```python
"""
backend/api.py

FastAPI 后端 — 全部 GET 接口（只读数据库）

启动命令：
    cd ~/.openclaw/workspace/skills/ai-news-monitor
    uvicorn backend.api:app --reload --port 8000 --host 127.0.0.1

API 文档（Swagger）：
    http://localhost:8000/docs
"""
import json
import math
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .reader import Reader
from .models import DailyRun, ConfigSnapshot

# ============================================================================
# 应用初始化
# ============================================================================
app = FastAPI(title="AI资讯早报监控面板", version="1.0")

# CORS：允许前端本地访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

reader = Reader()


# ============================================================================
# Pydantic 响应模型
# ============================================================================
class RunResponse(BaseModel):
    id: int
    date: str
    started_at: str
    finished_at: Optional[str]
    status: str
    duration_seconds: Optional[float]
    total_collected: int
    total_output: int
    error_message: Optional[str]


class FunnelStep(BaseModel):
    step: str
    input: int
    output: int
    removed: int
    duration: Optional[float]


class RemovedItemResponse(BaseModel):
    id: int
    title: str
    source: str
    reason: str
    reason_detail: str
    category: str
    step: str
    date: str


class RawNewsResponse(BaseModel):
    id: int
    source: str
    title: str
    link: str
    time_ago: str
    desc: str
    raw_extra: str
    collected_at: str
    filtered_by: Optional[str]


class ConfigHistoryItem(BaseModel):
    id: int
    date: str
    created_at: str


# ============================================================================
# API 路由（全部 GET）
# ============================================================================

@app.get("/")
async def root():
    """返回前端入口文件"""
    frontend_index = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if frontend_index.exists():
        return FileResponse(str(frontend_index))
    raise HTTPException(status_code=404, detail="前端未构建，请先运行 npm run build")


@app.get("/api/runs", response_model=dict)
async def get_runs(
    days: int = Query(default=30, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """每日任务列表"""
    runs, total = reader.get_runs(days=days, page=page, page_size=page_size)
    return {
        "runs": [RunResponse.model_validate(r).model_dump() for r in runs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0
    }


@app.get("/api/runs/{date}", response_model=dict)
async def get_run_detail(date: str):
    """单日任务完整数据"""
    data = reader.get_run_with_steps(date)
    if not data:
        raise HTTPException(status_code=404, detail="未找到该日期的数据")

    run = RunResponse.model_validate(data["run"]).model_dump()
    steps = []
    for s in data["steps"]:
        step_data = {
            "step": s["step"].step,
            "input_count": s["step"].input_count,
            "output_count": s["step"].output_count,
            "removed_count": s["step"].input_count - s["step"].output_count,
            "duration_seconds": s["step"].duration_seconds,
            "removed": [
                RemovedItemResponse(
                    id=r.id, title=r.title, source=r.source,
                    reason=r.reason, reason_detail=r.reason_detail,
                    category=r.category, step=s["step"].step, date=date
                ).model_dump()
                for r in s["removed"]
            ]
        }
        steps.append(step_data)

    return {"run": run, "steps": steps}


@app.get("/api/runs/{date}/funnel", response_model=dict)
async def get_funnel(date: str):
    """漏斗图数据"""
    data = reader.get_funnel_data(date)
    if not data or not data.get("run"):
        raise HTTPException(status_code=404, detail="未找到该日期的数据")

    run = RunResponse.model_validate(data["run"]).model_dump()
    funnel_steps = [
        FunnelStep(
            step=s["step"],
            input=s["input"],
            output=s["output"],
            removed=s["removed"],
            duration=s.get("duration")
        ).model_dump()
        for s in data["steps"]
    ]

    return {"run": run, "steps": funnel_steps}


@app.get("/api/raw-news", response_model=dict)
async def get_raw_news(
    date: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200)
):
    """原始数据列表"""
    items, total = reader.get_raw_news(
        date=date, source=source, page=page, page_size=page_size
    )

    return {
        "items": [
            RawNewsResponse(
                id=item.id,
                source=item.source,
                title=item.title,
                link=item.link,
                time_ago=item.time_ago,
                desc=item.desc,
                raw_extra=item.raw_extra,
                collected_at=item.collected_at,
                filtered_by=item.filtered_by
            ).model_dump()
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0
    }


@app.get("/api/removed", response_model=dict)
async def get_removed(
    date: Optional[str] = Query(default=None),
    step: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200)
):
    """被过滤的新闻列表"""
    items, total = reader.get_removed(
        date=date, step=step, source=source,
        page=page, page_size=page_size
    )

    result = [
        RemovedItemResponse(
            id=item.id,
            title=item.title,
            source=item.source,
            reason=item.reason,
            reason_detail=item.reason_detail,
            category=item.category,
            step=step_name,
            date=d
        ).model_dump()
        for item, step_name, d in items
    ]

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0
    }


@app.get("/api/config/current", response_model=dict)
async def get_current_config():
    """获取当前生效配置"""
    snapshot = reader.get_latest_config_snapshot()
    if snapshot:
        return {
            "config": json.loads(snapshot.config_json),
            "date": snapshot.date
        }
    return {"config": None, "date": None}


@app.get("/api/config/history", response_model=list)
async def get_config_history(
    limit: int = Query(default=30, ge=1, le=100)
):
    """配置变更历史"""
    snapshots = reader.get_config_history(limit=limit)
    return [
        ConfigHistoryItem(
            id=s.id, date=s.date, created_at=s.created_at
        ).model_dump()
        for s in snapshots
    ]


class ConfigUpdateRequest(BaseModel):
    config: dict


@app.post("/api/config", response_model=dict)
async def update_config(req: ConfigUpdateRequest):
    """保存配置（写入数据库快照 + config.json）"""
    today = datetime.now().strftime("%Y%m%d")
    config_json = json.dumps(req.config, ensure_ascii=False, indent=2)

    # 写入 config.json
    config_path = Path.home() / ".openclaw" / "data" / "ai-news-monitor" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
        else:
            existing = {}
        existing["ai-news-v10"] = req.config
        with open(config_path, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置失败: {e}")

    # 写入数据库快照
    reader.save_config_snapshot(today, config_json)

    return {"success": True, "date": today}


# ============================================================================
# 前端静态文件（构建后）
# ============================================================================
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")
```

---

## 八、API 完整列表

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/` | 返回前端入口文件 |
| GET | `/api/runs` | 每日任务列表 |
| GET | `/api/runs/{date}` | 单日完整数据 |
| GET | `/api/runs/{date}/funnel` | 漏斗图数据 |
| GET | `/api/raw-news` | 原始数据列表 |
| GET | `/api/removed` | 被过滤的新闻 |
| GET | `/api/config/current` | 当前配置 |
| GET | `/api/config/history` | 配置变更历史 |
| POST | `/api/config` | 保存配置 |

---

## 九、v10 埋点改造示例

在 v10 的 `main.py` 中加入以下改造（最小改动）：

```python
#!/usr/bin/env python3
"""
AI资讯早报 v10 - 主入口（加入监控埋点版）
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List

# 添加路径：指向 monitor 项目的 backend 目录
sys.path.insert(0, "/Users/wangkaipeng/.openclaw/workspace/skills/ai-news-monitor/backend")
from writer import MonitorDB

from sources import get_source
from interceptors import get_interceptor

# -------------------------------------------------------------------------
# 改造：加这一行
# -------------------------------------------------------------------------
monitor = MonitorDB()


def main():
    today = datetime.now().strftime("%Y%m%d")

    # 改造：任务开始
    run_id = monitor.start_run(today)

    try:
        config = load_config()
        html_news, api_news = collect_all_news(config)

        # 改造：收集阶段写原始数据
        for src, items in source_map.items():
            monitor.write_raw_news(run_id, src, items)

        # 拦截器阶段
        current_news = list(html_news)
        for name in config["interceptors"]:
            interceptor = get_interceptor(name)
            if not interceptor:
                continue

            before = len(current_news)
            result = interceptor.process(current_news)
            after = len(result.data) if result.success else before

            # 找出被移除的新闻
            before_titles = {getattr(i, "title", str(i)) for i in current_news}
            after_titles = {getattr(i, "title", str(i)) for i in (result.data or [])}
            removed = [i for i in current_news if getattr(i, "title", str(i)) in (before_titles - after_titles)]

            current_news = result.data or current_news

            # 改造：写拦截器步骤
            monitor.write_step(
                run_id=run_id,
                step_name=name,
                before=before,
                after=after,
                removed=removed,
                reason_fn=get_keyword_reason if name == "keyword_filter" else None
            )

        # 任务结束
        monitor.finish_run(
            run_id=run_id,
            status="success",
            total_collected=len(html_news),
            total_output=len(all_output)
        )

    except Exception as e:
        monitor.finish_run(run_id, status="failed", error_message=str(e))
        raise
```

---

## 十、历史数据迁移（scripts/migrate.py）

```python
"""
scripts/migrate.py

历史日志迁移脚本 — 解析现有的 logs/interceptors_*.log 文件，导入 SQLite

用法：
    cd ~/.openclaw/workspace/skills/ai-news-monitor
    python3 scripts/migrate.py

注意：此脚本只往 monitor.db 里写数据，不修改 v10 的日志文件
"""
import re
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from writer import MonitorDB


def parse_log_block(content: str) -> list:
    """
    解析日志块

    日志格式示例：
    [2026-04-10 09:16:05] keyword_filter - INPUT: 33条
      - [huxiu][国外AI资讯] 标题1
      - [infoq][] 标题2
    """
    blocks = []
    current = None
    current_items = []

    for line in content.split("\n"):
        header = re.match(
            r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\w+) - (INPUT|OUTPUT): (\d+)条',
            line.strip()
        )
        if header:
            if current:
                blocks.append((*current, list(current_items)))
            timestamp, step, direction, count = header.groups()
            current = (timestamp, step, direction, int(count))
            current_items = []
        else:
            item_match = re.match(r"\s+-\s+\[([^\]]+)\]\[([^\]]*)\]\s+(.+)", line)
            if item_match and current:
                source, category, title = item_match.groups()
                current_items.append({
                    "source": source,
                    "category": category,
                    "title": title.strip()
                })

    if current:
        blocks.append((*current, list(current_items)))

    return blocks


def migrate_log_file(log_path: Path, db: MonitorDB) -> dict:
    """迁移单个日志文件"""
    content = log_path.read_text(encoding="utf-8")
    date_match = re.search(r"interceptors_(\d{8})", log_path.name)
    date = date_match.group(1) if date_match else ""

    if not date:
        return {}

    blocks = parse_log_block(content)

    # 聚合每个拦截器的输入输出
    steps_data = {}
    for timestamp, step, direction, count, items in blocks:
        if step not in steps_data:
            steps_data[step] = {"input": 0, "output": 0, "removed": []}
        if direction == "INPUT":
            steps_data[step]["input"] = count
        elif direction == "OUTPUT":
            steps_data[step]["output"] = count
            steps_data[step]["removed"] = items

    try:
        run_id = db.start_run(date)
    except Exception:
        print(f"  ⚠️ {date} 已存在，跳过")
        return {}

    for step_name, data in steps_data.items():
        if data["input"] == 0:
            continue

        # 构造 RemovedItem 列表
        removed_items = []
        for item in data["removed"]:
            class FakeItem:
                title = item["title"]
                source = item["source"]
                category = item["category"]
            removed_items.append(FakeItem())

        db.write_step(
            run_id=run_id,
            step_name=step_name,
            before=data["input"],
            after=data["output"],
            removed=removed_items
        )

    total_input = sum(s["input"] for s in steps_data.values())
    total_output = sum(s["output"] for s in steps_data.values())
    db.finish_run(run_id, status="success",
                  total_collected=total_input,
                  total_output=total_output)

    return {
        "date": date,
        "steps": len(steps_data),
        "input": total_input,
        "output": total_output
    }


def main():
    print("📦 AI资讯早报 - 历史数据迁移")
    print("=" * 50)

    db = MonitorDB()

    # v10 的日志目录
    log_dir = Path.home() / ".openclaw" / "workspace" / "skills" / "ai-news-v10" / "scripts" / "output" / "logs"
    log_files = sorted(log_dir.glob("interceptors_*.log"))

    print(f"找到 {len(log_files)} 个日志文件\n")

    stats = {"files": 0}
    for log_file in log_files:
        print(f"处理: {log_file.name} ...", end=" ")
        result = migrate_log_file(log_file, db)
        if result:
            print(f"✅ {result['steps']} 步骤, {result['input']}→{result['output']}")
            stats["files"] += 1
        else:
            print("⏭️ 跳过")

    print(f"\n✅ 迁移完成！共 {stats['files']} 个文件")


if __name__ == "__main__":
    main()
```
