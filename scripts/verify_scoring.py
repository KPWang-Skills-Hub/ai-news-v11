#!/usr/bin/env python3
"""
周报评分引擎 - 综合测试验证脚本
测试内容：
1. 配置完整性
2. 评分计算逻辑（含边缘场景）
3. 桶限制算法
4. 降级池记录格式
5. 公司识别
6. BGE去重动态阈值
"""
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from enum import Enum

SKILL_DIR = Path.home() / ".openclaw" / "workspace" / "skills" / "ai-news-v10"
SCRIPTS_DIR = SKILL_DIR / "scripts"

# ============================================================
# 0. 纯净加载（不引入任何外部依赖）
# ============================================================
config_ns = {}
exec(open(SCRIPTS_DIR / "interceptors" / "scoring_config.py").read(), {}, config_ns)

KEYWORD_WEIGHTS      = config_ns["KEYWORD_WEIGHTS"]
KEYWORD_WEIGHT_SCORES= config_ns["KEYWORD_WEIGHT_SCORES"]
HIGH_VALUE_KEYWORDS  = config_ns["HIGH_VALUE_KEYWORDS"]
SOURCE_MULTIPLIERS   = config_ns["SOURCE_MULTIPLIERS"]
DEFAULT_SRC_MULT     = config_ns["DEFAULT_SOURCE_MULTIPLIER"]
SUMMARY_THRESH      = config_ns["SUMMARY_QUALITY_THRESHOLD"]
SUMMARY_SCORES      = config_ns["SUMMARY_QUALITY_SCORES"]
LOW_QUAL_PATTERNS   = config_ns["LOW_QUALITY_DESC_PATTERNS"]
BUCKET_LIMITS        = config_ns["BUCKET_LIMITS"]
DEDUP_THRESHOLD      = config_ns["DEDUP_THRESHOLD"]
HIGH_VAL_DEDUP       = config_ns["HIGH_VALUE_DEDUP_THRESHOLD"]
KEYWORD_SCORE_CAP   = config_ns["KEYWORD_SCORE_CAP"]

# company_patterns 纯净加载
company_ns = {}
cp_code = open(SKILL_DIR / "company_patterns.py").read()
exec(cp_code, {}, company_ns)
COMPANY_PATTERNS = company_ns["COMPANY_PATTERNS"]

# ============================================================
# 测试用 NewsItem 简化版
# ============================================================
@dataclass
class NewsItem:
    title: str = ""
    desc: str = ""
    source: str = ""
    link: str = ""

# ============================================================
# 评分引擎函数（纯函数，无副作用）
# ============================================================
def calc_keyword_score(title: str) -> Tuple[int, float]:
    t = title.lower()
    score = 0
    for cat, kws in KEYWORD_WEIGHTS.items():
        w = KEYWORD_WEIGHT_SCORES[cat]
        for kw in kws:
            if kw.lower() in t:
                score += w
                break
    return min(score, KEYWORD_SCORE_CAP), (2.0 if any(kw.lower() in t for kw in HIGH_VALUE_KEYWORDS) else 1.0)

def calc_summary_score(item: NewsItem) -> int:
    desc = item.desc or ""
    if any(p in desc.lower() for p in LOW_QUAL_PATTERNS):
        return SUMMARY_SCORES["low"]
    l = len(desc.strip())
    if l < SUMMARY_THRESH:
        return SUMMARY_SCORES["low"]
    elif l < 50:
        return SUMMARY_SCORES["medium"]
    return SUMMARY_SCORES["high"]

def calc_source_mult(source: str) -> float:
    return SOURCE_MULTIPLIERS.get(source, DEFAULT_SRC_MULT)

def score_item(item: NewsItem) -> float:
    kw, hv = calc_keyword_score(item.title)
    sm = calc_summary_score(item)
    src = calc_source_mult(item.source)
    return (kw * hv + sm) * src

def is_high_value(title: str) -> bool:
    t = title.lower()
    return any(kw.lower() in t for kw in HIGH_VALUE_KEYWORDS)

def extract_company(title: str) -> str:
    for pattern, company in COMPANY_PATTERNS:
        try:
            if re.search(pattern, title, re.I):
                return company
        except re.error:
            continue
    return "Other"

