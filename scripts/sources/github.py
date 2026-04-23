"""
GitHub Trending 数据源 - 基于 OSSInsight API
使用 ossinsight-github skill 的核心逻辑
"""
import json
import os
import subprocess
from typing import List

from .base import NewsSource, NewsItem, register_source


# OSSInsight-github skill 路径
SKILL_SCRIPT = os.path.expanduser(
    "~/.openclaw/workspace/skills/ossinsight-github/scripts/fetch_github.py"
)


@register_source
class GithubSource(NewsSource):
    """GitHub Trending 仓库数据源（基于 OSSInsight API）"""

    name = "github"
    url = "https://github.com/trending"

    def collect(self) -> List[NewsItem]:
        """通过 OSSInsight API 获取 GitHub AI 趋势项目"""
        try:
            # 调用 ossinsight-github skill 的脚本
            result = subprocess.run(
                ["python3", SKILL_SCRIPT, "--max", "15", "--output", "/tmp/github_ai_fetch.json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # 读取输出文件
            with open("/tmp/github_ai_fetch.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            self.news_list = self.parse(data)
            print(f"   📰 {self.name}: 获取到 {len(self.news_list)} 条")

        except Exception as e:
            print(f"   ❌ {self.name} 获取失败: {e}")

        return self.news_list

    def parse(self, data: list) -> List[NewsItem]:
        """解析 OSSInsight 返回的数据，转换为 NewsItem 格式"""
        news_list = []

        for item in data:
            repo_name = item.get("repo_name", "")
            description = item.get("description", "") or "无描述"

            # 额外信息（用于生成表格）
            extra = {
                "stars": item.get("stars", 0),
                "forks": item.get("forks", 0),
                "total_score": item.get("total_score", 0),
                "language": item.get("primary_language", ""),
                "description": description,
            }

            news = NewsItem(
                title=repo_name,
                desc=description,
                source=self.name,
                link=item.get("url", ""),
                time_ago="过去一周",
                extra=extra,
            )
            news_list.append(news)

        return news_list