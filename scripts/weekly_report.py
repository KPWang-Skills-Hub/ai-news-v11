#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"AI资讯周报生成器 v3 - LLM一步精选（参照文档重建，含4项改动）"
import sys, json, os, re, argparse
from pathlib import Path
from datetime import datetime, timedelta

SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPTS_DIR / 'output'

# 数据库路径（与 ai-news-monitor backend 保持一致）
MONITOR_DB_PATH = os.environ.get(
    "MONITOR_DB_PATH",
    os.path.join(os.path.expanduser("~"), ".openclaw", "data", "ai-news-monitor", "monitor.db")
)

MINIMAX_API_KEY = 'sk-cp-wTF01lPxZSg5kglem92SZUPwYthfQoAwvNa74N8ZySxN4TxPD0gnlNRt-eAMjtng41w-AL1D59j2W9IbpBMVrJH0xHRw-XG0PYU3fXnAbqjjvnkNcQoSSGY'
MINIMAX_MODEL = 'MiniMax-M2.5'

# ========== 配置 ==========
DEFAULT_CONFIG = {
    "filter_no_link": True,  # 是否过滤无链接的数据（True=过滤，False=保留）
}

def _call_minimax(prompt, model=MINIMAX_MODEL, temperature=0.1, max_tokens=8000, max_retries=5):
    import urllib.request, time
    api_url = 'https://api.minimax.chat/v1/text/chatcompletion_v2'
    body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': temperature, 'max_tokens': max_tokens}
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(api_url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + MINIMAX_API_KEY}, method='POST')
            with urllib.request.urlopen(req, timeout=300) as resp:
                rd = json.loads(resp.read().decode('utf-8'))
                choices = rd.get('choices', [{}])
                content = choices[0].get('message', {}).get('content', '')
                if content: return content
                last_err = 'empty response'
        except Exception as e:
            last_err = str(e)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f'      [warn] 调用失败({attempt+1}/{max_retries})，等{wait}s: {last_err}')
                time.sleep(wait)
    print(f'      [error] MiniMax调用最终失败: {last_err}')
    return ''

class DailyItem:
    __slots__ = ('title', 'desc', 'link', 'source', 'time_ago', 'category', 'summary', 'content', 'extra')
    def __init__(self, d):
        self.title = d.get('title', '').strip()
        self.desc = d.get('desc', '')
        self.link = d.get('link', '')
        self.source = d.get('source', '')
        self.time_ago = d.get('time_ago', '')
        self.category = d.get('category', '')
        self.summary = d.get('summary', '')
        self.content = d.get('content', '')
        self.extra = d.get('extra', {})

