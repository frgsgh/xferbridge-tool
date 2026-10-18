"""备份与回滚：全量 zip、增量 zip（清单对比）、一键回滚、config 文件夹独立备份。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .util import safe_id

log = logging.getLogger("xfer.backup")

EXCLUDE_DIRS = {"backups", "xfer_quarantine", ".staging"}


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _file_sha1(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _walk(save: Path) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(save):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            p = Path(root) / f
            try:
                if p.is_file():
                    out.append(p)
            except OSError:
                continue
    return out


def _zip_path(zf: zipfile.ZipFile, src: Path, arc_prefix: Path) -> None:
    zf.write(src, str(src.relative_to(arc_prefix)).replace("\\", "/"))


def full_backup(save_dir: Path, backup_root: Path, save_id: str,
                label: str = "full") -> dict[str, Any]:
    """全量备份整个存档目录为 zip + manifest。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = backup_root / safe_id(save_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{label}_{ts}.zip"
    target = out_dir / name
    manifest: dict[str, Any] = {
        "backup_id": name[:-4],
        "save_id": save_id,
        "kind": "full",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": {},
    }
    files = _walk(save_dir)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            rel = str(f.relative_to(save_dir)).replace("\\", "/")
            if rel in ("backups",):
                continue
            _zip_path(zf, f, save_dir)
            manifest["files"][rel] = {"sha1": _file_sha1(f), "size": f.stat().st_size}
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {**manifest, "archive": str(target), "file_count": len(files)}


def incremental_backup(save_dir: Path, backup_root: Path, save_id: str,
                       base_backup_id: str | None = None) -> dict[str, Any] | None:
    """增量备份：对比上次备份清单，仅打包新增/变更文件；无变化返回 None。"""
    out_dir = backup_root / safe_id(save_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_backup_id
    if base is None:
        base = _latest_full_id(out_dir)
    base_manifest: dict[str, Any] = {}
    if base:
        base_manifest = _read_manifest(out_dir, base)

    ts = time.strftime("%Y%m%d_%H%M%S")
    name = f"incr_{ts}_from_{base or 'none'}.zip"
    target = out_dir / name
    current: dict[str, Any] = {}
    changed: list[Path] = []
    removed: list[str] = []
    for f in _walk(save_dir):
        rel = str(f.relative_to(save_dir)).replace("\\", "/")
        if rel == "manifest.json":
            continue
        prev = base_manifest.get("files", {}).get(rel)
        if prev:
            try:
                same = prev.get("size") == f.stat().st_size and prev.get("sha1") == _file_sha1(f)
            except OSError:
                same = False
        else:
            same = False
        current[rel] = {"sha1": _file_sha1(f) if not same else prev["sha1"],
                        "size": f.stat().st_size}
        if not same:
            changed.append(f)
    for rel in base_manifest.get("files", {}):
        if rel not in current:
            removed.append(rel)

    if not changed and not removed:
        return None

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in changed:
            _zip_path(zf, f, save_dir)
        zf.writestr("deleted.json", json.dumps({"removed": removed}, ensure_ascii=False, indent=2))
        manifest = {
            "backup_id": name[:-4],
            "save_id": save_id,
            "kind": "incremental",
            "base": base,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "files": current,
            "changed": [str(f.relative_to(save_dir)).replace("\\", "/") for f in changed],
            "removed": removed,
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {**manifest, "archive": str(target), "changed_count": len(changed), "removed_count": len(removed)}


def _latest_full_id(out_dir: Path) -> str | None:
    best: str | None = None
    for p in sorted(out_dir.glob("full_*.zip"), reverse=True):
        best = p.stem
        break
    return best


def _read_manifest(out_dir: Path, backup_id: str) -> dict[str, Any]:
    with zipfile.ZipFile(out_dir / f"{backup_id}.zip") as zf:
        try:
            return json.loads(zf.read("manifest.json").decode("utf-8"))
        except KeyError:
            return {}


def list_backups(backup_root: Path, save_id: str) -> list[dict[str, Any]]:
    out_dir = backup_root / safe_id(save_id)
    if not out_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(out_dir.glob("*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(p) as zf:
                if "manifest.json" not in zf.namelist():
                    continue
                m = json.loads(zf.read("manifest.json").decode("utf-8"))
                m["archive"] = str(p)
                out.append(m)
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
            continue
    return out


def _safe_rel(rel: str) -> bool:
    return rel and not rel.startswith("/") and ".." not in rel.replace("\\", "/").split("/")


def restore(save_dir: Path, backup_root: Path, save_id: str, backup_id: str,
            progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """回滚：先备份当前状态为 pre_rollback，再应用备份（增量按链追溯）。"""
    out_dir = backup_root / safe_id(save_id)
    archive = out_dir / f"{backup_id}.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"备份不存在: {backup_id}")

    # 1) 先备份当前状态
    pre = full_backup(save_dir, backup_root, save_id, label="pre_rollback")

    # 2) 按链展开备份清单（当前备份 + 其后所有备份按顺序应用）
    chain = _expand_chain(out_dir, backup_id)

    for idx, bid in enumerate(chain):
        if progress:
            progress(int((idx + 1) / len(chain) * 90), f"应用备份 {bid}")
        with zipfile.ZipFile(out_dir / f"{bid}.zip") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if manifest.get("kind") == "full":
                _clear_save(save_dir)
            deleted: list[str] = []
            try:
                deleted = json.loads(zf.read("deleted.json").decode("utf-8")).get("removed", [])
            except KeyError:
                pass
            for rel in deleted:
                if _safe_rel(rel):
                    (save_dir / rel).unlink(missing_ok=True)
            for info in zf.infolist():
                if info.is_dir() or info.filename == "manifest.json" or info.filename == "deleted.json":
                    continue
                if not _safe_rel(info.filename):
                    continue
                dst = save_dir / info.filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)

    return {
        "backup_id": backup_id,
        "chain": chain,
        "pre_rollback_id": pre["backup_id"],
        "restored_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def _expand_chain(out_dir: Path, backup_id: str) -> list[str]:
    """从选定备份回溯到其基线全量备份，按时间顺序返回 [全量, ..., 选定]，
    实现「回滚到该备份点」的确切状态。"""
    manifests: dict[str, dict[str, Any]] = {}
    for p in out_dir.glob("*.zip"):
        manifests[p.stem] = _read_manifest(out_dir, p.stem)
    path: list[str] = []
    cur: str | None = backup_id
    guard = 0
    while cur and cur in manifests and guard < 1000:
        path.append(cur)
        m = manifests[cur]
        if m.get("kind") == "full":
            break
        cur = m.get("base")
        guard += 1
    return list(reversed(path))


def _clear_save(save_dir: Path) -> None:
    for child in list(save_dir.iterdir()):
        if child.name in EXCLUDE_DIRS:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def backup_config_folder(save_dir: Path, backup_root: Path, save_id: str) -> dict[str, Any] | None:
    """替换任何 config 前，先把目标存档 config 文件夹整体打包。"""
    cfg = save_dir / "config"
    if not cfg.is_dir():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = backup_root / safe_id(save_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"config_backup_{ts}.zip"
    target = out_dir / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in _walk(cfg):
            _zip_path(zf, f, cfg)
    return {"backup_id": name[:-4], "archive": str(target)}
