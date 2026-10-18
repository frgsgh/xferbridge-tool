"""暂存区机制：所有下载先进入 .staging，校验通过后才原子移入 mods/。"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("xfer.staging")

STAGING_DIR_NAME = ".staging"


def staging_dir(mods_dir: Path) -> Path:
    """目标实例 mods 目录下的 .staging 隐藏暂存文件夹。"""
    return mods_dir / STAGING_DIR_NAME


def stage_file(downloaded: Path, mods_dir: Path, filename: str) -> Path:
    """把已校验文件放入暂存区（工作区镜像或 .staging）。"""
    target = staging_dir(mods_dir) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(downloaded, target)
    return target


def list_staged(mods_dir: Path) -> list[Path]:
    d = staging_dir(mods_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".jar")


def install_staged(mods_dir: Path, filename: str | None = None) -> list[Path]:
    """把 .staging 中的 jar 原子移入 mods/，返回已安装文件。"""
    d = staging_dir(mods_dir)
    if not d.is_dir():
        return []
    installed: list[Path] = []
    for p in sorted(d.iterdir()):
        if p.suffix != ".jar":
            continue
        if filename and p.name != filename:
            continue
        target = mods_dir / p.name
        try:
            os.replace(p, target)
            installed.append(target)
            log.info("已安装到 mods: %s", target.name)
        except OSError as e:
            log.error("安装失败 %s: %s", p.name, e)
    return installed


def clear_staging(mods_dir: Path) -> None:
    d = staging_dir(mods_dir)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
