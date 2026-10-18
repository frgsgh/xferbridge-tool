"""配置管理：工作区路径、自定义存档路径、下载设置、CurseForge API Key。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_DIR_NAME = "XferBridge"


def default_workspace() -> Path:
    """默认工作区 %APPDATA%\\XferBridge（与模组默认一致）。"""
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_DIR_NAME


@dataclass
class Config:
    workspace: Path = field(default_factory=default_workspace)
    custom_paths: list[str] = field(default_factory=list)
    download_mirror: str = "modrinth"
    max_retries: int = 3
    retry_delay_sec: float = 2.0
    incremental_throttle_sec: int = 60
    curseforge_api_key: str = ""  # 可选；不填则 CurseForge 链接仅展示手动入口

    def path(self) -> Path:
        return self.workspace / "config.json"

    def save(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        data = {
            "workspace": str(self.workspace),
            "custom_paths": self.custom_paths,
            "download_mirror": self.download_mirror,
            "max_retries": self.max_retries,
            "retry_delay_sec": self.retry_delay_sec,
            "incremental_throttle_sec": self.incremental_throttle_sec,
            "curseforge_api_key": self.curseforge_api_key,
        }
        self.path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, config_path: str | None = None) -> "Config":
        cfg = cls()
        if config_path:
            cfg.workspace = Path(config_path).parent
        try:
            raw = json.loads(cfg.path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw.get("workspace"), str):
            cfg.workspace = Path(raw["workspace"])
        cfg.custom_paths = [str(p) for p in raw.get("custom_paths", []) if isinstance(p, str)]
        cfg.download_mirror = str(raw.get("download_mirror", cfg.download_mirror))
        cfg.max_retries = int(raw.get("max_retries", cfg.max_retries))
        cfg.retry_delay_sec = float(raw.get("retry_delay_sec", cfg.retry_delay_sec))
        cfg.incremental_throttle_sec = int(raw.get("incremental_throttle_sec", cfg.incremental_throttle_sec))
        cfg.curseforge_api_key = str(raw.get("curseforge_api_key", ""))
        return cfg


def ensure_workspace_dirs(ws: Path) -> None:
    for sub in ("requests", "responses", "events", "plans", "transfers",
                "staging", "backups", "quarantine", "moddb", "logs"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
