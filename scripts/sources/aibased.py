#!/usr/bin/env python3
"""
AIBase 资讯数据源
- 抓取 https://news.aibase.com/zh/news 列表页
- 使用 Playwright 渲染，避免反爬
- 结构：标题|||摘要|||时间|||热度
"""
import re
from typing import List
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .base import NewsSource, NewsItem, register_source


@register_source
class AibaseSource(NewsSource):
    name = "aibase"
    url = "https://news.aibase.com/zh/news"
    
    def collect(self) -> List[NewsItem]:
        items = self._fetch_list_page()
        self.news_list = items
        return items
    
    def _fetch_list_page(self) -> List[NewsItem]:
        """抓取 AIBase 列表页"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    extra_http_headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    }
                )
                page.goto(self.url, timeout=60000)
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # AIBase 结构：div.grid > a[href=/zh/news/xxx] > text: 标题|||摘要|||时间|||热度
            grid = soup.find('div', class_='grid')
            if not grid:
                print("   ❌ aibase: 未找到 grid 容器")
                return []
            
            links = grid.find_all('a', href=lambda h: h and '/zh/news/' in h)
            
            items = []
            seen_titles = set()
            
            for a in links:
                href = a.get('href', '')
                if not href:
                    continue
                
                # 完整链接
                link = f"https://news.aibase.com{href}"
                
                # text 分隔：标题|||摘要|||时间|||热度
                parts = [p.strip() for p in a.get_text(separator='|||').split('|||')]
                
                if len(parts) < 2:
                    continue
                
                title = parts[0].strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                
                # 摘要
                desc = parts[1].strip() if len(parts) > 1 else ''
                
                # 时间（处理 "6  小时前" 这种多余空格）
                time_ago = ''
                views = ''
                for part in parts[2:]:
                    part = part.strip()
                    if not part:
                        continue
                    # 匹配时间：刚刚 / N分钟前 / N小时前 / N天前
                    time_m = re.search(r'(\d+)\s*小时前', part)
                    if time_m:
                        time_ago = f"{time_m.group(1)}小时前"
                        continue
                    time_m = re.search(r'(\d+)\s*分钟前', part)
                    if time_m:
                        time_ago = f"{time_m.group(1)}分钟前"
                        continue
                    if '刚刚' in part:
                        time_ago = '刚刚'
                        continue
                    time_m = re.search(r'(\d+)\s*天前', part)
                    if time_m:
                        time_ago = f"{time_m.group(1)}天前"
                        continue
                    # 匹配热度
                    view_m = re.search(r'([\d.]+)\s*K', part, re.IGNORECASE)
                    if view_m:
                        views = f"{view_m.group(1)}K"
                        continue
                    view_m = re.search(r'([\d.]+)\s*万', part)
                    if view_m:
                        views = f"{view_m.group(1)}万"
                        continue
                
                item = NewsItem(
                    title=title,
                    desc=desc,
                    link=link,
                    source='aibase',
                    time_ago=time_ago,
                    extra={'views': views} if views else {},
                )
                items.append(item)
            
            print(f"   📰 aibase: 获取到 {len(items)} 条")
            return items
            
        except Exception as e:
            print(f"   ❌ aibase 抓取失败: {e}")
            return []
    
    def parse(self, html: str) -> List[NewsItem]:
        return self.news_list if self.news_list else []
