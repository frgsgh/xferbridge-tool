"""modmeta / 版本匹配 测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xfer_tool.modmeta import match_version, parse_mod_jar, parse_mods_dir
from tests.helpers import make_fabric_jar, make_forge_jar


class TestVersionMatch(unittest.TestCase):
    def test_exact_and_range(self):
        self.assertTrue(match_version("1.20.1", "[1.20.1]"))
        self.assertFalse(match_version("1.21", "[1.20.1]"))
        self.assertTrue(match_version("47.2.0", "[47,)"))
        self.assertTrue(match_version("15.2.0.27", "[15.0,16.0)"))
        self.assertFalse(match_version("14.9.0", "[15.0,16.0)"))
        self.assertTrue(match_version("1.0", "*"))
        self.assertTrue(match_version("1.0", ""))

    def test_fabric_style(self):
        self.assertTrue(match_version("0.90.0+1.20.1", ">=0.14.21"))
        self.assertTrue(match_version("1.20.2", "~1.20.1"))
        self.assertFalse(match_version("1.21.0", "~1.20.1"))
        self.assertTrue(match_version("1.5.0", "^1.2.3"))
        self.assertFalse(match_version("2.5.0", "^1.2.3"))


class TestParseJar(unittest.TestCase):
    def test_forge_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "jei-15.2.0.27.jar"
            make_forge_jar(jar, "jei", "15.2.0.27", "Just Enough Items",
                           [("minecraft", "required", "[1.20.1]"), ("forge", "required", "[47,)")])
            m = parse_mod_jar(jar)
            self.assertIsNotNone(m)
            assert m
            self.assertEqual(m.mod_id, "jei")
            self.assertEqual(m.version, "15.2.0.27")
            self.assertEqual(m.display_name, "Just Enough Items")
            self.assertEqual(len(m.dependencies), 2)
            self.assertEqual(m.sha1, m.sha1)

    def test_fabric_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "fapi-0.90.0.jar"
            make_fabric_jar(jar, "fabric-api", "0.90.0+1.20.1", "Fabric API",
                            {"minecraft": "~1.20.1"})
            m = parse_mod_jar(jar)
            self.assertIsNotNone(m)
            assert m
            self.assertEqual(m.mod_id, "fabric-api")
            self.assertEqual(m.loader, "fabric")
            self.assertEqual(m.dependencies[0]["mod_id"], "minecraft")

    def test_parse_dir_and_bad_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "mods"
            d.mkdir()
            make_forge_jar(d / "a-1.0.jar", "moda", "1.0")
            (d / "notmod.jar").write_bytes(b"PK\x03\x04 this is not a real jar")
            mods = parse_mods_dir(d)
            self.assertEqual([m.mod_id for m in mods], ["moda"])


if __name__ == "__main__":
    unittest.main()
