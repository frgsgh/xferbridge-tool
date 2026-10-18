"""迁移执行器：生成迁移计划（依赖/配置Diff/物品预扫描），并执行迁移。

流程：
  plan_transfer  -> build_plan()   （依赖+配置+物品预扫描，供游戏内审查）
  apply_transfer -> execute()      （备份→配置→模组安装→玩家数据合并→隔离写入）
"""
from __future__ import annotations

import base64
import difflib
import gzip
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from . import backup as backup_mod
from . import launchers
from . import quarantine as quarantine_mod
from . import staging as staging_mod
from .dependency import check_dependencies
from .downloader import enrich_missing
from .modmeta import ModEntry
from .nbt import NBTList, NBTError, read_nbt, read_nbt_file, write_nbt_gzip
from .workspace import Workspace

log = logging.getLogger("xfer.transfer")

DEFAULT_MC = "1.20.1"
DEFAULT_LOADER = "forge"

# 玩家数据合并字段（只覆盖这些，其余保留目标存档原值）
MERGE_FIELDS = {
    "Inventory": ("Inventory", "list"),
    "EnderItems": ("EnderItems", "list"),
    "Attributes": ("Attributes", "compound"),
    "XpLevel": ("XpLevel", "scalar"),
    "XpTotal": ("XpTotal", "scalar"),
    "XpProgress": ("XpProgress", "scalar"),
    "Health": ("Health", "scalar"),
    "FoodLevel": ("FoodLevel", "scalar"),
}


# ---------------------------------------------------------------- 工具
def _event(ws: Workspace, request_id: str, stage: str, percent: int, msg: str) -> None:
    ws.write_event(request_id, stage, percent, msg)
    log.info("[%s] %s%% %s", stage, percent, msg)


def _resolve_save_by_scan(ws: Workspace, save_id: str) -> launchers.SaveEntry | None:
    index = _load_index(ws)
    for s in index:
        if s["id"] == save_id:
            return _entry_from_json(s)
    return None


def resolve_save(ws: Workspace, save_id: str | None = None, save_path: str | None = None,
                 save_folder: str | None = None) -> launchers.SaveEntry | None:
    """按 id、绝对路径或世界文件夹名解析存档（供模组发来的请求使用）。"""
    if save_id:
        hit = _resolve_save_by_scan(ws, save_id)
        if hit:
            return hit
    if save_path or save_folder:
        idx = _load_index(ws)
        p = str(Path(save_path).resolve()).lower() if save_path else None
        f = save_folder.lower() if save_folder else None
        for s in idx:
            if p:
                try:
                    sp = str(Path(s.get("path", "")).resolve()).lower()
                except OSError:
                    sp = str(s.get("path", "")).lower()
                if sp == p:
                    return _entry_from_json(s)
            if f and Path(s.get("path", "")).name.lower() == f:
                return _entry_from_json(s)
    return None


def _entry_from_json(s: dict[str, Any]) -> launchers.SaveEntry:
    return launchers.SaveEntry(
        id=s["id"], name=s["name"], launcher=s["launcher"],
        instance=s["instance"], path=Path(s["path"]),
        version=s.get("version", ""),
        mods_dir=Path(s["mods_dir"]) if s.get("mods_dir") else None,
        last_played=s.get("last_played", 0),
        player_name=s.get("player_name", ""),
        player_uuid=s.get("player_uuid", ""),
        mods=[ModEntry(**{k: m[k] for k in
                          ("mod_id", "display_name", "version", "loader",
                           "mc_version", "file", "path", "sha1",
                           "dependencies", "optional_dependencies",
                           "conflicts", "breaks") if k in m})
              for m in s.get("mods", [])],
    )


