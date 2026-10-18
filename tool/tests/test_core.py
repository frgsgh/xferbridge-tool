"""依赖检测、备份回滚、NBT 往返、存档扫描 测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xfer_tool.backup import full_backup, incremental_backup, list_backups, restore
from xfer_tool.dependency import check_dependencies
from xfer_tool.launchers import build_index
from xfer_tool.modmeta import ModEntry, match_version
from xfer_tool.nbt import NBTList, read_nbt, read_nbt_file, write_nbt, write_nbt_gzip
from tests.helpers import make_forge_jar, make_save


def _mod(mod_id, version, deps=None, conflicts=None):
    return ModEntry(mod_id=mod_id, display_name=mod_id, version=version,
                    dependencies=deps or [], conflicts=conflicts or [])


class TestDependency(unittest.TestCase):
    def test_missing_and_mismatch(self):
        src = [_mod("a", "1.0", [{"mod_id": "libx", "type": "required", "version_range": "[2.0,3.0)"}])]
        tgt = [_mod("libx", "1.5")]
        rep = check_dependencies(src, tgt)
        self.assertEqual(len(rep.missing), 0)  # libx 存在，不算缺失
        self.assertEqual(len(rep.version_mismatch), 1)
        self.assertEqual(rep.version_mismatch[0]["mod_id"], "libx")

    def test_conflict_duplicate_cycle(self):
        src = [_mod("a", "1.0", [{"mod_id": "b", "type": "required", "version_range": "*"}],
                     conflicts=[{"mod_id": "bad", "type": "incompatible", "version_range": "*"}]),
               _mod("b", "1.0", [{"mod_id": "a", "type": "required", "version_range": "*"}])]
        tgt = [_mod("bad", "1.0"), _mod("dup", "1.0"), _mod("dup", "1.1")]
        rep = check_dependencies(src, tgt)
        self.assertEqual(len(rep.cycles), 1)
        self.assertEqual(len(rep.conflicts), 1)
        self.assertEqual(rep.conflicts[0]["with"], "bad")
        self.assertEqual(len(rep.duplicates), 1)
        self.assertEqual(rep.duplicates[0]["mod_id"], "dup")

    def test_target_missing_xferbridge(self):
        rep = check_dependencies([], [])
        self.assertTrue(rep.target_missing_xferbridge)


class TestNBT(unittest.TestCase):
    def test_roundtrip(self):
        tag = {
            "Data": {
                "LevelName": "世界一",
                "LastPlayed": 1690000000000,
                "Players": NBTList(10, [{"name": "Steve", "Health": 20.0}]),
                "Flags": 0,
                "SpawnX": 100,
                "Ratio": 0.5,
            }
        }
        raw = write_nbt("", tag)
        name, out = read_nbt(raw)
        self.assertEqual(name, "")
        self.assertEqual(out["Data"]["LevelName"], "世界一")
        self.assertEqual(out["Data"]["LastPlayed"], 1690000000000)
        self.assertIsInstance(out["Data"]["Players"], NBTList)
        self.assertEqual(out["Data"]["Players"].items[0]["Health"], 20.0)

    def test_gzip_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "level.dat"
            write_nbt_gzip(p, "", {"Data": {"LevelName": "w"}})
            _, root = read_nbt_file(p)
            self.assertEqual(root["Data"]["LevelName"], "w")


class TestBackup(unittest.TestCase):
    def test_full_incr_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save = root / "saves" / "world1"
            save.mkdir(parents=True)
            (save / "region").mkdir(parents=True)
            (save / "level.dat").write_bytes(b"L1")
            (save / "region" / "r.0.0.mca").write_bytes(b"R1")
            baks = root / "backups"

            f = full_backup(save, baks, "w1")
            self.assertTrue(Path(f["archive"]).is_file())

            (save / "region" / "r.0.0.mca").write_bytes(b"R2-CHANGED")
            (save / "level.dat").write_bytes(b"L2")
            inc = incremental_backup(save, baks, "w1")
            self.assertIsNotNone(inc)
            assert inc
            self.assertEqual(inc["changed_count"], 2)

            restore(save, baks, "w1", f["backup_id"])
            self.assertEqual((save / "level.dat").read_bytes(), b"L1")
            self.assertEqual((save / "region" / "r.0.0.mca").read_bytes(), b"R1")
            self.assertGreaterEqual(len(list_backups(baks, "w1")), 2)


class TestScan(unittest.TestCase):
    def test_scan_fake_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = root / "saves" / "world1"
            make_save(world, "world1", mods=[], config_files={"moda.toml": "a=1\n"})
            root_mods = root / "mods"
            root_mods.mkdir(exist_ok=True)
            make_forge_jar(root_mods / "moda-1.0.jar", "moda", "1.0")
            index = build_index([str(root)])
            self.assertGreaterEqual(len(index["saves"]), 1)
            found = next(s for s in index["saves"] if s["name"] == "world1")
            self.assertEqual(found["mod_count"], 1)
            self.assertEqual(found["mods"][0]["mod_id"], "moda")


if __name__ == "__main__":
    unittest.main()