# ========== Step 1: 从数据库读取日报数据 ==========
def load_week_data_from_db(days=7):
    """从 MonitorDB 数据库读取本周日报数据。
    数据来源：
    - 每天选取所有 status=success 且 total_output>0 的 DailyRun
    - 从 RawNews 表读取 filtered_by IS NULL 的记录
    - 按原始标题精确去重，跨 run 跨天重复的只保留一条
    """
    try:
        import sqlite3
    except ImportError:
        print('[error] sqlite3 未安装')
        return [], []
    
    today = datetime.now().date()
    seen_titles, all_items, loaded = set(), [], []
    
    db_dir = os.path.dirname(MONITOR_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    try:
        conn = sqlite3.connect(MONITOR_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    except Exception as e:
        print(f'[error] 无法连接数据库: {e}')
        return [], []
    
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime('%Y%m%d')
        
        cursor.execute("""
            SELECT id, total_output FROM daily_runs
            WHERE date = ? AND status = 'success' AND total_output > 0
            ORDER BY id DESC
        """, (date_str,))
        runs = cursor.fetchall()
        
        if not runs:
            print(f'   [db] {date_str}: 无成功运行，跳过')
            continue
        
        run_ids = [r['id'] for r in runs]
        placeholders = ','.join(['?'] * len(run_ids))
        
        cursor.execute(f"""
            SELECT title, link, source, time_ago, desc, raw_extra, run_id
            FROM raw_news
            WHERE run_id IN ({placeholders}) AND filtered_by IS NULL
        """, run_ids)
        
        rows = cursor.fetchall()
        if not rows:
            print(f'   [db] {date_str}: {len(run_ids)}个run均无通过数据，跳过')
            continue
        
        date_added = 0
        for r in rows:
            title = (r['title'] or '').strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            extra = {}
            try:
                extra = json.loads(r['raw_extra'] or '{}')
            except:
                pass
            item = DailyItem({
                'title': title,
                'desc': r['desc'] or '',
                'link': r['link'] or '',
                'source': r['source'] or '',
                'time_ago': r['time_ago'] or '',
                'category': '',
                'summary': '',
                'content': '',
                'extra': extra,
            })
            all_items.append(item)
            date_added += 1
        
        loaded.append(date.strftime('%Y-%m-%d'))
        print(f'   [db] {date_str}: {len(run_ids)}个run, DB记录{len(rows)}条, 去重后新增{date_added}条')
    
    conn.close()
    return all_items, loaded


def load_week_data(days=7):
    """兼容接口：优先从数据库读取"""
    items, loaded = load_week_data_from_db(days)
    if loaded:
        print(f'   [db] 从数据库加载 {len(items)} 条（日期: {loaded}）')
        return items, loaded
    print('   [warn] 数据库无数据')
    return [], []

# ========== Step 2: BGE 去重 ==========
def run_bge_dedup(items, thresh=0.75):
    # 检查本地是否有缓存的模型
    import os
    cache_dir = os.path.expanduser('~/.cache/huggingface/hub/models--BAAI--bge-small-zh-v1.5')
    if not os.path.exists(cache_dir):
        print('[warn] BGE模型未缓存，跳过BGE去重')
        return items
    # 设置离线模式，只用本地缓存不联网验证
    os.environ['HF_HUB_OFFLINE'] = '1'
    try:
        from sentence_transformers import SentenceTransformer
        import concurrent.futures
        def load_model():
            return SentenceTransformer('BAAI/bge-small-zh-v1.5')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(load_model)
            try:
                model = future.result(timeout=30)
                print('[info] BGE模型加载成功')
            except concurrent.futures.TimeoutError:
                print('[warn] BGE模型加载超时，跳过BGE去重')
                return items
    except Exception as e:
        print(f'[warn] BGE加载失败: {e}，跳过BGE去重')
        return items
    skip = {'github', 'huggingface', 'openrouter'}
    to_emb, idx_map = [], []
    for i, it in enumerate(items):
        if (it.source or '').strip().lower() not in skip:
            to_emb.append(it.title)
            idx_map.append(i)
    if not to_emb:
        return items
    print(f'[info] 向量化 {len(to_emb)} 条...')
    vecs = model.encode(to_emb, normalize_embeddings=True, batch_size=64)
    kept = set(range(len(items)))
    for i in range(len(vecs)):
        for j in range(i+1, len(vecs)):
            if float(vecs[i] @ vecs[j]) > thresh:
                rj = idx_map[j]
                if rj in kept:
                    kept.remove(rj)
    result = [items[i] for i in sorted(kept)]
    removed = len(items) - len(result)
    if removed > 0:
        print(f'[dedup] BGE移除 {removed} 条（剩 {len(result)} 条）')
    return result

# ========== LLM 精选 Prompt ==========
LLM_USER_PROMPT = (
    '你是一位资深的中国AI行业分析师，正在为国内读者制作一份聚焦**技术重大进展**的AI领域每周重要资讯精选。本精选严格排除融资、人事变动等非技术噪声，只收录真正影响技术格局的信息。\n\n'
    '# 任务目标\n'
    '从提供的本周AI资讯列表中，精选出最重要的12条技术向资讯，分为「国内AI资讯」和「国外AI资讯」两组，各6条。\n\n'
    '# 核心概念严格定义\n'
    '## 什么是「国内AI资讯」\n'
    '满足以下任一条件即为国内资讯：\n'
    '1. 事件主体是中国大陆公司（包括其海外分支/团队的行为，如字节跳动、阿里巴巴、腾讯、百度、华为、DeepSeek、月之暗面、智谱AI、百川智能、零一万物、科大讯飞，商汤、旷视、第四范式等）\n'
    '2. 事件发生在中国大陆境内（如中国政府的政策发布、中国举办的AI大会、中国学术机构的成果）\n'
    '3. 事件主体是华人创业者创办的，主要面向中国市场的公司\n'
    '特别说明：\n'
    '- 苹果、特斯拉、微软等外企在中国设立AI研发中心所发布的中国专属成果，归为国内资讯。\n'
    '- 中国公司在海外发布的产品/模型，仍算国内资讯。\n'
    '- 外国公司在中国市场的动作（如OpenAI与国内企业合作），归为国内资讯。\n\n'
    '## 什么是「国外AI资讯」\n'
    '国内资讯以外的所有资讯，即为国外资讯。主要包括：\n'
    '1. 事件主体是海外公司（OpenAI、Anthropic、Google DeepMind、Meta AI、Microsoft AI、Amazon、Apple、Mistral、Stability AI等）\n'
    '2. 事件发生在海外的AI政策、学术成果、行业动态\n'
    '3. 国际组织（如联合国、欧盟）发布的AI相关法规/报告\n\n'
    '## 边界案例处理规则\n'
    '遇到难以判断的，按以下优先级判定：\n'
    '- 观察事件最直接影响的市场。如果主要影响中国市场，归国内；主要影响海外/全球，归国外。\n'
    '- 如果事件同时涉及国内和国外主体，以主导方为准。若分不清主导方，则看谁对外发布了这个消息。\n'
    '- 如果仍然无法判断，归入国内资讯（宁可国内多一条）。\n\n'
    '# 硬性排除规则（必须先执行）\n'
    '以下类别无论涉及哪个公司或金额多大，一律直接归为C级，不纳入精选：\n'
    '- 任何形式的融资、投资、IPO、财务报告、估值变化\n'
    '- 公司高管或知名学者的常规人事变动、离职、入职（除非是国家级AI机构的一把手任免）\n'
    '- 非头部公司的新品发布、技术更新（除非该成果在权威基准测试上达到SOTA，且被多家一线媒体确认）\n'
    '- 单纯的市场分析、行业预测、观点评论类内容\n'
    '- 商业化合作、签约（纯技术开源合作或重大算力共建除外）\n\n'
    '# 重要性评估标准（仅限技术、政策与生态）\n'
    'S级（重大技术里程碑/国家级政策）：\n'
    '- 头部公司发布全新一代基础模型，或模型能力实现公认的质变（如GPT-5、Claude 4、Gemini 3、通义千问3.0等）\n'
    '- 颠覆性的技术突破，足以改变行业技术路径（如全新芯片架构、关键算法突破、训练范式变革）\n'
    '- 国家级重大AI政策正式发布（如中国AI法颁布、美国AI行政令）\n\n'
    'A级（重要技术进展/显著生态影响）：\n'
    '- 一线厂商的重大产品更新、核心能力开源、API价格颠覆性调整（直接影响开发者生态）\n'
    '- 核心技术突破（芯片、对齐、多模态、Agent、推理等方向），有权威验证\n'
    '- 在行业公认的权威基准测试（如MMLU、HumanEval、GPQA等）上登顶或大幅刷新纪录\n'
    '- 国际顶级学术会议（NeurIPS、ICML、CVPR等）最佳论文，或Nature/Science发表的重大AI研究成果\n\n'
    'B级（值得关注的技术进展）：\n'
    '- 非头部但有一定技术积累的公司发布达到一线水准的开源模型或工具\n'
    '- 重要的大规模技术应用落地案例，展现出可复用的技术范式\n'
    '- 国内外重大AI政策征求意见稿、重要监管动作\n'
    '- 头部公司发布具有技术前瞻性的重要开源项目、数据集、基准\n\n'
    'C级（不纳入精选）：\n'
    '- 以上未涵盖的常规动态，以及"硬性排除规则"中列出的所有内容\n\n'
    '# 操作流程\n'
    '1. 硬性过滤：先执行硬性排除规则，将所有融资、人事、小公司常规动态等直接移除。\n'
    '2. 扫描与初筛：快速扫描剩余资讯，剔除C级资讯，保留S/A/B级。\n'
    '3. 合并与去重（关键步骤）：\n'
    '   - 事件去重：对于多家媒体报道的同一个核心事件，必须合并为一条资讯。\n'
    '   - 主题合并：识别出信息碎片中的逻辑关联，凡是围绕同一事件或同一主题的连续报道、进展、不同角度的解读，都应合并成一条综合资讯。\n'
    '   - 正确做法：在合并后的摘要中，按时间线或逻辑顺序，概述核心进展。标题提炼出该事件最重要的结论。\n'
    '   - 错误做法：把两条互不相关的独立事件合并。\n'
    '4. 分级与初步排序：在合并后的资讯中，先按 S > A > B 排序，同级别内按影响力大小排序。\n'
    '5. 多样性调整：\n'
    '   - 主体均衡：在最终的Top6列表中，同一个主体出现的独条资讯数，原则上不超过2条。\n'
    '   - 例外条件：只有当同一主体的第3条资讯的重要性评级，明显高于被它挤掉的其他主体资讯，才允许例外。\n'
    '6. 配额分配：\n'
    '   - 从国内资讯中选出最重要的6条。\n'
    '   - 从国外资讯中选出最重要的6条。\n'
    '   - 如果某区域高质量资讯不足6条，可补入C级资讯；仍不足则宁可少选。\n\n'
    '# 输出格式要求\n'
    '请只输出下面这个JSON结构，不要包含任何解释，开场白或结尾语：\n\n'
    '{\n'
    '  "domestic_top6": [\n'
    '    {\n'
    '      "rank": 1,\n'
    '      "title": "精炼后的中文标题（直击要点，不超过30字）",\n'
    '      "summary": "综合摘要，包含核心事实和数据，不超过200字。",\n'
    '      "date": "2026-04-20",\n'
    '      "importance": "S/A/B",\n'
    '      "tags": ["大模型", "开源"],\n'
    '      "source": "虎嗅"\n'
    '    }\n'
    '  ],\n'
    '  "overseas_top6": [\n'
    '    {\n'
    '      "rank": 1,\n'
    '      "title": "...",\n'
    '      "summary": "...",\n'
    '      "date": "2026-04-20",\n'
    '      "importance": "S/A/B",\n'
    '      "tags": ["..."],\n'
    '      "source": "InfoQ"\n'
    '    }\n'
    '  ]\n'
    '}\n\n'
    '字段要求：\n'
    '- title：重新提炼，突出核心新闻点，不要直接照抄原标题\n'
    '- summary：用你自己的话重新组织，确保读者能快速获取关键信息\n'
    '- date：使用资讯原始日期，格式YYYY-MM-DD\n'
    '- importance：必须从S/A/B中选择\n'
    '- tags：从以下列表中选择1-3个最贴切的：大模型，开源，算力，政策，应用，学术，其他\n\n'
    '特别注意：\n'
    '- 所有输出文本使用简体中文\n'
    '- summary严格控制在150-200字之间，不允许超过200字\n'
    '- summary必须分段，每段不超过2-3句话，段落之间用空行分隔\n'
    '- 确保国内和国外各6条，总数恰好12条\n'
    '- 排序时，#1是最重要的\n'
    '- 不要输出任何JSON以外的内容\n\n'
    '# 本周资讯列表\n'
    '__NEWS_TEXT__'
)

# ========== Step 3: LLM 精选 ==========
def call_llm_classify_and_filter(items, week_start, week_end):
    print('   [llm] 调用MiniMax-M2.5...')
    news_lines = []
    for it in items:
        date = it.time_ago or ''
        src = it.source or ''
        body = (it.summary or it.desc or '').strip()
        news_lines.append('[' + date + '] ' + src + ' | ' + it.title + ' | ' + body)
    news_text = '\n'.join(news_lines)
    prompt = LLM_USER_PROMPT.replace('__NEWS_TEXT__', news_text)
    est = len(prompt) // 2
    print(f'   [info] 输入约 {est} tokens')
    if est > 180000:
        print('   [warn] 输入超出，截断...')
        prompt = prompt[: 270000]
    for call_att in range(3):
        try:
            response = _call_minimax(prompt, model=MINIMAX_MODEL, temperature=0.1, max_tokens=16000)
            if not response:
                if call_att < 2:
                    print(f'   [warn] 空响应，{call_att+1}/3 重试...')
                    continue
                break
            for pa in range(3):
                try:
                    m = re.search(r'\{[\s\S]*\}', response)
                    raw = m.group() if m else response
                    result = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    if pa < 2:
                        print(f'   [warn] JSON截断，{pa+1}/3 重试...')
                        response = _call_minimax(prompt, model=MINIMAX_MODEL, temperature=0.1, max_tokens=16000)
                        if not response:
                            break
                    else:
                        raise
            domestic = result.get('domestic_top6', result.get('domestic_top10', []))
            overseas = result.get('overseas_top6', result.get('overseas_top10', []))
            if not domestic:
                domestic = result.get('国内', [])
            if not overseas:
                overseas = result.get('国外', [])
            print(f'   [ok] 国内 {len(domestic)} 条 | 国外 {len(overseas)} 条')
            return {'domestic_top6': domestic, 'overseas_top6': overseas, 'raw_remaining': len(items)}
        except Exception as e:
            if call_att < 2:
                print(f'   [warn] 调用异常，{call_att+1}/3 重试: {e}')
                continue
            print(f'   [error] LLM最终失败: {e}')
            return {'domestic_top6': [], 'overseas_top6': [], 'raw_remaining': len(items)}
    return {'domestic_top6': [], 'overseas_top6': [], 'raw_remaining': len(items)}

# ========== Step 4: LLM 洞察 ==========
def _insight(domestic, international):
    def top(items, n=6):
        order = {'S': 0, 'A': 1, 'B': 2}
        return sorted(items, key=lambda x: order.get(x.get('importance', 'B'), 2))[:n]
    dp = top(domestic, 6)
    ip = top(international, 6)
    lines = []
    for d in dp:
        t = d.get('title', '')
        su = d.get('summary', d.get('desc', ''))
        if su:
            lines.append('[国内]' + t + '。' + su[:250])
        else:
            lines.append('[国内]' + t)
    for d in ip:
        t = d.get('title', '')
        su = d.get('summary', d.get('desc', ''))
        if su:
            lines.append('[国外]' + t + '。' + su[:250])
        else:
            lines.append('[国外]' + t)
    if not lines:
        return '本周AI领域继续保持高速发展，更多详情见正文。'
    ctx = '\n'.join(lines)

    header = (
        '你是一位资深的中国AI行业分析师，正在为国内读者撰写本周AI洞察。\n'
        '我会提供给你本周最重要的12条AI资讯（6条国内 + 6条国外），每条资讯包含标题和摘要。\n'
        '请仔细阅读并消化这些资讯，然后起笔写一段有深度、有因果串联的洞察分析，直接输出正文，不要任何标题、前缀或结束语。\n\n'
        '写一段280-320字的洞察分析。直接输出正文，不要任何标题、前缀或结束语。\n\n'
        '【分段要求】输出必须分成3段，每段之间用空行分隔：\n'
        '  - 第1段：【核心事件】点名1-2个本周最重要的具体事件，带上公司名、技术名或产品名\n'
        '  - 第2段：【趋势观察】提炼1-2个跨公司的行业趋势或信号\n'
        '  - 第3段：【深层思考】分析原因、预测影响、指出风险或机会\n\n'
        '在撰写时，请严格遵循以下三个维度：\n\n'
        '【核心事件】点名2-3个本周最重要的具体事件，必须带上具体的公司名、技术名或产品名。\n'
        '不要只停留在"大模型竞争加剧"这种抽象描述。\n\n'
        '【趋势观察】从事件中提炼出1-2个跨公司的、值得关注的行业趋势或信号。\n\n'
        '【深层思考】分析事件背后的原因，预测可能的影响，或指出隐藏的风险和机会。\n\n'
        '写作风格：像资深分析师和朋友聊天一样，自然平实，不写八股文。\n'
        '要有因果串联，不能是新闻的机械拼接。\n'
        '字数严格控制在280-320字之间，务必精简。段落之间必须用空行分隔。\n\n'
        '以下是本周精选资讯：\n'
    ) + ctx

    for attempt in range(3):
        try:
            r = _call_minimax(header, model='MiniMax-M2.5', temperature=0.3, max_tokens=750)
            if r and r.strip():
                result = r.strip()
                print(f"   [insight] 尝试{attempt+1}输出 {len(result)} 字")
                if len(result) >= 280:
                    return result
                if attempt == 2:
                    return result
        except Exception as e:
            print(f"   [insight] 调用失败: {e}")
            break
    return '本周AI领域继续保持高速发展，更多详情见正文。'

# ========== 辅助函数 ==========
def _get_title_unsafe(x):
    if isinstance(x, dict):
        return x.get('title', '') or ''
    return getattr(x, 'title', '') or ''

def _get_link_unsafe(x):
    if isinstance(x, dict):
        return x.get('link', '') or ''
    return getattr(x, 'link', '') or ''

def _fuzzy_match_links(llm_items, original_items, threshold=0.3):
    import difflib
    result = []
    for litem in llm_items:
        lt = _get_title_unsafe(litem).lower()
        best_sim, best_link = 0, ''
        for oit in original_items:
            ot = _get_title_unsafe(oit).lower()
            sim = difflib.SequenceMatcher(None, lt, ot).ratio()
            if sim > best_sim:
                best_sim = sim
                best_link = _get_link_unsafe(oit)
        item = dict(litem)
        item['link'] = best_link if best_sim >= threshold else ''
        result.append(item)
    return result

# ========== 生成 HTML ==========
def generate_html(domestic, intl, ws, we, hot, insight, github_img_url=None, hf_img_url=None):
    s = []
    if hot:
        s.append('<h2 style="color:#ff4d4f;font-weight:bold;font-size:20px;margin:20px 0 10px;">🔥 本周热点</h2>')
        s.append('<ul style="background:#fff5f5;padding:8px 20px;border-radius:8px;list-style:none;">')
        for t in hot:
            s.append('<li style="font-size:15px;margin-bottom:5px;">• ' + t + '</li>')
        s.append('</ul>')
    # 改动2：插入 GitHub + HuggingFace 趋势图
    if github_img_url:
        s.append('<h2 style="color:#000;font-weight:bold;font-size:19px;margin:20px 0 10px;">🔥 GitHub AI项目趋势榜</h2>')
        s.append(f'<img src="{github_img_url}" style="width:100%;max-width:1400px;display:block;margin:10px 0;" />')
    if hf_img_url:
        s.append('<h2 style="color:#000;font-weight:bold;font-size:19px;margin:20px 0 10px;">🔥 HuggingFace 模型热度榜</h2>')
        s.append(f'<img src="{hf_img_url}" style="width:100%;max-width:1400px;display:block;margin:10px 0;" />')
    
    def emit(items, label, emoji):
        if not items:
            return
        s.append(f'<h2 style="color:#000;font-weight:bold;font-size:19px;margin:20px 0 10px;">{emoji} {label}</h2>')
        for item in items:
            ti = item.get('title', '')
            su = item.get('summary', item.get('desc', ''))
            sc = item.get('source', '')
            da = item.get('date', item.get('time_ago', ''))
            url = item.get('link', '')
            s.append(f'<h3 style="color:#1890ff;font-weight:bold;font-size:17px;margin-top:15px;margin-bottom:5px;">{ti}</h3>')
            if su:
                s.append(f'<p style="color:#666;font-size:15px;margin-bottom:5px;">{su}</p>')
            if da:
                s.append(f'<p style="color:#666;font-size:13px;margin-top:0;">日期：{da}</p>')
            if sc:
                s.append(f'<p style="color:#666;font-size:13px;margin-top:0;">来源：{sc}</p>')
            if url:
                s.append(f'<p style="color:#666;font-size:13px;margin-top:0;">原文链接：<a href="{url}" target="_blank" style="color:#1890ff;text-decoration:underline;">{url}</a></p>')
    
    emit(domestic, '国内AI资讯', '🏷️')
    emit(intl, '国外AI资讯', '🌍')
    if insight:
        s.append('<h2 style="color:#000;font-weight:bold;font-size:19px;margin:20px 0 10px;">💡 本周洞察</h2>')
        s.append('<div style="background:#f6ffed;padding:15px;border-radius:8px;line-height:1.8;font-size:15px;">')
        s.append(f'<p>{insight}</p></div>')
    
    srcs = sorted(set(item.get('source', '') for item in domestic + intl if item.get('source', ''))) or ['虎嗅', 'InfoQ', '量子位']
    s.append(f'<p style="color:#999;margin-top:30px;text-align:center;font-size:13px;"><em>来源：{"、".join(srcs)} | 整理：Valkyrie</em><br>本文部分内容由AI整理生成</p>')
    return '<!DOCTYPE html><html><body><div style="font-family:-apple-system,BlinkMacSystemFont,Roboto,sans-serif;padding:0 10px;">' + '\n'.join(s) + '</div></body></html>'

# ========== 生成 Markdown ==========
def generate_md(domestic, intl, ws, we, hot, insight):
    today = datetime.now().strftime('%Y年%m月%d日')
    lines = ['# AI 资讯周报', f'**{ws} - {we}** | 整理：Valkyrie', '']
    if hot:
        lines.extend(['## 🔥 本周热点', ''] + ['- ' + t for t in hot] + [''])
    
    def emit(items, label, emoji):
        if not items:
            return
        lines.extend([f'## {emoji} {label}（共 {len(items)} 条）', ''])
        for i, item in enumerate(items, 1):
            ti = item.get('title', '')
            su = item.get('summary', item.get('desc', ''))
            sc = item.get('source', '')
            da = item.get('date', item.get('time_ago', ''))
            im = item.get('importance', '')
            tg = item.get('tags', [])
            lines.append(f'**{i}. {ti}**')
            if su:
                lines.append('   ' + su)
            meta = []
            if sc:
                meta.append('来源：' + sc)
            if da:
                meta.append(da)
            if im:
                meta.append(im + '级')
            if tg:
                meta.append('、'.join(tg))
            if meta:
                lines.append('   *' + ' | '.join(meta) + '*')
            lines.append('')
    
    emit(domestic, '国内AI资讯', '🏷️')
    emit(intl, '国外AI资讯', '🌍')
    if insight:
        lines.extend(['## 💡 本周洞察', '', '_' + insight + '_', ''])
    lines.extend(['', '---', f'*生成时间：{today}*'])
    return '\n'.join(lines)

# ========== 获取 GitHub/HuggingFace 数据并生成图片 ==========
def fetch_github_and_hf_data():
    """实时从 API 获取 GitHub 和 HuggingFace 数据，返回 items 和图片路径"""
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path.home() / ".openclaw" / "workspace" / "skills" / "table-image-generator"))
    
    github_items = []
    hf_items = []
    github_img_path = None
    hf_img_path = None
    
    # 获取 GitHub 数据
    try:
        from sources import get_source
        github_src = get_source('github')
        if github_src:
            # 正确方法：collect() 不是 fetch()
            raw = github_src.collect()
            github_items = [item for item in raw if hasattr(item, 'source') and item.source == 'github']
            print(f'   GitHub 获取到 {len(github_items)} 条')
    except Exception as e:
        print(f'   GitHub 获取失败: {e}')
    
    # 获取 HuggingFace 数据
    try:
        from sources import get_source
        hf_src = get_source('huggingface')
        if hf_src:
            # 正确方法：collect() 不是 fetch()
            raw = hf_src.collect()
            hf_items = [item for item in raw if hasattr(item, 'source') and item.source == 'huggingface']
            print(f'   HuggingFace 获取到 {len(hf_items)} 条')
    except Exception as e:
        print(f'   HuggingFace 获取失败: {e}')
    
    return github_items, hf_items

