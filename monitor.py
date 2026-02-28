#!/usr/bin/env python3
"""
GitHub Release & Commit Monitor
Checks target repositories for new releases/commits and sends Discord notifications.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CONFIG_PATH = Path(__file__).parent / "config.json"
STATE_PATH = Path(os.environ.get("STATE_PATH", Path(__file__).parent / "state.json"))

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_repo(entry: str) -> str:
    """Normalize repo entry: accept full URL or owner/repo shorthand."""
    entry = entry.strip().rstrip("/")
    if entry.startswith("https://github.com/"):
        return entry.removeprefix("https://github.com/")
    if entry.startswith("http://github.com/"):
        return entry.removeprefix("http://github.com/")
    return entry


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def github_get(url: str) -> dict | list | None:
    """GET request to GitHub API with error handling."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ⚠ GitHub API 返回 {resp.status_code}: {url}")
    except requests.RequestException as exc:
        print(f"  ⚠ 请求失败: {exc}")
    return None


# ---------------------------------------------------------------------------
# GitHub queries
# ---------------------------------------------------------------------------
def get_latest_release(repo: str) -> dict | None:
    """Return latest release info or None."""
    data = github_get(f"{GITHUB_API}/repos/{repo}/releases/latest")
    if data and "tag_name" in data:
        return {
            "tag": data["tag_name"],
            "name": data.get("name", data["tag_name"]),
            "url": data["html_url"],
            "published_at": data.get("published_at", ""),
            "body": (data.get("body") or "")[:3800],
        }
    return None


def get_latest_commit(repo: str, branch: str = "") -> dict | None:
    """Return latest commit on default branch or None."""
    # If branch unknown, query repo metadata first
    if not branch:
        repo_data = github_get(f"{GITHUB_API}/repos/{repo}")
        if repo_data:
            branch = repo_data.get("default_branch", "main")
        else:
            branch = "main"

    data = github_get(f"{GITHUB_API}/repos/{repo}/commits?sha={branch}&per_page=1")
    if data and isinstance(data, list) and len(data) > 0:
        commit = data[0]
        return {
            "sha": commit["sha"][:7],
            "message": (commit["commit"]["message"].split("\n")[0])[:120],
            "url": commit["html_url"],
            "author": commit["commit"]["author"]["name"],
            "date": commit["commit"]["author"]["date"],
        }
    return None


# ---------------------------------------------------------------------------
# Discord notification
# ---------------------------------------------------------------------------
def send_discord_embed(embeds: list[dict]) -> None:
    """Send embed messages to Discord via webhook (max 10 per request)."""
    if not DISCORD_WEBHOOK_URL:
        print("⚠ 未设置 DISCORD_WEBHOOK_URL，跳过通知发送。")
        return

    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i : i + 10]
        payload = {
            "username": "GitHub Monitor",
            "avatar_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
            "embeds": batch,
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
            if resp.status_code not in (200, 204):
                print(f"⚠ Discord webhook 返回 {resp.status_code}: {resp.text[:200]}")
            else:
                print(f"✅ Discord 通知已发送（{len(batch)} 条消息）")
        except requests.RequestException as exc:
            print(f"⚠ Discord webhook 发送失败: {exc}")


def build_release_embed(repo: str, release: dict) -> dict:
    return {
        "title": f"🚀 新版本发布: {repo}",
        "description": (
            f"**{release['name']}** (`{release['tag']}`)\n\n"
            f"{release['body']}{'…' if len(release['body']) >= 3800 else ''}"
        ),
        "url": release["url"],
        "color": 0x2EA043,  # green
        "footer": {"text": f"发布时间: {release['published_at'][:10]}"},
    }


def build_commit_embed(repo: str, commit: dict) -> dict:
    return {
        "title": f"📝 新提交: {repo}",
        "description": (
            f"`{commit['sha']}` by **{commit['author']}**\n"
            f"{commit['message']}"
        ),
        "url": commit["url"],
        "color": 0x1F6FEB,  # blue
        "footer": {"text": f"提交时间: {commit['date'][:10]}"},
    }


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def main() -> None:
    config = load_json(CONFIG_PATH)
    repos = config.get("repos", [])
    check_releases = config.get("check_releases", True)
    check_commits = config.get("check_commits", True)

    if not repos:
        print("未在 config.json 中配置任何仓库")
        sys.exit(0)

    state = load_json(STATE_PATH)
    embeds: list[dict] = []
    updated = False

    for raw_repo in repos:
        repo = parse_repo(raw_repo)
        print(f"🔍 正在检查 {repo} ...")
        repo_state = state.setdefault(repo, {})

        # --- Releases ---
        if check_releases:
            release = get_latest_release(repo)
            if release:
                last_tag = repo_state.get("last_release_tag")
                if release["tag"] != last_tag:
                    print(f"  🆕 发现新版本 {release['tag']}（上次: {last_tag}）")
                    embeds.append(build_release_embed(repo, release))
                    repo_state["last_release_tag"] = release["tag"]
                    updated = True
                else:
                    print(f"  ✓ 版本无变化（{release['tag']}）")

        # --- Commits ---
        if check_commits:
            commit = get_latest_commit(repo)
            if commit:
                last_sha = repo_state.get("last_commit_sha")
                if commit["sha"] != last_sha:
                    print(f"  🆕 发现新提交 {commit['sha']}（上次: {last_sha}）")
                    embeds.append(build_commit_embed(repo, commit))
                    repo_state["last_commit_sha"] = commit["sha"]
                    updated = True
                else:
                    print(f"  ✓ 提交无变化（{commit['sha']}）")

    # --- Send notifications ---
    if embeds:
        print(f"\n📬 正在发送 {len(embeds)} 条通知到 Discord ...")
        send_discord_embed(embeds)
    else:
        print("\n✅ 没有发现新的更新。")

    # --- Persist state ---
    if updated:
        state["_last_updated"] = datetime.now(timezone.utc).isoformat()
        save_json(STATE_PATH, state)
        print(f"💾 状态已保存到 {STATE_PATH}")


if __name__ == "__main__":
    main()
