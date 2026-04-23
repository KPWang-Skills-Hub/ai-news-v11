#!/usr/bin/env python3
"""
虎嗅AI资讯数据源 - Playwright版本
"""
import re
import json
from datetime import datetime, timedelta
from typing import List

from .base import NewsSource, NewsItem, register_source

API_URL = "https://www.huxiu.com/ainews/"


@register_source
class HuxiuSource(NewsSource):
    name = "huxiu"
    url = API_URL
    
    def collect(self) -> List[NewsItem]:
        """收集数据 - 使用 Playwright"""
        html = self._fetch_with_playwright()
        if html:
            items = self.parse(html)
            self.news_list = items  # 设置 news_list 供 filter_recent 使用
            return items
        self.news_list = []
        return []
    
    def _fetch_with_playwright(self) -> str:
        """使用 Playwright 获取页面"""
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                
                # 访问页面
                page.goto(self.url, wait_until='domcontentloaded', timeout=30000)
                
                # 等待内容加载
                try:
                    page.wait_for_selector('.content-list__item, .ai-news-item-wrap', timeout=30000)
                except:
                    pass
                
                # 获取页面内容
                html = page.content()
                browser.close()
                
                return html
                
        except Exception as e:
            print(f"   ⚠️ Playwright 获取失败: {e}")
            return ""
    
    def parse(self, html: str) -> List[NewsItem]:
        """解析 HTML 获取新闻列表"""
        news_list = []
        
        if not html or 'aliyun_waf' in html:
            print(f"   ⚠️ 虎嗅返回 WAF 页面")
            return news_list
        
        # 从 NUXT_DATA 提取
        nuxt_match = re.search(r'id="__NUXT_DATA__"[^>]*>([^<]+)<', html)
        if nuxt_match:
            try:
                nuxt_data = json.loads(nuxt_match.group(1))
                
                # 解码 Nuxt 序列化格式
                # 格式: [["ShallowReactive", idx], {field: value_idx, ...}, value1, value2, ...]
                
                # 找到 aiNewsList 和对象模板
                ai_news_list = None
                obj_template = None
                values = {}
                
                for item in nuxt_data:
                    if isinstance(item, list) and len(item) >= 2:
                        # ["ShallowReactive", idx]
                        if item[0] == "ShallowReactive":
                            # 下一个 dict 是模板
                            pass
                    elif isinstance(item, dict):
                        if 'aiNewsList' in item:
                            ai_news_list_idx = item['aiNewsList']
                            # 在 nuxt_data 中找这个索引
                            if ai_news_list_idx < len(nuxt_data):
                                ai_news_list = nuxt_data[ai_news_list_idx]
                        # 检查是否是对象模板（有 ainews_id 字段指向值）
                        if 'ainews_id' in item:
                            obj_template = item
                
                # 如果没找到直接的 aiNewsList，搜索
                if not ai_news_list:
                    for item in nuxt_data:
                        if isinstance(item, list) and len(item) > 1:
                            first = item[0]
                            if isinstance(first, list) and len(first) >= 2:
                                # 检查是否有 ainews_id
                                if first[0] == 'ShallowReactive':
                                    idx = first[1]
                                    if idx < len(nuxt_data):
                                        template_obj = nuxt_data[idx]
                                        if isinstance(template_obj, dict) and 'ainews_id' in template_obj:
                                            obj_template = template_obj
                                            ai_news_list = item[1:]  # 剩余的是 ID 列表
                                            break
                
                # 解析每条新闻
                if ai_news_list and obj_template:
                    for news_idx in ai_news_list:
                        if isinstance(news_idx, int):
                            # 获取对象数据
                            if news_idx < len(nuxt_data):
                                news_obj = nuxt_data[news_idx]
                                if isinstance(news_obj, dict):
                                    # 提取字段值
                                    ainews_id = self._get_value(nuxt_data, news_obj.get('ainews_id'))
                                    title = self._get_value(nuxt_data, news_obj.get('title'))
                                    desc = self._get_value(nuxt_data, news_obj.get('desc'))
                                    publish_time = self._get_value(nuxt_data, news_obj.get('publish_time'))
                                    
                                    if title and ainews_id:
                                        news_list.append(NewsItem(
                                            title=title,
                                            desc=str(desc) if desc else '',
                                            source=self.name,
                                            link=f"https://www.huxiu.com/ainews/{ainews_id}.html",
                                            time_ago=self._format_time(publish_time) if isinstance(publish_time, (int, float)) else '',
                                            extra={'publish_time': publish_time}
                                        ))
                
            except Exception as e:
                print(f"   ⚠️ NUXT 解析失败: {e}")
                import traceback
                traceback.print_exc()
        
        return news_list
    
    def _get_value(self, nuxt_data: list, idx):
        """从 Nuxt 数据中获取值（处理引用）"""
        if idx is None:
            return None
        if isinstance(idx, int):
            if idx < len(nuxt_data):
                return nuxt_data[idx]
            return None
        return idx
    
    def _format_time(self, timestamp: int) -> str:
        """将时间戳转为相对时间"""
        if not timestamp:
            return ''
        dt = datetime.fromtimestamp(timestamp / 1000)
        diff = datetime.now() - dt
        
        if diff < timedelta(hours=1):
            mins = int(diff.total_seconds() / 60)
            return f'{mins}分钟前' if mins > 0 else '刚刚'
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f'{hours}小时前'
        elif diff < timedelta(days=7):
            days = diff.days
            return f'{days}天前'
        else:
            return dt.strftime('%m-%d')
    
    def filter_recent(self, days: int = 2) -> List[NewsItem]:
        """过滤最近几天的数据（使用 self.news_list）"""
        recent_items = []
        for item in self.news_list:
            if item.time_ago:
                if '分钟' in item.time_ago or '小时' in item.time_ago or '天' in item.time_ago:
                    recent_items.append(item)
            elif item.extra.get('publish_time'):
                ts = item.extra.get('publish_time', 0)
                if ts:
                    dt = datetime.fromtimestamp(ts / 1000)
                    if (datetime.now() - dt).days <= days:
                        item.time_ago = self._format_time(ts)
                        recent_items.append(item)
        return recent_items
    
    def filter_items(self, items: List[NewsItem], days: int = 2) -> List[NewsItem]:
        """过滤最近几天数据（别名方法，供 main.py 调用）"""
        recent_items = []
        for item in items:
            if item.time_ago:
                if '分钟' in item.time_ago or '小时' in item.time_ago or '天' in item.time_ago:
                    recent_items.append(item)
            elif item.extra.get('publish_time'):
                ts = item.extra.get('publish_time', 0)
                if ts:
                    dt = datetime.fromtimestamp(ts / 1000)
                    if (datetime.now() - dt).days <= days:
                        item.time_ago = self._format_time(ts)
                        recent_items.append(item)
        return recent_items