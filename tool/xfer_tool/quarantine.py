"""隔离区管理：写入目标存档、镜像到工作区、导出 zip / Base64。"""
from __future__ import annotations

import base64
import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Any

from .util import safe_id

log = logging.getLogger("xfer.quarantine")

QUARANTINE_DIR = "xfer_quarantine"


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def write_quarantine(target_save_dir: Path, transfer_id: str, source_save: str,
                     items: list[dict[str, Any]], quarantine_nbt_b64: str,
                     workspace_quarantine: Path | None = None) -> dict[str, Any]:
    """把隔离物品写入目标存档的 xfer_quarantine 文件夹 + 工作区镜像。"""
    doc = {
        "format": "xferbridge.quarantine.v1",
        "transfer_id": transfer_id,
        "source_save": source_save,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(items),
        "items": items,
        "payload_base64": quarantine_nbt_b64,
    }
    # 目标存档内
    qdir = target_save_dir / QUARANTINE_DIR
    qdir.mkdir(parents=True, exist_ok=True)
    fname = f"items_{_ts()}.json"
    (qdir / fname).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    # 工作区镜像
    mirrored: str | None = None
    if workspace_quarantine:
        ws_dir = workspace_quarantine / safe_id(source_save)
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / fname).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        mirrored = str(ws_dir / fname)
    return {"count": len(items), "path": str(qdir / fname), "mirror": mirrored}


def read_quarantine(save_dir: Path) -> list[dict[str, Any]]:
    """合并读取存档内全部隔离批次。"""
    qdir = save_dir / QUARANTINE_DIR
    if not qdir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(qdir.glob("items_*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def export_zip(save_dir: Path, workspace_quarantine: Path, save_id: str) -> dict[str, Any]:
    """把隔离区打包为 zip：manifest.json + items.json + payload_base64.txt。"""
    batches = read_quarantine(save_dir)
    ws_dir = workspace_quarantine / safe_id(save_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    name = f"export_{_ts()}.zip"
    target = ws_dir / name
    manifest = {
        "format": "xferbridge.quarantine.v1",
        "save_id": save_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "batch_count": len(batches),
        "total_items": sum(int(b.get("count", 0)) for b in batches),
        "batches": [b.get("transfer_id", "") for b in batches],
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("items.json", json.dumps(batches, ensure_ascii=False, indent=2))
        payloads = "\n".join(str(b.get("payload_base64", "")) for b in batches if b.get("payload_base64"))
        zf.writestr("payload_base64.txt", payloads)
    return {**manifest, "archive": str(target)}


def export_base64(save_dir: Path, workspace_quarantine: Path, save_id: str) -> dict[str, Any]:
    """隔离区导出为 Base64 字符串（单行，可复制/分享）。"""
    batches = read_quarantine(save_dir)
    doc = {
        "format": "xferbridge.quarantine.v1",
        "save_id": save_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "batch_count": len(batches),
        "total_items": sum(int(b.get("count", 0)) for b in batches),
        "batches": batches,
    }
    encoded = base64.b64encode(json.dumps(doc, ensure_ascii=False).encode("utf-8")).decode("ascii")
    ws_dir = workspace_quarantine / safe_id(save_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    out_path = ws_dir / f"export_{_ts()}.b64.txt"
    out_path.write_text(encoded, encoding="ascii")
    return {"format": "xferbridge.quarantine.v1", "base64": encoded, "path": str(out_path)}
