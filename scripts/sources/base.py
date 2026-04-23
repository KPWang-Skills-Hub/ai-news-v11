"""
数据源基类与统一数据结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
import re


@dataclass
class NewsItem:
    """单条新闻数据结构（v11统一格式）"""
    title: str = ""           # 原文标题
    desc: str = ""            # 原文摘要
    link: str = ""            # 原文链接
    source: str = ""          # 来源名称
    time_ago: str = ""        # 相对时间
    category: str = ""        # 分类（国内AI资讯/国外AI资讯/智能硬件/其它科技资讯）
    summary: str = ""         # LLM重写后的正文（200-300字）
    rewritten_title: str = ""  # LLM重写后的标题（30字以内）
    content: str = ""          # 正文内容（暂不使用）
    extra: dict = field(default_factory=dict)  # 额外字段
    llm_description: str = ""  # LLM生成的中文介绍（仅GitHub项目）
    
    def to_dict(self):
        return {
            'title': self.title,
            'desc': self.desc,
            'link': self.link,
            'source': self.source,
            'time_ago': self.time_ago,
            'category': self.category,
            'summary': self.summary,
            'rewritten_title': self.rewritten_title,
            'content': self.content,
            'extra': self.extra,
            'llm_description': self.llm_description,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'NewsItem':
        """从字典创建"""
        return cls(
            title=d.get('title', ''),
            desc=d.get('desc', ''),
            link=d.get('link', ''),
            source=d.get('source', ''),
            time_ago=d.get('time_ago', ''),
            category=d.get('category', ''),
            summary=d.get('summary', ''),
            rewritten_title=d.get('rewritten_title', ''),
            content=d.get('content', ''),
            extra=d.get('extra', {}),
        )
    
    @property
    def hours(self) -> int:
        """将时间转换为小时数"""
        time_str = self.time_ago or ''

        minute_match = re.search(r'(\d+)\s*分钟前', time_str)
        hour_match = re.search(r'(\d+)\s*小时前', time_str)
        day_match = re.search(r'(\d+)\s*天前', time_str)

        if minute_match:
            return int(minute_match.group(1)) // 60
        elif hour_match:
            return int(hour_match.group(1))
        elif day_match:
            return int(day_match.group(1)) * 24
        elif '前天' in time_str:
            # 量子位格式：前天 18:17 → 48小时前
            return 48
        elif '昨天' in time_str:
            # 量子位格式：昨天 18:17 → 24小时前
            return 24

        return 999


class NewsSource(ABC):
    """新闻数据源抽象基类"""
    
    name: str = ""           # 数据源名称
    url: str = ""            # 数据源URL
    enabled: bool = True      # 是否启用
    
    def __init__(self):
        self.news_list: List[NewsItem] = []
    
    @abstractmethod
    def collect(self) -> List[NewsItem]:
        """收集新闻，返回新闻列表"""
        pass
    
    def filter_recent(self, days: int = 2) -> List[NewsItem]:
        """过滤近N天的新闻"""
        return [n for n in self.news_list if n.hours < days * 24 + 24]


# 注册表
SOURCES_REGISTRY: dict = {}


def register_source(cls):
    """装饰器：注册数据源"""
    SOURCES_REGISTRY[cls.name.lower()] = cls
    return cls


def get_source(name: str, **kwargs) -> Optional[NewsSource]:
    """获取数据源实例"""
    cls = SOURCES_REGISTRY.get(name.lower())
    if cls:
        return cls(**kwargs)
    return None


def list_sources() -> List[str]:
    """列出所有已注册的数据源"""
    return list(SOURCES_REGISTRY.keys())