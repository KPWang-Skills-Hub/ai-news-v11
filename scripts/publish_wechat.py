#!/usr/bin/env python3
"""
微信公众号上传脚本
接收周报 HTML 内容，上传到草稿箱
"""
import sys
import json
import requests
from pathlib import Path
from datetime import datetime


APP_ID = "wxdef888862e3ecca1"
APP_SECRET = "1483a2e68153e9cf6a5f1580e223e660"
COVER_PATH = Path.home() / ".openclaw/workspace/ai-news/cover.jpg"


def upload_to_wechat_draft(html_content: str, title: str, digest: str = None) -> bool:
    """
    上传 HTML 到微信公众号草稿箱。
    返回 True/False。
    """
    # 1. 获取 access_token
    resp = requests.get(
        f"https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}",
        timeout=10
    ).json()
    token = resp.get("access_token")
    if not token:
        print(f"❌ 获取 access_token 失败: {resp}")
        return False
    print(f"✅ access_token 获取成功")

    # 2. 上传封面
    thumb_media_id = None
    if COVER_PATH.exists():
        with open(COVER_PATH, "rb") as f:
            files = {"media": ("cover.jpg", f, "image/jpeg")}
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
            r = requests.post(url, files=files, timeout=30).json()
        thumb_media_id = r.get("media_id")
        if thumb_media_id:
            print(f"✅ 封面上传成功: {thumb_media_id}")
        else:
            print(f"⚠️ 封面上传失败（将使用默认封面）: {r}")
    else:
        print(f"⚠️ 封面文件不存在: {COVER_PATH}")

    # 3. 构造草稿
    if digest is None:
        digest = "国内+国外AI本周热点资讯精选，附深度洞察 | 整理：Valkyrie"

    draft = {
        "articles": [{
            "title": title,
            "author": "Valkyrie",
            "digest": digest[:120] if digest else "",
            "content": html_content,
            "thumb_media_id": thumb_media_id,
        }]
    }

    # 4. 提交草稿
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    resp = requests.post(
        url,
        data=json.dumps(draft, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30
    )
    result = resp.json()

    if "media_id" in result:
        print(f"✅ 已上传到公众号草稿箱")
        print(f"   media_id: {result['media_id']}")

        # 缓存 HTML
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        for path in [
            output_dir / f"wechat_draft_{date_str}.html",
            Path.home() / ".openclaw/workspace/ai-news" / f"wechat_draft_{date_str}.html",
        ]:
            path.write_text(html_content, encoding="utf-8")
            print(f"   💾 HTML已缓存: {path}")
        return True
    else:
        print(f"❌ 上传失败: {result}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 publish_wechat.py <html_file> <title>")
        sys.exit(1)

    html_path = Path(sys.argv[1])
    title = sys.argv[2]
    digest = sys.argv[3] if len(sys.argv) > 3 else None

    if not html_path.exists():
        print(f"❌ HTML文件不存在: {html_path}")
        sys.exit(1)

    html_content = html_path.read_text(encoding="utf-8")
    ok = upload_to_wechat_draft(html_content, title, digest)
    sys.exit(0 if ok else 1)
