#!/usr/bin/env python3
"""
InfoQ 数据源 - 从 AI 快讯页面采集
"""
import re
import json
import subprocess
from datetime import datetime
from typing import List

from .base import NewsSource, NewsItem, register_source


@register_source
class InfoqSource(NewsSource):
    """InfoQ AI 资讯数据源"""
    
    name = "infoq"
    url = "https://www.infoq.cn/aibriefs"
    
    def collect(self) -> List[NewsItem]:
        user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
        cmd = [
            'curl', '-s', '-L',
            '-A', user_agent,
            '-H', 'Accept: text/html,application/xhtml+xml',
            '-H', 'Accept-Language: zh-CN,zh;q=0.9',
            '--compressed',
            self.url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            self.news_list = self.parse(result.stdout.decode('utf-8'))
            print(f"   📰 {self.name}: 获取到 {len(self.news_list)} 条")
            return self.news_list
        except Exception as e:
            print(f"   ❌ {self.name} 获取失败: {e}")
            return []
    
    def parse(self, html: str) -> List[NewsItem]:
        """从 __NUXT_DATA__ 提取 AI 快讯"""
        news_list = []
        
        # 查找 __NUXT_DATA__ 脚本标签
        nuxt_match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not nuxt_match:
            print("   ⚠️ 未找到 __NUXT_DATA__")
            return news_list
        
        try:
            data_str = nuxt_match.group(1)
            
            # 找到数组开始和结束
            start_idx = data_str.find('[["ShallowReactive"')
            if start_idx == -1:
                start_idx = data_str.find('[')
            
            # 找到匹配的结束括号
            depth = 0
            end_idx = start_idx
            in_string = False
            escape_next = False
            
            for i, c in enumerate(data_str[start_idx:], start_idx):
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\':
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                if not in_string:
                    if c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
            
            json_str = data_str[start_idx:end_idx]
            nuxt_data = json.loads(json_str)
            
            # 辅助函数：从 Nuxt 数据中获取值
            def get_value(idx):
                if isinstance(idx, int) and idx < len(nuxt_data):
                    return nuxt_data[idx]
                return idx
            
            # 查找 aibriefsList 索引
            aibriefs_idx = None
            for item in nuxt_data:
                if isinstance(item, dict) and 'aibriefsList' in item:
                    aibriefs_idx = item['aibriefsList']
                    break
            
            if aibriefs_idx is None:
                print("   ⚠️ 未找到 aibriefsList")
                return news_list
            
            # 获取 aibriefs 数据
            aibriefs_data = nuxt_data[aibriefs_idx]
            list_idx = aibriefs_data.get('list')
            
            if not list_idx or list_idx >= len(nuxt_data):
                print("   ⚠️ list 索引无效")
                return news_list
            
            # 获取新闻列表
            news_indices = nuxt_data[list_idx]
            
            # 解析每条新闻
            for news_idx in news_indices:
                if not isinstance(news_idx, int) or news_idx >= len(nuxt_data):
                    continue
                
                news_obj = nuxt_data[news_idx]
                if not isinstance(news_obj, dict):
                    continue
                
                # 获取字段值
                title = get_value(news_obj.get('title'))
                desc = get_value(news_obj.get('description'))
                # InfoQ 的 original_link 是 Twitter 链接，不是 InfoQ 自己的文章，不采集
                link = ''
                
                # collect_time 可能是索引，需要解析
                collect_time_idx = news_obj.get('collect_time')
                collect_time = get_value(collect_time_idx) if collect_time_idx else None
                
                if title:
                    news_list.append(NewsItem(
                        title=str(title),
                        desc=str(desc) if desc else '',
                        link=str(link) if link else '',
                        source=self.name,
                        time_ago=self._format_time(collect_time) if collect_time else '',
                        extra={'collect_time': collect_time}
                    ))
            
            print(f"   ✅ 解析到 {len(news_list)} 条新闻")
            
        except Exception as e:
            print(f"   ⚠️ NUXT 解析失败: {e}")
            import traceback
            traceback.print_exc()
        
        return news_list
    
    def _format_time(self, timestamp: int) -> str:
        """将时间戳转为相对时间"""
        if not timestamp:
            return ''
        dt = datetime.fromtimestamp(timestamp / 1000)
        diff = datetime.now() - dt
        
        if diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f'{mins}分钟前' if mins > 0 else '刚刚'
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f'{hours}小时前'
        else:
            days = diff.days
            return f'{days}天前'
    
    def filter_recent(self, days: int = 2) -> List[NewsItem]:
        """过滤最近几天的数据"""
        recent_items = []
        for item in self.news_list:
            if item.time_ago:
                if '分钟' in item.time_ago or '小时' in item.time_ago or '天' in item.time_ago:
                    recent_items.append(item)
            elif item.extra.get('collect_time'):
                ts = item.extra.get('collect_time', 0)
                if ts:
                    dt = datetime.fromtimestamp(ts / 1000)
                    if (datetime.now() - dt).days <= days:
                        item.time_ago = self._format_time(ts)
                        recent_items.append(item)
        return recent_items