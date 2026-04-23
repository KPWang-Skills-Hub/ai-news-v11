"""
评分拦截器
整合 BGE 语义去重 + 综合评分 + 桶限制 + 降级池记录

设计原则：
- BGE 去重在评分前执行，高价值新闻使用更高阈值（0.9 vs 0.75）
- 所有降级信息（by_dedup / by_bucket_limit）统一记录
- 评分公式：(min(keyword_score,40) × high_value_multiplier + summary_score) × source_multiplier
"""
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interceptors.base import Interceptor, InterceptorResult, register_interceptor
from sources.base import NewsItem
from interceptors.logger import log_interceptor
from interceptors.scoring_config import (
    KEYWORD_WEIGHTS,
    KEYWORD_WEIGHT_SCORES,
    HIGH_VALUE_KEYWORDS,
    SOURCE_MULTIPLIERS,
    DEFAULT_SOURCE_MULTIPLIER,
    SUMMARY_QUALITY_THRESHOLD,
    SUMMARY_QUALITY_SCORES,
    LOW_QUALITY_DESC_PATTERNS,
    BUCKET_LIMITS,
    DEDUP_THRESHOLD,
    HIGH_VALUE_DEDUP_THRESHOLD,
    KEYWORD_SCORE_CAP,
)


class DemotedReason(Enum):
    """降级原因"""
    COMPANY_LIMIT = "company_limit_exceeded"
    DOMAIN_LIMIT = "domain_limit_exceeded"
    BGE_DEDUP = "bge_dedup_similarity_exceeded"


@dataclass
class ScoredNewsItem:
    """带评分的新闻项"""
    item: NewsItem
    keyword_score: int = 0
    high_value_multiplier: float = 1.0
    summary_score: int = 0
    source_multiplier: float = 1.0
    company: str = "Other"
    domain: str = "Other"
    final_score: float = 0.0


@dataclass
class DemotedItem:
    """被降级的新闻"""
    item: NewsItem
    reason: str               # DemotedReason.value
    company: str = "Other"
    domain: str = "Other"
    score: float = 0.0
    similarity: float = 0.0   # 仅 dedup 用
    kept_title: str = ""


