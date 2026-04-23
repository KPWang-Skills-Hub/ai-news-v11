"""
拦截器日志记录
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List


LOG_DIR = Path(__file__).parent.parent / "output" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file(date_str: str = None) -> Path:
    """获取当天的日志文件"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    return LOG_DIR / f"interceptors_{date_str}.log"


def log_interceptor(name: str, stage: str, data: List, extra: str = ""):
    """记录拦截器输入/输出"""
    log_file = get_log_file()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 提取关键信息（完整记录所有数据）
    data_summary = []
    for item in data:
        title = getattr(item, 'title', str(item))[:50]
        category = getattr(item, 'category', '')
        source = getattr(item, 'source', '')
        data_summary.append(f"  - [{source}][{category}] {title}")
    
    summary = f"{stage}: {len(data)}条"
    if extra:
        summary += f" | {extra}"
    
    log_entry = f"""
[{timestamp}] {name} - {summary}
{"="*60}
{chr(10).join(data_summary)}
"""
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry)


def log_section(title: str):
    """记录分段标题"""
    log_file = get_log_file()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {title}\n")