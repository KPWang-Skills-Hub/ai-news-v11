"""
OpenRouter 模型榜单数据源
从 MonitorDB raw_news 表读取 openrouter 数据
"""
import json
import sys
from pathlib import Path
from typing import List

from .base import NewsItem, register_source
from sqlalchemy import text  # noqa: E402

# 复用 company_patterns 的公司提取逻辑
_ai_news_v10_path = str(Path(__file__).parent.parent.parent)
if _ai_news_v10_path not in sys.path:
    sys.path.insert(0, _ai_news_v10_path)
try:
    from company_patterns import extract_company  # type: ignore
except ImportError:
    # 兜底：如果导入失败，手动定义简单提取逻辑
    def extract_company(title: str) -> str:
        """从模型名称中提取公司名称（兜底实现）"""
        import re
        # 常见公司/产品前缀
        patterns = [
            (r"\bOpenAI\b", "OpenAI"),
            (r"\bAnthropic\b", "Anthropic"),
            (r"\bGoogle\b", "Google"),
            (r"\bMeta\b", "Meta"),
            (r"\bMicrosoft\b", "Microsoft"),
            (r"\bDeepSeek\b", "DeepSeek"),
            (r"\bMistral\b", "Mistral"),
            (r"\bAmazon\b", "Amazon"),
            (r"\bxAI\b", "xAI"),
            (r"\bGrok\b", "xAI"),
            (r"\bMiniMax\b", "MiniMax"),
            (r"\bByteDance\b", "ByteDance"),
            (r"\b01\.AI\b", "01.AI"),
            (r"\bQwen", "Alibaba"),
            (r"\bLlama", "Meta"),
            (r"\bGemma", "Google"),
            (r"\bGemini", "Google"),
            (r"\bClaude", "Anthropic"),
            (r"\bGPT", "OpenAI"),
            (r"\bMiMo", "Xiaomi"),
            (r"\bGLM", "ZhipuAI"),
            (r"\bYi-", "01.AI"),
            (r"\bSpark", "iFlytek"),
            (r"\bERNIE", "Baidu"),
            (r"\bDoubao", "ByteDance"),
            (r"\bKimi", "Moonshot"),
            (r"\bMoonshot", "Moonshot"),
        ]
        for pattern, company in patterns:
            if re.search(pattern, title, re.I):
                return company
        return "Other"


def _get_db():
    """获取 MonitorDB 实例"""
    _backend_path = str(
        Path.home() / ".openclaw" / "workspace" / "skills" / "ai-news-monitor" / "backend"
    )
    if _backend_path not in sys.path:
        sys.path.insert(0, _backend_path)
    from writer import MonitorDB
    return MonitorDB()


@register_source
class OpenRouterSource:
    """OpenRouter 模型榜单"""

    name = "openrouter"
    description = "OpenRouter 模型调用量榜单"

    def collect(self) -> List[NewsItem]:
        """从 MonitorDB raw_news 表读取 openrouter 数据"""
        try:
            db = _get_db()
            from sqlmodel import Session

            with Session(db.engine) as sess:
                rows = sess.exec(
                    text(
                        "SELECT title, desc, link, time_ago, raw_extra "
                        "FROM raw_news "
                        "WHERE source='openrouter' AND title != '' "
                        "ORDER BY id DESC LIMIT 20"
                    )
                ).all()

            if not rows:
                print(f"   ⚠️ openrouter: MonitorDB 无数据")
                return []

            items = []
            for row in rows:
                title, desc, link, time_ago, raw_extra = row
                try:
                    extra = json.loads(raw_extra) if raw_extra else {}
                except Exception:
                    extra = {}

                # 提取公司名称
                company = extract_company(title or "")

                items.append(
                    NewsItem(
                        title=title or "",
                        desc=desc or "",
                        link=link or "",
                        source="openrouter",
                        time_ago=time_ago or "-",
                        category="openrouter",
                        extra={
                            "rank": extra.get("rank", ""),
                            "change": extra.get("change", ""),
                            "company": company,
                        },
                    )
                )

            print(f"   📰 openrouter: MonitorDB 获取到 {len(items)} 条")
            return items

        except Exception as e:
            print(f"   ⚠️ openrouter: MonitorDB 读取失败: {e}")
            return []

    def filter_recent(self, days: int = 2) -> List[NewsItem]:
        """榜单不需要按时间过滤"""
        return self.collect()
