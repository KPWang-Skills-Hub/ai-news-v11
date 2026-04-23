#!/usr/bin/env python3
"""
OpenRouter 榜单爬虫脚本
通过 Playwright 抓取 openrouter.ai/rankings 页面，存入 MonitorDB

Usage:
    python3 openrouter_scraper.py

重试机制：最多 3 次，间隔 5s → 10s → 20s（指数退避）
"""
import sys
import time
import json
import re
from datetime import datetime
from pathlib import Path

# ── MonitorDB 路径（与 v10 main.py 保持一致）───────────────────
_backend_path = str(
    Path.home() / ".openclaw" / "workspace" / "skills" / "ai-news-monitor" / "backend"
)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from writer import MonitorDB, RawNews  # noqa: E402


# ── Playwright 爬取（带重试）───────────────────────────────────
def parse_token_value(token_str: str) -> int:
    """把 '1.37T tokens' → 1370000000000"""
    if not token_str:
        return 0
    num_str = re.sub(r"[^\d.]", "", token_str)
    num = float(num_str) if num_str else 0
    suffix = token_str[-1].upper()
    if suffix == "T":
        num *= 1e12
    elif suffix == "B":
        num *= 1e9
    elif suffix == "M":
        num *= 1e6
    elif suffix == "K":
        num *= 1e3
    return int(num)


def parse_rankings_via_playwright() -> list[dict]:
    """
    用 Playwright 抓取 openrouter.ai/rankings，返回模型列表
    最多重试 3 次，指数退避
    """
    from playwright.sync_api import sync_playwright

    max_retries = 3
    backoff = [5, 10, 20]  # 秒

    for attempt in range(max_retries):
        try:
            print(f"  [Attempt {attempt+1}/{max_retries}] 启动浏览器...")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(
                    "https://openrouter.ai/rankings",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(6000)  # 等待 JS 渲染

                rows = page.query_selector_all("div.grid.grid-cols-12.items-center")
                if len(rows) == 0:
                    raise RuntimeError("页面加载成功但未找到数据行")

                print(f"  找到 {len(rows)} 行数据")
                results = []
                for row in rows:
                    try:
                        rank_el = row.query_selector('div[class*="col-span-1"]')
                        name_el = row.query_selector('div[class*="col-span-7"] a')
                        token_el = row.query_selector(
                            'div[class*="col-span-4"] div:not([class*="mt-1"])'
                        )
                        change_el = row.query_selector(
                            'div[title*="Increase"] span'
                        )

                        rank = rank_el.inner_text().strip() if rank_el else ""
                        name = name_el.inner_text().strip() if name_el else ""
                        link = name_el.get_attribute("href") if name_el else ""
                        tokens_str = (
                            token_el.inner_text()
                            .replace("tokens", "")
                            .strip()
                            if token_el
                            else ""
                        )
                        change_str = (
                            change_el.inner_text().strip() if change_el else "-"
                        )

                        # 跳过空行（页面其他推荐模块）
                        if not name or not tokens_str:
                            continue

                        results.append(
                            {
                                "rank": rank,
                                "name": name,
                                "link": link,
                                "tokens": tokens_str,
                                "change": change_str,
                            }
                        )
                    except Exception:
                        continue

                browser.close()
                print(f"  解析完成: {len(results)} 条")
                return results

        except Exception as e:
            print(f"  ⚠️ Attempt {attempt+1} 失败: {e}")
            if attempt < max_retries - 1:
                wait = backoff[attempt]
                print(f"  等待 {wait}s 后重试...")
                time.sleep(wait)
            else:
                print(f"  ❌ 全部重试失败，退出")
                raise RuntimeError(f"Playwright 抓取失败（已重试 {max_retries} 次）")

    return []


# ── 写入 MonitorDB ──────────────────────────────────────────────
def write_to_monitor(items: list[dict], run_id: int) -> int:
    """把抓取结果写入 MonitorDB raw_news 表，返回写入条数"""
    today = datetime.now().strftime("%Y-%m-%d")
    written = 0

    db = MonitorDB()
    from sqlmodel import Session

    with Session(db.engine) as sess:
        for item in items:
            name = item["name"]
            # 去掉公司前缀
            if "/" in name:
                name = name.split("/", 1)[-1].strip()

            extra = json.dumps(
                {"rank": item["rank"], "change": item["change"]},
                ensure_ascii=False,
            )

            raw = RawNews(
                run_id=run_id,
                source="openrouter",
                title=name,
                desc=item["tokens"],
                link=f"https://openrouter.ai{item['link']}" if item["link"] else "",
                time_ago=item["change"],
                raw_extra=extra,
                collected_at=today,
            )
            sess.add(raw)
            written += 1

        sess.commit()
    return written


# ── 主流程 ──────────────────────────────────────────────────────
def main():
    print(f"🤖 OpenRouter 榜单爬虫 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. Playwright 抓取
    items = parse_rankings_via_playwright()
    if not items:
        print("❌ 抓取为空，退出")
        sys.exit(1)

    # 2. 写入 MonitorDB
    try:
        db = MonitorDB()
        run_id = db.start_run(datetime.now().strftime("%Y%m%d"))
        written = write_to_monitor(items, run_id)
        db.finish_run(run_id, status="success", total_collected=len(items))
        print(f"✅ 写入 MonitorDB 成功: {written} 条 (run_id={run_id})")
    except Exception as e:
        print(f"❌ MonitorDB 写入失败: {e}")
        sys.exit(1)

    print("=" * 50)
    print("✅ 完成!")


if __name__ == "__main__":
    main()
