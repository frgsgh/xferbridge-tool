"""测试辅助：构造合成模组 jar 与合成存档。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

MODS_TOML = """modLoader="javafml"
loaderVersion="[47,)"
license="test"
[[mods]]
modId="{mod_id}"
version="{version}"
displayName="{display}"
[[dependencies.{mod_id}]]
modId="{dep}"
type="{dep_type}"
versionRange="{dep_range}"
"""


def make_forge_jar(path: Path, mod_id: str, version: str, display: str | None = None,
                   deps: list[tuple[str, str, str]] | None = None) -> None:
    """deps: (dep_mod_id, type, version_range)"""
    display = display or mod_id
    deps = deps or [("minecraft", "required", "[1.20.1]"), ("forge", "required", "[47,)")]
    sections = [MODS_TOML.format(mod_id=mod_id, version=version, display=display,
                                 dep=d, dep_type=t, dep_range=r) for d, t, r in deps]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/mods.toml", "\n".join(sections))
        z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nImplementation-Title: {display}\nImplementation-Version: {version}\n")


def make_fabric_jar(path: Path, mod_id: str, version: str, display: str | None = None,
                    depends: dict[str, str] | None = None) -> None:
    data = {
        "id": mod_id, "version": version, "name": display or mod_id,
        "depends": depends or {"minecraft": "~1.20.1"},
        "conflicts": {}, "breaks": {},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("fabric.mod.json", json.dumps(data, indent=2))


def make_save(save_dir: Path, name: str, mods: list[tuple[str, str]] | None = None,
              config_files: dict[str, str] | None = None) -> Path:
    """mods: (mod_id, version)；config_files: {相对路径: 内容}。"""
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / "level.dat").write_bytes(b"\x1f\x8b\x08\x00fake-level-dat")
    mods_dir = save_dir / "mods"
    mods_dir.mkdir(exist_ok=True)
    for mid, ver in (mods or []):
        make_forge_jar(mods_dir / f"{mid}-{ver}.jar", mid, ver)
    cfg = save_dir / "config"
    cfg.mkdir(exist_ok=True)
    for rel, content in (config_files or {}).items():
        p = cfg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return save_dir
