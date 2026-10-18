"""依赖树构建与冲突检测。

输入：源存档模组列表 + 目标存档模组列表。
输出：缺失（required 依赖）、版本不匹配、冲突（conflicts/breaks）、重复 modId、依赖环。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .modmeta import ModEntry, match_version

PLATFORM_MODS = {"minecraft", "forge", "fml", "fabricloader", "fabric", "neoforge", "javafml"}


@dataclass
class DepReport:
    source_save: str
    target_save: str
    source_mods: list[ModEntry] = field(default_factory=list)
    target_mods: list[ModEntry] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    version_mismatch: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    target_missing_xferbridge: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "source_save": self.source_save,
            "target_save": self.target_save,
            "source_mods": [m.to_json() for m in self.source_mods],
            "target_mods": [m.to_json() for m in self.target_mods],
            "missing": self.missing,
            "version_mismatch": self.version_mismatch,
            "conflicts": self.conflicts,
            "duplicates": self.duplicates,
            "cycles": self.cycles,
            "target_missing_xferbridge": self.target_missing_xferbridge,
            "summary": {
                "missing": len(self.missing),
                "mismatch": len(self.version_mismatch),
                "conflicts": len(self.conflicts),
                "duplicates": len(self.duplicates),
                "cycles": len(self.cycles),
            },
        }


def _find_duplicates(mods: list[ModEntry]) -> list[dict[str, Any]]:
    by_id: dict[str, list[str]] = {}
    for m in mods:
        by_id.setdefault(m.mod_id, []).append(m.file)
    return [{"mod_id": mid, "files": files} for mid, files in by_id.items() if len(files) > 1]


def _find_cycles(mods_by_id: dict[str, ModEntry]) -> list[list[str]]:
    """在源模组的 required 依赖图中找环（只沿源内存在的边）。"""
    visited: dict[str, int] = {}  # 0=visiting 1=done
    stack: list[str] = []
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        visited[node] = 0
        stack.append(node)
        mod = mods_by_id.get(node)
        if mod:
            for dep in mod.dependencies:
                if dep["type"] != "required" or dep["mod_id"] in PLATFORM_MODS:
                    continue
                dep_id = dep["mod_id"]
                if dep_id not in mods_by_id:
                    continue
                if visited.get(dep_id) == 0:
                    idx = stack.index(dep_id)
                    cyc = stack[idx:] + [dep_id]
                    key = tuple(cyc)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cyc)
                elif visited.get(dep_id) == 1:
                    dfs(dep_id)
        stack.pop()
        visited[node] = 1

    for mid in mods_by_id:
        if mid not in visited:
            dfs(mid)
    return cycles


def check_dependencies(source_mods: list[ModEntry], target_mods: list[ModEntry],
                       source_save: str = "", target_save: str = "") -> DepReport:
    report = DepReport(source_save=source_save, target_save=target_save,
                       source_mods=source_mods, target_mods=target_mods)
    src_by_id = {m.mod_id: m for m in source_mods}
    tgt_by_id = {m.mod_id: m for m in target_mods}

    report.target_missing_xferbridge = "xferbridge" not in tgt_by_id
    report.duplicates = _find_duplicates(target_mods)

    # 1) 缺失与版本不匹配
    seen_missing: dict[str, dict[str, Any]] = {}
    for src in source_mods:
        for dep in src.dependencies:
            if dep["type"] != "required" or dep["mod_id"] in PLATFORM_MODS:
                continue
            dep_id = dep["mod_id"]
            if dep_id == src.mod_id:
                continue
            tgt = tgt_by_id.get(dep_id)
            if tgt is None:
                entry = seen_missing.setdefault(dep_id, {
                    "mod_id": dep_id,
                    "display_name": dep_id,
                    "version": "",
                    "required_by": [],
                    "version_range": dep["version_range"],
                    "downloads": [],
                    "can_auto_install": True,
                })
                if src.display_name not in entry["required_by"]:
                    entry["required_by"].append(src.display_name)
            else:
                rng = dep["version_range"]
                if rng and rng != "*" and tgt.version and not match_version(tgt.version, rng):
                    report.version_mismatch.append({
                        "mod_id": dep_id,
                        "in_source": src.version,
                        "in_target": tgt.version,
                        "range": rng,
                        "required_by": src.display_name,
                    })

    # 缺失项补 display_name（若目标有同名但版本不对的，用目标的名字）
    for entry in seen_missing.values():
        tgt = tgt_by_id.get(entry["mod_id"])
        if tgt:
            entry["display_name"] = tgt.display_name or entry["mod_id"]
    report.missing = list(seen_missing.values())

    # 2) 冲突：源模组声明 conflicts/breaks 命中目标（或源）存在的模组
    present_ids = set(src_by_id) | set(tgt_by_id)
    for src in source_mods:
        for dep in src.conflicts:
            dep_id = dep["mod_id"]
            if dep_id in present_ids and dep_id != src.mod_id:
                report.conflicts.append({
                    "mod_id": src.mod_id,
                    "with": dep_id,
                    "reason": f"{src.display_name or src.mod_id} 声明与 {dep_id} 冲突",
                    "range": dep["version_range"],
                })

    # 3) 依赖环（源内）
    report.cycles = _find_cycles(src_by_id)
    return report
