"""
douban-neodb-sync: 豆瓣 RSS → NeoDB 自动同步
每次运行只处理上次运行后新增的条目，已同步的条目记录在 synced.json 中。
"""

import os
import json
import time
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# ── 配置 ──────────────────────────────────────────────────────────────────────
DOUBAN_ID = os.environ["DOUBAN_ID"]
NEODB_TOKEN = os.environ["NEODB_TOKEN"]
NEODB_BASE = "https://neodb.social"
SYNCED_FILE = Path("synced.json")

RSS_URL = f"https://www.douban.com/feed/people/{DOUBAN_ID}/interests"

SHELF_TYPE = "complete"

# 豆瓣评分（1-5星）→ NeoDB 评分（0-10）
RATING_MAP = {"1": 2, "2": 4, "3": 6, "4": 8, "5": 10}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; douban-neodb-sync/1.0)",
}

NEODB_HEADERS = {
    "Authorization": f"Bearer {NEODB_TOKEN}",
    "Content-Type": "application/json",
}


def load_synced() -> set:
    if SYNCED_FILE.exists():
        return set(json.loads(SYNCED_FILE.read_text()))
    return set()


def save_synced(synced: set):
    SYNCED_FILE.write_text(json.dumps(sorted(synced), ensure_ascii=False, indent=2))


def fetch_rss() -> list[dict]:
    """拉取豆瓣 RSS，返回条目列表。"""
    resp = requests.get(RSS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.iter("item"):
        # 豆瓣 RSS 的 title 格式是"看过XXX"/"读过XXX"/"听过XXX"
        title_full = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        content = item.findtext("description", "")

        # 通过 title 判断是否为"已完成"标记，跳过"想看/在看"等
        if not any(title_full.startswith(k) for k in ["看过", "读过", "听过", "玩过"]):
            continue

        # 去掉前缀，得到真实标题
        title = title_full
        for prefix in ["看过", "读过", "听过", "玩过"]:
            if title_full.startswith(prefix):
                title = title_full[len(prefix):]
                break

        # 解析评分（推荐: 力荐/推荐/还行/较差/很差）
        rating = None
        rating_match = re.search(r"推荐:\s*(力荐|推荐|还行|较差|很差)", content)
        if rating_match:
            rating_text = rating_match.group(1)
            rating_map_cn = {"力荐": "5", "推荐": "4", "还行": "3", "较差": "2", "很差": "1"}
            rating = RATING_MAP.get(rating_map_cn.get(rating_text, ""), None)

        # 解析短评（备注字段）
        comment = None
        comment_match = re.search(r"备注:\s*(.+?)(?:\s*(?:<|\Z))", content, re.DOTALL)
        if comment_match:
            comment = comment_match.group(1).strip()

        # 豆瓣条目链接直接在 <link> 里
        douban_url = link

        items.append({
            "title": title,
            "douban_url": douban_url,
            "rating": rating,
            "comment": comment,
        })
    return items


def search_neodb(douban_url: str) -> str | None:
    """用豆瓣 URL 在 NeoDB 搜索对应条目，返回 UUID。"""
    resp = requests.get(
        f"{NEODB_BASE}/api/catalog/fetch",
        params={"url": douban_url},
        headers=NEODB_HEADERS,
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("uuid")
    return None


def mark_neodb(uuid: str, rating: int | None, comment: str | None) -> bool:
    """在 NeoDB 标记条目为 complete，附带评分和短评。"""
    payload = {"shelf_type": SHELF_TYPE, "visibility": 0}
    if rating is not None:
        payload["rating_grade"] = rating
    if comment:
        payload["comment_text"] = comment

    resp = requests.post(
        f"{NEODB_BASE}/api/me/shelf/item/{uuid}",
        headers=NEODB_HEADERS,
        json=payload,
        timeout=30,
    )
    return resp.status_code in (200, 201)


def main():
    synced = load_synced()
    items = fetch_rss()
    print(f"RSS 获取到 {len(items)} 条已完成条目")

    new_count = 0
    fail_count = 0

    for item in items:
        key = item["douban_url"]
        if key in synced:
            print(f"  跳过（已同步）: {item['title']}")
            continue

        print(f"  处理: {item['title']} ({key})")
        uuid = search_neodb(key)
        if not uuid:
            print(f"    ⚠️  NeoDB 未找到对应条目，跳过")
            fail_count += 1
            continue

        ok = mark_neodb(uuid, item["rating"], item["comment"])
        if ok:
            print(f"    ✅ 同步成功（评分={item['rating']}, 短评={'有' if item['comment'] else '无'}）")
            synced.add(key)
            new_count += 1
        else:
            print(f"    ❌ 同步失败")
            fail_count += 1

        time.sleep(1)

    save_synced(synced)
    print(f"\n完成：新同步 {new_count} 条，失败/未找到 {fail_count} 条")


if __name__ == "__main__":
    main()