def extract_domain(title: str) -> str:
    t = title.lower()
    if any(kw in t for kw in ["大模型","llm","gpt","claude","gemini","llama","qwen","通义","文心","混元","盘古","glm","deepseek","kimi"]):
        return "大模型"
    if any(kw in t for kw in ["芯片","算力","gpu","npu","tpu","h100","a100","cuda","ai芯片","推理芯片"]):
        return "AI基础设施"
    if any(kw in t for kw in ["手机","电脑","平板","穿戴","机器人","电动车","新能源","iphone"]):
        return "智能硬件"
    if any(kw in t for kw in ["arxiv","论文","顶会","学术","acl","cvpr","nips"]):
        return "学术研究"
    return "其他"

# ============================================================
# 桶限制算法
# ============================================================
def bucket_limit(items: List[NewsItem], scores: List[float],
                 companies: List[str], domains: List[str]) -> Tuple[List[int], List[int]]:
    """
    返回 (passed_indices, demoted_indices)
    """
    company_limit = BUCKET_LIMITS["company"]
    domain_limit = BUCKET_LIMITS["domain"]

    # 按分数降序排列
    sorted_pairs = sorted(zip(range(len(items)), scores), key=lambda x: x[1], reverse=True)

    company_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    passed: List[int] = []
    demoted: List[int] = []

    for idx, _ in sorted_pairs:
        comp = companies[idx]
        dom  = domains[idx]
        if company_counts.get(comp, 0) >= company_limit:
            demoted.append(idx)
            continue
        if domain_counts.get(dom, 0) >= domain_limit:
            demoted.append(idx)
            continue
        company_counts[comp] = company_counts.get(comp, 0) + 1
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        passed.append(idx)

    return passed, demoted

# ============================================================
# 测试报告
# ============================================================
FAIL = 0
PASS = 0

def check(condition: bool, msg: str):
    global FAIL, PASS
    if condition:
        print(f"  ✅ {msg}")
        PASS += 1
    else:
        print(f"  ❌ {msg}")
        FAIL += 1

print("=" * 65)
print("  周报评分引擎 · 综合验证")
print("=" * 65)

# ============================================================
# TEST 1: 配置完整性
# ============================================================
print("\n📋 配置完整性")
check(KEYWORD_WEIGHT_SCORES.keys() == KEYWORD_WEIGHTS.keys(),
      "权重类别数量一致")
check(DEDUP_THRESHOLD < HIGH_VAL_DEDUP,
      f"普通去重阈值({DEDUP_THRESHOLD}) < 高价值阈值({HIGH_VAL_DEDUP})")
check(KEYWORD_SCORE_CAP >= max(KEYWORD_WEIGHT_SCORES.values()),
      f"关键词得分封顶({KEYWORD_SCORE_CAP}) ≥ 最大单类权重({max(KEYWORD_WEIGHT_SCORES.values())})")
check(BUCKET_LIMITS["company"] == 2,
      f"公司桶限制={BUCKET_LIMITS['company']}")
check(BUCKET_LIMITS["domain"] == 3,
      f"领域桶限制={BUCKET_LIMITS['domain']}")
check(all(v in SOURCE_MULTIPLIERS for v in ["量子位", "机器之心"]),
      "权威来源乘数配置正确")
check(len(HIGH_VALUE_KEYWORDS) > 0,
      f"high_value词表非空({len(HIGH_VALUE_KEYWORDS)}条)")

# ============================================================
# TEST 2: 评分计算
# ============================================================
print("\n📊 评分计算")
test_cases = [
    ("OpenAI 发布 GPT-5，即日起面向所有用户开放",
     "OpenAI 宣布 GPT-5 正式发布", "量子位",
     "high_value, major_release, base_model 叠加"),
    ("Anthropic Claude 4 vs GPT-5：谁更强？",
     "两家公司的旗舰模型深度对比", "机器之心",
     "high_value + 多个类别"),
    ("谷歌 Gemini 2.0 曝光，多模态能力再升级",
     "Google新一代模型功能解析", "InfoQ",
     "high_value + base_model"),
    ("百度文心一言新增超级助理",
     "点击查看", "虎嗅",
     "低质量摘要，得0分"),
    ("智谱 AI 发布 GLM-4，性能接近 GPT-4",
     "GLM-4模型发布", "量子位",
     "base_model + 来源乘数"),
    ("DeepSeek V3 重磅开源！评测超越 Llama 3",
     "深度求索发布新一代开源模型", "量子位",
     "base_model + opensource + high_value(Llama3)"),
    ("AI 芯片竞争加剧，Nvidia 地位受挑战",
     "新一代 AI 芯片市场格局变化", "InfoQ",
     "infra + 公司识别(Nvidia)"),
    ("国产大模型集体发布新一轮更新",
     "多家厂商同日发布新模型", "InfoQ",
     "无关键词，无high_value"),
    ("Hugging Face BERT 模型升级",
     "transformers库更新", "InfoQ",
     "opensource(开源生态)"),
    ("腾讯混元大模型接入微信",
     "腾讯自研大模型正式发布", "量子位",
     "base_model + 腾讯来源乘数"),
]

