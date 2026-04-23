"""
LLM 分类拦截器 - v11 分批串行版本
使用大模型对新闻进行过滤和分类，每批20条，串行处理
"""
import json
import time
from typing import List, Optional, Tuple
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from interceptors.base import Interceptor, InterceptorResult, register_interceptor
from sources.base import NewsItem
from interceptors.logger import log_interceptor


# MiniMax API 配置
MINI_MAX_API_KEY = "sk-cp-wTF01lPxZSg5kglem92SZUPwYthfQoAwvNa74N8ZySxN4TxPD0gnlNRt-eAMjtng41w-AL1D59j2W9IbpBMVrJH0xHRw-XG0PYU3fXnAbqjjvnkNcQoSSGY"
MINI_MAX_BASE_URL = "https://api.minimax.chat/v1"

# 每批数量
BATCH_SIZE = 20


@register_interceptor
class LlmClassifyInterceptor(Interceptor):
    """LLM 分类拦截器 - 分批串行"""

    name = "llm_classify"
    description = "使用大模型过滤和分类新闻（每批20条，串行处理）"

    def process(self, data: List[NewsItem], **kwargs) -> InterceptorResult:
        """分批串行：每批20条，过滤+分类"""

        log_interceptor("llm_classify", "INPUT", data)

        if not data:
            return InterceptorResult(success=True, data=[], message="无数据")

        # 统计
        total_in = len(data)
        all_filtered: List[NewsItem] = []

        # 分批
        batches = [data[i:i + BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
        batch_num = len(batches)

        for batch_idx, batch in enumerate(batches, 1):
            print(f"   🤖 LLM分类 第{batch_idx}/{batch_num}批 ({len(batch)}条)...")

            # 串行：等上一批完成再发下一批
            result = self._process_batch(batch)

            if result is None:
                # 本批完全失败，整批跳过
                print(f"   ⚠️ 第{batch_idx}批LLM调用失败，跳过该批")
                continue

            # 合并结果
            for item, category in result:
                item.category = category
                all_filtered.append(item)

        # 统计
        cat_counts = {}
        for item in all_filtered:
            cat_counts[item.category] = cat_counts.get(item.category, 0) + 1

        print(f"   🤖 LLM分类: 保留{len(all_filtered)}/{total_in}条")
        for cat, cnt in cat_counts.items():
            print(f"      {cat}: {cnt}条")

        log_interceptor("llm_classify", "OUTPUT", all_filtered,
                       f"保留{len(all_filtered)}条")

        return InterceptorResult(
            success=True,
            data=all_filtered,
            message=f"过滤+分类完成，保留{len(all_filtered)}条"
        )

    def _process_batch(self, batch: List[NewsItem]) -> Optional[List[Tuple]]:
        """
        处理单批：发送LLM，返回 [(item, category), ...]
        返回 None 表示本批完全失败
        """
        # 构造新闻文本
        news_text = ""
        for i, item in enumerate(batch, 1):
            news_text += f"{i}. {item.title}\n"

        prompt = f"""你是一个AI行业技术资讯筛选专家。请对以下新闻进行两项任务：

## 任务1: 过滤
剔除以下类型的新闻（只要符合任一条件就剔除）：
- 纯融资、债务、投资、股权相关：包括IPO、上市、股价、市值、并购、收购、债务融资、A轮B轮C轮融资、投资协议等（AI公司的产品/技术发布融资除外）
- 政治、宏观经济：关税、制裁、外交、政府政策、国会、总统等
- 纯招聘、裁员、求职：招聘岗位、裁员名单、求职经验分享
- 纯会议活动：征稿、报名、参会、展位、博览会、Meetup、沙龙报名

注意：AI公司发布新产品/新技术时的融资新闻应该保留，因为这是业务动态而非纯财务投资新闻。

## 任务2: 分类
对保留的新闻进行分类：
- 国内AI资讯：国内公司/模型/国内市场相关的新闻
- 国外AI资讯：国外公司/模型/国际市场相关的新闻（包括OpenAI、Anthropic、Google、Meta、Microsoft、NVIDIA等）
- 智能硬件：智能眼镜、AI眼镜、VR、AR、机器人、人形机器人等智能硬件相关新闻
- 其它科技资讯：不属于以上三类的科技新闻

## 新闻列表
{news_text}

输出JSON格式：
{{
  "filtered_indices": [保留的新闻序号列表],
  "categories": [{{"index": 序号, "category": "分类名称"}}, ...]
}}

只输出JSON，不要其它文字。"""

        result = self._call_llm(prompt)

        if not result:
            log_interceptor("llm_classify", "ERROR", batch, "LLM调用失败")
            return None

        try:
            filtered_indices = set(result.get('filtered_indices', []))
            categories = result.get('categories', [])

            # 建立 序号 -> 分类 的映射
            cat_map = {c['index']: c['category'] for c in categories}

            output = []
            for i, item in enumerate(batch, 1):
                if i in filtered_indices:
                    category = cat_map.get(i, '其它科技资讯')
                    output.append((item, category))
                # 不在 filtered_indices 中的新闻直接丢弃（过滤掉）

            return output

        except Exception as e:
            print(f"   ⚠️ 解析LLM结果失败: {e}")
            return None

    def _call_llm(self, prompt: str, max_retries: int = 5) -> Optional[dict]:
        """调用 MiniMax API，带指数退避重试"""
        import urllib.request

        payload = {
            "model": "MiniMax-M2.5",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000
        }

        for attempt in range(max_retries):
            try:
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    f"{MINI_MAX_BASE_URL}/text/chatcompletion_v2",
                    data=data,
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {MINI_MAX_API_KEY}'
                    }
                )

                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                    if 'choices' in result and result['choices']:
                        content = result['choices'][0]['message']['content']
                        content = content.strip()
                        if content.startswith('```'):
                            content = content.split('```')[1]
                            if content.startswith('json'):
                                content = content[4:]
                        return json.loads(content.strip())

            except Exception as e:
                status_code = getattr(e, 'code', None)
                if status_code is None and hasattr(e, 'reason'):
                    status_code = e.reason

                is_retryable = (
                    status_code in (429, 500, 502, 503, 504, 529) or
                    'timed out' in str(e).lower() or
                    'connection' in str(e).lower()
                )

                if is_retryable and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"   ⚠️ LLM调用失败(可重试,{attempt+1}/{max_retries}), 等{wait}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"   ⚠️ LLM调用最终失败({attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)

        return None
