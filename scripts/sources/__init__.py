"""数据源模块入口"""
from .base import NewsSource, NewsItem, SOURCES_REGISTRY, register_source, get_source, list_sources

# 自动注册内置数据源
from . import huxiu
from . import infoq
from . import qbitai
from . import aibased
from . import huggingface
from . import github
from . import openrouter

__all__ = [
    'NewsSource',
    'NewsItem', 
    'SOURCES_REGISTRY',
    'register_source',
    'get_source',
    'list_sources',
]