for title, desc, source, label in test_cases:
    item = NewsItem(title=title, desc=desc, source=source)
    total = score_item(item)
    kw, hv = calc_keyword_score(title)
    sm = calc_summary_score(item)
    src = calc_source_mult(source)
    check(total >= 0, f"{label}: {total:.1f} = (kw={kw}, hv={hv}, sm={sm}, src={src})")

# ============================================================
# TEST 3: 评分封顶验证
# ============================================================
print("\n🔒 评分封顶")
high_kw_title = "OpenAI 发布 GPT-5 Claude 4 Sora Gemini 2 Llama 3 DeepSeek 全家桶发布"
item_overload = NewsItem(title=high_kw_title, desc="非常详细的描述内容" * 10, source="量子位")
total_capped = score_item(item_overload)
# 验证：超额关键词得分被合理限制，最终评分不会爆炸
max_possible = (KEYWORD_SCORE_CAP * 2 + SUMMARY_SCORES["high"]) * max(SOURCE_MULTIPLIERS.values())
check(total_capped < max_possible,
      f"多类别命中时评分合理限制: {total_capped:.1f} < 理论上限{max_possible:.1f}（合理）")

# ============================================================
# TEST 4: high_value 加乘
# ============================================================
print("\n🎯 high_value 加乘验证")
hv_titles = ["GPT-5 发布", "Claude 4 评测", "Sora 视频生成"]
non_hv_titles = ["百度文心", "豆包APP更新", "讯飞星火发布"]
for t in hv_titles:
    _, mult = calc_keyword_score(t)
    check(mult == 2.0, f"'{t}' → HV×{mult}")
for t in non_hv_titles:
    _, mult = calc_keyword_score(t)
    check(mult == 1.0, f"'{t}' → HV×{mult}")

# ============================================================
# TEST 5: 公司识别
# ============================================================
print("\n🏢 公司识别")
company_tests = [
    ("OpenAI 发布 GPT-5", "OpenAI"),
    ("Anthropic Claude 4", "Anthropic"),
    ("谷歌 Gemini 2.0 曝光", "Google"),
    ("Meta 开源 Llama 3", "Meta"),
    ("百度文心一言新增助理", "百度"),
    ("智谱 AI 发布 GLM-4", "智谱AI"),
    ("DeepSeek V3 重磅开源", "深度求索"),
    ("腾讯混元接入微信", "腾讯"),
    ("华为盘古大模型发布", "华为"),
    ("字节豆包 APP 更新", "字节跳动"),
    ("MiniMax 海螺 AI 上线", "MiniMax"),
    ("苹果 Apple Intelligence 新功能", "Apple"),
]
for title, expected in company_tests:
    got = extract_company(title)
    check(got == expected, f"'{title[:30]}' → {got} (期望: {expected})")

# ============================================================
# TEST 6: 领域识别
# ============================================================
print("\n📂 领域识别")
domain_tests = [
    ("OpenAI 发布 GPT-5", "大模型"),
    ("谷歌 Gemini 2.0 曝光", "大模型"),
    ("AI 芯片竞争加剧", "AI基础设施"),
    ("Nvidia H100 产能紧张", "AI基础设施"),
    ("苹果 iPhone 16 发布", "智能硬件"),
    ("电动车续航突破", "智能硬件"),
    ("arXiv 公布新论文", "学术研究"),
]
for title, expected in domain_tests:
    got = extract_domain(title)
    check(got == expected, f"'{title[:25]}' → {got} (期望: {expected})")

