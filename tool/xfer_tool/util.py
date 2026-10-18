"""通用工具函数。"""
from __future__ import annotations

import re

# Windows 文件名非法字符
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_id(identifier: str) -> str:
    """把存档 id（可能含 | 等非法字符）转为可安全用于目录/文件名的形式。"""
    cleaned = _INVALID.sub("_", identifier).strip(" .")
    return cleaned or "unknown"
