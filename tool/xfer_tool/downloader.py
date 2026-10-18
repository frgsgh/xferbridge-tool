"""模组下载器：Modrinth v2 API 搜索与下载，SHA1/MD5 哈希校验，断点式重试。"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("xfer.downloader")

UA = "XferBridge/1.0 (Minecraft mod cross-save tool; contact: local)"
MODRINTH_API = "https://api.modrinth.com/v2"
SEARCH_URL = f"{MODRINTH_API}/search"
VERSION_URL = f"{MODRINTH_API}/project/{{id}}/version"


class DownloadError(Exception):
    pass


def http_json(url: str, retries: int = 3, delay: float = 2.0, timeout: float = 30.0) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise DownloadError(f"资源不存在 (404): {url}") from e
            if attempt < retries - 1:
                log.warning("请求失败(第%d次): %s: %s", attempt + 1, url, e)
                time.sleep(delay * (attempt + 1))
    raise DownloadError(f"请求失败: {url}: {last}")


def search_modrinth(query: str, game_version: str = "1.20.1",
                    loader: str = "forge", limit: int = 8) -> list[dict[str, Any]]:
    facets = json.dumps([["versions:" + game_version], ["project_type:mod"]], separators=(",", ":"))
    params = urllib.parse.urlencode({
        "query": query,
        "facets": facets,
        "limit": str(limit),
    })
    data = http_json(f"{SEARCH_URL}?{params}")
    hits = data.get("hits") or []
    out = []
    for h in hits:
        loaders = h.get("loaders") or []
        if loader not in loaders and "loader" not in h:
            continue
        out.append({
            "project_id": h.get("project_id", ""),
            "slug": h.get("slug", ""),
            "title": h.get("title", ""),
            "description": (h.get("description") or "")[:160],
            "loaders": loaders,
            "versions": h.get("versions") or [],
        })
    return out


def get_versions(project_id: str, game_version: str = "1.20.1",
                 loader: str = "forge") -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({
        "game_versions": json.dumps([game_version], separators=(",", ":")),
        "loaders": json.dumps([loader], separators=(",", ":")),
    })
    data = http_json(f"{VERSION_URL.format(id=urllib.parse.quote(project_id))}?{params}")
    if not isinstance(data, list):
        return []
    out = []
    for v in data:
        if not isinstance(v, dict):
            continue
        files = v.get("files") or []
        out.append({
            "id": v.get("id", ""),
            "version_number": v.get("version_number", ""),
            "game_versions": v.get("game_versions") or [],
            "loaders": v.get("loaders") or [],
            "files": [{
                "url": f.get("url", ""),
                "filename": f.get("filename", ""),
                "size": f.get("size", 0),
                "hashes": f.get("hashes") or {},
            } for f in files if isinstance(f, dict)],
        })
    return out


def pick_best_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """优先选第一个（服务端已按推荐度/时间排序）且含可下载文件的版本。"""
    for v in versions:
        for f in v.get("files", []):
            if f.get("url"):
                return v
    return versions[0] if versions else None


def resolve_download(project_id: str, game_version: str = "1.20.1",
                     loader: str = "forge") -> dict[str, Any] | None:
    """解析项目在指定版本/加载器下的最优下载文件。"""
    versions = get_versions(project_id, game_version, loader)
    best = pick_best_version(versions)
    if not best:
        return None
    file = next((f for f in best.get("files", []) if f.get("url")), None)
    if not file:
        return None
    return {
        "source": "modrinth",
        "project_id": project_id,
        "version_id": best.get("id", ""),
        "version_number": best.get("version_number", ""),
        "filename": file["filename"],
        "url": file["url"],
        "size": file.get("size", 0),
        "sha1": (file.get("hashes") or {}).get("sha1", ""),
        "sha512": (file.get("hashes") or {}).get("sha512", ""),
    }


def enrich_missing(missing_entries: list[dict[str, Any]],
                   game_version: str = "1.20.1", loader: str = "forge",
                   progress: Callable[[int, str], None] | None = None) -> None:
    """为缺失模组条目填充 downloads（Modrinth 直接解析）与手动链接。"""
    total = len(missing_entries)
    for i, entry in enumerate(missing_entries):
        if progress:
            progress(i, f"搜索下载源: {entry['mod_id']} ({i + 1}/{total})")
        try:
            hits = search_modrinth(entry["mod_id"], game_version, loader, limit=3)
            dl: dict[str, Any] | None = None
            for h in hits:
                if h["slug"] == entry["mod_id"] or h["title"].lower() == entry["mod_id"].lower():
                    dl = resolve_download(h["project_id"], game_version, loader)
                    break
            if dl is None and hits:
                dl = resolve_download(hits[0]["project_id"], game_version, loader)
                if dl:
                    dl["matched_by"] = hits[0]["title"]
            if dl:
                dl["display_name"] = entry["display_name"] or entry["mod_id"]
                entry["downloads"] = [dl]
                entry["can_auto_install"] = True
                continue
        except DownloadError as e:
            log.warning("解析下载源失败 %s: %s", entry["mod_id"], e)
        # 未找到：提供手动搜索链接
        entry["downloads"] = [{
            "source": "manual",
            "url": f"https://modrinth.com/mods?q={urllib.parse.quote(entry['mod_id'])}&g={game_version}&l={loader}",
            "display_name": entry["display_name"] or entry["mod_id"],
        }]
        entry["can_auto_install"] = False


def download_file(url: str, dest: Path, expected_sha1: str = "", expected_md5: str = "",
                  expected_size: int = 0, retries: int = 3, delay: float = 2.0,
                  progress: Callable[[int, int], None] | None = None) -> Path:
    """流式下载到 dest，校验 SHA1/MD5/大小，失败丢弃重试。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(retries):
        tmp = dest.with_suffix(dest.suffix + f".part{attempt}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
                sha1 = hashlib.sha1()
                md5 = hashlib.md5()
                total = int(resp.headers.get("Content-Length", 0) or 0) or expected_size
                done = 0
                while True:
                    block = resp.read(1 << 16)
                    if not block:
                        break
                    f.write(block)
                    sha1.update(block)
                    md5.update(block)
                    done += len(block)
                    if progress and total:
                        progress(done, total)
            if expected_size and done != expected_size:
                raise DownloadError(f"大小不符: 期望 {expected_size}, 实际 {done}")
            if expected_sha1 and sha1.hexdigest().lower() != expected_sha1.lower():
                raise DownloadError(f"SHA1 校验失败: 期望 {expected_sha1}, 实际 {sha1.hexdigest()}")
            if expected_md5 and md5.hexdigest().lower() != expected_md5.lower():
                raise DownloadError(f"MD5 校验失败: 期望 {expected_md5}, 实际 {md5.hexdigest()}")
            tmp.replace(dest)
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, DownloadError) as e:
            last = e
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt < retries - 1:
                log.warning("下载失败(第%d次) %s: %s", attempt + 1, url, e)
                time.sleep(delay * (attempt + 1))
    raise DownloadError(f"下载失败: {url}: {last}")
