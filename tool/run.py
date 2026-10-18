"""XferBridge 外部工具启动入口。

用法:
    python run.py           启动图形界面
    python run.py --daemon  仅启动 IPC 守护（无界面）
    python run.py --scan    仅扫描存档并输出索引
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="XferBridge 跨存档迁移外部工具")
    parser.add_argument("--daemon", action="store_true", help="仅启动 IPC 守护模式")
    parser.add_argument("--scan", action="store_true", help="扫描存档并输出索引到工作区")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径（默认 %APPDATA%\\XferBridge\\config.json）")
    args = parser.parse_args()

    setup_logging()
    from xfer_tool.config import Config, ensure_workspace_dirs
    from xfer_tool.workspace import Workspace

    cfg = Config.load(args.config)
    ensure_workspace_dirs(cfg.workspace)
    ws = Workspace(cfg.workspace)
    logging.getLogger("xfer").info("工作区: %s", cfg.workspace)

    if args.scan:
        from xfer_tool import launchers
        index = launchers.build_index(cfg.custom_paths)
        ws.write_json(ws.save_index(), index)
        print(f"扫描完成：{len(index['saves'])} 个存档 -> {ws.save_index()}")
        return 0

    if args.daemon:
        from xfer_tool import ipc
        ipc.run_forever(ws)
        return 0

    try:
        from xfer_tool.ui.main_window import MainWindow
        MainWindow(cfg).mainloop()
    except Exception as e:  # noqa: BLE001
        logging.getLogger("xfer").exception("GUI 启动失败: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
