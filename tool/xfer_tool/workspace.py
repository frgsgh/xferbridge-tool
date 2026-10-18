"""工作区工具：JSON 读写、请求/响应/事件信封、任务状态跟踪。"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from . import PROTOCOL

log = logging.getLogger("xfer.workspace")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        log.warning("JSON 解析失败: %s", path)
        return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class Workspace:
    def __init__(self, ws: Path):
        self.root = ws
        from .config import ensure_workspace_dirs
        ensure_workspace_dirs(ws)

    # ---------- 目录 ----------
    @property
    def requests(self) -> Path:
        return self.root / "requests"

    @property
    def responses(self) -> Path:
        return self.root / "responses"

    @property
    def events(self) -> Path:
        return self.root / "events"

    @property
    def plans(self) -> Path:
        return self.root / "plans"

    @property
    def transfers(self) -> Path:
        return self.root / "transfers"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def quarantine(self) -> Path:
        return self.root / "quarantine"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def new_uuid(self) -> str:
        return str(uuid.uuid4())

    def write_json(self, path: Path, data: Any) -> None:
        write_json(path, data)

    def read_json(self, path: Path) -> dict[str, Any] | list[Any] | None:
        return read_json(path)

    def save_index(self) -> Path:
        return self.root / "saves_index.json"

    # ---------- 信封 ----------
    @staticmethod
    def new_request(action: str, payload: dict[str, Any], sender: str = "tool") -> dict[str, Any]:
        return {
            "protocol": PROTOCOL,
            "request_id": str(uuid.uuid4()),
            "action": action,
            "from": sender,
            "created_at": now_iso(),
            "payload": payload,
        }

    def write_request(self, action: str, payload: dict[str, Any], sender: str = "tool") -> str:
        req = self.new_request(action, payload, sender)
        write_json(self.requests / f"req_{req['request_id']}.json", req)
        return req["request_id"]

    def write_response(self, request_id: str, ok: bool, result: Any = None, error: str | None = None) -> None:
        resp = {
            "protocol": PROTOCOL,
            "request_id": request_id,
            "ok": ok,
            "error": error,
            "result": result,
            "completed_at": now_iso(),
        }
        write_json(self.responses / f"resp_{request_id}.json", resp)

    def write_event(self, request_id: str, stage: str, percent: int, message: str) -> None:
        evt = {
            "protocol": PROTOCOL,
            "request_id": request_id,
            "stage": stage,
            "percent": int(percent),
            "message": message,
            "at": now_iso(),
        }
        write_json(self.events / f"evt_{request_id}_{int(time.time()*1000)}.json", evt)

    # ---------- 轮询 ----------
    def pending_requests(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.requests.glob("req_*.json")):
            data = read_json(p)
            if isinstance(data, dict):
                out.append(data)
        return out

    def response_for(self, request_id: str) -> dict[str, Any] | None:
        data = read_json(self.responses / f"resp_{request_id}.json")
        return data if isinstance(data, dict) else None

    def events_for(self, request_id: str, since_ms: int = 0) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.events.glob(f"evt_{request_id}_*.json")):
            try:
                ts = int(p.stem.split("_")[-1])
            except ValueError:
                ts = 0
            if ts >= since_ms:
                data = read_json(p)
                if isinstance(data, dict):
                    out.append(data)
        return out

    def latest_event(self, request_id: str) -> dict[str, Any] | None:
        evts = self.events_for(request_id)
        return evts[-1] if evts else None

    def consume_request(self, request_id: str) -> bool:
        p = self.requests / f"req_{request_id}.json"
        if p.exists():
            p.unlink()
            return True
        return False


class TransferTask:
    """一次跨存档迁移任务的状态跟踪（供 GUI / IPC 查询）。"""

    def __init__(self, ws: Workspace, transfer_id: str):
        self.ws = ws
        self.transfer_id = transfer_id
        self.dir = ws.transfers / transfer_id
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def state(self) -> dict[str, Any]:
        data = read_json(self.state_path)
        return data if isinstance(data, dict) else {"transfer_id": self.transfer_id, "stage": "created"}

    def update(self, **kw: Any) -> None:
        st = self.state()
        st.update(kw)
        st["updated_at"] = now_iso()
        write_json(self.state_path, st)

    def write_payload(self, payload: dict[str, Any]) -> Path:
        p = self.dir / "payload.json"
        write_json(p, payload)
        return p

    def write_decision(self, decision: dict[str, Any]) -> Path:
        p = self.dir / "decision.json"
        write_json(p, decision)
        return p

    def read_decision(self) -> dict[str, Any] | None:
        data = read_json(self.dir / "decision.json")
        return data if isinstance(data, dict) else None

    def read_payload(self) -> dict[str, Any] | None:
        data = read_json(self.dir / "payload.json")
        return data if isinstance(data, dict) else None
