"""
AI新闻公司/模型正则匹配表
用途：从新闻标题中提取公司主体，用于桶限制（bucket_limit）中的同一公司上限控制

测试命令：/usr/bin/python3 company_patterns.py

规则：
- 英文术语保留 \b 词边界以确保精确匹配
- 中文用纯字符串匹配（\b 对中文无效）
- 匹配顺序很重要：可能产生冲突的模式，更具体的放前面
  - 例如 "GLM-4" 和 r"\bGPT-\d" 都能匹配 "GPT-4"，中文词应放前面
  - 例如 "Llama-2" 和 "LLaMA" 应区分大小写
- 先匹配到的优先命中
"""

import re

# ============================================================
# 公司名/产品名正则列表（按匹配顺序排列）
# ============================================================
COMPANY_PATTERNS = [
    # ============================================================
    # 第一类：中国AI公司产品（中文/拼音，纯字符串匹配）
    # 这些产品的名字可能和英文产品名冲突（如 GLM-4 vs GPT-4）
    # 必须放在英文产品模式之前
    # ============================================================
    ("智谱AI", "智谱AI"),
    ("智谱", "智谱AI"),
    ("Zhipu", "智谱AI"),
    ("GLM-4", "智谱AI"),
    ("GLM-5", "智谱AI"),
    ("ChatGLM", "智谱AI"),
    ("月之暗面", "月之暗面"),
    ("Moonshot", "月之暗面"),
    ("Kimi", "月之暗面"),
    ("深度求索", "深度求索"),
    ("DeepSeek", "深度求索"),
    ("零一万物", "零一万物"),
    ("01.AI", "零一万物"),
    ("Yi-", "零一万物"),
    ("阶跃星辰", "阶跃星辰"),
    ("StepFun", "阶跃星辰"),
    ("Step-", "阶跃星辰"),
    ("面壁智能", "面壁智能"),
    ("面壁", "面壁智能"),
    ("MiniCPM", "面壁智能"),
    ("科大讯飞", "科大讯飞"),
    ("讯飞", "科大讯飞"),
    ("星火", "科大讯飞"),
    ("Spark", "科大讯飞"),
    ("商汤科技", "商汤"),
    ("商汤", "商汤"),
    ("SenseTime", "商汤"),
    ("SenseNova", "商汤"),
    ("秒画", "商汤"),
    ("旷视科技", "旷视"),
    ("旷视", "旷视"),
    ("云从科技", "云从科技"),
    ("云从", "云从科技"),
    ("出门问问", "出门问问"),
    ("MiniMax", "MiniMax"),
    ("稀宇科技", "MiniMax"),
    ("海螺AI", "MiniMax"),
    ("Hailuo", "MiniMax"),
    ("澜舟科技", "澜舟科技"),
    ("中科闻歌", "中科闻歌"),
    ("硅基流动", "硅基流动"),
    ("九章云极", "九章云极"),
    ("百分点", "百分点"),
    ("晓多科技", "晓多科技"),

    # ============================================================
    # 第二类：中国大厂（中文，纯字符串匹配）
    # ============================================================
    ("特斯拉", "特斯拉"),
    ("小马智行", "小马智行"),
    ("美团", "美团"),
    ("京东", "京东"),
    ("腾讯云", "腾讯云"),
    ("智元机器人", "智元"),
    ("智元", "智元"),
    ("PPIO", "PPIO"),
    ("百度", "百度"),
    ("文心一言", "百度"),
    ("文心", "百度"),
    ("ERNIE", "百度"),
    ("飞桨", "百度"),
    ("PaddlePaddle", "百度"),
    ("字节跳动", "字节跳动"),
    ("字节", "字节跳动"),
    ("ByteDance", "字节跳动"),
    ("豆包", "字节跳动"),
    ("Doubao", "字节跳动"),
    ("即梦", "字节跳动"),
    ("Dreamina", "字节跳动"),
    ("Coze", "字节跳动"),
    ("阿里", "阿里"),
    ("阿里巴巴", "阿里"),
    ("阿里云", "阿里"),
    ("通义千问", "阿里"),
    ("通义", "阿里"),
    ("通义万相", "阿里"),
    ("通义听悟", "阿里"),
    ("通义星尘", "阿里"),
    ("Qwen", "阿里"),
    ("钉钉AI", "阿里"),
    ("腾讯", "腾讯"),
    ("混元", "腾讯"),
    ("Tencent", "腾讯"),
    ("华为", "华为"),
    ("华为云", "华为"),
    ("盘古", "华为"),
    ("小米", "小米"),
    ("小爱同学", "小米"),
    ("MiLM", "小米"),
    ("OPPO", "Oppo"),
    ("Vivo", "Vivo"),
    ("荣耀", "荣耀"),
    ("三星", "三星"),
    ("Galaxy AI", "三星"),
    ("Vivo", "Vivo"),
    ("荣耀", "荣耀"),
    ("三星", "三星"),
    ("Galaxy AI", "三星"),

    # ============================================================
    # 第三类：海外 Big Tech 英文公司名（\b 精确匹配）
    # ============================================================
    (r"\bOpenAI\b", "OpenAI"),
    (r"\bAnthropic\b", "Anthropic"),
    (r"\bClaude\b", "Anthropic"),
    (r"\bOpus\b", "Anthropic"),
    (r"\bSonnet\b", "Anthropic"),
    (r"\bHaiku\b", "Anthropic"),
    (r"\bConstitutional AI\b", "Anthropic"),
    (r"\bGoogle\b", "Google"),
    (r"\bDeepMind\b", "Google"),
    (r"\bGemini\b", "Google"),
    (r"\bGemma\b", "Google"),
    (r"\bBard\b", "Google"),
    (r"\bImagen\b", "Google"),
    (r"\bVeo\b", "Google"),
    (r"\bPaLM\b", "Google"),
    (r"\bGoogle Cloud\b", "Google"),
    (r"\bMeta\b", "Meta"),
    (r"\bFacebook\b", "Meta"),
    (r"\bLlama\b", "Meta"),
    (r"\bLLaMA\b", "Meta"),
    (r"\bSAM\b", "Meta"),
    (r"\bSegment Anything\b", "Meta"),
    (r"\bMicrosoft\b", "Microsoft"),
    (r"\bCopilot\b", "Microsoft"),
    (r"\bAzure\b", "Microsoft"),
    (r"\bPhi-\d\b", "Microsoft"),
    (r"\bAmazon\b", "Amazon"),
    (r"\bAWS\b", "Amazon"),
    (r"\bBedrock\b", "Amazon"),
    (r"\bApple\b", "Apple"),
    (r"\bApple Intelligence\b", "Apple"),
    (r"\bxAI\b", "xAI"),
    (r"\bGrok\b", "xAI"),
    (r"\bNvidia\b", "Nvidia"),
    (r"\bNVIDIA\b", "Nvidia"),
    (r"\bCUDA\b", "Nvidia"),
    (r"\bNeMo\b", "Nvidia"),
    (r"\bNemotron\b", "Nvidia"),
    (r"\bIntel\b", "Intel"),
    (r"\bAMD\b", "AMD"),
    (r"\bQualcomm\b", "Qualcomm"),
    (r"\bTSMC\b", "TSMC"),

    # ============================================================
    # 第四类：海外 Big Tech 系别名（产品线/生态）
    # ============================================================
    (r"\bDeepMind\b", "Google"),
    (r"\bGemini\b", "Google"),
    (r"\bBard\b", "Google"),
    (r"\bPaLM\b", "Google"),
    (r"\bGemma\b", "Google"),
    (r"\bFacebook\b", "Meta"),
    (r"\bLLaMA\b", "Meta"),         # 大写 LLaMA = Meta 模型
    (r"\bLlama-\d", "Meta"),        # Llama-2/3 专属模式
    (r"\bLlama \d", "Meta"),        # Llama 2/3 专属模式
    (r"\bGitHub Copilot\b", "Microsoft"),
    (r"\bCopilot\b", "Microsoft"),
    (r"\bAzure\b", "Microsoft"),
    (r"\bBing\b", "Microsoft"),
    (r"\bPhi-\d\b", "Microsoft"),
    (r"\bApple Intelligence\b", "Apple"),
    (r"\bBedrock\b", "Amazon"),
    (r"\bAWS\b", "Amazon"),
    (r"\bCUDA\b", "Nvidia"),
    (r"\bH100\b", "Nvidia"),
    (r"\bB100\b", "Nvidia"),
    (r"\bBlackwell\b", "Nvidia"),
    (r"\bA100\b", "Nvidia"),
    (r"\bDGX\b", "Nvidia"),
    (r"\bGrok\b", "xAI"),

    # ============================================================
    # 第五类：OpenAI / Anthropic 产品（英文 \b 匹配）
    # 注意：这些模式在中文公司产品之后，避免误匹配 GLM-4/Claude 冲突
    # ============================================================
    (r"\bChatGPT\b", "OpenAI"),
    (r"\bSam Altman\b", "OpenAI"),
    (r"\bAltman(?!e)\b", "OpenAI"),   # Altman 但不匹配 Altman-e
    (r"\bSora\b", "OpenAI"),
    (r"\bo[13]\b", "OpenAI"),         # 匹配 o1/o3
    (r"\bGPT-\d", "OpenAI"),          # 匹配 GPT-4o/GPT-5/o1/o3
    (r"\bClaude-\d", "Anthropic"),
    (r"\bClaude \d", "Anthropic"),

    # ============================================================
    # 第六类：海外 AI 创业 / 研究机构
    # ============================================================
    (r"\bWaymo\b", "Waymo"),
    (r"\bCoreWeave\b", "CoreWeave"),
    (r"\bCoinbase\b", "Coinbase"),
    (r"\bLuma AI\b", "Luma AI"),
    (r"\bLuma\b", "Luma"),
    (r"\bCadence\b", "Cadence"),
    (r"\bIDC\b", "IDC"),
    (r"\bGartner\b", "Gartner"),
    (r"\bYann LeCun\b", "Meta"),
    (r"\bMistral(?:AI)?\b", "Mistral"),
    (r"\bMixtral\b", "Mistral"),
    (r"\bStability AI\b", "Stability AI"),
    (r"\bStable Diffusion\b", "Stability AI"),
    (r"\bStableLM\b", "Stability AI"),
    (r"\bMidjourney\b", "Midjourney"),
    (r"\bRunway\b", "Runway"),
    (r"\bPerplexity\b", "Perplexity"),
    (r"\bCohere\b", "Cohere"),
    (r"\bHugging Face\b", "Hugging Face"),
    (r"\bElevenLabs\b", "ElevenLabs"),
    (r"\bScale AI\b", "Scale AI"),
    (r"\bCharacter\.ai\b", "Character AI"),
    (r"\bInflection\b", "Inflection"),
    (r"\bJasper\b", "Jasper"),
    (r"\bReplicate\b", "Replicate"),
    (r"\bNotion AI\b", "Notion AI"),
    (r"\bPoe\b", "Poe"),
    (r"\bAleph Alpha\b", "Aleph Alpha"),

    # ============================================================
    # 第七类：通用兜底
    # ============================================================
    (r"\b大模型\b", "AI行业"),
    (r"\bLLM\b", "AI行业"),
    (r"\b多模态\b", "AI行业"),
    (r"\bAIGC\b", "AI行业"),
    (r"\b生成式AI\b", "AI行业"),
    (r"\bAGI\b", "AI行业"),
    (r"\bAgent\b", "AI行业"),
    (r"\bAI芯片\b", "AI基础设施"),
    (r"\bAI算力\b", "AI基础设施"),
    (r"\bAI基础设施\b", "AI基础设施"),
]


