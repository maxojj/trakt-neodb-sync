#!/usr/bin/env python3
"""Trakt to NeoDB 同步脚本。

从 Trakt 拉取观影历史（电影和剧集），同步到 NeoDB 标记为"看过"。
通过 last_sync 时间戳实现增量同步，避免重复。
"""

import os
import sys
import datetime
from pathlib import Path

import requests

# ── 配置（从环境变量读取）──
TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID", "")
TRAKT_ACCESS_TOKEN = os.environ.get("TRAKT_ACCESS_TOKEN", "")
NEODB_ACCESS_TOKEN = os.environ.get("NEODB_ACCESS_TOKEN", "")
TRAKT_USERNAME = os.environ.get("TRAKT_USERNAME", "")

# ── API 端点 ──
TRAKT_API_BASE = "https://api.trakt.tv"
NEODB_API_BASE = "https://neodb.social/api"

# ── last_sync 时间戳文件 ──
LAST_SYNC_FILE = Path(__file__).parent / ".last_sync"


def log(msg: str) -> None:
    """打印带时间戳的日志。"""
    ts = datetime.datetime.now().isoformat()
    print(f"[{ts}] {msg}")


# ── Trakt API ──

def trakt_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
        "Authorization": f"Bearer {TRAKT_ACCESS_TOKEN}",
    }


def fetch_trakt_history(history_type: str, start_at: str | None = None) -> list:
    """从 Trakt 拉取观影历史。

    Args:
        history_type: 'movies' 或 'shows'
        start_at: ISO 时间戳，仅拉取此时间之后的记录

    Returns:
        历史记录列表
    """
    url = f"{TRAKT_API_BASE}/users/{TRAKT_USERNAME}/history/{history_type}"
    params = {"limit": 100}
    if start_at:
        params["start_at"] = start_at

    all_entries: list = []
    page = 1

    while True:
        params["page"] = page
        log(f"  Trakt {history_type} 历史 — 第 {page} 页")
        resp = requests.get(url, headers=trakt_headers(), params=params, timeout=30)
        resp.raise_for_status()
        entries = resp.json()

        if not entries:
            break
        all_entries.extend(entries)

        total_pages = int(resp.headers.get("X-Pagination-Page-Count", "1"))
        if page >= total_pages or len(entries) < 100:
            break
        page += 1

    return all_entries


# ── NeoDB API ──

def neodb_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NEODB_ACCESS_TOKEN}",
    }


def search_neodb(title: str, category: str) -> str | None:
    """在 NeoDB 搜索条目，返回首个匹配的 UUID。"""
    url = f"{NEODB_API_BASE}/catalog/search"
    params = {"query": title, "category": category}
    resp = requests.get(url, headers=neodb_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 兼容 list / dict 两种返回格式
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("data", [])
    else:
        results = []

    if results:
        item = results[0]
        return item.get("uuid") or item.get("item_uuid") or item.get("id")
    return None


def mark_neodb_watched(item_uuid: str, watched_at: str) -> bool:
    """在 NeoDB 标记条目为"看过"。"""
    url = f"{NEODB_API_BASE}/me/shelf/complete"
    body = {
        "item_uuid": item_uuid,
        "rating_grade": None,
        "text": "",
        "created_time": watched_at,
    }
    resp = requests.post(url, headers=neodb_headers(), json=body, timeout=30)

    if resp.status_code in (200, 201):
        return True
    if resp.status_code == 409:
        log("  已标记过，跳过")
        return True
    log(f"  标记失败: HTTP {resp.status_code} — {resp.text[:200]}")
    return False


# ── 同步逻辑 ──

def sync_movies(entries: list) -> tuple[int, int, int]:
    """同步电影记录到 NeoDB。"""
    success = failed = skipped = 0

    for entry in entries:
        movie = entry.get("movie", {})
        title = movie.get("title", "")
        watched_at = entry.get("watched_at", "")

        if not title:
            skipped += 1
            continue

        log(f"电影: {title} (观看于 {watched_at})")
        try:
            uuid = search_neodb(title, "movie")
            if not uuid:
                log("  NeoDB 未找到，跳过")
                failed += 1
                continue
            if mark_neodb_watched(uuid, watched_at):
                success += 1
            else:
                failed += 1
        except Exception as e:
            log(f"  异常: {e}")
            failed += 1

    return success, failed, skipped


def sync_shows(entries: list) -> tuple[int, int, int]:
    """同步剧集记录到 NeoDB（按剧名去重）。"""
    success = failed = skipped = 0
    seen: set[str] = set()

    for entry in entries:
        show = entry.get("show", {})
        title = show.get("title", "")
        watched_at = entry.get("watched_at", "")

        if not title:
            skipped += 1
            continue
        if title in seen:
            skipped += 1
            continue

        seen.add(title)
        log(f"剧集: {title} (观看于 {watched_at})")
        try:
            uuid = search_neodb(title, "tv")
            if not uuid:
                log("  NeoDB 未找到，跳过")
                failed += 1
                continue
            if mark_neodb_watched(uuid, watched_at):
                success += 1
            else:
                failed += 1
        except Exception as e:
            log(f"  异常: {e}")
            failed += 1

    return success, failed, skipped


# ── last_sync 管理 ──

def get_last_sync() -> str | None:
    """读取上次同步时间戳。"""
    if LAST_SYNC_FILE.exists():
        ts = LAST_SYNC_FILE.read_text().strip()
        if ts:
            log(f"上次同步时间: {ts}")
            return ts
    log("未找到上次同步记录，将同步全部历史")
    return None


def save_last_sync(timestamp: str) -> None:
    """保存同步时间戳。"""
    LAST_SYNC_FILE.write_text(timestamp)
    log(f"已保存同步时间: {timestamp}")


# ── 主流程 ──

def main() -> None:
    # 校验环境变量
    required = {
        "TRAKT_CLIENT_ID": TRAKT_CLIENT_ID,
        "TRAKT_ACCESS_TOKEN": TRAKT_ACCESS_TOKEN,
        "NEODB_ACCESS_TOKEN": NEODB_ACCESS_TOKEN,
        "TRAKT_USERNAME": TRAKT_USERNAME,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log(f"错误: 缺少环境变量: {', '.join(missing)}")
        sys.exit(1)

    log("=== Trakt → NeoDB 同步开始 ===")

    last_sync = get_last_sync()
    sync_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 电影
    log("--- 电影 ---")
    try:
        movie_entries = fetch_trakt_history("movies", start_at=last_sync)
    except Exception as e:
        log(f"获取电影历史失败: {e}")
        movie_entries = []
    m_ok, m_fail, m_skip = sync_movies(movie_entries)
    log(f"电影完成: 成功 {m_ok}, 失败 {m_fail}, 跳过 {m_skip}")

    # 剧集
    log("--- 剧集 ---")
    try:
        show_entries = fetch_trakt_history("shows", start_at=last_sync)
    except Exception as e:
        log(f"获取剧集历史失败: {e}")
        show_entries = []
    s_ok, s_fail, s_skip = sync_shows(show_entries)
    log(f"剧集完成: 成功 {s_ok}, 失败 {s_fail}, 跳过 {s_skip}")

    save_last_sync(sync_start)

    total_ok = m_ok + s_ok
    total_fail = m_fail + s_fail
    total_skip = m_skip + s_skip
    log(f"=== 同步完成: 成功 {total_ok}, 失败 {total_fail}, 跳过 {total_skip} ===")


if __name__ == "__main__":
    main()