def _load_index(ws: Workspace) -> list[dict[str, Any]]:
    import json as _json
    try:
        data = _json.loads(ws.save_index().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("saves") or []
    except (OSError, _json.JSONDecodeError):
        pass
    return []


def _config_files(cfg_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not cfg_dir.is_dir():
        return out
    for root, _, files in cfg_dir.walk():
        for f in files:
            rel = (root / f).relative_to(cfg_dir).as_posix()
            out[rel] = root / f
    return out


def _owning_mod(rel: str) -> str | None:
    """尽力推断 config 文件归属的模组：取顶层目录名或文件名前缀。"""
    parts = rel.split("/")
    if len(parts) > 1:
        return parts[0]
    stem = Path(parts[0]).stem
    # config/<modid>-client.toml / config/<modid>.toml
    for sep in ("-client", "-server", "-common"):
        if stem.endswith(sep):
            return stem[: -len(sep)]
    return stem


def _diff_preview(src: Path | None, dst: Path | None, limit: int = 200) -> list[str]:
    a = src.read_text(encoding="utf-8", errors="replace").splitlines() if src and src.is_file() else []
    b = dst.read_text(encoding="utf-8", errors="replace").splitlines() if dst and dst.is_file() else []
    return list(difflib.unified_diff(a, b, lineterm="", n=1))[:limit]


# ---------------------------------------------------------------- 计划
def build_plan(ws: Workspace, request_id: str, source: launchers.SaveEntry,
               target: launchers.SaveEntry, player_manifest: dict[str, Any]) -> dict[str, Any]:
    _event(ws, request_id, "dep_analysis", 5, "正在解析模组依赖…")
    dep = check_dependencies(source.mods, target.mods, source.id, target.id)

    _event(ws, request_id, "dep_analysis", 25, f"缺失模组 {len(dep.missing)} 个，正在解析下载源…")
    enrich_missing(dep.missing, source.version or DEFAULT_MC, DEFAULT_LOADER,
                   progress=lambda i, m: _event(ws, request_id, "dep_analysis",
                                                25 + int(i / max(len(dep.missing), 1) * 25), m))

    _event(ws, request_id, "config_diff", 55, "正在对比配置文件…")
    src_cfg = _config_files(source.path / "config")
    tgt_cfg = _config_files(target.path / "config")
    coexist_ids = {m.mod_id for m in source.mods} & {m.mod_id for m in target.mods}
    coexist_diff: list[dict[str, Any]] = []
    for rel in sorted(set(src_cfg) | set(tgt_cfg)):
        owner = _owning_mod(rel)
        if owner and owner not in coexist_ids:
            continue
        s, t = src_cfg.get(rel), tgt_cfg.get(rel)
        if s and t and s.read_bytes() == t.read_bytes():
            status = "identical"
        elif s and t:
            status = "changed"
        elif s:
            status = "only_source"
        else:
            status = "only_target"
        coexist_diff.append({
            "mod_id": owner or "?",
            "file": rel,
            "status": status,
            "source": str(s) if s else None,
            "target": str(t) if t else None,
            "diff_preview": _diff_preview(s, t) if status == "changed" else [],
        })

    missing_ids = {m["mod_id"] for m in dep.missing}
    missing_mods_configs = [rel for rel in src_cfg
                            if (_owning_mod(rel) or "?") in missing_ids]

    _event(ws, request_id, "item_scan", 80, "正在预扫描物品…")
    items = player_manifest.get("items") or []
    tgt_ids = {m.mod_id for m in target.mods}
    quarantine_candidates: dict[str, dict[str, Any]] = {}
    for it in items:
        mod_id = str(it.get("mod_id", "") or "")
        if mod_id and mod_id not in tgt_ids:
            reg = str(it.get("registry", "unknown"))
            q = quarantine_candidates.setdefault(reg, {
                "registry": reg, "count": 0, "mod_id": mod_id,
                "reason": "target_missing_mod",
            })
            q["count"] += int(it.get("count", 1))
    item_preview = {
        "quarantine_candidates": list(quarantine_candidates.values()),
        "same_name_diff_id": [],
        "total_quarantine_count": sum(q["count"] for q in quarantine_candidates.values()),
    }

    plan = {
        "transfer_id": ws.new_uuid(),
        "source_save": source.id,
        "target_save": target.id,
        "dep_report": dep.to_json(),
        "config_diff": {
            "coexist_diff": coexist_diff,
            "missing_mods_configs": missing_mods_configs,
            "target_config_backup_required": True,
        },
        "item_preview": item_preview,
        "mods_to_install": dep.missing,
        "steps": ["backup", "config", "mods", "playerdata", "quarantine", "report"],
    }
    ws.write_json(ws.plans / f"plan_{plan['transfer_id']}.json", plan)
    _event(ws, request_id, "plan_ready", 100, "迁移计划已生成")
    return plan


# ---------------------------------------------------------------- 执行
def execute(ws: Workspace, request_id: str, transfer_id: str) -> dict[str, Any]:
    from .workspace import TransferTask
    task = TransferTask(ws, transfer_id)
    payload = task.read_payload()
    decision = task.read_decision()
    if not payload or not decision:
        raise ValueError("缺少载荷或决策文件，无法执行迁移")
    if not decision.get("proceed"):
        raise ValueError("玩家已取消迁移")
    source = resolve_save(ws, payload.get("source_save"),
                          payload.get("world_path"), payload.get("world_folder")) \
        or _resolve_save_by_scan(ws, payload["source_save"])
    target = _resolve_save_by_scan(ws, payload["target_save"])
    if source is None or target is None:
        raise FileNotFoundError("无法定位源/目标存档，请重新扫描")

    result: dict[str, Any] = {"transfer_id": transfer_id, "steps": {}}

    # 1) 备份目标（全量）
    _event(ws, request_id, "backup", 10, f"正在全量备份目标存档 {target.name}…")
    bak = backup_mod.full_backup(target.path, ws.backups, target.id, label="pre_transfer")
    result["backup_id"] = bak["backup_id"]

    # 2) 配置处理（先整体备份 config）
    _event(ws, request_id, "config", 25, "正在处理配置文件…")
    cfg_bak = backup_mod.backup_config_folder(target.path, ws.backups, target.id)
    applied, kept = _apply_config_choices(ws, source, target, decision)
    _move_missing_configs_to_quarantine(ws, source, target, decision)

    # 3) 安装暂存模组
    installed: list[dict[str, Any]] = []
    if decision.get("install_mode") == "auto" and target.mods_dir:
        _event(ws, request_id, "mods", 40, "正在安装暂存区模组…")
        for p in staging_mod.install_staged(target.mods_dir):
            installed.append({"mod_id": p.stem, "file": p.name, "sha1_ok": True})
        staging_mod.clear_staging(target.mods_dir)

    # 4) 玩家数据合并
    _event(ws, request_id, "playerdata", 60, "正在合并玩家数据…")
    merged = _merge_playerdata(target, payload)

    # 5) 隔离物品写入目标存档
    _event(ws, request_id, "quarantine", 80, "正在写入隔离区…")
    qitems = payload.get("quarantine_meta") or []
    qb64 = payload.get("quarantine_nbt_base64") or ""
    qres = quarantine_mod.write_quarantine(
        target.path, transfer_id, source.id, qitems, qb64,
        workspace_quarantine=ws.quarantine)

    result.update({
        "config_applied": applied,
        "config_kept": kept,
        "config_backup_id": cfg_bak["backup_id"] if cfg_bak else None,
        "mods_installed": installed,
        "playerdata_merged": merged,
        "quarantine_written": qres,
        "restart_required": bool(installed),
    })
    task.update(stage="done", result=result)
    _event(ws, request_id, "done", 100, "迁移完成")
    if installed:
        ws.write_event(request_id, "restart_prompt", 100,
                       "缺失模组已下载完毕，需要重启游戏才能生效，是否现在重启？")
    return result


def _apply_config_choices(ws: Workspace, source: launchers.SaveEntry,
                          target: launchers.SaveEntry, decision: dict[str, Any]) -> tuple[int, int]:
    choices = decision.get("config_choices") or {}
    applied = kept = 0
    for rel, choice in choices.items():
        src = source.path / "config" / rel
        dst = target.path / "config" / rel
        if choice == "use_source" and src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            applied += 1
        else:
            kept += 1
    return applied, kept


def _move_missing_configs_to_quarantine(ws: Workspace, source: launchers.SaveEntry,
                                        target: launchers.SaveEntry,
                                        decision: dict[str, Any]) -> list[str]:
    """缺失模组的配置：不覆盖目标，复制进工作区隔离目录留档。"""
    rels = decision.get("missing_configs_quarantine") or []
    moved: list[str] = []
    from .util import safe_id
    qdir = ws.quarantine / safe_id(source.id) / "missing_mods_configs"
    for rel in rels:
        src = source.path / "config" / rel
        if src.is_file():
            dst = qdir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            moved.append(rel)
    return moved


def _merge_playerdata(target: launchers.SaveEntry, payload: dict[str, Any]) -> dict[str, Any]:
    """把玩家载荷合并进目标存档 playerdata/<uuid>.dat。"""
    import base64 as _b64
    b64 = payload.get("nbt_base64", "")
    if not b64:
        raise ValueError("载荷缺少 nbt_base64")
    try:
        nbt_bytes = gzip.decompress(_b64.b64decode(b64))
    except Exception as e:
        raise NBTError(f"载荷解码失败: {e}") from e
    _, src_tag = read_nbt(nbt_bytes)
    if not isinstance(src_tag, dict):
        raise NBTError("载荷根标签不是 Compound")

    pd_dir = target.path / "playerdata"
    pd_dir.mkdir(parents=True, exist_ok=True)
    uuid = (payload.get("player") or {}).get("uuid", "")
    dat: Path | None = None
    if uuid:
        cand = pd_dir / f"{uuid}.dat"
        if cand.is_file():
            dat = cand
    if dat is None:
        dat = next((p for p in sorted(pd_dir.glob("*.dat")) if p.stem != "level"), None)
    if dat is None:
        dat = pd_dir / f"{uuid or '00000000-0000-0000-0000-000000000000'}.dat"

    if dat.exists():
        try:
            _, root = read_nbt_file(dat)
        except (NBTError, OSError):
            root = {}
        if not isinstance(root, dict):
            root = {}
        # 写前留档
        pre = pd_dir / f"{dat.stem}.pre_xfer_{time.strftime('%Y%m%d_%H%M%S')}.dat"
        shutil.copy2(dat, pre)
    else:
        root = {}
        pre = None

    for key, (dst_key, kind) in MERGE_FIELDS.items():
        if key not in src_tag:
            continue
        val = src_tag[key]
        if kind == "list" and not isinstance(val, NBTList):
            continue
        if kind == "compound" and not isinstance(val, dict):
            continue
        root[dst_key] = val

    write_nbt_gzip(dat, "", root)
    return {"file": str(dat), "pre_backup": str(pre) if pre else None,
            "fields": list(MERGE_FIELDS.keys())}
