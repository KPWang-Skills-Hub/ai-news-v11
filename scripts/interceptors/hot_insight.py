#!/usr/bin/env python3
"""
AI 选择热点和生成洞察
"""
import json
from typing import List, Tuple, Dict

# MiniMax API 配置
MINI_MAX_API_KEY = "sk-cp-wTF01lPxZSg5kglem92SZUPwYthfQoAwvNa74N8ZySxN4TxPD0gnlNRt-eAMjtng41w-AL1D59j2W9IbpBMVrJH0xHRw-XG0PYU3fXnAbqjjvnkNcQoSSGY"
MINI_MAX_BASE_URL = "https://api.minimax.chat/v1"


def call_minimax(prompt: str) -> str:
    """调用 MiniMax API"""
    import requests
    
    headers = {
        'Authorization': f'Bearer {MINI_MAX_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': 'MiniMax-M2.5',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 1000,
        'temperature': 0.7
    }
    
    try:
        resp = requests.post(
            f"{MINI_MAX_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        result = resp.json()
        return result.get('choices', [{}])[0].get('message', {}).get('content', '')
    except Exception as e:
        print(f"   ❌ MiniMax API 调用失败: {e}")
        return ''


def ai_select_hot_and_insight(news: List, categories: Dict[str, str]) -> Tuple[List[str], str]:
    """
    AI 选择热点和生成洞察
    
    Args:
        news: 新闻列表 (NewsItem)
        categories: 分类配置 {"分类名": 数量}
    
    Returns:
        (hot_items, insight) - 热点标题列表 和 洞察文本
    """
    # 按分类收集新闻
    news_by_cat = {}
    for cat in categories:
        news_by_cat[cat] = [n for n in news if n.category == cat]
    
    # 构建新闻文本
    news_text = ""
    for cat, items in news_by_cat.items():
        news_text += f"【{cat}】\n"
        for i, n in enumerate(items[:5], 1):
            # 优先用重写后的标题
            title = getattr(n, 'rewritten_title', None) or n.title
            news_text += f"{i}. {title}\n"
        news_text += "\n"
    
    # 计算热点数量
    total_hot = sum(categories.values())
    
    # 构建 prompt
    prompt = f"""你是科技分析师。请从以下新闻中选择{total_hot}条今日热点，并写一段200-300字的今日洞察。

热点要求：{'、'.join([f"{cat}{count}条" for cat, count in categories.items()])}

## 新闻列表
{news_text}

输出JSON格式：
{{"hot_items": ["标题1", "标题2", ...], "insight": "洞察内容"}}

注意：hot_items 必须正好 {total_hot} 条，insight 必须在 200-300 字之间。"""

    # 最多重试 5 次
    for attempt in range(5):
        print(f"   🔄 AI 选择热点尝试 {attempt + 1}/5...")
        
        result_str = call_minimax(prompt)
        if not result_str:
            print(f"   ⚠️ AI 返回为空")
            continue
        
        # 解析 JSON
        try:
            # 尝试提取 JSON
            if '```json' in result_str:
                result_str = result_str.split('```json')[1].split('```')[0]
            elif '```' in result_str:
                result_str = result_str.split('```')[1].split('```')[0]
            
            result = json.loads(result_str.strip())
            hot_items = result.get('hot_items', [])
            insight = result.get('insight', '')
            
            # 校验
            if len(hot_items) >= total_hot and 100 <= len(insight) <= 500:
                print(f"   ✅ 热点 {len(hot_items)} 条，洞察 {len(insight)} 字")
                return hot_items[:total_hot], insight
            else:
                print(f"   ⚠️ 校验失败: 热点{len(hot_items)}条, 洞察{len(insight)}字")
        except json.JSONDecodeError as e:
            print(f"   ⚠️ JSON 解析失败: {e}")
    
    # 备用方案：直接取前几条
    print(f"   ⚠️ AI 生成失败，使用备用方案")
    hot_items = []
    for cat, count in categories.items():
        items = news_by_cat.get(cat, [])
        for item in items[:count]:
            hot_items.append(item.title)
    
    return hot_items[:total_hot], "今日AI行业有多个重要动态，详情请查看各板块内容。"