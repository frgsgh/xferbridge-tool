"""IPC 请求处理：mod→tool 请求的解析与执行，写入响应/事件。"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from . import backup as backup_mod
from . import downloader, launchers, quarantine as quarantine_mod, staging as staging_mod
from .dependency import check_dependencies
from .transfer import build_plan, execute
from .workspace import Workspace

log = logging.getLogger("xfer.ipc")


def _resolve(ws: Workspace, save_id: str) -> launchers.SaveEntry | None:
    from .transfer import _resolve_save_by_scan
    return _resolve_save_by_scan(ws, save_id)


def _resolve_smart(ws: Workspace, payload: dict[str, Any]) -> launchers.SaveEntry | None:
    """优先按 id，其次按世界绝对路径/文件夹名解析（兼容模组请求）。"""
    from .transfer import resolve_save
    return resolve_save(ws,
                        payload.get("save_id") or payload.get("source_save"),
                        payload.get("save_path") or payload.get("world_path"),
                        payload.get("world_folder"))


def handle_request(ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
    action = str(req.get("action", ""))
    request_id = str(req.get("request_id", ""))
    payload = req.get("payload") or {}
    try:
        result = _dispatch(ws, request_id, action, payload)
        ws.write_response(request_id, True, result)
        return {"request_id": request_id, "ok": True, "result": result}
    except Exception as e:  # noqa: BLE001 —— 记录并返回错误，不中断
        log.exception("请求处理失败: %s", action)
        ws.write_response(request_id, False, error=str(e))
        return {"request_id": request_id, "ok": False, "error": str(e)}


def _dispatch(ws: Workspace, request_id: str, action: str,
              payload: dict[str, Any]) -> Any:
    if action == "ping":
        return {"pong": True, "version": "1.0.0", "protocol": "xferbridge.ipc.v1"}

    if action == "scan_saves":
        custom = payload.get("custom_paths") or None
        index = launchers.build_index(custom)
        ws.write_json(ws.save_index(), index)
        return {"saves_count": len(index["saves"]), "index": index}

    if action == "check_deps":
        source = _resolve_smart(ws, payload)
        target = _resolve(ws, str(payload["target_save"]))
        if not source or not target:
            raise FileNotFoundError("无法定位存档，请先扫描")
        report = check_dependencies(source.mods, target.mods, source.id, target.id)
        downloader.enrich_missing(report.missing, source.version or "1.20.1", "forge")
        return report.to_json()

    if action == "plan_transfer":
        source = _resolve_smart(ws, payload)
        target = _resolve(ws, str(payload["target_save"]))
        if not source or not target:
            raise FileNotFoundError("无法定位存档，请先扫描")
        player_manifest = payload.get("player_manifest") or {}
        plan = build_plan(ws, request_id, source, target, player_manifest)
        return {"transfer_id": plan["transfer_id"], "plan": plan}

    if action == "apply_transfer":
        transfer_id = str(payload["transfer_id"])
        return execute(ws, request_id, transfer_id)

    if action == "backup":
        save = _resolve_smart(ws, payload) or _resolve(ws, str(payload.get("save_id", "")))
        if not save:
            raise FileNotFoundError("无法定位存档")
        kind = str(payload.get("kind", "full"))
        if kind == "incremental":
            return backup_mod.incremental_backup(save.path, ws.backups, save.id)
        return backup_mod.full_backup(save.path, ws.backups, save.id,
                                      label=str(payload.get("label", "manual")))

    if action == "rollback":
        save = _resolve_smart(ws, payload) or _resolve(ws, str(payload.get("save_id", "")))
        if not save:
            raise FileNotFoundError("无法定位存档")
        backup_id = str(payload["backup_id"])
        return backup_mod.restore(save.path, ws.backups, save.id, backup_id)

    if action == "install_mods":
        target = _resolve(ws, str(payload["target_save"]))
        if not target:
            raise FileNotFoundError("无法定位目标存档")
        mods = payload.get("mods") or []
        return _install_mods(ws, request_id, target, mods)

    if action == "install_guided":
        return {"links": payload.get("mods") or []}

    if action == "export_quarantine":
        save = _resolve_smart(ws, payload) or _resolve(ws, str(payload.get("save_id", "")))
        if not save:
            raise FileNotFoundError("无法定位存档")
        fmt = str(payload.get("format", "zip"))
        if fmt == "base64":
            return quarantine_mod.export_base64(save.path, ws.quarantine, save.id)
        return quarantine_mod.export_zip(save.path, ws.quarantine, save.id)

    if action == "status":
        transfer_id = str(payload.get("transfer_id", ""))
        from .workspace import TransferTask
        task = TransferTask(ws, transfer_id)
        return {"state": task.state(), "events": ws.events_for(transfer_id)[-5:]}

    raise ValueError(f"未知 action: {action}")


def _install_mods(ws: Workspace, request_id: str, target: launchers.SaveEntry,
                  mods: list[dict[str, Any]]) -> dict[str, Any]:
    """自动安装：下载到 .staging（目标 mods 目录 + 工作区镜像），哈希校验，不直写 mods。"""
    if not target.mods_dir:
        raise FileNotFoundError("目标实例没有 mods 目录")
    staged_dir = staging_mod.staging_dir(target.mods_dir)
    staged_dir.mkdir(parents=True, exist_ok=True)
    total = len(mods)
    installed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for i, mod in enumerate(mods):
        dl_list = mod.get("downloads") or []
        dl = next((d for d in dl_list if d.get("source") != "manual"), None)
        if not dl:
            failed.append({"mod_id": mod.get("mod_id"), "reason": "no_auto_download"})
            continue
        ws.write_event(request_id, "downloading", int(i / total * 80),
                       f"正在下载 {dl.get('filename', mod.get('mod_id'))} ({i + 1}/{total})")
        try:
            mirror = ws.staging / dl.get("filename", "mod.jar")
            downloader.download_file(
                dl["url"], mirror,
                expected_sha1=dl.get("sha1", ""),
                expected_md5=dl.get("md5", ""),
                expected_size=int(dl.get("size", 0) or 0),
                progress=lambda done, tot: ws.write_event(
                    request_id, "downloading",
                    int(i / total * 80 + (done / max(tot, 1)) * (80 / total)),
                    f"下载中 {dl.get('filename', '')} {done // 1024}KB/{tot // 1024}KB"),
            )
            staged = staging_mod.stage_file(mirror, target.mods_dir, dl["filename"])
            installed.append({
                "mod_id": mod.get("mod_id"),
                "display_name": mod.get("display_name", mod.get("mod_id")),
                "file": dl["filename"],
                "staged_path": str(staged),
                "sha1_ok": True,
            })
        except downloader.DownloadError as e:
            failed.append({"mod_id": mod.get("mod_id"), "reason": str(e)})
    ws.write_event(request_id, "staged", 100,
                   f"下载完成：成功 {len(installed)}，失败 {len(failed)}（文件位于 .staging，重启后生效）")
    return {"installed": installed, "failed": failed,
            "staged_dir": str(staged_dir),
            "restart_required": True}


def run_once(ws: Workspace) -> int:
    """处理一个待办请求，返回处理数量。"""
    reqs = ws.pending_requests()
    count = 0
    for req in reqs:
        request_id = str(req.get("request_id", ""))
        if not request_id:
            continue
        handle_request(ws, req)
        ws.consume_request(request_id)
        count += 1
    return count


def run_forever(ws: Workspace, interval: float = 1.0, stop: Any = None) -> None:
    """守护模式：轮询请求目录。stop 为可调用对象，返回 True 时退出。"""
    log.info("IPC 守护启动: %s", ws.root)
    while True:
        try:
            run_once(ws)
        except Exception:  # noqa: BLE001
            log.exception("IPC 轮询异常")
        if stop is not None and stop():
            break
        time.sleep(interval)
