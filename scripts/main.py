#!/usr/bin/env python3
"""
AI资讯早报 v10 - 主入口（加入监控埋点版）
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List

# 添加 scripts 到路径
sys.path.insert(0, str(Path(__file__).parent))

from sources import get_source, list_sources, NewsItem
from interceptors import get_interceptor, list_interceptors

# 添加 table-image-generator 路径
sys.path.insert(0, str(Path.home() / ".openclaw" / "workspace" / "skills" / "table-image-generator"))

# 添加 monitor 路径（可选，如果没有则跳过埋点）
MONITOR_DB = None
try:
    sys.path.insert(0, str(Path.home() / ".openclaw" / "workspace" / "skills" / "ai-news-monitor" / "backend"))
    from writer import MonitorDB
    MONITOR_DB = MonitorDB()
    print("✅ MonitorDB 埋点已就绪")
except Exception as e:
    print(f"⚠️ MonitorDB 埋点不可用: {e}")


# 配置
DEFAULT_CONFIG = {
    "sources": [
        {"name": "huxiu", "enabled": True},
        {"name": "infoq", "enabled": True},
        {"name": "量子位", "enabled": True},
        {"name": "aibase", "enabled": True},
        {"name": "openrouter", "enabled": True},
        {"name": "huggingface", "enabled": True},
        {"name": "github", "enabled": True},
    ],
    "wechat_thumb_media_id": "OBa7s7v5pJj8C3xsRSuJHIpA0CnVzzikHstbq7wpg6b1PIl6_YmqTQiEm13GpoJ8",
    "interceptors": [
        "time_filter",
        "keyword_filter",
        "bge_dedup",
        "llm_classify",
        "llm_summary"
    ],
    "bge_skip_sources": ["huggingface", "github", "openrouter"],
    "fetch_content_sources": ["量子位"],  # 只有这些数据源需要抓取正文
    "limits": {
        "国内AI资讯": 20,
        "国外AI资讯": 20,
        "智能硬件": 5,
        "其它科技资讯": 5
    }
}


def get_keyword_reason(item: NewsItem) -> str:
    """获取 keyword_filter 命中了哪些关键词"""
    try:
        from interceptors.keyword_filter import FILTER_KEYWORDS
        title = (getattr(item, "title", "") or "").lower()
        desc = (getattr(item, "desc", "") or "").lower()
        text = title + " " + desc
        hit = [kw for kw in FILTER_KEYWORDS if kw.lower() in text]
        if hit:
            return f"命中关键词：[{', '.join(hit)}]"
        return "命中关键词"
    except Exception:
        return "keyword_filter"


def load_config() -> dict:
    """加载配置"""
    config_path = Path.home() / ".openclaw" / "config.json"

    if config_path.exists():
        try:
            with open(config_path) as f:
                user_config = json.load(f)

            if user_config.get("ai-news-v10"):
                config = DEFAULT_CONFIG.copy()
                config.update(user_config["ai-news-v10"])
                return config
        except Exception as e:
            print(f"⚠️ 读取配置失败: {e}")

    return DEFAULT_CONFIG


def collect_all_news(config: dict) -> tuple:
    """
    收集所有数据源的新闻，返回 (html_news, api_news, source_map)

    source_map: dict = { "huxiu": [items], "infoq": [items], "github": [items], "huggingface": [items], "openrouter": [items] }
    """
    html_news = []
    api_news = []
    source_map = {}  # 记录每个来源的原始数据（HTML 和 API 都记录）

    print("\n📥 收集数据源...")

    api_sources = {'huggingface', 'github', 'openrouter'}

    for source_config in config.get("sources", []):
        name = source_config.get("name")
        enabled = source_config.get("enabled", True)

        if not enabled:
            continue

        source = get_source(name)
        if source:
            news = source.collect()

            if name in api_sources:
                api_news.extend(news)
                source_map[name] = news  # API 来源也记录，方便埋点
                print(f"   📰 {name}: 获取到 {len(news)} 条 (直接输出)")
            else:
                news = source.filter_recent(days=2)
                html_news.extend(news)
                source_map[name] = news
                print(f"   📰 {name}: 获取到 {len(news)} 条 (待处理)")
        else:
            print(f"   ⚠️ 未知数据源: {name}")

    print(f"   ✅ HTML源共 {len(html_news)} 条，API源共 {len(api_news)} 条")
    return html_news, api_news, source_map


def process_interceptors_with_monitor(news: List[NewsItem], config: dict, monitor, run_id: int) -> List[NewsItem]:
    """
    依次执行拦截器（带监控埋点）
    返回处理后的列表
    """
    interceptor_names = config.get("interceptors", [])

    print("\n🔄 处理拦截器...")

    current_news = list(news)  # 复制，避免直接修改原列表

    for name in interceptor_names:
        interceptor = get_interceptor(name)

        if not interceptor:
            print(f"   ⚠️ 未知拦截器: {name}")
            continue

        before = len(current_news)
        step_start = time.time()

        # 传递配置给拦截器
        interceptor_kwargs = {}
        if name == "bge_dedup":
            interceptor_kwargs['skip_sources'] = config.get('bge_skip_sources', set())
        elif name == "llm_summary":
            interceptor_kwargs['fetch_content_sources'] = config.get('fetch_content_sources', [])
        
        result = interceptor.process(current_news, **interceptor_kwargs)

        step_duration = time.time() - step_start

        if result.success:
            after = len(result.data) if result.data else before

            # 找出被移除的新闻（通过标题比对）
            before_titles = {getattr(i, "title", str(i)) for i in current_news}
            after_titles = {getattr(i, "title", str(i)) for i in (result.data or [])}
            removed_titles = before_titles - after_titles
            removed_items = [i for i in current_news if getattr(i, "title", str(i)) in removed_titles]

            current_news = result.data or current_news

            print(f"   ▶ {name} [{step_duration:.1f}s]")
            print(f"      → {after} 条")

            # ========== 埋点 ==========
            if monitor:
                reason_fn = get_keyword_reason if name == "keyword_filter" else None
                monitor.write_step(
                    run_id=run_id,
                    step_name=name,
                    before=before,
                    after=after,
                    removed=removed_items,
                    reason_fn=reason_fn
                )
            # ========================
        else:
            print(f"   ⚠️ {name}: {result.message}")

    return current_news


def limit_by_category(news: List[NewsItem], limits: dict) -> List[NewsItem]:
    """按分类限制数量"""
    print("\n📊 分类筛选...")

    cat_counts = {}
    for item in news:
        cat = item.category or '其它科技资讯'
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    limited = []
    cat_current = {}

    for item in news:
        cat = item.category or '其它科技资讯'
        limit = limits.get(cat, 999)

        if cat_current.get(cat, 0) < limit:
            limited.append(item)
            cat_current[cat] = cat_current.get(cat, 0) + 1

    for cat, limit in limits.items():
        current = cat_current.get(cat, 0)
        print(f"   {cat}: {current}/{limit}")

    return limited


def generate_html(news: List[NewsItem], github_img_url: str = None, hf_img_url: str = None,
                   or_img_url: str = None,
                   hot_items: List[str] = None, insight: str = None,
                   github_items: List[NewsItem] = None) -> str:
    """生成微信公众号 HTML"""
    cats = ['国内AI资讯', '国外AI资讯', '智能硬件', '其它科技资讯']

    h2_style = 'color:#000000;font-weight:bold;font-size:19px;margin-top:20px;margin-bottom:10px;'
    h3_style = 'color:#1890ff;font-weight:bold;font-size:17px;margin-top:15px;margin-bottom:5px;'
    p_desc_style = 'color:#666;font-size:15px;margin-bottom:5px;'
    p_source_style = 'color:#666;font-size:13px;margin-top:0;'

    sections_html = []

    if hot_items:
        sections_html.append('<h2 style="color:#ff4d4f;font-weight:bold;font-size:20px;margin-top:20px;margin-bottom:10px;">🔥 今日热点</h2>')
        sections_html.append('<ul style="background:#fff5f5;padding:8px 20px;border-radius:8px;list-style:none;">')
        for item_title in hot_items:
            sections_html.append(f'<li style="font-size:15px;line-height:1.5;margin-bottom:5px;">• {item_title}</li>')
        sections_html.append('</ul>')

    if github_img_url:
        sections_html.append(f'''
        <h2 style="{h2_style}">🔥 GitHub AI项目趋势榜</h2>
        <img src="{github_img_url}" style="width:100%;max-width:1400px;display:block;margin:10px 0;" />
        ''')
        if github_items:
            links_html = ['<p style="font-size:13px;color:#666;line-height:2;margin-top:10px;">']
            for i, item in enumerate(github_items[:10], 1):
                if item.link:
                    links_html.append(f'[{i}]<a href="{item.link}" target="_blank" style="color:#1890ff;text-decoration:none;">{item.link}</a><br/>')
            links_html.append('</p>')
            sections_html.append(''.join(links_html))



    if hf_img_url:
        sections_html.append(f'''
        <h2 style="{h2_style}">🔥 Hugging Face模型热度榜</h2>
        <img src="{hf_img_url}" style="width:100%;max-width:1400px;display:block;margin:10px 0;" />
        ''')

    if or_img_url:
        sections_html.append(f'''
        <h2 style="{h2_style}">🔥 OpenRouter模型调用量榜单</h2>
        <img src="{or_img_url}" style="width:100%;max-width:1400px;display:block;margin:10px 0;" />
        ''')

    # 判断是否为兜底模式（分类失败，不分组）
    ungrouped = all(not item.category for item in news)

    if ungrouped:
        # 兜底模式：全部展示为一个无分类的大列表
        sections_html.append('<h2 style="color:#000000;font-weight:bold;font-size:19px;margin-top:20px;margin-bottom:10px;">📋 今日AI资讯汇总</h2>')
        for item in news:
            display_title = item.rewritten_title or item.title
            sections_html.append(f'<h3 style="{h3_style}">{display_title}</h3>')
            content = item.summary or item.desc
            if content:
                sections_html.append(f'<p style="{p_desc_style}">{content}</p>')
            source_parts = []
            if item.source:
                source_parts.append(f'来源：{item.source}')
            if item.time_ago:
                source_parts.append(item.time_ago)
            if source_parts:
                sections_html.append(f'<p style="{p_source_style}">{" | ".join(source_parts)}</p>')
            if item.link:
                sections_html.append(f'<p style="{p_source_style}">原文链接：<a href="{item.link}" target="_blank" style="color:#1890ff;text-decoration:underline;">{item.link}</a></p>')
    else:
        for cat in cats:
            items = [n for n in news if n.category == cat]
            if not items:
                continue

            cat_emoji = {
                '国内AI资讯': '🏷️ 国内AI资讯',
                '国外AI资讯': '🌍 国外AI资讯',
                '智能硬件': '📱 智能硬件',
                '其它科技资讯': '💡 其它科技资讯',
            }.get(cat, cat)

            sections_html.append(f'<h2 style="{h2_style}">{cat_emoji}</h2>')

            for item in items:
                display_title = item.rewritten_title or item.title
                sections_html.append(f'<h3 style="{h3_style}">{display_title}</h3>')
                content = item.summary or item.desc
                if content:
                    sections_html.append(f'<p style="{p_desc_style}">{content}</p>')
                source_parts = []
                if item.source:
                    source_parts.append(f'来源：{item.source}')
                if item.time_ago:
                    source_parts.append(item.time_ago)
                if source_parts:
                    sections_html.append(f'<p style="{p_source_style}">{" | ".join(source_parts)}</p>')
                if item.link:
                    sections_html.append(f'<p style="{p_source_style}">原文链接：<a href="{item.link}" target="_blank" style="color:#1890ff;text-decoration:underline;">{item.link}</a></p>')

    if insight:
        sections_html.append(f'''
        <h2 style="{h2_style}">💡 今日洞察</h2>
        <div style="background:#f6ffed;padding:15px;border-radius:8px;line-height:1.8;font-size:15px;">
            <p>{insight}</p>
        </div>
        ''')

    unique_sources = sorted(set(item.source for item in news if item.source))
    if not unique_sources:
        unique_sources = ['虎嗅', 'InfoQ', '量子位']
    sources_str = '、'.join(unique_sources)
    footer = f'''
    <p style="color:#999;margin-top:30px;text-align:center;font-size:13px;">
        <em>来源：{sources_str} | 整理：Valkyrie</em>
        <br>本文部分内容由AI整理生成
    </p>
    '''

    html = f'''<!DOCTYPE html>
<html>
<body>
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:0 10px;font-size:16px;line-height:1.6;color:#333;">

{''.join(sections_html)}

{footer}
</div>
</body>
</html>'''

    return html


def save_output(news: List[NewsItem], api_news: List[NewsItem], output_dir: Path,
                github_img_path: str = None, hf_img_path: str = None, or_img_path: str = None,
                hot_items: List[str] = None, insight: str = None,
                github_items: List[NewsItem] = None):
    """保存输出"""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_file = output_dir / f"news_{datetime.now().strftime('%Y%m%d')}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump([n.to_dict() for n in news], f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存: {json_file}")

    html = generate_html(news, github_img_path, hf_img_path, or_img_path, hot_items, insight, github_items)
    html_file = output_dir / f"news_{datetime.now().strftime('%Y%m%d')}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"💾 已保存: {html_file}")

    md_file = output_dir / f"news_{datetime.now().strftime('%Y%m%d')}.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# AI资讯早报 - {datetime.now().strftime('%Y年%m月%d日')}\n\n")
        cats = ['国内AI资讯', '国外AI资讯', '智能硬件', '其它科技资讯']
        for cat in cats:
            items = [n for n in news if n.category == cat]
            if items:
                f.write(f"## {cat}\n\n")
                for item in items:
                    f.write(f"### {item.title}\n")
                    if item.summary:
                        f.write(f"{item.summary}\n")
                    f.write(f"- 来源: {item.source} | [原文]({item.link})\n\n")

    print(f"💾 已保存: {md_file}")


def upload_to_wechat(html_content: str, title: str, github_img_path: str = None, hf_img_path: str = None, or_img_path: str = None, config: dict = None) -> bool:
    """上传到微信公众号草稿箱"""
    if config is None:
        config = DEFAULT_CONFIG
    import requests

    app_id = "wxdef888862e3ecca1"
    app_secret = "1483a2e68153e9cf6a5f1580e223e660"

    cache_dir = Path.home() / ".openclaw" / "workspace" / "ai-news"
    cache_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    cached_html_path = cache_dir / f"wechat_draft_{today_str}.html"
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    cached_html_timestamp_path = cache_dir / f"wechat_draft_{timestamp_str}.html"
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_cached = output_dir / f"wechat_draft_{datetime.now().strftime('%Y%m%d')}.html"

    print(f"   💾 缓存HTML到: {cached_html_path}")

    resp = requests.get(
        f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}",
        timeout=10
    ).json()
    token = resp.get("access_token")

    if not token:
        print(f"   ❌ 获取 token 失败")
        return False

    github_img_url = None
    hf_img_url = None
    or_img_url = None

    if github_img_path and Path(github_img_path).exists():
        with open(github_img_path, 'rb') as f:
            files = {'media': ('github.png', f, 'image/png')}
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
            r = requests.post(url, files=files, timeout=30).json()
        github_img_url = r.get("url", "")
        print(f"   GitHub图片: {'✅' if github_img_url else '❌'}")

    if hf_img_path and Path(hf_img_path).exists():
        with open(hf_img_path, 'rb') as f:
            files = {'media': ('hf.png', f, 'image/png')}
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
            r = requests.post(url, files=files, timeout=30).json()
        hf_img_url = r.get("url", "")
        print(f"   HF图片: {'✅' if hf_img_url else '❌'}")

    if or_img_path and Path(or_img_path).exists():
        with open(or_img_path, 'rb') as f:
            files = {'media': ('openrouter.png', f, 'image/png')}
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
            r = requests.post(url, files=files, timeout=30).json()
        or_img_url = r.get("url", "")
        print(f"   OpenRouter图片: {'✅' if or_img_url else '❌'}")

    if github_img_url:
        html_content = html_content.replace(github_img_path, github_img_url)
    if hf_img_url:
        html_content = html_content.replace(hf_img_path, hf_img_url)
    if or_img_url:
        html_content = html_content.replace(or_img_path, or_img_url)

    saved_thumb_id = config.get("wechat_thumb_media_id")
    if saved_thumb_id:
        thumb_media_id = saved_thumb_id
        print(f"   ✅ 使用已保存的封面 media_id")
    else:
        cover_path = Path.home() / ".openclaw" / "workspace" / "ai-news" / "cover.jpg"
        with open(cover_path, 'rb') as f:
            files = {'media': ('cover.jpg', f, 'image/jpeg')}
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
            r = requests.post(url, files=files, timeout=30).json()

        thumb_media_id = r.get("media_id")
        if not thumb_media_id:
            print(f"   ❌ 封面上传失败")
            return False
        print(f"   ✅ 新封面上传成功: {thumb_media_id}")

    import json as json2
    draft = {
        "articles": [{
            "title": title,
            "author": "Valkyrie",
            "digest": "今日AI热点：GitHub AI项目趋势榜、HuggingFace模型热度榜、以及国内外AI资讯精选",
            "content": html_content,
            "thumb_media_id": thumb_media_id,
        }]
    }

    post_data = json2.dumps(draft, ensure_ascii=False).encode('utf-8')
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    resp = requests.post(url, data=post_data, headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=30)
    result = resp.json()

    if "media_id" in result:
        print(f"   ✅ 已上传到公众号草稿箱")
        with open(cached_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        with open(cached_html_timestamp_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        with open(output_cached, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"   💾 HTML已缓存: {cached_html_path}")
        return True
    else:
        print(f"   ❌ 上传失败: {result}")
        return False


def fetch_github_total_stars(owner: str, repo: str) -> str:
    """通过 GitHub API 获取项目的总 star 数"""
    import urllib.request
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return str(data.get('stargazers_count', ''))
    except Exception:
        return ""


def fetch_github_readme(owner: str, repo: str) -> str:
    """抓取 GitHub 项目的 README 内容（优先 raw，次选 API）"""
    import urllib.request

    # 优先尝试 raw.githubusercontent.com
    for branch in ['main', 'master']:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                if content and len(content) > 50:
                    return content[:5000]
        except Exception:
            pass

    # 备选：GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github.v3+json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            import base64
            data = json.loads(resp.read().decode('utf-8'))
            content = base64.b64decode(data['content']).decode('utf-8', errors='ignore')
            return content[:5000]
    except Exception:
        pass

    return ""


def _call_llm(prompt: str, max_tokens: int = 300, timeout: int = 30, max_retries: int = 1) -> str:
    """调用 MiniMax LLM，返回文本内容。
    
    Args:
        max_retries: 最大重试次数，默认1表示不重试。>1时会 对瞬时错误(429/502/503/504/timeout)进行重试。
    """
    from interceptors.llm_summary import MINI_MAX_API_KEY, MINI_MAX_BASE_URL
    import urllib.request
    import socket

    payload = {
        "model": "MiniMax-M2.5",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens
    }

    backoff = [2, 4, 8, 16]  # 重试间隔(秒)

    for attempt in range(max_retries):
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                MINI_MAX_BASE_URL + "/text/chatcompletion_v2",
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {MINI_MAX_API_KEY}'
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result.get('choices'):
                    return result['choices'][0]['message']['content'].strip()
            return ""
        except urllib.error.HTTPError as e:
            # 429 Rate Limit / 502 / 503 / 504 - 值得重试
            if e.code in (429, 502, 503, 504) and attempt < max_retries - 1:
                import time
                time.sleep(backoff[attempt] if attempt < len(backoff) else backoff[-1])
                continue
            return ""
        except (urllib.error.URLError, socket.timeout) as e:
            # 网络/连接超时 - 值得重试
            if attempt < max_retries - 1:
                import time
                time.sleep(backoff[attempt] if attempt < len(backoff) else backoff[-1])
                continue
            return ""
        except Exception:
            # 其他异常( JSON解析失败等) - 不重试，直接返回空
            return ""
    return ""


def _get_cache_path(owner: str, repo: str) -> Path:
    """获取缓存文件路径"""
    cache_dir = Path.home() / ".openclaw" / "workspace" / "ai-news" / "github_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{owner}_{repo}.json"


def _load_cache(owner: str, repo: str) -> dict:
    """尝试从本地缓存读取（24小时TTL），返回 dict 或 None"""
    import time
    cache_path = _get_cache_path(owner, repo)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > 24 * 3600:
            return None  # 过期
        return data
    except Exception:
        return None


def _save_cache(owner: str, repo: str, readme: str, total_stars: str):
    """保存数据到本地缓存"""
    import time
    cache_path = _get_cache_path(owner, repo)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({
                "readme": readme,
                "stars": total_stars,
                "cached_at": time.time()
            }, f, ensure_ascii=False)
    except Exception:
        pass


def _fetch_project_data(item: NewsItem) -> dict:
    """并行抓取单个项目的 README 和总 star 数，返回 dict"""
    parts = item.link.strip('/').split('/')
    owner, repo = parts[-2], parts[-1]

    # 尝试从缓存读取（24小时TTL）
    cached = _load_cache(owner, repo)
    if cached:
        readme = cached.get("readme", "")
        total_stars = cached.get("stars", "")
    else:
        import concurrent.futures

        def fetch_readme():
            return fetch_github_readme(owner, repo)

        def fetch_stars():
            return fetch_github_total_stars(owner, repo)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_readme = pool.submit(fetch_readme)
            f_stars = pool.submit(fetch_stars)
            readme = f_readme.result() or ""
            total_stars = f_stars.result() or ""

        # 写入缓存
        _save_cache(owner, repo, readme, total_stars)

    # README 内容：取前5000字，按段落分割保留完整语义
    if readme:
        paragraphs = readme.split('\n\n')
        readme_content = ""
        for para in paragraphs:
            if len(readme_content) + len(para) <= 5000:
                readme_content += para + "\n\n"
            else:
                break
        readme_content = readme_content.strip()
    else:
        readme_content = ""

    # Stars 格式化为 xK（stars/1000 四舍五入保留一位小数）
    if total_stars:
        try:
            stars_k = round(int(total_stars) / 1000, 1)
            stars_display = f"目前总star数为{stars_k}K"
        except Exception:
            stars_display = f"目前总star数为{total_stars}"
    else:
        stars_display = ""

    return {
        "title": item.title,
        "readme": readme_content,
        "stars": total_stars,
        "stars_display": stars_display,
    }


def generate_github_summary(github_items: List[NewsItem]) -> str:
    """为 GitHub Top 5 项目生成项目简介和趋势总结。
    - Step 1: 5个线程并行抓取 README 和 stars
    - Step 2: 1个 LLM 调用，一次性输出 Top1-Top5 简介 + 趋势观察
    """
    if not github_items:
        return ""

    top5 = github_items[:5]

    # Step 1: 并行抓取所有项目的 README 和 stars
    print(f"   📝 并行抓取 {len(top5)} 个项目数据...")
    import concurrent.futures
    project_data_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_project_data, item): item for item in top5}
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
                project_data_list.append(data)
            except Exception:
                pass

    # 按原始顺序排序
    title_order = [item.title for item in top5]
    project_data_list.sort(key=lambda x: title_order.index(x["title"]) if x["title"] in title_order else 999)

    # 构建项目信息文本
    project_infos = []
    for i, p in enumerate(project_data_list, 1):
        readme_section = f"README 内容：{p['readme']}" if p['readme'] else "README：无"
        star_section = p["stars_display"]
        project_infos.append(f"【项目{i}】\n项目名：{p['title']}\n{readme_section}\n{star_section}")
    projects_text = "\n\n".join(project_infos)

    # Step 2: 一次 LLM 调用，生成完整输出
    print(f"   📝 生成项目简介和趋势观察...")
    prompt = f"""以下是目前最热门的 5 个 GitHub AI 项目及其 README 内容，请严格按格式输出：