def generate_github_table(github_items, output_dir):
    """生成 GitHub 趋势图"""
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from main import generate_github_html_table
        if github_items:
            img_path = generate_github_html_table(github_items, output_dir)
            return img_path
    except Exception as e:
        print(f'   GitHub 图片生成失败: {e}')
    return None

def generate_hf_table(hf_items, output_dir):
    """生成 HuggingFace 热度榜图片"""
    try:
        from table_image import generate_table
        if not hf_items:
            return None
        
        type_map = {
            'text-generation': '文本生成', 'text2text-generation': '文本转换',
            'image-text-to-text': '图文理解', 'visual-question-answering': '视觉问答',
            'automatic-speech-recognition': '语音识别', 'text-to-speech': '语音合成',
            'text-to-image': '文生图', 'image-classification': '图像分类',
            'object-detection': '目标检测', 'feature-extraction': '特征提取',
            'sentence-similarity': '句子相似度',
        }
        header = ['模型', '下载量', '点赞数', '类型', '更新时间']
        rows = []
        for i, item in enumerate(hf_items[:10], 1):
            extra = getattr(item, 'extra', {}) or {}
            downloads = extra.get('downloads', 0)
            likes = extra.get('likes', 0)
            downloads_str = f'{downloads/1000:.1f}K' if downloads >= 1000 else str(downloads)
            likes_str = f'{likes/1000:.1f}K' if likes >= 1000 else str(likes)
            pipeline = extra.get('pipeline_tag', '-')
            type_cn = type_map.get(pipeline, pipeline)
            last_modified = extra.get('last_modified', '-')
            rows.append([getattr(item, 'title', '') or '', downloads_str, likes_str, type_cn, last_modified])
        
        hf_img_path = str(output_dir / 'huggingface_trending.png')
        result = generate_table(
            data=[header] + rows,
            title='Hugging Face模型热度榜单',
            width=1080, font_size=16, header_color='#1E40AF',
            col_widths=[4, 1.5, 1.5, 1.5, 1.5], padding=15, output_path=hf_img_path
        )
        if result.get('success'):
            print(f'   HuggingFace 热度榜: ✅')
            return hf_img_path
    except Exception as e:
        print(f'   HuggingFace 图片生成失败: {e}')
    return None

