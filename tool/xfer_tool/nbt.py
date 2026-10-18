"""最小 NBT 读写器：用于解析 level.dat 与合并目标存档 playerdata。

- Minecraft Java 存档使用 GZip 压缩、大端序 NBT。
- Compound 表示为 dict；List 用 NBTList 保留元素类型以支持往返写入。
"""
from __future__ import annotations

import gzip
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

TAG_NAMES = {
    TAG_END: "End", TAG_BYTE: "Byte", TAG_SHORT: "Short", TAG_INT: "Int",
    TAG_LONG: "Long", TAG_FLOAT: "Float", TAG_DOUBLE: "Double",
    TAG_BYTE_ARRAY: "ByteArray", TAG_STRING: "String", TAG_LIST: "List",
    TAG_COMPOUND: "Compound", TAG_INT_ARRAY: "IntArray", TAG_LONG_ARRAY: "LongArray",
}


class NBTError(Exception):
    pass


@dataclass
class NBTList:
    elem_type: int
    items: list = field(default_factory=list)


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _need(self, n: int) -> None:
        if self.pos + n > len(self.data):
            raise NBTError(f"NBT 数据截断: 需要 {n} 字节, 剩余 {len(self.data) - self.pos}")

    def read(self, fmt: str) -> int:
        size = struct.calcsize(fmt)
        self._need(size)
        val = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return val

    def read_tag(self) -> tuple[int, str]:
        t = self.read(">b")
        if t == TAG_END:
            return t, ""
        n = self.read(">H")
        self._need(n)
        name = self.data[self.pos:self.pos + n].decode("utf-8", "replace")
        self.pos += n
        return t, name

    def read_payload(self, t: int) -> Any:
        if t == TAG_BYTE:
            return self.read(">b")
        if t == TAG_SHORT:
            return self.read(">h")
        if t == TAG_INT:
            return self.read(">i")
        if t == TAG_LONG:
            return self.read(">q")
        if t == TAG_FLOAT:
            return struct.unpack(">f", self._read_raw(4))[0]
        if t == TAG_DOUBLE:
            return struct.unpack(">d", self._read_raw(8))[0]
        if t == TAG_BYTE_ARRAY:
            n = self.read(">i")
            self._need(n)
            out = self.data[self.pos:self.pos + n]
            self.pos += n
            return out
        if t == TAG_STRING:
            n = self.read(">H")
            self._need(n)
            out = self.data[self.pos:self.pos + n].decode("utf-8", "replace")
            self.pos += n
            return out
        if t == TAG_LIST:
            elem = self.read(">b")
            n = self.read(">i")
            items = [self.read_payload(elem) for _ in range(n)]
            return NBTList(elem, items)
        if t == TAG_COMPOUND:
            out: dict[str, Any] = {}
            while True:
                et, name = self.read_tag()
                if et == TAG_END:
                    break
                out[name] = self.read_payload(et)
            return out
        if t == TAG_INT_ARRAY:
            n = self.read(">i")
            return list(struct.unpack(f">{n}i", self._read_raw(4 * n)))
        if t == TAG_LONG_ARRAY:
            n = self.read(">i")
            return list(struct.unpack(f">{n}q", self._read_raw(8 * n)))
        raise NBTError(f"未知 TAG 类型 {t}")

    def _read_raw(self, n: int) -> bytes:
        self._need(n)
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out


class _Writer:
    def __init__(self):
        self.buf = bytearray()

    def write(self, fmt: str, val) -> None:
        self.buf += struct.pack(fmt, val)

    def write_payload(self, t: int, val) -> None:
        if t == TAG_BYTE:
            self.write(">b", val)
        elif t == TAG_SHORT:
            self.write(">h", val)
        elif t == TAG_INT:
            self.write(">i", val)
        elif t == TAG_LONG:
            self.write(">q", val)
        elif t == TAG_FLOAT:
            self.buf += struct.pack(">f", val)
        elif t == TAG_DOUBLE:
            self.buf += struct.pack(">d", val)
        elif t == TAG_BYTE_ARRAY:
            self.write(">i", len(val))
            self.buf += val
        elif t == TAG_STRING:
            raw = str(val).encode("utf-8")
            self.write(">H", len(raw))
            self.buf += raw
        elif t == TAG_LIST:
            lst = val
            self.write(">b", lst.elem_type)
            self.write(">i", len(lst.items))
            for item in lst.items:
                self.write_payload(lst.elem_type, item)
        elif t == TAG_COMPOUND:
            for k, v in val.items():
                et = type_of(v)
                raw = k.encode("utf-8")
                self.buf += bytes([et]) + struct.pack(">H", len(raw)) + raw
                self.write_payload(et, v)
            self.buf += bytes([TAG_END])
        elif t == TAG_INT_ARRAY:
            self.write(">i", len(val))
            self.buf += struct.pack(f">{len(val)}i", *val)
        elif t == TAG_LONG_ARRAY:
            self.write(">i", len(val))
            self.buf += struct.pack(f">{len(val)}q", *val)
        else:
            raise NBTError(f"无法写入 TAG 类型 {t}")


def type_of(val) -> int:
    if isinstance(val, bool):
        return TAG_BYTE
    if isinstance(val, int):
        if -128 <= val <= 127:
            return TAG_BYTE
        if -32768 <= val <= 32767:
            return TAG_SHORT
        if -2147483648 <= val <= 2147483647:
            return TAG_INT
        return TAG_LONG
    if isinstance(val, float):
        return TAG_DOUBLE
    if isinstance(val, str):
        return TAG_STRING
    if isinstance(val, bytes):
        return TAG_BYTE_ARRAY
    if isinstance(val, NBTList):
        return TAG_LIST
    if isinstance(val, dict):
        return TAG_COMPOUND
    if isinstance(val, (list, tuple)):
        if all(isinstance(x, int) for x in val):
            return TAG_INT_ARRAY
        if all(isinstance(x, float) for x in val):
            return TAG_DOUBLE
        raise NBTError(f"无法推断 List 的 TAG 类型: {val!r}")
    raise NBTError(f"不支持的值类型: {type(val)!r}")


def read_nbt(data: bytes) -> tuple[str, dict | NBTList]:
    r = _Reader(data)
    t, name = r.read_tag()
    if t not in (TAG_COMPOUND, TAG_LIST):
        raise NBTError(f"根 TAG 必须是 Compound 或 List, 实际 {TAG_NAMES.get(t, t)}")
    return name, r.read_payload(t)


def write_nbt(name: str, tag) -> bytes:
    t = type_of(tag)
    w = _Writer()
    raw = name.encode("utf-8")
    w.buf += bytes([t]) + struct.pack(">H", len(raw)) + raw
    w.write_payload(t, tag)
    return bytes(w.buf)


def read_nbt_file(path: Path) -> tuple[str, dict | NBTList]:
    raw = path.read_bytes()
    try:
        data = gzip.decompress(raw)
    except (OSError, gzip.BadGzipFile, zlib.error):
        data = raw
    return read_nbt(data)


def write_nbt_gzip(path: Path, name: str, tag) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(write_nbt(name, tag), compresslevel=6))


def read_level_dat(path: Path) -> dict:
    """读取存档 level.dat，返回其中的 Data 复合标签。"""
    _, root = read_nbt_file(path)
    if isinstance(root, NBTList) or not isinstance(root, dict):
        raise NBTError("level.dat 根结构异常")
    data = root.get("Data")
    if not isinstance(data, dict):
        raise NBTError("level.dat 缺少 Data 标签")
    return data
