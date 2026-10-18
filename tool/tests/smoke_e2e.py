"""端到端冒烟：构造合成存档 → 扫描 → IPC 请求（check_deps/backup/rollback）→ 验证响应。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xfer_tool import ipc, launchers
from xfer_tool.config import Config
from xfer_tool.workspace import Workspace
from tests.helpers import make_forge_jar, make_save


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ws_dir = root / "workspace"
        cfg = Config(workspace=ws_dir)
        ws = Workspace(ws_dir)

        # 合成实例 A（moda + libx）与实例 B（libx 老版本）
        mc_a = root / "mcA"
        mc_b = root / "mcB"
        save_a = mc_a / "saves" / "worldA"
        save_b = mc_b / "saves" / "worldB"
        make_save(save_a, "worldA", mods=[], config_files={"moda.toml": "k=v\n"})
        make_save(save_b, "worldB", mods=[])
        mods_a = mc_a / "mods"
        mods_a.mkdir(parents=True, exist_ok=True)
        make_forge_jar(mods_a / "moda-1.0.jar", "moda", "1.0",
                       deps=[("minecraft", "required", "[1.20.1]"),
                             ("forge", "required", "[47,)"),
                             ("libx", "required", "[2.0,3.0)")])
        make_forge_jar(mods_a / "libx-2.1.jar", "libx", "2.1")
        mods_b = mc_b / "mods"
        mods_b.mkdir(parents=True, exist_ok=True)  # B 无任何模组 → libx 缺失
        # 扫描
        index = launchers.build_index([str(mc_a), str(mc_b)])
        ws.write_json(ws.save_index(), index)
        saves = {s["name"]: s["id"] for s in index["saves"]}
        assert "worldA" in saves and "worldB" in saves, saves
        print(f"[1] 扫描 OK: {len(index['saves'])} 个存档")

        # IPC: check_deps
        rid = ws.write_request("check_deps", {
            "source_save": saves["worldA"], "target_save": saves["worldB"]})
        assert ipc.run_once(ws) == 1
        resp = ws.response_for(rid)
        assert resp and resp["ok"], resp
        missing = resp["result"]["missing"]
        assert any(m["mod_id"] == "libx" for m in missing), missing
        print(f"[2] check_deps OK: 缺失 {len(missing)} 个，含 libx")

        # IPC: backup full + rollback
        rid = ws.write_request("backup", {"save_id": saves["worldB"], "kind": "full"})
        ipc.run_once(ws)
        resp = ws.response_for(rid)
        assert resp and resp["ok"], resp
        backup_id = resp["result"]["backup_id"]
        # 破坏 worldB
        (save_b / "level.dat").write_bytes(b"BROKEN")
        rid = ws.write_request("rollback", {"save_id": saves["worldB"], "backup_id": backup_id})
        ipc.run_once(ws)
        resp = ws.response_for(rid)
        assert resp and resp["ok"], resp
        print(f"[3] backup+rollback OK: {backup_id}")

        # IPC: export quarantine base64
        rid = ws.write_request("export_quarantine", {"save_id": saves["worldB"], "format": "base64"})
        ipc.run_once(ws)
        resp = ws.response_for(rid)
        assert resp and resp["ok"] and resp["result"].get("base64"), resp
        print("[4] export_quarantine base64 OK")

        print("端到端冒烟全部通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
