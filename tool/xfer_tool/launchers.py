"""存档/实例扫描：官方启动器、PCL、HMCL、CurseForge、Prism/MultiMC 及自定义路径。

判定规则：
- 存档 = 目录下存在 level.dat（含 region 目录更可靠，这里以 level.dat 为准）。
- 实例 = 目录下存在 mods/ 目录（且包含版本信息时记录）。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .modmeta import ModEntry, parse_mods_dir
from .nbt import NBTError, read_level_dat

log = logging.getLogger("xfer.launchers")


def _default_mc_dirs() -> list[Path]:
    """候选的 .minecraft 根目录。"""
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / ".minecraft")
    # PCL / HMCL 常放在非 APPDATA 位置，交给自定义路径与扫描兜底
    return roots


@dataclass
class SaveEntry:
    id: str
    name: str
    launcher: str
    instance: str
    path: Path
    version: str = ""
    mods_dir: Path | None = None
    last_played: int = 0
    player_name: str = ""
    player_uuid: str = ""
    mods: list[ModEntry] = field(default_factory=list)

    @property
    def has_xferbridge(self) -> bool:
        return any(m.mod_id == "xferbridge" for m in self.mods)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": f"{self.name} ({self.version or '?'})",
            "launcher": self.launcher,
            "instance": self.instance,
            "path": str(self.path),
            "version": self.version,
            "mods_dir": str(self.mods_dir) if self.mods_dir else None,
            "last_played": self.last_played,
            "player_name": self.player_name,
            "player_uuid": self.player_uuid,
            "has_xferbridge": self.has_xferbridge,
            "mod_count": len(self.mods),
            "mods": [m.to_json() for m in self.mods],
        }


def _is_save_dir(d: Path) -> bool:
    return d.is_dir() and (d / "level.dat").is_file()


def _version_from_path(d: Path, root: Path) -> str:
    """从路径推断版本：...\\versions\\<ver>\\saves\\<world>。"""
    try:
        rel = d.relative_to(root).parts
    except ValueError:
        return ""
    for i, part in enumerate(rel):
        if part == "versions" and i + 1 < len(rel):
            return rel[i + 1]
    return ""


def _read_save_info(save: Path) -> tuple[str, int]:
    """读取 level.dat 的 LevelName 与 LastPlayed（失败返回目录名与 0）。"""
    try:
        data = read_level_dat(save / "level.dat")
    except (NBTError, OSError):
        return save.name, 0
    name = data.get("LevelName")
    if not isinstance(name, str) or not name:
        name = save.name
    last = data.get("LastPlayed")
    return name, int(last) if isinstance(last, int) else 0


def _find_player_uuid(save: Path) -> str:
    pd = save / "playerdata"
    if not pd.is_dir():
        return ""
    for p in sorted(pd.glob("*.dat")):
        if p.stem != "level":
            return p.stem
    return ""


def _collect_saves(save_root: Path, launcher: str, instance: str,
                   mods_dir: Path | None, version: str) -> list[SaveEntry]:
    out: list[SaveEntry] = []
    if not save_root.is_dir():
        return out
    for world in sorted(save_root.iterdir()):
        if not _is_save_dir(world):
            continue
        name, last = _read_save_info(world)
        entry = SaveEntry(
            id=f"{launcher}|{instance}|{world.name}",
            name=name,
            launcher=launcher,
            instance=instance,
            path=world,
            version=version,
            mods_dir=mods_dir,
            last_played=last,
            player_uuid=_find_player_uuid(world),
        )
        if mods_dir and mods_dir.is_dir():
            entry.mods = parse_mods_dir(mods_dir)
        out.append(entry)
    return out


def _scan_official(root: Path) -> list[SaveEntry]:
    out = _collect_saves(root / "saves", "official", "minecraft",
                         root / "mods", "")
    # 版本隔离目录：versions\\<ver>\\saves + mods
    ver_root = root / "versions"
    if ver_root.is_dir():
        for vdir in sorted(ver_root.iterdir()):
            if not vdir.is_dir():
                continue
            ver = vdir.name
            vmods = vdir / "mods" if (vdir / "mods").is_dir() else root / "mods"
            out += _collect_saves(vdir / "saves", "official", f"versions/{ver}", vmods, ver)
    return out


def _scan_pcl_hmcl(root: Path) -> list[SaveEntry]:
    """PCL / HMCL 与官方启动器同构（.minecraft），同样扫描版本隔离目录。"""
    out = _collect_saves(root / "saves", "pcl_hmcl", "minecraft", root / "mods", "")
    ver_root = root / "versions"
    if ver_root.is_dir():
        for vdir in sorted(ver_root.iterdir()):
            if not vdir.is_dir():
                continue
            ver = vdir.name
            vmods = vdir / "mods" if (vdir / "mods").is_dir() else root / "mods"
            out += _collect_saves(vdir / "saves", "pcl_hmcl", f"versions/{ver}", vmods, ver)
    return out


def _scan_curseforge(roots: list[Path]) -> list[SaveEntry]:
    out: list[SaveEntry] = []
    for base in roots:
        inst_root = base / "Minecraft" / "Instances"
        if not inst_root.is_dir():
            continue
        for inst in sorted(inst_root.iterdir()):
            if not inst.is_dir():
                continue
            mc = inst / ".minecraft"
            saves_dir = inst / "saves" if (inst / "saves").is_dir() else (mc / "saves")
            mods_dir = inst / "mods" if (inst / "mods").is_dir() else (mc / "mods")
            version = _instance_version(inst)
            out += _collect_saves(saves_dir, "curseforge", inst.name, mods_dir, version)
    return out


def _scan_prism_mm(roots: list[Path]) -> list[SaveEntry]:
    out: list[SaveEntry] = []
    for base in roots:
        inst_root = base / "instances"
        if not inst_root.is_dir():
            continue
        for inst in sorted(inst_root.iterdir()):
            if not inst.is_dir():
                continue
            mc = inst / ".minecraft"
            saves_dir = mc / "saves"
            mods_dir = mc / "mods"
            version = _instance_version(inst, mm_cfg=True)
            out += _collect_saves(saves_dir, "prism_multimc", inst.name, mods_dir, version)
    return out


def _instance_version(inst: Path, mm_cfg: bool = False) -> str:
    cfg = inst / ("instance.cfg" if mm_cfg else "manifest.json")
    if mm_cfg and cfg.is_file():
        try:
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("IntendedVersion="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            return ""
    if not mm_cfg and cfg.is_file():
        try:
            import json
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                ver = data.get("version")
                if isinstance(ver, dict):
                    for k in ("minecraftVersion", "gameVersion"):
                        v = ver.get(k)
                        if isinstance(v, str) and v:
                            return v
                if isinstance(ver, str):
                    return ver
        except (OSError, json.JSONDecodeError):
            return ""
    return ""


def scan_all(custom_paths: list[str] | None = None) -> list[SaveEntry]:
    """扫描所有已知位置 + 自定义路径，返回去重后的存档列表。"""
    seen: set[str] = set()
    out: list[SaveEntry] = []

    def add(entries: list[SaveEntry]) -> None:
        for e in entries:
            key = str(e.path).lower()
            if key not in seen:
                seen.add(key)
                out.append(e)

    for root in _default_mc_dirs():
        add(_scan_official(root))
        add(_scan_pcl_hmcl(root))

    pf = os.environ.get("PROGRAMFILES")
    cf_roots: list[Path] = []
    if pf:
        cf_roots.append(Path(pf) / "CurseForge")
        cf_roots.append(Path(pf) / "Overwolf" / "CurseForge")
    add(_scan_curseforge(cf_roots))

    mm_roots: list[Path] = []
    for env, name in (("PRISMLAUNCHER_DIR", "PrismLauncher"),
                      ("MULTIMC_DIR", "MultiMC")):
        v = os.environ.get(env)
        if v:
            mm_roots.append(Path(v))
    if pf:
        mm_roots.append(Path(pf) / "PrismLauncher")
        mm_roots.append(Path(pf) / "MultiMC")
    add(_scan_prism_mm(mm_roots))

    for cp in custom_paths or []:
        p = Path(cp)
        if not p.is_dir():
            continue
        # 自定义路径可能是 .minecraft 根、实例根或存档目录
        if (p / "level.dat").is_file():
            add(_collect_saves(p.parent, "custom", p.name, None, ""))
        elif (p / "mods").is_dir() or (p / "saves").is_dir():
            mc = p if (p / "saves").is_dir() else p
            add(_collect_saves(mc / "saves", "custom", p.name, mc / "mods", ""))
        else:
            # 深度一层找 save
            for sub in sorted(p.iterdir()):
                if (sub / "saves").is_dir():
                    add(_collect_saves(sub / "saves", "custom", sub.name,
                                       sub / "mods" if (sub / "mods").is_dir() else None, ""))
    return out


def build_index(custom_paths: list[str] | None = None) -> dict[str, Any]:
    saves = scan_all(custom_paths)
    return {
        "protocol": "xferbridge.ipc.v1",
        "kind": "saves_index",
        "tool_version": __version__,
        "scanned_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        "saves": [s.to_json() for s in saves],
        "launchers": [
            {"launcher": "official", "found": any(s.launcher == "official" for s in saves)},
            {"launcher": "pcl_hmcl", "found": any(s.launcher == "pcl_hmcl" for s in saves)},
            {"launcher": "curseforge", "found": any(s.launcher == "curseforge" for s in saves)},
            {"launcher": "prism_multimc", "found": any(s.launcher == "prism_multimc" for s in saves)},
            {"launcher": "custom", "found": any(s.launcher == "custom" for s in saves)},
        ],
        "custom_paths": custom_paths or [],
    }