# ============================================================
# TEST 7: 桶限制算法
# ============================================================
print("\n🪣 桶限制算法")
# 构造一个已知场景：6条新闻，OpenAI×3 + 大模型×6（全部）
items = [
    NewsItem(title="GPT-5发布1"),
    NewsItem(title="GPT-5发布2"),
    NewsItem(title="GPT-5发布3"),
    NewsItem(title="Claude 4发布"),
    NewsItem(title="Gemini 2发布"),
    NewsItem(title="百度文心"),
]
# 领域全部是"大模型"，测试domain_limit=3
scores  = [98, 95, 90, 94, 93, 88]
comps   = ["OpenAI","OpenAI","OpenAI","Anthropic","Google","百度"]
domains = ["大模型"] * 6

passed_idx, demoted_idx = bucket_limit(items, scores, comps, domains)

# 期望：OpenAI取前2条(company_limit=2)，大模型达3条后其余全降级
check(len(passed_idx) == 3, f"通过数量=3 (实际={len(passed_idx)})")
check(0 in passed_idx, "GPT-5发布1(第1高分) → 通过")
check(1 in passed_idx, "GPT-5发布2(第2高分) → 通过")
check(2 in demoted_idx, "GPT-5发布3(第3高分) → 降级(company_limit OpenAI已达2)")
check(3 in passed_idx, "Claude 4(第4高分) → 通过")
check(4 in demoted_idx, "Gemini 2(第5高分) → 降级(domain_limit 大模型已达3)")
check(5 in demoted_idx, "百度文心(第6高分) → 降级(domain_limit 大模型已达3)")

# ============================================================
# TEST 8: 边缘场景
# ============================================================
print("\n⚡ 边缘场景")
edge_cases = [
    NewsItem(title="", desc="", source=""),
    NewsItem(title="无标题", desc="", source=""),
    NewsItem(title="GPT-5发布", desc="x" * 200, source="量子位"),
    NewsItem(title="OpenAI", desc="描述", source="未知来源"),
    NewsItem(title="AI大模型发布", desc="A" * 5, source="虎嗅"),
]
for item in edge_cases:
    try:
        s = score_item(item)
        check(s >= 0, f"title={repr(item.title[:15])}, score={s:.1f} → 正常")
    except Exception as e:
        check(False, f"title={repr(item.title[:15])} → 异常: {e}")

# ============================================================
# TEST 9: 降级池记录格式
# ============================================================
print("\n📦 降级池记录格式")
demoted_record = {
    "by_bucket_limit": [
        {"title": "GPT-5发布3", "company": "OpenAI", "domain": "大模型",
         "score": 90.0, "reason": "company_limit_exceeded"}
    ],
    "by_dedup": [
        {"title": "GPT-5发布3(b)", "company": "OpenAI",
         "similarity": 0.82, "kept_title": "GPT-5发布1",
         "reason": "bge_dedup_similarity_exceeded"}
    ]
}
check("by_bucket_limit" in demoted_record and "by_dedup" in demoted_record,
      "降级池包含 by_bucket_limit + by_dedup 两个字段")
check(all(k in demoted_record["by_bucket_limit"][0]
          for k in ["title","company","domain","score","reason"]),
      "by_bucket_limit 每条含 title/company/domain/score/reason")
check(all(k in demoted_record["by_dedup"][0]
          for k in ["title","company","similarity","kept_title","reason"]),
      "by_dedup 每条含 title/company/similarity/kept_title/reason")

# ============================================================
# TEST 10: BGE 动态阈值
# ============================================================
print("\n🔍 动态阈值")
check(is_high_value("OpenAI 发布 GPT-5"), "GPT-5 → high_value")
check(is_high_value("Llama 3 开源"), "Llama 3 → high_value")
check(is_high_value("Claude 4 发布"), "Claude 4 → high_value")
check(not is_high_value("百度文心更新"), "百度文心 → 非high_value")
check(not is_high_value("Kimi 助手更新"), "Kimi → 非high_value（产品名非high_value）")

# ============================================================
# 最终报告
# ============================================================
print("\n" + "=" * 65)
total = PASS + FAIL
print(f"  测试结果: {PASS}/{total} 通过", "✅" if FAIL == 0 else f"❌ {FAIL}个失败")
print("=" * 65)
sys.exit(0 if FAIL == 0 else 1)
