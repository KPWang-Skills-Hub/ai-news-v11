"""
LLM 摘要拦截器 - v11 分批串行版本
使用大模型批量重写标题+正文，每批20条，串行处理
输入：原文标题 + 原文摘要
输出：重写标题（rewritten_title）+ 重写正文（summary）
"""
import json
import re
import time
from typing import List, Optional
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
class LlmSummaryInterceptor(Interceptor):
    """LLM 摘要拦截器 - 分批串行重写版本"""

    name = "llm_summary"
    description = "使用大模型重写标题+正文（每批20条，串行处理）"

    def process(self, data: List[NewsItem], **kwargs) -> InterceptorResult:
        """分批串行：每批20条，生成重写标题 + 重写正文"""

        log_interceptor("llm_summary", "INPUT", data)

        if not data:
            return InterceptorResult(success=True, data=[], message="无数据")

        # 分批
        batches = [data[i:i + BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
        batch_num = len(batches)

        total_success = 0

        for batch_idx, batch in enumerate(batches, 1):
            print(f"   🤖 LLM摘要 第{batch_idx}/{batch_num}批 ({len(batch)}条)...")

            # 串行：等上一批完成再发下一批
            batch_ok = self._process_batch(batch)
            total_success += batch_ok

            if batch_idx < batch_num:
                # 两批之间稍微等一下，避免连续快速请求
                time.sleep(1)

        print(f"   ✅ LLM摘要: 成功{total_success}/{len(data)}条")
        log_interceptor("llm_summary", "OUTPUT", data, f"成功{total_success}条")

        return InterceptorResult(
            success=True,
            data=data,
            message=f"生成{total_success}条摘要"
        )

    def _process_batch(self, batch: List[NewsItem]) -> int:
        """
        处理单批：发送LLM，解析分隔符格式，填充 rewritten_title + summary
        返回成功数量
        """
        # 构造输入文本
        input_text = ""
        for i, item in enumerate(batch, 1):
            input_text += f"# 第{i}条\n【原标题】{item.title}\n【原摘要】{item.desc or '（无摘要）'}\n\n"

        prompt = f"""你是一个专业的新闻资讯整合编辑。请批量处理以下新闻素材，生成适合在公众号发布的原创内容。

# 输入说明
每条素材包含【原标题】和【原摘要】。请逐条独立处理，绝对不要将多条内容合并或混淆。

# 处理规则

## 1. 标题重写规则（必须执行）
- 基于【原摘要】的核心事实进行创作。
- 严禁直接复制、粘贴原标题。
- 严禁简单替换同义词。
- 必须使用全新的句式和结构。
- 控制在30字以内。

## 2. 正文重写规则（必须执行）
- 严格基于【原摘要】中的客观事实（时间、地点、人物、事件、原因、结果）进行创作。
- 严禁复制原摘要的任何原句。
- 严禁沿用原文的段落结构和表达习惯。
- 必须使用全新的叙述逻辑和词汇进行深度改写。
- 字数控制在200-300字之间。
- 文风：客观、简洁、正式，符合资讯号风格。

## 3. 绝对禁止项
- 禁止添加任何主观评论、观点、预测或情感色彩。
- 禁止编造摘要中不存在的信息。
- 禁止侵犯原内容的著作权。

# 输出格式（极其重要，必须严格遵守）
按以下格式逐条输出，一条不多，一条不少。

---【第1条】
# 标题：[此处填写你重写的标题]
# 正文：[此处填写你重写的正文]
---
---【第2条】
# 标题：[此处填写你重写的标题]
# 正文：[此处填写你重写的正文]
---
...（以此类推）

# 注意事项
- 严格按照序号顺序处理，不得遗漏任何一条。
- 每条之间必须用---分隔，格式必须与示例完全一致。
- 输出内容为纯净的可直接复制文本，不要包含任何额外的解释、说明或问候语。
- 确保生成的正文与原标题/摘要无实质性相似。

# 开始处理
{input_text.strip()}"""

        raw_result = self._call_llm(prompt)

        if not raw_result:
            print(f"   ⚠️ LLM调用失败，该批全部跳过")
            return 0

        # 解析分隔符格式
        items_data = self._parse_delimiter_output(raw_result, len(batch))

        if items_data is None:
            print(f"   ⚠️ 解析分隔符失败，该批全部跳过")
            return 0

        # 填充到 NewsItem（按序号对应）
        success_count = 0
        for i, item in enumerate(batch, 1):
            if i in items_data:
                item.rewritten_title = items_data[i]['title']
                item.summary = items_data[i]['body']
                success_count += 1
            else:
                # 该条解析失败，跳过（保留原字段，不覆盖）
                print(f"   ⚠️ 第{i}条解析失败，跳过")

        print(f"   ✅ 本批成功 {success_count}/{len(batch)} 条")
        return success_count

    def _parse_delimiter_output(self, text: str, expected_count: int) -> Optional[dict]:
        """
        解析分隔符格式输出
        返回 {(序号): {"title": "...", "body": "..."}}
        """
        result = {}

        # 按 --- 分隔条目
        # 支持两种格式：
        # 1. ---【第1条】...\n# 标题：...\n# 正文：...
        # 2. ---\n---【第1条】\n# 标题：...\n# 正文：...

        # 先去掉可能的前后空白
        text = text.strip()

        # 按 --- 分割（考虑多种换行风格）
        parts = re.split(r'\n*---\n*', text)
        parts = [p.strip() for p in parts if p.strip()]

        for part in parts:
            # 匹配 "【第N条】"
            m = re.search(r'【第(\d+)条】', part)
            if not m:
                continue

            idx = int(m.group(1))

            # 提取标题
            title_m = re.search(r'#\s*标题[：:]\s*(.+)', part)
            # 提取正文
            body_m = re.search(r'#\s*正文[：:]\s*(.+)', part, re.DOTALL)

            if title_m and body_m:
                title = title_m.group(1).strip()
                body = body_m.group(1).strip()

                # 清理可能的 markdown 代码块标记
                title = re.sub(r'^```.*?```', '', title, flags=re.DOTALL).strip()
                body = re.sub(r'^```.*?```', '', body, flags=re.DOTALL).strip()

                if title and body:
                    result[idx] = {'title': title, 'body': body}

        # 检查是否所有条目都被解析
        found_count = len(result)
        if found_count == 0:
            print(f"   ⚠️ 未解析到任何条目，原始输出前200字: {text[:200]}")
            return None

        print(f"   📝 解析到 {found_count}/{expected_count} 条")
        return result

    def _call_llm(self, prompt: str, max_retries: int = 5) -> Optional[str]:
        """调用 MiniMax API，返回原始文本"""
        import urllib.request

        payload = {
            "model": "MiniMax-M2.5",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8000
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

                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                    if 'choices' in result and result['choices']:
                        content = result['choices'][0]['message']['content']
                        return content.strip()

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
