"""
HuggingFace Trending 数据源
参考 ai-news 的 fetch_huggingface.py 实现
"""
import json
import requests
from typing import List
from .base import NewsSource, NewsItem, register_source


API_URL = "https://hf-mirror.com/api/models"


def format_number(n: int) -> str:
    """格式化数字"""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


@register_source
class HuggingFaceSource(NewsSource):
    """HuggingFace Trending 模型数据源"""
    
    name = "huggingface"
    url = "https://huggingface.co/models"
    
    def collect(self) -> List[NewsItem]:
        """获取 HuggingFace Trending 列表"""
        headers = {"User-Agent": "Mozilla/5.0 (AI-News-v10)"}
        params = {
            "limit": 20,
            "sort": "trendingScore",
            "full": "False",
        }
        
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json()
                self.news_list = self.parse(data)
                print(f"   📰 {self.name}: 获取到 {len(self.news_list)} 条")
            else:
                print(f"   ❌ {self.name}: API返回 {resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ {self.name} 获取失败: {e}")
        
        return self.news_list
    
    def parse(self, data: list) -> List[NewsItem]:
        """解析 HuggingFace API 返回的数据"""
        news_list = []
        
        for model in data:
            model_id = model.get('id', '')
            if not model_id:
                continue
            
            # 提取关键指标
            downloads = model.get('downloads', 0)
            likes = model.get('likes', 0)
            pipeline = model.get('pipeline_tag', '')
            tags = model.get('tags', [])
            last_modified = model.get('lastModified', '')
            
            # 提取参数规模
            param_size = self._parse_param_size(model_id, tags)
            
            # 构建标题
            title = model_id
            if param_size:
                title = f"{model_id} ({param_size})"
            
            # 构建描述
            desc_parts = []
            desc_parts.append(f"⬇️{format_number(downloads)}")
            if likes > 0:
                desc_parts.append(f"❤️{format_number(likes)}")
            if pipeline:
                task_name = self._get_task_name(pipeline)
                desc_parts.append(f"🎯{task_name}")
            
            desc = " | ".join(desc_parts)
            
            # 额外信息（用于生成表格）
            extra = {
                'downloads': downloads,
                'likes': likes,
                'trendingScore': model.get('trendingScore', 0),
                'pipeline_tag': pipeline,
                'tags': tags[:5],
                'last_modified': last_modified[:10] if last_modified else '',
            }
            
            news = NewsItem(
                title=title,
                desc=desc,
                source=self.name,
                link=f"https://huggingface.co/{model_id}",
                time_ago="今日",
                extra=extra,
            )
            news_list.append(news)
        
        return news_list
    
    def _parse_param_size(self, model_id: str, tags: list) -> str:
        """解析参数规模"""
        size_keywords = {
            '0.5b': '0.5B', '1b': '1B', '1.5b': '1.5B', '2b': '2B', '2.5b': '2.5B', '3b': '3B',
            '4b': '4B', '7b': '7B', '8b': '8B', '9b': '9B', '10b': '10B', '12b': '12B',
            '13b': '13B', '14b': '14B', '20b': '20B', '30b': '30B', '32b': '32B',
            '70b': '70B', '72b': '72B', '110b': '110B', '180b': '180B', '405b': '405B',
        }
        
        model_id_lower = model_id.lower().replace('-', '').replace('_', '').replace('.', '')
        
        # 从ID中查找
        for key in sorted(size_keywords.keys(), key=len, reverse=True):
            if key in model_id_lower:
                return size_keywords[key]
        
        # 从tags中查找
        for tag in tags:
            tag_lower = tag.lower().replace('-', '').replace('_', '')
            for key in sorted(size_keywords.keys(), key=len, reverse=True):
                if key in tag_lower:
                    return size_keywords[key]
        
        return ''
    
    def _get_task_name(self, pipeline: str) -> str:
        """获取任务类型中文名"""
        task_names = {
            'text-generation': '文本生成',
            'text2text-generation': '文本转换',
            'image-text-to-text': '图文理解',
            'visual-question-answering': '视觉问答',
            'automatic-speech-recognition': '语音识别',
            'text-to-speech': '语音合成',
            'text-to-image': '文生图',
            'image-classification': '图像分类',
            'object-detection': '目标检测',
            'feature-extraction': '特征提取',
            'sentence-similarity': '句子相似度',
        }
        return task_names.get(pipeline, pipeline.replace('-', ' '))