@register_interceptor
class ScoringInterceptor(Interceptor):
    """
    评分拦截器（整合版）
    流程：BGE去重 → 评分 → 桶限制 → 输出
    """
    name = "scoring"
    description = "BGE去重+评分+桶限制整合拦截器"

    def __init__(self):
        self._scored_items: List[ScoredNewsItem] = []
        self._demoted_by_bucket: List[DemotedItem] = []
        self._demoted_by_dedup: List[DemotedItem] = []
        self._company_patterns: List[Tuple[str, str]] = []
        self._dedup_skipped_sources: set = set()

    # ============================================================
    # 公司识别
    # ============================================================
    def _load_company_patterns(self) -> List[Tuple[str, str]]:
        """延迟加载 company_patterns.py"""
        import re
        if self._company_patterns:
            return self._company_patterns

        patterns = []
        try:
            cp_path = Path(__file__).parent.parent / "company_patterns.py"
            if cp_path.exists():
                with open(cp_path, encoding="utf-8") as f:
                    code = f.read()
                local_ns: dict = {}
                exec(code, {}, local_ns)
                raw = local_ns.get("COMPANY_PATTERNS", [])
                for p, c in raw:
                    patterns.append((p, c))
        except Exception:
            pass

        self._company_patterns = patterns
        return patterns

    def _extract_company(self, title: str) -> str:
        """从标题中提取公司名"""
        import re
        patterns = self._load_company_patterns()
        for pattern, company in patterns:
            try:
                if re.search(pattern, title, re.I):
                    return company
            except re.error:
                continue
        return "Other"

    def _extract_domain(self, title: str) -> str:
        """从标题中识别领域"""
        t = title.lower()
        if any(kw in t for kw in ["大模型", "llm", "gpt", "claude", "gemini", "llama", "qwen", "通义", "文心", "混元", "盘古", "glm", "deepseek", "kimi"]):
            return "大模型"
        if any(kw in t for kw in ["芯片", "算力", "gpu", "npu", "tpu", "h100", "a100", "cuda", "ai芯片", "推理芯片"]):
            return "AI基础设施"
        if any(kw in t for kw in ["手机", "电脑", "平板", "穿戴", "耳机", "音箱", "机器人", "电动车", "新能源", "iphone"]):
            return "智能硬件"
        if any(kw in t for kw in ["arxiv", "论文", "顶会", "学术", "acl", "cvpr", "nips"]):
            return "学术研究"
        return "其他"

    # ============================================================
    # 关键词得分
    # ============================================================
    def _calc_keyword_score(self, title: str) -> Tuple[int, float]:
        """(keyword_score, high_value_multiplier)"""
        t = title.lower()
        score = 0

        for category, keywords in KEYWORD_WEIGHTS.items():
            weight = KEYWORD_WEIGHT_SCORES.get(category, 0)
            for kw in keywords:
                if kw.lower() in t:
                    score += weight
                    break

        multiplier = 1.0
        for kw in HIGH_VALUE_KEYWORDS:
            if kw.lower() in t:
                multiplier = 2.0
                break

        return min(score, KEYWORD_SCORE_CAP), multiplier

    # ============================================================
    # 摘要质量分
    # ============================================================
    def _calc_summary_score(self, item: NewsItem) -> int:
        desc = item.desc or ""
        for p in LOW_QUALITY_DESC_PATTERNS:
            if p in desc.lower():
                return SUMMARY_QUALITY_SCORES["low"]

        l = len(desc.strip())
        if l < SUMMARY_QUALITY_THRESHOLD:
            return SUMMARY_QUALITY_SCORES["low"]
        elif l < 50:
            return SUMMARY_QUALITY_SCORES["medium"]
        return SUMMARY_QUALITY_SCORES["high"]

    # ============================================================
    # BGE 语义去重（整合在评分前）
    # ============================================================
    def _is_high_value(self, title: str) -> bool:
        t = title.lower()
        return any(kw.lower() in t for kw in HIGH_VALUE_KEYWORDS)

    def _run_bge_dedup(self, items: List[NewsItem], skip_sources: set) -> List[NewsItem]:
        """执行 BGE 语义去重，高价值新闻使用更高阈值"""
        # 过滤掉需要跳过的来源
        original_count = len(items)
        if skip_sources:
            items = [it for it in items if it.source not in skip_sources]
            skipped_count = original_count - len(items)
            if skipped_count:
                print(f"   ⏭️ BGE去重: 跳过 {skipped_count} 条 ({', '.join(skip_sources)})")

        if len(items) <= 1:
            return items

        try:
            # 配置 HuggingFace 镜像
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from sentence_transformers import SentenceTransformer
            import numpy as np

            print(f"   🔄 BGE去重中 ({len(items)}条)...")
            model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

            titles = [it.title for it in items]
            embeddings = model.encode(titles, convert_to_numpy=True)

            # 预建索引映射：title -> index，避免 items.index() O(n) 查找
            title_to_idx = {it.title: i for i, it in enumerate(items)}

            unique_items: List[NewsItem] = []
            for i, item in enumerate(items):
                emb = embeddings[i]
                is_dup = False
                dup_simi = 0.0
                dup_kept_title = ""

                for u_item in unique_items:
                    u_idx = title_to_idx[u_item.title]  # O(1) 查表代替 O(n) index()
                    u_emb = embeddings[u_idx]
                    sim = float(np.dot(emb, u_emb) / (np.linalg.norm(emb) * np.linalg.norm(u_emb)))

                    # 动态阈值：高价值新闻用 0.9，普通新闻用 0.75
                    threshold = HIGH_VALUE_DEDUP_THRESHOLD if self._is_high_value(item.title) else DEDUP_THRESHOLD

                    if sim > threshold:
                        is_dup = True
                        dup_simi = sim
                        dup_kept_title = u_item.title
                        break

                if is_dup:
                    self._demoted_by_dedup.append(DemotedItem(
                        item=item,
                        reason=DemotedReason.BGE_DEDUP.value,
                        company=self._extract_company(item.title),
                        similarity=dup_simi,
                        kept_title=dup_kept_title,
                    ))
                else:
                    unique_items.append(item)

            removed = len(items) - len(unique_items)
            print(f"   ✅ BGE去重: {len(items)}条 -> {len(unique_items)}条 (移除{removed}条, high_value阈值={HIGH_VALUE_DEDUP_THRESHOLD})")

            # 记录被 dedup 移除的新闻（用于监控埋点）
            if removed > 0:
                log_interceptor("scoring/bge_dedup", "DEDUP_REMOVED",
                               [d.item for d in self._demoted_by_dedup[-removed:]],
                               f"similarity>=threshold")

            return unique_items

        except ImportError:
            print("   ⚠️ sentence-transformers 未安装，跳过BGE去重")
            return items
        except Exception as e:
            print(f"   ⚠️ BGE去重失败: {e}，跳过去重")
            return items

    # ============================================================
    # 核心处理流程
    # ============================================================
    def process(self, data: List[NewsItem], **kwargs) -> InterceptorResult:
        """
        流程：预过滤 → BGE去重 → 评分 → 桶限制 → 输出
        """
        log_interceptor("scoring", "INPUT", data)

        # 重置状态
        self._scored_items = []
        self._demoted_by_bucket = []
        self._demoted_by_dedup = []
        self._dedup_skipped_sources = set(kwargs.get('skip_sources', set()))

        if not data:
            return InterceptorResult(success=True, data=[], message="无数据")

        # 加载公司模式
        self._load_company_patterns()

        # ---- Step 1: BGE 去重 ----
        after_dedup = self._run_bge_dedup(list(data), self._dedup_skipped_sources)

        # ---- Step 2: 对每条新闻评分 ----
        for item in after_dedup:
            company = self._extract_company(item.title)
            domain = self._extract_domain(item.title)
            kw_score, hv_mult = self._calc_keyword_score(item.title)
            summary_score = self._calc_summary_score(item)
            source_mult = SOURCE_MULTIPLIERS.get(item.source, DEFAULT_SOURCE_MULTIPLIER)

            final = (kw_score * hv_mult + summary_score) * source_mult

            self._scored_items.append(ScoredNewsItem(
                item=item,
                keyword_score=kw_score,
                high_value_multiplier=hv_mult,
                summary_score=summary_score,
                source_multiplier=source_mult,
                company=company,
                domain=domain,
                final_score=final,
            ))

        # ---- Step 3: 按评分降序排列 ----
        self._scored_items.sort(key=lambda x: x.final_score, reverse=True)

        # ---- Step 4: 桶限制 ----
        self._apply_bucket_limit()

        # ---- 输出 ----
        passed = [s.item for s in self._scored_items]
        total_demoted = len(self._demoted_by_bucket) + len(self._demoted_by_dedup)

        print(f"   📊 评分筛选: {len(data)}条 -> {len(passed)}条 "
              f"(去重{len(self._demoted_by_dedup)}条 / 桶限制{len(self._demoted_by_bucket)}条)")

        if self._demoted_by_bucket:
            for d in self._demoted_by_bucket[:2]:
                print(f"      🚫 [{d.reason}] {d.item.title[:35]}")

        if self._scored_items:
            scores = [s.final_score for s in self._scored_items]
            print(f"   📈 评分: max={max(scores):.1f} / median={sorted(scores)[len(scores)//2]:.1f}")

        log_interceptor("scoring", "OUTPUT", passed, f"降级{total_demoted}条")

        return InterceptorResult(
            success=True,
            data=passed,
            message=f"评分完成，降级{total_demoted}条"
        )

    # ============================================================
    # 桶限制
    # ============================================================
    def _apply_bucket_limit(self):
        company_counts: Dict[str, int] = {}
        domain_counts: Dict[str, int] = {}
        company_limit = BUCKET_LIMITS["company"]
        domain_limit = BUCKET_LIMITS["domain"]

        remaining: List[ScoredNewsItem] = []

        for scored in self._scored_items:
            company = scored.company
            domain = scored.domain

            if company_counts.get(company, 0) >= company_limit:
                self._demoted_by_bucket.append(DemotedItem(
                    item=scored.item,
                    reason=DemotedReason.COMPANY_LIMIT.value,
                    company=company,
                    domain=domain,
                    score=scored.final_score,
                ))
                continue

            if domain_counts.get(domain, 0) >= domain_limit:
                self._demoted_by_bucket.append(DemotedItem(
                    item=scored.item,
                    reason=DemotedReason.DOMAIN_LIMIT.value,
                    company=company,
                    domain=domain,
                    score=scored.final_score,
                ))
                continue

            company_counts[company] = company_counts.get(company, 0) + 1
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            remaining.append(scored)

        self._scored_items = remaining

    # ============================================================
    # 公开接口
    # ============================================================
    def get_demoted_record(self) -> dict:
        """
        获取降级池记录（用于 JSON 输出）
        """
        return {
            "by_bucket_limit": [
                {
                    "title": d.item.title,
                    "company": d.company,
                    "domain": d.domain,
                    "score": round(d.score, 2),
                    "reason": d.reason,
                }
                for d in self._demoted_by_bucket
            ],
            "by_dedup": [
                {
                    "title": d.item.title,
                    "company": d.company,
                    "similarity": round(d.similarity, 3),
                    "kept_title": d.kept_title,
                    "reason": d.reason,
                }
                for d in self._demoted_by_dedup
            ],
        }

    def get_scored_items(self) -> List[ScoredNewsItem]:
        return self._scored_items
