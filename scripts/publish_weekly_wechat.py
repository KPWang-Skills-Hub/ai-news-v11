#!/usr/bin/env python3
"""
微信公众号周报上传脚本 - 多账号版
- 支持上传到多个微信公众号草稿箱
- 每个账号独立管理 token、封面 media_id
"""
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

# ========== 账号配置 ==========
# 每个账号的凭证和封面可独立配置
# 封面图可以是同一张（会各自上传获取各自的 media_id）
DEFAULT_COVER = Path.home() / ".openclaw/workspace/ai-news/weekly_cover.jpg"

ACCOUNTS = {
    "main": {
        "app_id": "wxdef888862e3ecca1",
        "app_secret": "1483a2e68153e9cf6a5f1580e223e660",
    },
    "tao": {
        "app_id": "wxa0284492b951e1ae",
        "app_secret": "ea9f397f58bfc2737b6491a776346c7e",
    },
}

# 兼容旧版单账号用法：如果没配置任何账号，使用内置的硬编码凭证
FALLBACK_APP_ID = "wxdef888862e3ecca1"
FALLBACK_APP_SECRET = "1483a2e68153e9cf6a5f1580e223e660"


def get_config_dir(account_name):
    """获取账号配置目录"""
    base = Path.home() / ".openclaw/workspace/ai-news/accounts" / account_name
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_access_token(account_cfg):
    """获取指定账号的 access_token"""
    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={account_cfg['app_id']}&secret={account_cfg['app_secret']}",
        timeout=10
    ).json()
    token = resp.get("access_token")
    if not token:
        print(f"   ❌ [{account_cfg['_name']}] 获取 access_token 失败: {resp}")
        return None
    print(f"   ✅ [{account_cfg['_name']}] access_token 获取成功")
    return token


def load_saved_media_id(account_cfg):
    """从账号独立配置文件读取已保存的 media_id"""
    cfg_dir = get_config_dir(account_cfg['_name'])
    media_id_path = cfg_dir / "thumb_media_id.json"
    if media_id_path.exists():
        try:
            data = json.loads(media_id_path.read_text(encoding="utf-8"))
            media_id = data.get("media_id")
            if media_id:
                print(f"   💾 [{account_cfg['_name']}] 使用已保存的封面 media_id: {media_id}")
                return media_id
        except Exception:
            pass
    return None


def upload_cover_and_save(token, account_cfg):
    """上传封面图，获取 media_id 并保存到账号独立配置文件"""
    cover_path = Path(account_cfg.get("cover_path", str(DEFAULT_COVER)))
    if not cover_path.exists():
        print(f"   ⚠️ [{account_cfg['_name']}] 封面文件不存在: {cover_path}")
        return None

    with open(cover_path, "rb") as f:
        files = {"media": (cover_path.name, f, "image/jpeg")}
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
        r = requests.post(url, files=files, timeout=30).json()

    media_id = r.get("media_id")
    if not media_id:
        print(f"   ❌ [{account_cfg['_name']}] 封面上传失败: {r}")
        return None

    print(f"   ✅ [{account_cfg['_name']}] 封面上传成功: {media_id}")

    cfg_dir = get_config_dir(account_cfg['_name'])
    media_id_path = cfg_dir / "thumb_media_id.json"
    config = {
        "media_id": media_id,
        "cover_path": str(cover_path),
        "updated_at": datetime.now().isoformat()
    }
    media_id_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ [{account_cfg['_name']}] media_id 已保存到: {media_id_path}")
    return media_id


def get_thumb_media_id(token, account_cfg):
    """
    获取周报封面 thumb_media_id（账号级别独立管理）：
    1. 优先使用已保存的 media_id
    2. 没有则上传并保存
    3. 上传失败返回 None（使用微信默认封面）
    """
    saved_id = load_saved_media_id(account_cfg)
    if saved_id:
        return saved_id

    print(f"   📤 [{account_cfg['_name']}] 首次使用，正在上传周报封面...")
    return upload_cover_and_save(token, account_cfg)