def upload_img_to_wechat(img_path, name):
    """上传图片到微信获取永久 URL"""
    try:
        import requests
        token_resp = requests.get(
            f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=wxdef888862e3ecca1&secret=1483a2e68153e9cf6a5f1580e223e660",
            timeout=10
        ).json()
        token = token_resp.get("access_token")
        if not token:
            return None
        with open(img_path, 'rb') as f:
            files = {'media': (f'{name}.png', f, 'image/png')}
            r = requests.post(f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image", files=files, timeout=30).json()
        return r.get("url", "")
    except Exception as e:
        print(f'   {name} 图片上传失败: {e}')
        return None

# ========== Main ==========
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--wechat', nargs='?', const='__all__', default=None,
                        help='上传到微信公众号草稿箱。可指定账号名（逗号分隔），不指定则上传到所有已配置账号')
    ap.add_argument('--no-filter-no-link', action='store_true', help='不过滤无链接的数据（默认会过滤）')
    args = ap.parse_args()
    
    today = datetime.now().date()
    week_end = today.strftime('%Y年%m月%d日')
    week_start = (today - timedelta(days=args.days-1)).strftime('%Y年%m月%d日')
    
    print('=' * 60)
    print('  [v3] AI资讯周报生成器')
    print(f'  周期：{week_start} - {week_end}')
    print('=' * 60)
    
    # Step 1: 加载日报数据
    print('\n[1/7] 加载日报...')
    all_items, loaded = load_week_data(days=args.days)
    print(f'   日期: {", ".join(loaded) if loaded else "无"}')
    print(f'   合并去重: {len(all_items)} 条')
    if not all_items:
        print('[error] 无数据')
        sys.exit(1)
    
    # 改动1：过滤无链接数据（可配置开关）
    filter_no_link = DEFAULT_CONFIG.get('filter_no_link', True)
    if args.no_filter_no_link:
        filter_no_link = False
    if filter_no_link:
        before_filter = len(all_items)
        all_items = [it for it in all_items if (it.link or '').strip()]
        filtered = before_filter - len(all_items)
        print(f'   [filter] 无链接移除 {filtered} 条（剩 {len(all_items)} 条）')
    else:
        print(f'   [filter] 无链接过滤已关闭，保留 {len(all_items)} 条')
    
    # 过滤短内容
    all_items = [it for it in all_items if len((it.summary or it.desc or '').strip()) >= 10]
    if not all_items:
        print('[error] 过滤后无数据')
        sys.exit(1)
    
    # Step 2: 收集 GitHub + HuggingFace 数据（改动2）
    print('\n[2/7] 收集 GitHub + HuggingFace 数据...')
    github_items, hf_items = fetch_github_and_hf_data()
    
    github_img_path = None
    hf_img_path = None
    
    if github_items:
        print('   生成 GitHub 趋势图...')
        github_img_path = generate_github_table(github_items, OUTPUT_DIR)
        print(f'   GitHub 趋势图: {"✅" if github_img_path else "❌"}')
    
    if hf_items:
        print('   生成 HuggingFace 热度榜...')
        hf_img_path = generate_hf_table(hf_items, OUTPUT_DIR)
    
    # Step 3: BGE 去重
    print('\n[3/7] BGE去重...')
    all_items = run_bge_dedup(all_items)
    print(f'   剩余: {len(all_items)} 条')
    
    # Step 4: LLM 精选
    print('\n[4/7] LLM精选...')
    llm = call_llm_classify_and_filter(all_items, week_start, week_end)
    domestic, international = llm.get('domestic_top6', []), llm.get('overseas_top6', [])
    if not domestic and not international:
        print('[error] LLM无输出')
        sys.exit(1)
    
    # 通过标题相似度恢复原文链接
    domestic = _fuzzy_match_links(domestic, all_items, threshold=0.3)
    international = _fuzzy_match_links(international, all_items, threshold=0.3)
    
    # Step 5: 热点
    print('\n[5/7] 热点...')
    hot_all = sorted(domestic + international, key=lambda x: {'S':0,'A':1,'B':2}.get(x.get('importance','B'), 2))[:6]
    hot = [it.get('title', '') for it in hot_all]
    print(f'   {str(hot[:3])}...')
    
    # Step 6: 洞察
    print('\n[6/7] 洞察...')
    insight = _insight(domestic, international)
    print(f'   {insight[:50]}...')
    
    # Step 7: 生成周报
    print('\n[7/7] 生成周报...')
    md = generate_md(domestic, international, week_start, week_end, hot, insight)
    
    if args.dry_run:
        for line in md.split('\n')[:80]:
            print(line)
        print('\n[ok] dry-run完成')
        return
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ds = today.strftime('%Y%m%d')
    
    # 上传图片到微信获取永久URL
    github_img_url = None
    hf_img_url = None
    if args.wechat is not None:
        if github_img_path and Path(github_img_path).exists():
            github_img_url = upload_img_to_wechat(github_img_path, 'github')
            print(f'   GitHub图片: {"✅" if github_img_url else "❌"}')
        if hf_img_path and Path(hf_img_path).exists():
            hf_img_url = upload_img_to_wechat(hf_img_path, 'hf')
            print(f'   HF图片: {"✅" if hf_img_url else "❌"}')
    
    mf = OUTPUT_DIR / ('weekly_report_' + ds + '.md')
    mf.write_text(md, encoding='utf-8')
    print(f'   保存: {mf.name}')
    
    jf = OUTPUT_DIR / ('weekly_llm_output_' + ds + '.json')
    jf.write_text(json.dumps({
        'period': week_start + ' - ' + week_end,
        'generated_at': datetime.now().isoformat(),
        'domestic_count': len(domestic),
        'international_count': len(international),
        'domestic': domestic,
        'international': international
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'   保存: {jf.name}')
    
    if args.wechat is not None:
        import subprocess
        html = generate_html(domestic, international, week_start, week_end, hot, insight, github_img_url, hf_img_url)
        hf = OUTPUT_DIR / ('weekly_report_' + ds + '.html')
        hf.write_text(html, encoding='utf-8')
        title = 'AI资讯周报 | ' + week_start + ' - ' + week_end

        # 构建 publish_weekly_wechat.py 的调用参数
        cmd = [sys.executable, str(SCRIPTS_DIR / 'publish_weekly_wechat.py'), str(hf), title]
        if insight:
            cmd.extend(['--digest', insight])

        # 账号参数
        if args.wechat != '__all__':
            # 指定了具体账号
            accounts = [a.strip() for a in args.wechat.split(',')]
            for acct in accounts:
                cmd.extend(['--account', acct])

        print(f'   执行: {" ".join(cmd[:4])} ...')
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(r.stdout.strip())
        if r.returncode != 0:
            print(f'   [error] {r.stderr[:200]}')

    print('\n[ok] 完成')

if __name__ == '__main__':
    main()