{projects_text}

请严格按以下格式输出（全部用中文，禁止 markdown 格式如**或##等，禁止脑补，只基于 README 信息）：

Top1【项目名】100-200字描述。如果查到总star数，加一句"目前总star数为xK"。
Top2【项目名】100-200字描述。如果查到总star数，加一句"目前总star数为xK"。
Top3【项目名】100-200字描述。如果查到总star数，加一句"目前总star数为xK"。
Top4【项目名】100-200字描述。如果查到总star数，加一句"目前总star数为xK"。
Top5【项目名】100-200字描述。如果查到总star数，加一句"目前总star数为xK"。

【趋势观察】150-200字，基于这5个项目的共同主题提炼，不要夸大、不要泛泛而谈。"""

    result = _call_llm(prompt, max_tokens=1500, timeout=60)

    if not result:
        return ""

    # 去掉可能的 markdown 格式
    import re
    result = re.sub(r'\*\*(.+?)\*\*', r'\1', result)

    return result


def _generate_repo_chinese_desc(item: NewsItem) -> str:
    """为单个仓库生成中文介绍：抓取 README → LLM 生成 80-150 字摘要（带 5 天缓存）"""
    import re
    import sys
    import json
    import time

    parts = item.link.strip('/').split('/')
    if len(parts) < 2:
        print(f"      ⚠️ {item.title}: 无法解析 owner/repo", file=sys.stderr)
        return item.desc or "暂无描述"
    owner, repo = parts[-2], parts[-1]
    cache_key = f"{owner}/{repo}"

    # ── 缓存读写 ────────────────────────────────────────────────
    CACHE_PATH = Path.home() / ".openclaw" / "workspace" / "ai-news" / "github_desc_cache.json"
    CACHE_TTL = 5 * 24 * 3600  # 5 天

    def _load_cache() -> dict:
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(cache: dict):
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    cache = _load_cache()
    entry = cache.get(cache_key)
    now = time.time()

    if entry and (now - entry.get("ts", 0)) < CACHE_TTL:
        days_left = int((CACHE_TTL - (now - entry["ts"])) / 86400)
        print(f"      💾 {cache_key}: 命中缓存（剩余 {days_left} 天）", file=sys.stderr)
        return entry["desc"]

    # ── 缓存未命中，走 LLM 生成流程 ────────────────────────────
    readme = fetch_github_readme(owner, repo)
    if not readme:
        print(f"      ⚠️ {cache_key}: README 获取失败或为空", file=sys.stderr)
        return item.desc or "暂无描述"

    readme_clean = re.sub(r'<[^>]+>', ' ', readme)
    readme_clean = re.sub(r'\s+', ' ', readme_clean).strip()
    readme_clip = readme_clean[:2500]
    prompt = (
        "你是一个专业的中文技术写作人员。请仔细阅读以下项目的 README 内容，"
        "用 80-150 字的中文（纯中文，禁止任何英文单词，禁止中英混杂）介绍这个项目。"
        "必须以句号（。）结尾，禁止在句子中间截断。如果 README 内容不足以生成介绍，请明确说明[暂无足够信息]。\n\n"
        "README 内容：\n" + readme_clip
    )
    result = _call_llm(prompt, max_tokens=800, timeout=60, max_retries=4)

    if not result:
        print(f"      ⚠️ {cache_key}: LLM 返回空（超时/限速）", file=sys.stderr)
        return item.desc or "暂无描述"
    if len(result.strip()) < 10:
        print(f"      ⚠️ {cache_key}: LLM 返回过短: {result[:50]}", file=sys.stderr)
        return item.desc or "暂无描述"

    result = re.sub(r'\*\*?(.+?)\*\*?', r'\1', result)
    result = re.sub(r'#{1,6}\s*', '', result)
    result = re.sub(r'`[^`]*`', '', result)
    result = re.sub(r'>\s*', '', result)
    result = re.sub(r'\n+', ' ', result).strip()

    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', result))
    if chinese_chars == 0:
        print(f"      ⚠️ {cache_key}: LLM 返回无中文，回退英文", file=sys.stderr)
        return item.desc or "暂无描述"
    if '暂无足够信息' in result:
        print(f"      ⚠️ {cache_key}: 暂无足够信息", file=sys.stderr)
        return item.desc or "暂无描述"

    if len(result) > 30 and result[-1] not in '。！？':
        tail = result[-50:] if len(result) > 50 else result
        for punct in ('。', '！', '？'):
            idx = tail.rfind(punct)
            if idx >= 0:
                result = result[:len(result) - len(tail) + idx + 1]
                break

    # ── 写入缓存 ────────────────────────────────────────────────
    cache[cache_key] = {"desc": result, "ts": now}
    _save_cache(cache)
    print(f"      ✅ {cache_key}: 生成并缓存（5 天）{result[:40]}...", file=sys.stderr)
    return result


def generate_github_html_table(github_items: List[NewsItem], output_dir: Path) -> str:
    """使用 Jinja2 + Playwright 生成 GitHub 趋势榜图片（HTML 渲染方案）"""
    from jinja2 import Environment, FileSystemLoader
    from playwright.sync_api import sync_playwright
    import concurrent.futures

    if not github_items:
        return None

    # 准备基础数据
    repos = []
    for i, item in enumerate(github_items[:10], 1):
        repos.append({
            "rank": i,
            "name": item.title,
            "author": item.extra.get("author", "-"),
            "description": item.desc or "暂无描述",
            "language": item.extra.get("language") or "-",
            "stars": item.extra.get("stars", "-"),
        })

    # 并行抓取 README + LLM 生成中文介绍
    print(f"   📝 并行生成 {len(repos)} 个项目的中文介绍...")
    top10 = github_items[:10]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_generate_repo_chinese_desc, item): i for i, item in enumerate(top10)}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                chinese_desc = future.result()
                repos[idx]["description"] = chinese_desc
                # 写回 NewsItem，以便存入数据库
                top10[idx].llm_description = chinese_desc
            except Exception as e:
                print(f"      ⚠️ GitHub #{idx+1} {top10[idx].title} 中文介绍生成失败: {e}")

    date_str = datetime.now().strftime("%Y-%m-%d")

    # 渲染 HTML
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("github_trending.html")
    html_content = template.render(date=date_str, repos=repos)

    # 保存 HTML（调试用）
    html_debug_path = output_dir / "github_trending_debug.html"
    with open(html_debug_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Playwright 截图
    img_path = str(output_dir / "github_trending.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_viewport_size({"width": 820, "height": 1200})
            page.goto(f"file://{html_debug_path.absolute()}", wait_until="domcontentloaded")
            page.wait_for_timeout(500)  # 等待字体加载
            page.screenshot(path=img_path, full_page=True)
            browser.close()
        return img_path
    except Exception as e:
        print(f"   ⚠️ Playwright 截图失败: {e}")
        return None


def generate_tables(api_news: List[NewsItem], openrouter_items: List[NewsItem], output_dir: Path) -> tuple:
    """生成 GitHub、HuggingFace、OpenRouter 趋势表格"""
    from table_image import generate_table, send_to_feishu

    github_img_path = None
    hf_img_path = None
    or_img_path = None

    type_map = {
        'text-generation': '文本生成',
        'text2text-generation': '文本转换',
        'image-text-to-text': '图文理解',
        'visual-question-answering': '视觉问答',
        'automatic-speech-recognition': '语音识别',
        'text-to-speech': '语音合成',
        'text-to-image': '文生图',
        'image-classification': '图像分类',
        'object-detection': '目标检测',
        'feature-extraction': '特征提取',
        'sentence-similarity': '句子相似度',
    }

    github_items = [n for n in api_news if n.source == 'github']
    hf_items = [n for n in api_news if n.source == 'huggingface']

    if github_items:
        print("\n📊 生成 GitHub AI 趋势榜（HTML渲染方案）...")
        github_img_path = generate_github_html_table(github_items, output_dir)
        if github_img_path:
            print(f"   ✅ GitHub 表格已生成")

    if hf_items:
        print("\n📊 生成 HuggingFace 模型热度榜...")
        header = ['模型', '下载量', '点赞数', '类型', '更新时间']
        rows = []
        for i, item in enumerate(hf_items[:10], 1):
            downloads = item.extra.get('downloads', 0)
            likes = item.extra.get('likes', 0)
            downloads_str = f'{downloads/1000:.1f}K' if downloads >= 1000 else str(downloads)
            likes_str = f'{likes/1000:.1f}K' if likes >= 1000 else str(likes)
            pipeline = item.extra.get('pipeline_tag', '')
            type_cn = type_map.get(pipeline, pipeline)
            last_modified = item.extra.get('last_modified', '-')
            rows.append([item.title, downloads_str, likes_str, type_cn, last_modified])

        all_data = [header] + rows
        hf_img_path = str(output_dir / "huggingface_trending.png")
        result = generate_table(
            data=all_data,
            title='Hugging Face模型热度榜单',
            width=1080, font_size=16,
            header_color='#1E40AF',
            col_widths=[4, 1.5, 1.5, 1.5, 1.5],
            padding=15,
            output_path=hf_img_path
        )
        if result.get('success'):
            print("   ✅ HuggingFace 表格已生成")

    if openrouter_items:
        print("\n📊 生成 OpenRouter 模型榜单...")
        header = ['排名', '模型', '公司', 'Token使用量', '增长率']
        rows = []
        for i, item in enumerate(openrouter_items[:10], 1):
            tokens = item.desc or '-'
            change = item.time_ago or '-'
            rows.append([str(i), item.title, item.extra.get('company', item.source), tokens, change])

        all_data = [header] + rows
        or_img_path = str(output_dir / "openrouter_rankings.png")
        result = generate_table(
            data=all_data,
            title='OpenRouter模型调用量榜单',
            width=1080, font_size=16,
            header_color='#1E40AF',
            col_widths=[1, 3, 1.5, 1.5, 1],
            padding=15,
            output_path=or_img_path
        )
        if result.get('success'):
            print("   ✅ OpenRouter 表格已生成")

    return github_img_path, hf_img_path, or_img_path, github_items[:10] if github_items else []


def main():
    start_time = time.time()
    today = datetime.now().strftime("%Y%m%d")

    print("🤖 AI资讯早报 v10")
    print("=" * 50)

    # ========== 埋点：任务开始 ==========
    run_id = None
    if MONITOR_DB:
        try:
            run_id = MONITOR_DB.start_run(today)
            print(f"✅ MonitorDB run_id={run_id}")
        except Exception as e:
            print(f"⚠️ MonitorDB start_run 失败: {e}")

    try:
        # 1. 加载配置
        config = load_config()
        print(f"📋 数据源: {[s['name'] for s in config['sources'] if s.get('enabled')]}")
        print(f"📋 拦截器: {config['interceptors']}")

        # 2. 收集数据
        html_news, api_news, source_map = collect_all_news(config)

        # ========== 埋点：写入原始数据 ==========
        if MONITOR_DB and run_id is not None:
            try:
                # source_map 现在包含所有来源（HTML + API）
                for src, items in source_map.items():
                    MONITOR_DB.write_raw_news(run_id, src, items)
                print(f"✅ MonitorDB 写入原始数据完成")
            except Exception as e:
                print(f"⚠️ MonitorDB write_raw_news 失败: {e}")

        # 3. 处理 HTML 来源
        processed_html = []
        if html_news:
            processed_html = process_interceptors_with_monitor(html_news, config, MONITOR_DB, run_id)
            processed_html = limit_by_category(processed_html, config.get("limits", {}))

        # 4. 设置默认分类（仅 LLM 分类成功时生效）
        llm_classify_failed = all(not item.category for item in processed_html)
        if llm_classify_failed:
            print("   ⚠️ LLM 分类失败，跳过默认分类和热点洞察，全量保留不分组展示")
            all_output = processed_html
            hot_items_out = None
            insight_out = None
        else:
            for item in processed_html:
                if not item.category:
                    item.category = '其它科技资讯'
            all_output = processed_html

            # 5. AI 选择热点和生成洞察
            from interceptors.hot_insight import ai_select_hot_and_insight
            print("\n🤖 AI 选择热点和生成洞察...")
            hot_items_out, insight_out = ai_select_hot_and_insight(all_output, {
                '国内AI资讯': 3,
                '国外AI资讯': 2,
                '智能硬件': 1
            })
            print(f"   ✅ 热点 {len(hot_items_out)} 条，洞察 {len(insight_out)} 字")

        # 6. 生成表格
        work_dir = Path(__file__).parent
        output_dir = work_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 从 api_news 直接提取（避免重复抓取 OpenRouter）
        openrouter_items = [n for n in api_news if n.source == 'openrouter']
        print(f"   📊 OpenRouter 获取到 {len(openrouter_items)} 条")

        github_img_path, hf_img_path, or_img_path, github_top_items = generate_tables(api_news, openrouter_items, output_dir)

        # 7. 保存输出
        save_output(all_output, api_news, output_dir, github_img_path, hf_img_path, or_img_path, hot_items_out, insight_out, github_top_items)

        # 7.5 写入 GitHub 项目的 LLM 中文介绍（覆盖之前写入的原始数据）
        if MONITOR_DB and run_id is not None and github_top_items:
            try:
                MONITOR_DB.upsert_llm_description(run_id, github_top_items)
                print(f"✅ MonitorDB 更新 GitHub LLM介绍完成")
            except Exception as e:
                print(f"⚠️ MonitorDB 更新 GitHub LLM介绍失败: {e}")

        # 8. 上传到微信公众号
        html_file = output_dir / f"news_{datetime.now().strftime('%Y%m%d')}.html"
        if html_file.exists():
            html_content = html_file.read_text(encoding='utf-8')
            today_str = datetime.now().strftime("%Y年%m月%d日")
            title = f"AI资讯早报（{today_str}）"
            print(f"\n📤 上传到公众号...")
            upload_to_wechat(html_content, title, github_img_path, hf_img_path, or_img_path, config)

        duration = time.time() - start_time

        # ========== 埋点：任务结束 ==========
        if MONITOR_DB and run_id is not None:
            try:
                MONITOR_DB.finish_run(
                    run_id=run_id,
                    status="success",
                    total_collected=len(html_news),
                    total_output=len(all_output)
                )
                print(f"✅ MonitorDB finish_run 完成")
            except Exception as e:
                print(f"⚠️ MonitorDB finish_run 失败: {e}")

    except Exception as e:
        duration = time.time() - start_time
        print(f"\n❌ 任务失败: {e}")

        if MONITOR_DB and run_id is not None:
            try:
                MONITOR_DB.finish_run(
                    run_id=run_id,
                    status="failed",
                    error_message=str(e)
                )
            except Exception:
                pass

        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("✅ 完成!")
    print(f"   总耗时: {duration:.1f}s")
    print(f"   API数据: {len(api_news)} 条")
    print(f"   HTML处理后: {len(processed_html)} 条")
    print(f"   最终输出: {len(all_output)} 条")


if __name__ == "__main__":
    main()