def extract_company(title: str) -> str:
    """
    从标题中提取公司名。
    遍历 COMPANY_PATTERNS 列表，第一个命中的公司名即为结果。
    若全部未命中，返回 "Other"。
    """
    for pattern, company in COMPANY_PATTERNS:
        try:
            if re.search(pattern, title, re.I):
                return company
        except re.error:
            continue
    return "Other"


if __name__ == "__main__":
    test_titles = [
        "OpenAI 发布 GPT-5，即日起面向所有用户开放",
        "Anthropic Claude 4 vs GPT-5：谁更强？",
        "谷歌 Gemini 2.0 曝光，多模态能力再升级",
        "Meta 开源 Llama 3，性能直逼 GPT-4",
        "微软 GitHub Copilot 新功能一览",
        "百度文心一言新增超级助理",
        "阿里 Qwen-72B 开源，刷新 SOTA",
        "腾讯混元大模型接入微信",
        "华为盘古大模型 5.0 发布",
        "字节豆包 APP 月活突破 1 亿",
        "智谱 AI 发布 GLM-4，性能接近 GPT-4",
        "月之暗面 Kimi 智能助手全面升级",
        "DeepSeek V3 重磅开源！评测超越 Llama 3",
        "零一万物 Yi-34B 开源，大海归来的模型",
        "阶跃星辰 Step-2 多模态大模型发布",
        "科大讯飞星火大模型 4.0 发布",
        "商汤 SenseNova 5.0 视觉能力曝光",
        "MiniMax 海螺 AI 文生视频功能上线",
        "国产大模型集体发布新一轮更新",
        "AI 芯片竞争加剧，Nvidia 地位受挑战",
        "Sam Altman 最新采访：OpenAI 未来规划曝光",
        "Altman 谈 GPT-5 安全问题",
        "LLaMA 3 被曝存在安全漏洞",
        "Llama 3.1 重磅发布",
        "Google AI 新突破，Bert 也要大改",
        "Bing 搜索引入 GPT-4，准确率提升 30%",
        "Amazon AWS 发布新 AI 芯片",
        "Azure AI 助力企业数字化转型",
        "Apple Intelligence 登陆 iPhone",
        "Stability AI 推出新图生图模型",
        "Hugging Face BERT 模型升级",
    ]

    print(f"{'标题':<48} {'公司':<12}")
    print("-" * 62)
    for t in test_titles:
        company = extract_company(t)
        print(f"{t:<48} {company:<12}")
