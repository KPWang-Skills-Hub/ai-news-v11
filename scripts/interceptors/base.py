"""
拦截器基类
"""
from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass


@dataclass
class InterceptorResult:
    """拦截器处理结果"""
    success: bool
    data: List  # 处理后的数据
    message: str = ""
    skipped: bool = False  # 是否跳过（被禁用）


class Interceptor(ABC):
    """拦截器抽象基类"""
    
    name: str = ""
    description: str = ""
    enabled: bool = True  # 默认启用
    
    @abstractmethod
    def process(self, data: List, **kwargs) -> InterceptorResult:
        """处理数据"""
        pass
    
    def __repr__(self):
        return f"<Interceptor: {self.name}>"


# 注册表
INTERCEPTORS_REGISTRY: dict = {}


def register_interceptor(cls):
    """装饰器：注册拦截器"""
    INTERCEPTORS_REGISTRY[cls.name.lower()] = cls
    return cls


def get_interceptor(name: str, **kwargs) -> Interceptor:
    """获取拦截器实例"""
    cls = INTERCEPTORS_REGISTRY.get(name.lower())
    if cls:
        return cls(**kwargs)
    return None


def list_interceptors() -> List[str]:
    """列出所有已注册的拦截器"""
    return list(INTERCEPTORS_REGISTRY.keys())