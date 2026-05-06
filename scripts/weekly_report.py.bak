#!/usr/bin/env python3
"""
周报生成脚本
读取过去7天的日报 JSON，合并后走评分+桶限制流程，生成周报

用法：
  python3 weekly_report.py                  # 生成过去7天周报
  python3 weekly_report.py --days 14         # 生成过去14天周报
  python3 weekly_report.py --dry-run        # 只跑流程不生成文件
"""
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# ---- 路径 setup ----
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent

# ---- 配置文件加载（直接读文件，不走 interceptors 导入链）----
def _load_scoring_config() -> dict:
    cfg_file = SCRIPTS_DIR / "interceptors" / "scoring_config.py"
    ns = {}
    exec(cfg_file.read_text(encoding="utf-8"), {}, ns)
    return ns


def _load_company_patterns() -> list:
    cp_file = SKILL_DIR / "company_patterns.py"
    ns = {}
    exec(cp_file.read_text(encoding="utf-8"), {}, ns)
    return ns.get("COMPANY_PATTERNS", [])


# ---- 数据结构 ----
class DailyItem:
    """兼容日报 JSON 格式的轻量数据结构"""
    __slots__ = ("title", "desc", "link", "source", "time_ago", "category",
                 "summary", "content", "extra")

    def __init__(self, d: dict):
        self.title = d.get("title", "").strip()
        self.desc = d.get("desc", "")
        self.link = d.get("link", "")
        self.source = d.get("source", "")
        self.time_ago = d.get("time_ago", "")
        self.category = d.get("category", "")
        self.summary = d.get("summary", "")
        self.content = d.get("content", "")
        self.extra: dict = d.get("extra", {})

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


# ---- 数据加载 ----
def load_week_data(days: int = 7) -> Tuple[List[DailyItem], List[str]]:
    """加载过去 N 天的日报 JSON，返回 (items, loaded_date_strs)"""
    today = datetime.now().date()
    items_map: Dict[str, DailyItem] = {}
    loaded_dates = []

    for i in range(days):
        date = today - timedelta(days=i)
        json_file = SCRIPTS_DIR / "output" / f"news_{date.strftime('%Y%m%d')}.json"
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            loaded_dates.append(date.strftime("%m/%d"))
            for d in data:
                title = d.get("title", "").strip()
                if title and title not in items_map:
                    items_map[title] = DailyItem(d)
        except Exception as e:
            print(f"   ⚠️  读取 {json_file.name} 失败: {e}")

    return list(items_map.values()), loaded_dates


# ---- 评分引擎 ----
def _extract_company(title: str, patterns: list) -> str:
    for p, company in patterns:
        try:
            if re.search(p, title, re.I):
                return company
        except re.error:
            continue
    return "Other"


def _extract_domain(title: str) -> str:
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


def _calc_keyword(title: str, cfg: dict) -> Tuple[int, float]:
    t = title.lower()
    score = 0
    for cat, kws in cfg["KEYWORD_WEIGHTS"].items():
        w = cfg["KEYWORD_WEIGHT_SCORES"][cat]
        if any(kw.lower() in t for kw in kws):
            score += w
    score = min(score, cfg["KEYWORD_SCORE_CAP"])
    hv_mult = 2.0 if any(kw.lower() in t for kw in cfg["HIGH_VALUE_KEYWORDS"]) else 1.0
    return score, hv_mult


def _calc_summary(item: DailyItem, cfg: dict) -> int:
    desc = (item.summary or item.desc or "").strip()
    if len(desc) < cfg["SUMMARY_QUALITY_THRESHOLD"]:
        return cfg["SUMMARY_QUALITY_SCORES"]["low"]
    if any(p in desc.lower() for p in cfg["LOW_QUALITY_DESC_PATTERNS"]):
        return cfg["SUMMARY_QUALITY_SCORES"]["low"]
    if len(desc) < 50:
        return cfg["SUMMARY_QUALITY_SCORES"]["medium"]
    return cfg["SUMMARY_QUALITY_SCORES"]["high"]


def _is_high_value(title: str, cfg: dict) -> bool:
    t = title.lower()
    return any(kw.lower() in t for kw in cfg["HIGH_VALUE_KEYWORDS"])