def upload_to_single_account(html_content: str, title: str, digest: str, account_name: str, account_cfg: dict) -> bool:
    """
    上传周报 HTML 到单个微信公众号草稿箱。
    """
    print(f"\n{'='*50}")
    print(f"  [{account_name}] 开始上传")
    print(f"{'='*50}")

    token = get_access_token(account_cfg)
    if not token:
        return False

    thumb_media_id = get_thumb_media_id(token, account_cfg)
    if not thumb_media_id:
        print(f"   ⚠️ [{account_cfg['_name']}] 封面获取失败，将使用默认封面")

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

    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    resp = requests.post(
        url,
        data=json.dumps(draft, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30
    )
    result = resp.json()

    if "media_id" in result:
        print(f"   ✅ [{account_cfg['_name']}] 周报已上传到草稿箱")
        print(f"      media_id: {result['media_id']}")
        return True
    else:
        print(f"   ❌ [{account_cfg['_name']}] 周报上传失败: {result}")
        return False


def upload_to_accounts(html_content: str, title: str, digest: str = None,
                        target_accounts: list = None) -> dict:
    """
    上传周报 HTML 到指定的一个或多个微信公众号草稿箱。

    Args:
        html_content: HTML 内容
        title: 文章标题
        digest: 摘要（可选）
        target_accounts: 目标账号列表，如 ["aiweekly", "aitongzhi"]
                        为 None 时上传到所有已配置的账号

    Returns:
        dict: {account_name: success_bool}
    """
    results = {}

    # 确定要上传的账号
    if not ACCOUNTS:
        # 没有任何账号配置时，使用兼容模式（单账号）
        print("⚠️ 未配置多账号，使用兼容模式（单账号）")
        account_cfg = {
            "_name": "default",
            "app_id": FALLBACK_APP_ID,
            "app_secret": FALLBACK_APP_SECRET,
            "cover_path": str(DEFAULT_COVER),
        }
        results["default"] = upload_to_single_account(html_content, title, digest, "default", account_cfg)
        return results

    accounts_to_upload = []
    if target_accounts:
        # 只上传指定账号
        for name in target_accounts:
            if name in ACCOUNTS:
                accounts_to_upload.append((name, ACCOUNTS[name]))
            else:
                print(f"   ⚠️ 账号 '{name}' 不在配置中，已跳过")
    else:
        # 上传到所有账号
        accounts_to_upload = list(ACCOUNTS.items())

    if not accounts_to_upload:
        print("❌ 没有可上传的账号")
        return results

    # HTML 只需生成一次（写到缓存）
    cache_dir = Path.home() / ".openclaw/workspace/ai-news"
    cache_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    cache_path = cache_dir / f"weekly_draft_{date_str}.html"
    cache_path.write_text(html_content, encoding="utf-8")
    print(f"💾 HTML已缓存: {cache_path}")

    # 依次上传到各账号
    for account_name, cfg in accounts_to_upload:
        # 注入 _name 方便打印
        cfg = dict(cfg)
        cfg["_name"] = account_name
        results[account_name] = upload_to_single_account(html_content, title, digest, account_name, cfg)

    return results


# ========== CLI ==========
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="上传周报到微信公众号草稿箱（多账号版）")
    parser.add_argument("html_file", help="HTML 文件路径")
    parser.add_argument("title", help="文章标题")
    parser.add_argument("--digest", help="摘要（可选）")
    parser.add_argument(
        "--account",
        action="append",
        dest="accounts",
        help="指定要上传的账号（可多次使用），不指定则上传到所有账号"
    )
    args = parser.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"❌ HTML文件不存在: {html_path}")
        sys.exit(1)

    html_content = html_path.read_text(encoding="utf-8")

    if not ACCOUNTS:
        print("⚠️ 警告: ACCOUNTS 配置为空，将使用兼容模式（单账号）")

    results = upload_to_accounts(
        html_content,
        args.title,
        args.digest,
        target_accounts=args.accounts if args.accounts else None
    )

    # 打印汇总
    print(f"\n{'='*50}")
    print("  上传结果汇总")
    print(f"{'='*50}")
    for name, ok in results.items():
        status = "✅ 成功" if ok else "❌ 失败"
        print(f"  [{name}] {status}")

    all_ok = all(results.values())
    sys.exit(0 if all_ok else 1)
