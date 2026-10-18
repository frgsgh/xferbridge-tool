"""模组元数据解析：读取 mods 目录下的 jar，解析 Forge mods.toml / Fabric fabric.mod.json。"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEP_TYPES = ("required", "optional", "incompatible")
TYPE_LABEL = {"required": "前置(必选)", "optional": "可选", "incompatible": "冲突"}


def sha1_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def md5_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@dataclass
class ModEntry:
    mod_id: str
    display_name: str = ""
    version: str = ""
    loader: str = "forge"  # forge / fabric / both
    file: str = ""
    path: str = ""
    sha1: str = ""
    mc_version: str = ""
    dependencies: list[dict[str, str]] = field(default_factory=list)
    optional_dependencies: list[dict[str, str]] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)
    breaks: list[dict[str, str]] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "mod_id": self.mod_id,
            "display_name": self.display_name,
            "version": self.version,
            "loader": self.loader,
            "mc_version": self.mc_version,
            "file": self.file,
            "path": self.path,
            "sha1": self.sha1,
            "dependencies": self.dependencies,
            "optional_dependencies": self.optional_dependencies,
            "conflicts": self.conflicts,
            "breaks": self.breaks,
        }


# ---------------------------------------------------------------- 版本范围匹配
_NUM_RE = re.compile(r"\d+")


def _tokens(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in _NUM_RE.findall(v or ""))


def _compare(a: str, b: str) -> int:
    ta, tb = _tokens(a), _tokens(b)
    n = max(len(ta), len(tb))
    for i in range(n):
        x = ta[i] if i < len(ta) else 0
        y = tb[i] if i < len(tb) else 0
        if x != y:
            return -1 if x < y else 1
    return 0


def _match_op(version: str, op: str, bound: str) -> bool:
    c = _compare(version, bound)
    if op in ("=", "=="):
        return c == 0
    if op == ">=":
        return c >= 0
    if op == "<=":
        return c <= 0
    if op == ">":
        return c > 0
    if op == "<":
        return c < 0
    if op == "~":  # ~1.2.3 => >=1.2.3, <1.3.0
        return c >= 0 and _compare(version, _bump_minor(bound)) < 0
    if op == "^":  # ^1.2.3 => >=1.2.3, <2.0.0
        return c >= 0 and _compare(version, _bump_major(bound)) < 0
    return False


def _bump_minor(v: str) -> str:
    parts = _NUM_RE.findall(v or "")
    if len(parts) >= 2:
        parts[1] = str(int(parts[1]) + 1)
        parts = parts[:2]
    return ".".join(parts)


def _bump_major(v: str) -> str:
    parts = _NUM_RE.findall(v or "")
    if parts:
        parts[0] = str(int(parts[0]) + 1)
        parts = parts[:1]
    return ".".join(parts)


def match_version(version: str, range_spec: str) -> bool:
    """宽松的版本范围匹配，兼容 Forge 的 [a,b) 与 Fabric 的 >=a / ~a / ^a / * / 精确。"""
    spec = (range_spec or "").strip()
    if not spec or spec == "*":
        return True
    if spec.startswith(("[", "(")):
        # Maven 风格区间：[a,b) / (a,b] / [a,) / (,b] / [a] / (a)
        m = re.match(r"^([\[(])([^,]*)(?:,([^)\]]*))?([)\]])$", spec)
        if m:
            lo_b, lo, hi, hi_b = m.groups()
            if hi is None:  # 无逗号的单值形式
                return _compare(version, lo) == 0 if lo_b == "[" else _compare(version, lo) != 0
            if lo:
                c = _compare(version, lo)
                if lo_b == "[" and c < 0:
                    return False
                if lo_b == "(" and c <= 0:
                    return False
            if hi:
                c = _compare(version, hi)
                if hi_b == "]" and c > 0:
                    return False
                if hi_b == ")" and c >= 0:
                    return False
            return True
    m = re.match(r"^\s*(>=|<=|==|=|>|<|~|\^)\s*(.+)$", spec)
    if m:
        return _match_op(version, m.group(1), m.group(2).strip())
    return _compare(version, spec) == 0


# ---------------------------------------------------------------- 解析器
def _parse_forge_toml(text: str, filename: str) -> list[ModEntry]:
    try:
        data = tomllib.loads(text)
    except Exception:
        return []
    mods = data.get("mods") or []
    deps_map: dict[str, list[dict[str, str]]] = data.get("dependencies") or {}
    out: list[ModEntry] = []
    for m in mods:
        mod_id = str(m.get("modId") or m.get("modid") or "")
        if not mod_id:
            continue
        deps: list[dict[str, str]] = []
        opt: list[dict[str, str]] = []
        conf: list[dict[str, str]] = []
        for d in deps_map.get(mod_id, []):
            dep = {
                "mod_id": str(d.get("modId", "")),
                "type": str(d.get("type", "required")),
                "version_range": str(d.get("versionRange", "*")),
                "ordering": str(d.get("ordering", "NONE")),
                "side": str(d.get("side", "BOTH")),
            }
            t = dep["type"]
            if t == "required":
                deps.append(dep)
            elif t == "optional":
                opt.append(dep)
            elif t in ("incompatible", "conflicts"):
                conf.append(dep)
        out.append(ModEntry(
            mod_id=mod_id,
            display_name=str(m.get("displayName", mod_id)),
            version=str(m.get("version", "")),
            loader="forge",
            mc_version=str(data.get("minecraftVersion", "") or data.get("minecraft", "")),
            dependencies=deps,
            optional_dependencies=opt,
            conflicts=conf,
            source={"toml_file": filename},
        ))
    return out


def _parse_fabric_json(text: str, filename: str) -> list[ModEntry]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    mod_id = str(data.get("id", ""))
    if not mod_id:
        return []
    deps: list[dict[str, str]] = []
    opt: list[dict[str, str]] = []
    conf: list[dict[str, str]] = []
    for group, target in (("depends", deps), ("suggests", opt)):
        for k, v in (data.get(group) or {}).items():
            target.append({
                "mod_id": str(k),
                "type": "required" if group == "depends" else "optional",
                "version_range": str(v),
            })
    for group, target in (("conflicts", conf), ("breaks", conf)):
        for k, v in (data.get(group) or {}).items():
            target.append({
                "mod_id": str(k),
                "type": "incompatible",
                "version_range": str(v),
            })
    return [ModEntry(
        mod_id=mod_id,
        display_name=str(data.get("name", mod_id)),
        version=str(data.get("version", "")),
        loader="fabric",
        mc_version="",
        dependencies=deps,
        optional_dependencies=opt,
        conflicts=conf,
        source={"json_file": filename},
    )]


def _parse_manifest(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        if line.startswith(" ") and out:
            out[list(out.keys())[-1]] += line.strip()
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def parse_mod_jar(jar_path: Path) -> ModEntry | None:
    """解析单个模组 jar。返回 None 表示该 jar 不含可识别模组元数据（可能是 lib/前置包）。"""
    try:
        with zipfile.ZipFile(jar_path) as z:
            names = set(z.namelist())
            entries: list[ModEntry] = []
            if "META-INF/mods.toml" in names:
                entries += _parse_forge_toml(z.read("META-INF/mods.toml").decode("utf-8", "replace"),
                                             "META-INF/mods.toml")
            if "META-INF/neoforge.mods.toml" in names:
                entries += _parse_forge_toml(z.read("META-INF/neoforge.mods.toml").decode("utf-8", "replace"),
                                             "META-INF/neoforge.mods.toml")
            if "fabric.mod.json" in names:
                entries += _parse_fabric_json(z.read("fabric.mod.json").decode("utf-8", "replace"),
                                              "fabric.mod.json")
            manifest: dict[str, str] = {}
            if "META-INF/MANIFEST.MF" in names:
                manifest = _parse_manifest(z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace"))
    except (zipfile.BadZipFile, OSError):
        return None

    if not entries:
        return None

    main = entries[0]
    # 多加载器并存：合并
    if len(entries) > 1:
        main.loader = "both"
        for extra in entries[1:]:
            if main.mod_id == extra.mod_id:
                main.optional_dependencies += extra.optional_dependencies
                main.conflicts += extra.conflicts
            else:
                main.optional_dependencies.append(
                    {"mod_id": extra.mod_id, "type": "optional", "version_range": "*"})
    if not main.version:
        main.version = manifest.get("Implementation-Version", "")
    if not main.display_name:
        main.display_name = manifest.get("Implementation-Title", main.mod_id)
    main.file = jar_path.name
    main.path = str(jar_path)
    main.sha1 = sha1_of(jar_path)
    return main


def parse_mods_dir(mods_dir: Path) -> list[ModEntry]:
    """解析 mods 目录下全部模组。"""
    if not mods_dir.is_dir():
        return []
    out: list[ModEntry] = []
    for p in sorted(mods_dir.glob("*.jar")):
        m = parse_mod_jar(p)
        if m:
            out.append(m)
    return out