def run_scoring(items: List[DailyItem], cfg: dict, patterns: list,
                 skip_sources: set = None, *, skip_buckets: bool = False) -> Tuple[List[DailyItem], dict]:
    """
    在内存中对新闻评分、桶限制。
    返回 (passed_items, demoted_record)
    """
    if skip_sources is None:
        skip_sources = {"huggingface", "github", "openrouter"}

    # 过滤 skip_sources
    original = len(items)
    items = [it for it in items if it.source not in skip_sources]
    if original != len(items):
        print(f"   ⏭️ 过滤 skip_sources={skip_sources}，{original}条 -> {len(items)}条")

    # ---- BGE 语义去重 ----
    demoted_by_dedup: List[dict] = []
    try:
        import os
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from sentence_transformers import SentenceTransformer
        import numpy as np

        if len(items) > 1:
            print(f"   🔄 BGE语义去重 ({len(items)}条)...", flush=True)
            model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            titles = [it.title for it in items]
            embeddings = model.encode(titles, convert_to_numpy=True)
            title_to_idx = {it.title: i for i, it in enumerate(items)}

            unique_items: List[DailyItem] = []
            for i, item in enumerate(items):
                emb = embeddings[i]
                is_dup = False
                dup_simi = 0.0
                dup_kept = ""
                threshold = (cfg["HIGH_VALUE_DEDUP_THRESHOLD"] if _is_high_value(item.title, cfg)
                             else cfg["DEDUP_THRESHOLD"])
                for u_item in unique_items:
                    u_emb = embeddings[title_to_idx[u_item.title]]
                    sim = float(np.dot(emb, u_emb) / (np.linalg.norm(emb) * np.linalg.norm(u_emb)))
                    if sim > threshold:
                        is_dup = True
                        dup_simi = sim
                        dup_kept = u_item.title
                        break
                if is_dup:
                    demoted_by_dedup.append({
                        "title": item.title,
                        "company": _extract_company(item.title, patterns),
                        "similarity": round(dup_simi, 3),
                        "kept_title": dup_kept,
                        "reason": "bge_dedup_similarity_exceeded",
                    })
                else:
                    unique_items.append(item)

            removed = len(items) - len(unique_items)
            print(f"   ✅ BGE去重: {len(items)}条 -> {len(unique_items)}条 (移除{removed}条)")
            items = unique_items
    except Exception as e:
        print(f"   ⚠️ BGE去重不可用: {e}，跳过")

    # ---- 评分 ----
    scored: List[tuple] = []  # (item, score, company, domain)
    for item in items:
        kw_score, hv_mult = _calc_keyword(item.title, cfg)
        summary_score = _calc_summary(item, cfg)
        src_mult = cfg["SOURCE_MULTIPLIERS"].get(item.source, cfg["DEFAULT_SOURCE_MULTIPLIER"])
        final = (kw_score * hv_mult + summary_score) * src_mult
        company = _extract_company(item.title, patterns)
        domain = _extract_domain(item.title)
        scored.append((item, final, company, domain))

    # 降序
    scored.sort(key=lambda x: x[1], reverse=True)

    if skip_buckets:
        # 不做桶限制，返回所有通过去重的项目
        demoted_record = {
            "by_bucket_limit": [],
            "by_dedup": demoted_by_dedup,
        }
        return [item for item, _, _, _ in scored], demoted_record

    # ---- 桶限制 ----
    company_limit = cfg["BUCKET_LIMITS"]["company"]
    domain_limit = cfg["BUCKET_LIMITS"]["domain"]
    company_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    passed: List[tuple] = []
    demoted_by_bucket: List[dict] = []

    for item, score, company, domain in scored:
        if company_counts.get(company, 0) >= company_limit:
            demoted_by_bucket.append({
                "title": item.title, "company": company, "domain": domain,
                "score": round(score, 2), "reason": "company_limit_exceeded",
            })
            continue
        if domain_counts.get(domain, 0) >= domain_limit:
            demoted_by_bucket.append({
                "title": item.title, "company": company, "domain": domain,
                "score": round(score, 2), "reason": "domain_limit_exceeded",
            })
            continue
        company_counts[company] = company_counts.get(company, 0) + 1
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        passed.append((item, score, company, domain))

    total_demoted = len(demoted_by_bucket) + len(demoted_by_dedup)
    print(f"   📊 桶限制: {len(scored)}条 -> {len(passed)}条 "
          f"(桶限制{len(demoted_by_bucket)}条 / 去重{len(demoted_by_dedup)}条)")

    demoted_record = {
        "by_bucket_limit": demoted_by_bucket,
        "by_dedup": demoted_by_dedup,
    }
    return [item for item, _, _, _ in passed], demoted_record


