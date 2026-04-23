"""拦截器模块入口"""
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from interceptors.base import Interceptor, InterceptorResult, INTERCEPTORS_REGISTRY, register_interceptor, get_interceptor, list_interceptors

# 自动注册内置拦截器
from interceptors import keyword_filter
from interceptors import bge_dedup
from interceptors import llm_classify
from interceptors import llm_summary
from interceptors import time_filter

__all__ = [
    'Interceptor',
    'InterceptorResult',
    'INTERCEPTORS_REGISTRY',
    'register_interceptor',
    'get_interceptor',
    'list_interceptors',
]
