#!/usr/bin/env python3
"""
量子位（QbitAI）资讯数据源
- 只抓列表页，不进详情页（约5-8秒）
- 只保留作者为"量子位"的新闻
- 返回 NewsItem 列表（与虎嗅/InfoQ 格式统一）
"""
import re
from typing import List
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .base import NewsSource, NewsItem, register_source


@register_source
class QbitaiSource(NewsSource):
    name = "量子位"
    url = "https://www.qbitai.com/category/%E8%B5%84%E8%AE%AF"
    
    def collect(self) -> List[NewsItem]:
        """收集数据 - 只抓列表页，不进详情页"""
        items = self._fetch_list_page()
        self.news_list = items
        return items
    
    def _fetch_list_page(self) -> List[NewsItem]:
        """快速抓取列表页：标题 + 摘要 + 作者 + 时间"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, timeout=60000)
                page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
            
            soup = BeautifulSoup(html, 'html.parser')
            text_boxes = soup.select('.text_box')
            
            items = []
            for box in text_boxes:
                # 标题 + 链接
                title_elem = box.select_one('h4 a')
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                if not title or not link:
                    continue
                
                # 作者
                author_elem = box.select_one('.author a')
                author = author_elem.get_text(strip=True) if author_elem else ''
                
                # ★ 过滤：只保留作者为"量子位"的新闻
                if author != '量子位':
                    continue
                
                # 摘要：h4之后、.info之前的第一个非空p
                desc = ''
                h4_parent = title_elem.find_parent('h4')
                if h4_parent:
                    for sibling in h4_parent.find_next_siblings():
                        if sibling.name == 'div' and 'info' in sibling.get('class', []):
                            break
                        if sibling.name == 'p':
                            t = sibling.get_text(strip=True)
                            if t:
                                desc = t
                                break
                
                # 时间
                time_elem = box.select_one('.time')
                time_ago = time_elem.get_text(strip=True) if time_elem else ''
                
                items.append(NewsItem(
                    title=title,
                    desc=desc,
                    link=link,
                    source='量子位',
                    time_ago=time_ago,
                ))
            
            print(f"   📰 量子位: 获取到 {len(items)} 条（列表页快速抓取）")
            return items
            
        except Exception as e:
            print(f"   ❌ 量子位抓取失败: {e}")
            return []
    
    def parse(self, html: str) -> List[NewsItem]:
        """解析 HTML（兼容基类）"""
        return self.news_list if self.news_list else []