# ---- 周报分类 ----
def _apply_buckets_separate(domestic_items, international_items, cfg, patterns):
    """
    对国内/国际两组分别做评分 + 桶限制。
    返回 (dom_passed, dom_demoted, int_passed, int_demoted, combined_demoted)
    """
    import re
    KWW = cfg["KEYWORD_WEIGHTS"]
    KWWS = cfg["KEYWORD_WEIGHT_SCORES"]
    HV = cfg["HIGH_VALUE_KEYWORDS"]
    cl = cfg["BUCKET_LIMITS"]["company"]
    dl = cfg["BUCKET_LIMITS"]["domain"]

    def score_item(title):
        t = title.lower()
        kw = sum(KWWS[cat] for cat, kws in KWW.items() if any(k.lower() in t for k in kws))
        kw = min(kw, 40)
        hv = 2.0 if any(k.lower() in t for k in HV) else 1.0
        return kw * hv

    def extract_domain(title):
        t = title.lower()
        if any(kw in t for kw in ["大模型","llm","gpt","claude","gemini","llama","qwen","通义","文心","混元","盘古","glm","deepseek","kimi"]): return "大模型"
        if any(kw in t for kw in ["芯片","算力","gpu","npu","tpu","h100","a100","cuda","ai芯片","推理芯片"]): return "AI基础设施"
        if any(kw in t for kw in ["手机","电脑","平板","穿戴","机器人","电动车","新能源","iphone"]): return "智能硬件"
        if any(kw in t for kw in ["arxiv","论文","顶会","学术","acl","cvpr","nips"]): return "学术研究"
        return "其他"

    def apply_buckets(items):
        scored = [(it, score_item(it.title), extract_domain(it.title)) for it in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        cc = {}; dc = {}; passed = []; demoted = []
        for it, score, domain in scored:
            co = _extract_company_fast(it.title, patterns)
            if cc.get(co, 0) >= cl:
                demoted.append({"title": it.title, "company": co, "domain": domain, "score": round(score, 2), "reason": "company_limit_exceeded"})
                continue
            if dc.get(domain, 0) >= dl:
                demoted.append({"title": it.title, "company": co, "domain": domain, "score": round(score, 2), "reason": "domain_limit_exceeded"})
                continue
            cc[co] = cc.get(co, 0) + 1
            dc[domain] = dc.get(domain, 0) + 1
            passed.append(it)
        return passed, demoted

    dom_passed, dom_demo = apply_buckets(domestic_items)
    int_passed, int_demo = apply_buckets(international_items)
    combined = dom_demo + int_demo
    return dom_passed, dom_demo, int_passed, int_demo, combined


def _extract_company_fast(title, patterns):
    import re
    for p, c in patterns:
        try:
            if re.search(p, title, re.I): return c
        except re.error: continue
    return "Other"


def split_domestic_international(items: List[DailyItem]) -> Tuple[List[DailyItem], List[DailyItem]]:
    """按分类/来源拆分国内/国外（大小写不敏感）"""
    domestic_keywords = ["阿里", "腾讯", "百度", "字节", "华为", "小米", "荣耀", "OPPO", "Vivo",
                         "商汤", "旷视", "云从", "科大讯飞", "智谱", "月之暗面", "深度求索",
                         "零一万物", "阶跃星辰", "面壁", "硅基流动", "海螺", "MiniMax",
                         "中国移动", "中国电信", "联通", "国家电网", "清华", "北大", "中科院",
                         "国产", "国内", "中国", "特斯拉", "小马智行", "美团", "京东", "腾讯云", "智元",
                         "PPIO", "出门问问", "晓多科技", "百分点", "九章云极", "中科闻歌", "澜舟科技"]
    international_keywords = ["Google", "OpenAI", "Anthropic", "Meta", "Microsoft", "Apple",
                             "Amazon", "Nvidia", "Intel", "AMD", "Qualcomm", "TSMC", "xAI",
                             "Mistral", "Stability AI", "Hugging Face", "Perplexity", "Midjourney",
                             "Runway", "Cohere", "Character.AI", "ElevenLabs", "Canva", "Samsung",
                             "Gemini", "GPT", "Claude", "Llama", "LLaMA", "ChatGPT", "Copilot",
                             "A4X", "L40S", "CVPR", "NeurIPS", "ICML", "ACL", "Waymo",
                             "CoreWeave", "Coinbase", "Cadence", "IDC", "Gartner", "Yann LeCun", "Garry"]
    domestic_srcs = {"huxiu", "量子位", "机器之心", "虎嗅", "qbitai"}
    international_srcs = {"infoq", "github", "huggingface", "openrouter"}

    domestic, international = [], []
    for item in items:
        src = item.source or ""
        title = item.title or ""
        title_lower = title.lower()
        cat = item.category or ""

        # 英文来源 → 国际
        if src in international_srcs:
            international.append(item)
            continue

        # international 关键词优先（大小写不敏感）
        if any(kw.lower() in title_lower for kw in international_keywords):
            international.append(item)
            continue

        # domestic 关键词（大小写不敏感）
        if any(kw.lower() in title_lower for kw in domestic_keywords):
            domestic.append(item)
            continue

        # 中文来源 → 国内
        if src in domestic_srcs:
            domestic.append(item)
            continue

        # 都匹配不上：看分类
        (domestic if "国内" in cat or "中国" in cat else international).append(item)

    return domestic, international

def _generate_weekly_insight(domestic, international) -> str:
    """用 MiniMax 生成本周洞察（200-300字）"""
    import requests

    _MINIMAX_KEY = "sk-cp-wTF01lPxZSg5kglem92SZUPwYthfQoAwvNa74N8ZySxN4TxPD0gnlNRt-eAMjtng41w-AL1D59j2W9IbpBMVrJH0xHRw-XG0PYU3fXnAbqjjvnkNcQoSSGY"
    _MINIMAX_URL = "https://api.minimax.chat/v1/chat/completions"

    # 取最高分的国内3条 + 国际3条
    all_items = domestic[:3] + international[:3]
    news_text = ""
    for i, item in enumerate(all_items, 1):
        title = item.title.strip()
        desc = (item.summary or item.desc or "").strip()
        news_text += f"{i}. {title}\n"
        if desc:
            news_text += f"   {desc[:100]}\n"

    prompt = f"""你是科技行业分析师。请根据以下本周重点新闻，写一段150字的精炼洞察（不超过150字）。

## 本周重点新闻
{news_text}

要求：
- 总结1-2个最值得关注的核心趋势
- 结合国内外动态横向对比
- 洞察要有观点，不要流水账
- 控制在150字以内"""

    headers = {
        "Authorization": f"Bearer {_MINIMAX_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-M2.5",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 350,
        "temperature": 0.7,
    }

    try:
        resp = requests.post(_MINIMAX_URL, headers=headers, json=payload, timeout=60)
        result = resp.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            # 去掉思考痕迹（MiniMax 模型可能在输出中包含思考标记）
            content = content.strip()
            # 去掉思考痕迹
            if content.startswith("<think>"):
                content = content.split("</think>", 1)[-1].strip()
            # 去掉 "洞察：" / "**洞察：**" 等前缀
            for prefix in ["**洞察：**", "**洞察：**", "洞察：", "洞察:", "本周洞察：", "本周洞察:"]:
                if content.startswith(prefix):
                    content = content[len(prefix):].strip()
                    break
            if content:
                print(f"   ✅ 本周洞察生成成功 ({len(content)}字)")
                return content
        else:
            print(f"   ⚠️ MiniMax返回为空: {result}")
    except Exception as e:
        print(f"   ❌ 洞察生成失败: {e}")
    return "本周AI领域继续保持高速发展，更多详情见正文。"


def generate_weekly_html(domestic, international, week_start, week_end,
                              hot_topics=None, insight=None) -> str:
    """
    生成微信公众号 HTML（完全参照日报格式）。
    hot_topics: 本周热点标题列表（Top N）
    insight: 本周洞察文字
    """
    hot_topics = hot_topics or []
    today_str = datetime.now().strftime("%Y年%m月%d日")

    sections = []

    # ===== 🔥 本周热点 =====（复用日报的今日热点样式）
    if hot_topics:
        sections.append(
            '<h2 style="color:#ff4d4f;font-weight:bold;font-size:20px;margin-top:20px;margin-bottom:10px;">🔥 本周热点</h2>'
        )
        sections.append('<ul style="background:#fff5f5;padding:8px 20px;border-radius:8px;list-style:none;">')
        for title in hot_topics:
            sections.append(
                f'<li style="font-size:15px;line-height:1.5;margin-bottom:5px;">• {title}</li>'
            )
        sections.append('</ul>')

    # ===== 🏷️ 国内AI资讯 =====
    if domestic:
        sections.append(
            '<h2 style="color:#000000;font-weight:bold;font-size:19px;margin-top:20px;margin-bottom:10px;">🏷️ 国内AI资讯</h2>'
        )
        for item in domestic:
            title = item.title.strip()
            desc = (item.summary or item.desc or "").strip()
            src = item.source or ""
            link = item.link or ""
            sections.append(
                f'<h3 style="color:#1890ff;font-weight:bold;font-size:17px;margin-top:15px;margin-bottom:5px;">{title}</h3>'
            )
            if desc:
                sections.append(
                    f'<p style="color:#666;font-size:15px;margin-bottom:5px;">{desc}</p>'
                )
            meta_parts = []
            if src:
                meta_parts.append(f'来源：{src}')
            if meta_parts:
                sections.append(
                    f'<p style="color:#666;font-size:13px;margin-top:0;">{" | ".join(meta_parts)}</p>'
                )
            if link:
                sections.append(
                    f'<p style="color:#666;font-size:13px;margin-top:0;">原文链接：<a href="{link}" target="_blank" style="color:#1890ff;text-decoration:underline;">{link}</a></p>'
                )

    # ===== 🌍 国外AI资讯 =====
    if international:
        sections.append(
            '<h2 style="color:#000000;font-weight:bold;font-size:19px;margin-top:20px;margin-bottom:10px;">🌍 国外AI资讯</h2>'
        )
        for item in international:
            title = item.title.strip()
            desc = (item.summary or item.desc or "").strip()
            src = item.source or ""
            link = item.link or ""
            sections.append(
                f'<h3 style="color:#1890ff;font-weight:bold;font-size:17px;margin-top:15px;margin-bottom:5px;">{title}</h3>'
            )
            if desc:
                sections.append(
                    f'<p style="color:#666;font-size:15px;margin-bottom:5px;">{desc}</p>'
                )
            meta_parts = []
            if src:
                meta_parts.append(f'来源：{src}')
            if meta_parts:
                sections.append(
                    f'<p style="color:#666;font-size:13px;margin-top:0;">{" | ".join(meta_parts)}</p>'
                )
            if link:
                sections.append(
                    f'<p style="color:#666;font-size:13px;margin-top:0;">原文链接：<a href="{link}" target="_blank" style="color:#1890ff;text-decoration:underline;">{link}</a></p>'
                )

    # ===== 💡 本周洞察 =====
    if insight:
        sections.append(
            '<h2 style="color:#000000;font-weight:bold;font-size:19px;margin-top:20px;margin-bottom:10px;">💡 本周洞察</h2>'
        )
        sections.append(
            '<div style="background:#f6ffed;padding:15px;border-radius:8px;line-height:1.8;font-size:15px;">'
        )
        sections.append(f'<p>{insight}</p>')
        sections.append('</div>')

    # ===== 来源 + footer =====
    all_srcs = sorted(set(
        item.source for item in domestic + international if item.source
    ))
    if not all_srcs:
        all_srcs = ["虎嗅", "InfoQ", "量子位", "aibase"]
    srcs_str = "、".join(all_srcs)
    sections.append(
        f'<p style="color:#999;margin-top:30px;text-align:center;font-size:13px;">'
        f'<em>来源：{srcs_str} | 整理：Valkyrie</em></p>'
    )

    html = (
        '<!DOCTYPE html><html><body><div style="'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;'
        'padding:0 10px;font-size:16px;line-height:1.6;color:#333;">'
        + "\n".join(sections) +
        '</div></body></html>'
    )
    return html


def generate_weekly_markdown(domestic, international, demoted, week_start, week_end) -> str:
    today = datetime.now().strftime("%Y年%m月%d日")
    lines = [
        f"# AI 资讯周报",
        f"**{week_start} - {week_end}** | 整理：Valkyrie",
        "",
    ]

    dom_display = domestic[:15]
    intl_display = international[:15]

    lines.append(f"## 🏠 国内 AI 动态（共筛选 {len(domestic)} 条，展示 Top{len(dom_display)}）")
    lines.append("")
    if dom_display:
        for i, item in enumerate(dom_display, 1):
            title = item.title.strip()
            desc = (item.summary or item.desc or "").strip()
            src = item.source or ""
            link = item.link or ""
            lines.append(f"**{i}. {title}**")
            if desc:
                lines.append(f"   {desc}")
            meta_parts = []
            if src:
                meta_parts.append(f"来源：{src}")
            if link:
                meta_parts.append(f"[原文链接]({link})")
            if meta_parts:
                lines.append(f"   *{' | '.join(meta_parts)}*")
            lines.append("")
    else:
        lines.append("_暂无数据_")
        lines.append("")

    lines.append(f"## 🌍 国际 AI 动态（共筛选 {len(international)} 条，展示 Top{len(intl_display)}）")
    lines.append("")
    if intl_display:
        for i, item in enumerate(intl_display, 1):
            title = item.title.strip()
            desc = (item.summary or item.desc or "").strip()
            src = item.source or ""
            link = item.link or ""
            lines.append(f"**{i}. {title}**")
            if desc:
                lines.append(f"   {desc}")
            meta_parts = []
            if src:
                meta_parts.append(f"来源：{src}")
            if link:
                meta_parts.append(f"[原文链接]({link})")
            if meta_parts:
                lines.append(f"   *{' | '.join(meta_parts)}*")
            lines.append("")
    else:
        lines.append("_暂无数据_")
        lines.append("")

    # 降级池摘要
    total_demoted = len(demoted.get("by_bucket_limit", [])) + len(demoted.get("by_dedup", []))
    if total_demoted > 0:
        lines.append("---")
        lines.append(f"**📦 降级池记录**（{total_demoted} 条不在正文中展示）")
        lines.append("")
        bl = demoted.get("by_bucket_limit", [])
        dd = demoted.get("by_dedup", [])
        if bl:
            lines.append(f"- 桶限制过滤：{len(bl)} 条")
            for d in bl[:5]:
                lines.append(f"  - [{d['company']}] {d['title'][:40]} ({d['reason']})")
        if dd:
            lines.append(f"- 语义去重：{len(dd)} 条")
            for d in dd[:3]:
                lines.append(f"  - {d['title'][:40]} (与「{d['kept_title'][:20]}」相似度{d['similarity']})")

    lines.extend(["", "---", f"*生成时间：{today}*"])
    return "\n".join(lines)


# ---- 主流程 ----
def main():
    parser = argparse.ArgumentParser(description="AI资讯周报生成器")
    parser.add_argument("--days", type=int, default=7, help="回溯天数（默认7天）")
    parser.add_argument("--dry-run", action="store_true", help="只跑流程，不写文件")
    parser.add_argument("--wechat", action="store_true", help="上传到微信公众号草稿箱")
    args = parser.parse_args()

    today = datetime.now().date()
    week_end = today.strftime("%Y年%m月%d日")
    week_start = (today - timedelta(days=args.days - 1)).strftime("%Y年%m月%d日")

    print("=" * 55)
    print(f"  🤖 AI资讯周报生成器（回溯 {args.days} 天）")
    print("=" * 55)
    print(f"  📅 周期：{week_start} - {week_end}")
    print()

    # 加载配置
    print("⚙️  加载评分配置...")
    cfg = _load_scoring_config()
    patterns = _load_company_patterns()
    print(f"   ✅ 配置加载完成（{len(patterns)} 条公司识别规则）")

    # 1. 加载数据
    print("\n📥 加载日报数据...")
    all_items, loaded_dates = load_week_data(days=args.days)
    print(f"   📅 日期: {', '.join(loaded_dates) if loaded_dates else '无'}")
    print(f"   📊 合并后: {len(all_items)} 条（按标题去重）")

    if not all_items:
        print("❌ 没有找到任何日报数据，退出")
        sys.exit(1)

    # 2. 过滤无实质内容的新闻（没有 desc/summary 的条目对读者无价值）
    contentful = []
    for it in all_items:
        desc = (it.summary or it.desc or "").strip()
        if len(desc) < 10:  # 少于10字符的摘要认为是无效内容
            continue
        contentful.append(it)
    removed_empty = len(all_items) - len(contentful)
    if removed_empty > 0:
        print(f"   ⏭️ 过滤无实质内容({removed_empty}条)，剩余{len(contentful)}条")
    all_items = contentful

    if not all_items:
        print("❌ 过滤后无有效数据，退出")
        sys.exit(1)

    # 3. 评分（不做桶限制）
    print("\n📊 评分与BGE去重...")
    all_scored, dedup_record = run_scoring(all_items, cfg, patterns, skip_buckets=True)

    if not all_scored:
        print("❌ 评分后无有效数据，退出")
        sys.exit(1)

    # 3. 分类（先分，再各自桶限制）
    print("\n📂 分类 + 各自桶限制...")
    domestic_raw, international_raw = split_domestic_international(all_scored)
    print(f"   国内: {len(domestic_raw)} 条 | 国外: {len(international_raw)} 条")

    # 各自应用桶限制
    dom_passed, dom_demo, int_passed, int_demo, combined_demoted = \
        _apply_buckets_separate(domestic_raw, international_raw, cfg, patterns)

    print(f"   国内通过: {len(dom_passed)} 条（降级{len(dom_demo)}条）")
    print(f"   国外通过: {len(int_passed)} 条（降级{len(int_demo)}条）")

    # 合并降级记录
    demoted_record = {
        "by_bucket_limit": combined_demoted,
        "by_dedup": dedup_record.get("by_dedup", []),
    }

    domestic = dom_passed
    international = int_passed

    # 4. 生成热点 + 洞察
    print("\n🔥 生成本周热点...")
    # 取国内+国际各最高分3条合成热点
    hot_topics = [it.title.strip() for it in (domestic[:3] + international[:3])]
    print(f"   热点：{hot_topics[:3]}...")

    print("\n💡 生成本周洞察...")
    insight = _generate_weekly_insight(domestic, international)

    # 4. 生成周报
    print("\n📝 生成周报...")
    md_content = generate_weekly_markdown(domestic, international, demoted_record, week_start, week_end)

    if args.dry_run:
        # dry-run 也显示热点和洞察
        print(f"   热点 Top6：")
        for t in hot_topics:
            print(f"     • {t}")
        print(f"   洞察：{insight[:50]}...")
        md_lines = md_content.split("\n")
        print("\n📋 周报预览（前 60 行）：")
        print("-" * 55)
        for line in md_lines[:60]:
            print(line)
        print("-" * 55)
        print(f"\n✅ dry-run 完成（共 {len(md_lines)} 行）")
        return

    # 5. 写文件
    OUTPUT_DIR = SCRIPTS_DIR / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = today.strftime("%Y%m%d")

    md_file = OUTPUT_DIR / f"weekly_report_{date_str}.md"
    md_file.write_text(md_content, encoding="utf-8")
    print(f"   💾 已保存: {md_file.name}")

    json_out = OUTPUT_DIR / f"weekly_scored_{date_str}.json"
    json_content = {
        "period": f"{week_start} - {week_end}",
        "generated_at": datetime.now().isoformat(),
        "domestic_count": len(domestic),
        "international_count": len(international),
        "domestic": [it.to_dict() for it in domestic[:15]],
        "international": [it.to_dict() for it in international[:15]],
        "demoted": demoted_record,
    }
    json_out.write_text(json.dumps(json_content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   💾 已保存: {json_out.name}")


    # 6. 上传微信公众号（可选）
    if args.wechat:
        print("\n📤 上传微信公众号...")
        import subprocess

        html_content = generate_weekly_html(domestic, international, week_start, week_end, hot_topics, insight)
        title = f"AI资讯周报 | {week_start} - {week_end}"

        # 先保存 HTML 临时文件
        html_file = OUTPUT_DIR / f"weekly_report_{date_str}.html"
        html_file.write_text(html_content, encoding="utf-8")

        # 调用独立上传脚本
        result = subprocess.run(
            ["/usr/bin/python3", str(SCRIPTS_DIR / "publish_wechat.py"),
             str(html_file), title, insight or ""],
            capture_output=True, text=True, timeout=60
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            print(f"   ❌ 公众号上传失败: {result.stderr[:200]}")

    print(f"\n✅ 周报生成完成")


if __name__ == "__main__":
    main()
