from interceptors.base import Interceptor, InterceptorResult, register_interceptor
from sources.base import NewsItem
from typing import List
from datetime import datetime, timedelta


@register_interceptor
class TimeFilterInterceptor(Interceptor):
    name = "time_filter"
    description = "只保留距过滤器执行时刻24小时内的新闻"
    
    def process(self, data: List[NewsItem], config=None) -> InterceptorResult:
        
        if not data:
            return InterceptorResult(success=True, data=[], message="无数据")
        
        filter_threshold = datetime.now() - timedelta(hours=24)
        
        filtered = []
        removed = []
        
        for item in data:
            pt = None
            
            # 优先使用 extra.publish_time 精确时间戳
            extra = getattr(item, 'extra', None) or {}
            ts = extra.get('publish_time')
            if ts:
                try:
                    ts_val = int(ts)
                    if ts_val > 1e12:
                        ts_val = ts_val / 1000
                    pt = datetime.fromtimestamp(ts_val)
                except:
                    pass
            
            # 回退：从 time_ago 等字符串解析
            if pt is None:
                time_str = getattr(item, 'time_ago', None) or getattr(item, 'publish_time', None) or getattr(item, 'time', None)
                if time_str:
                    try:
                        s = str(time_str)
                        if "小时前" in s:
                            h = int(s.replace("小时前", "").strip())
                            pt = datetime.now() - timedelta(hours=h)
                        elif "天前" in s:
                            d = int(s.replace("天前", "").strip())
                            pt = datetime.now() - timedelta(days=d)
                        elif "分钟前" in s:
                            m = int(s.replace("分钟前", "").strip())
                            pt = datetime.now() - timedelta(minutes=m)
                        elif "前天" in s:
                            # 量子位格式：前天 18:17 → 前天=2天前
                            days_ago = 2
                            # 尝试解析时间部分：前天 18:17
                            import re
                            m2 = re.search(r'前天\s*(\d+):(\d+)', s)
                            if m2:
                                h = int(m2.group(1))
                                minute = int(m2.group(2))
                                target = datetime.now().replace(hour=h, minute=minute, second=0, microsecond=0) - timedelta(days=2)
                                pt = target
                            else:
                                pt = datetime.now() - timedelta(days=days_ago)
                        elif "昨天" in s:
                            # 量子位格式：昨天 18:17 → 昨天=1天前
                            import re
                            m2 = re.search(r'昨天\s*(\d+):(\d+)', s)
                            if m2:
                                h = int(m2.group(1))
                                minute = int(m2.group(2))
                                target = datetime.now().replace(hour=h, minute=minute, second=0, microsecond=0) - timedelta(days=1)
                                pt = target
                            else:
                                pt = datetime.now() - timedelta(days=1)
                        else:
                            for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                                try:
                                    pt = datetime.strptime(s, fmt)
                                    break
                                except:
                                    continue
                    except:
                        pass
            
            if pt is None:
                filtered.append(item)
                continue
            
            if pt >= filter_threshold:
                filtered.append(item)
            else:
                removed.append(item)
        
        return InterceptorResult(
            success=True,
            data=filtered,
            message=f"过滤{len(removed)}条，保留{len(filtered)}条"
        )
