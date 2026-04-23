"""
关键词过滤拦截器
过滤掉与AI/智能硬件无关的新闻
"""
import re
from typing import List
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from interceptors.base import Interceptor, InterceptorResult, register_interceptor
from sources.base import NewsItem
from interceptors.logger import log_interceptor


# 关键词过滤 - 包含以下关键词的资讯会被移除
FILTER_KEYWORDS = [
    # 政治相关
    '中美', '外交', '制裁', '关税', '政策', '政府', '国会', '总统', '总理',
    # 宏观经济相关
    'IPO', '上市', '股价', '市值', '并购', '收购', '融资', '债务', '投资', '股权', '估值', '贷款', '出售',
    # 会议活动
    '征稿', '报名', '参会', '展位', '博览会', 'Meetup', '活动', '论坛',
    # 医疗健康（非AI相关）
    '医院', '药物',
    # 公益慈善
    '捐赠', '捐款',
    # 其他不相关内容
    '短剧', '奖学金', 'AAAI', '议题', '拿地',
    # 高校相关
    '高校', '学院', '校友', '毕业', '开学',
    # 招聘求职
    '招聘', '求职', '简历', '面试', '裁员', '就业', '招募', '年薪',
    # 企业/品牌特定
    '名创优品', '持股',
]


@register_interceptor
class KeywordFilterInterceptor(Interceptor):
    """关键词过滤拦截器"""
    
    name = "keyword_filter"
    description = "过滤掉与AI/智能硬件无关的新闻"
    
    def process(self, data: List[NewsItem], **kwargs) -> InterceptorResult:
        """根据关键词过滤新闻"""
        
        # 记录输入
        log_interceptor("keyword_filter", "INPUT", data)
        
        filtered = []
        removed = []
        
        for item in data:
            title = (item.title or '').lower()
            desc = (item.desc or '').lower()
            text = title + ' ' + desc
            
            # 检查是否匹配过滤关键词
            should_remove = False
            for kw in FILTER_KEYWORDS:
                if kw.lower() in text:
                    should_remove = True
                    break
            
            if should_remove:
                removed.append(item)
            else:
                filtered.append(item)
        
        print(f"   🔍 关键词过滤: {len(data)}条 -> {len(filtered)}条 (移除{len(removed)}条)")
        
        # 记录输出
        log_interceptor("keyword_filter", "OUTPUT", filtered, f"移除{len(removed)}条")
        
        return InterceptorResult(
            success=True,
            data=filtered,
            message=f"过滤掉{len(removed)}条无关新闻"
        )