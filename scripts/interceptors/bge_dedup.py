"""
BGE 去重拦截器
使用 BGE 语义向量实现新闻去重
"""
from typing import List
import sys
import os
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from interceptors.base import Interceptor, InterceptorResult, register_interceptor
from sources.base import NewsItem
from interceptors.logger import log_interceptor

# 配置 HuggingFace 镜像（解决国内网络无法访问 huggingface.co 的问题）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


THRESHOLD = 0.8


@register_interceptor
class BgeDedupInterceptor(Interceptor):
    """BGE 语义去重拦截器"""
    
    name = "bge_dedup"
    description = "使用 BGE 语义向量去重，阈值0.8"
    
    def process(self, data: List[NewsItem], **kwargs) -> InterceptorResult:
        """使用 BGE 语义向量去重"""
        
        # 记录输入
        log_interceptor("bge_dedup", "INPUT", data)
        
        # 获取配置：需要跳过的来源
        skip_sources = kwargs.get('skip_sources', set())
        
        # 过滤掉指定来源的数据
        original_count = len(data)
        if skip_sources:
            data = [item for item in data if item.source not in skip_sources]
            skipped_count = original_count - len(data)
            if skipped_count > 0:
                print(f"   ⏭️ BGE去重: 跳过 {skipped_count} 条 ({', '.join(skip_sources)})")
        
        if len(data) <= 1:
            log_interceptor("bge_dedup", "OUTPUT", data, "数据量<=1，跳过")
            return InterceptorResult(
                success=True,
                data=data,
                message="数据量<=1，跳过去重"
            )
        
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            
            print(f"   🔄 BGE去重中 ({len(data)}条)...")
            
            # 加载模型
            model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            
            # 提取标题
            titles = [item.title for item in data]
            
            # 计算向量
            embeddings = model.encode(titles, convert_to_numpy=True)
            
            # 去重
            unique_data = []
            for i, item in enumerate(data):
                emb = embeddings[i]
                is_duplicate = False
                
                for u_item in unique_data:
                    u_idx = data.index(u_item)
                    u_emb = embeddings[u_idx]
                    
                    # 计算余弦相似度
                    sim = float(np.dot(emb, u_emb) / (np.linalg.norm(emb) * np.linalg.norm(u_emb)))
                    
                    if sim > THRESHOLD:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_data.append(item)
            
            removed_count = len(data) - len(unique_data)
            print(f"   ✅ BGE去重: {len(data)}条 -> {len(unique_data)}条 (移除{removed_count}条)")
            
            # 记录输出
            log_interceptor("bge_dedup", "OUTPUT", unique_data, f"移除{removed_count}条")
            
            return InterceptorResult(
                success=True,
                data=unique_data,
                message=f"去重移除{removed_count}条"
            )
            
        except ImportError:
            print(f"   ⚠️ sentence-transformers 未安装，使用简单去重")
            return self._simple_dedup(data)
        except Exception as e:
            print(f"   ⚠️ BGE去重失败: {e}")
            log_interceptor("bge_dedup", "ERROR", data, str(e))
            return InterceptorResult(
                success=False,
                data=data,
                message=f"BGE去重失败: {e}"
            )
    
    def _simple_dedup(self, data: List[NewsItem]) -> InterceptorResult:
        """简单去重（基于标题完全匹配）"""
        seen = set()
        unique = []
        
        for item in data:
            title = item.title.strip()
            if title and title not in seen:
                seen.add(title)
                unique.append(item)
        
        removed = len(data) - len(unique)
        print(f"   🔄 简单去重: {len(data)}条 -> {len(unique)}条")
        
        return InterceptorResult(
            success=True,
            data=unique,
            message=f"简单去重移除{removed}条"
        )