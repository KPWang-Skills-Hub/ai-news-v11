"""
评分引擎配置
包含：关键词权重表、high_value 词表、来源乘数表、领域识别映射
所有评分相关配置集中管理，便于迭代调整
"""

# ============================================================
# 1. 关键词权重体系
# 每命中一个关键词类别，累加对应分数
# ============================================================
KEYWORD_WEIGHTS = {
    # 重大发布（+10分）
    "major_release": [
        "GPT-5", "Claude 4", "Sora", "Gemini 2",
        "Llama 3", "Claude 3.5", "o1", "o3", "GPT-4o",
        "GPT5", "Claude4", "Sora视频",
        # 新增：重要模型产品
        "Claude Opus", "Opus 4", "Opus 4.7",
        "Codex", "Gemma 4", "Gemma4",
        "Mistral", "MoE", "QwQ",
        "Qwen3", "Qwen2", "Qwen-Max",
        "DeepSeek-V3", "DeepSeek R1",
        "GLM-5", "GLM-4",
        "Yi-Large", "YI-Large",
        "Kimi-lite", "Doubao-Pro",
    ],
    # 基础模型（+6分）
    "base_model": [
        "GPT-4", "GPT4", "Claude 3", "Claude3",
        "LLaMA", "Llama 2", "Llama3",
        "通义", "文心", "混元", "盘古",
        "GLM-4", "GLM4", "ChatGLM",
        "DeepSeek", "Kimi", "Mistral",
        "Qwen2.5", "Qwen3.0", "Qwen-Turbo",
        "ERNIE-Speed", "ERNIE-4",
        "Hunyuan-Large", "Hunyuan-Turbo",
        "Yi-34B", "Yi-VL", "GLM-Edge",
        "Phi-3", "Phi-4",
    ],
    # 应用产品（+4分）
    "product": [
        "Copilot", "Perplexity", "Kimi", "豆包",
        "海螺", "星火", "SenseNova",
        "ChatGPT", "Gemini", "Claude",
    ],
    # AI智能体与应用（+5分）
    "intelligence": [
        "Agent", "AI Agent", "智能体", "AI智能体",
        "MCP", "模型上下文协议",
        "Grok", "Perplexity",
        "Agentic", "Agentic AI",
        "SWE-Pro",
        "Copilot", "CoPilot",
        "RAG", "检索增强", "知识库",
        "多智能体", "自主智能体",
        "o1", "o3", "推理模型", "Reasoning",
        "CoT", "思维链",
    ],
    # 开源生态（+3分）
    "opensource": [
        "开源", "GitHub", "Apache", "MIT",
        "开源模型", "开源大模型", "开源项目",
        "Hugging Face", "ModelScope", "魔搭",
        "Weights", "权重开放", "Open Weights",
    ],
    # 学术论文与研究（+2分）
    "academic": [
        "论文", "arxiv", "ACL", "CVPR", "NeurIPS",
        "ICML", "ICLR", "EMNLP", "AAAI",
        "ACL论文", "顶会", "学术",
        "报告", "指数", "榜单", "研究",
        "Benchmark", "SOTA",
        "Fine-tuning", "微调", "LoRA", "RLHF",
        "预训练", "Scaling Law",
    ],
    # AI基础设施（+4分）
    "infra": [
        "AI芯片", "算力", "NPU", "TPU",
        "GPU", "H100", "A100", "B100",
        "Blackwell", "CUDA", "训练集群",
        "推理芯片", "AI服务器",
        "API", "接口", "平台", "云端",
        "数据中心", "云服务",
    ],
    # 安全与漏洞（+4分）
    "security": [
        "漏洞", "安全", "攻击", "风险",
        "风险", "隐私", "数据泄露",
        "故障", "崩溃", "宕机",
    ],
}

# 权重分值表（与 KEYWORD_WEIGHTS 顺序对应）
KEYWORD_WEIGHT_SCORES = {
    "major_release": 10,
    "base_model": 6,
    "product": 4,
    "intelligence": 5,
    "opensource": 3,
    "academic": 2,
    "infra": 4,
    "security": 4,
}

# ============================================================
# 2. high_value 词表（加乘 2x）
# 命中任一词，关键词得分翻倍
# ============================================================
HIGH_VALUE_KEYWORDS = [
    "GPT-5", "Claude 4", "Sora", "Gemini 2",
    "Llama 3", "Claude 3.5", "o1", "o3", "GPT-4o",
    "GPT5", "Claude4",
    "OpenAI", "Anthropic", "Google",
    # 新增：高价值关键词
    "Opus 4", "Claude Opus", "Gemma 4",
    "Agent", "智能体",
    "DeepSeek", "MiniMax",
]

# ============================================================
# 3. 来源乘数表
# 权威来源 ×1.3，其他来源 ×1.0
# ============================================================
SOURCE_MULTIPLIERS = {
    "量子位": 1.3,
    "机器之心": 1.3,
    "虎嗅": 1.1,
    "InfoQ": 1.1,
}

DEFAULT_SOURCE_MULTIPLIER = 1.0

# ============================================================
# 4. 摘要质量阈值
# 低于此分数认为是"点击查看"类劣质摘要
# ============================================================
SUMMARY_QUALITY_THRESHOLD = 10  # desc 字符数低于此值，无实质内容

SUMMARY_QUALITY_SCORES = {
    "low": 0,      # < 10字符，或含"点击查看"等
    "medium": 5,   # 10-50字符，有简单描述
    "high": 15,    # > 50字符，有实质内容
}

# 低质量摘要关键词（含这些词的 desc 得 0 分）
LOW_QUALITY_DESC_PATTERNS = [
    "点击查看", "点击了解", "查看全文",
    "了解更多", "详情点击", "详情见",
    "请回复", "请查看",
]


# ============================================================
# 5. 桶限制配置
# ============================================================
BUCKET_LIMITS = {
    "company": 2,   # 同一公司最多展示条数
    "domain": 3,    # 同一领域最多展示条数
}

# ============================================================
# 6. BGE 去重配置
# ============================================================
DEDUP_THRESHOLD = 0.75          # 普通新闻去重阈值
HIGH_VALUE_DEDUP_THRESHOLD = 0.9  # high_value 新闻去重阈值（更高，保护重要新闻不被误杀）

# ============================================================
# 7. 评分结果封顶配置
# ============================================================
KEYWORD_SCORE_CAP = 40           # 关键词得分上限（防止通货膨胀）
MAX_FINAL_SCORE = 200           # 最终得分上限（参考值）
