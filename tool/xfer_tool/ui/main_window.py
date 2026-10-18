"""XferTool 主窗口：存档列表、操作按钮、日志、IPC 守护。"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from .. import backup as backup_mod
from .. import downloader, ipc as ipc_mod, launchers, quarantine as quarantine_mod
from ..config import Config, default_workspace
from ..dependency import check_dependencies
from ..workspace import Workspace
from .dialogs import (DisclaimerDialog, InfoDialog, ProgressDialog, SavePairDialog)

log = logging.getLogger("xfer.ui")


class MainWindow(tk.Tk):
    def __init__(self, config: Config):
        super().__init__()
        self.cfg = config
        self.ws = Workspace(config.workspace)
        self.title("XferBridge 外部工具 — 跨存档迁移助手")
        self.geometry("1080x640")
        self.minsize(940, 520)

        self._daemon_stop = threading.Event()
        self._daemon_thread: threading.Thread | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._refresh_timer()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_log)

    # ------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="扫描存档", command=self._scan).pack(side="left", padx=3)
        ttk.Button(toolbar, text="依赖检查", command=self._check_deps).pack(side="left", padx=3)
        ttk.Button(toolbar, text="自动安装缺失模组", command=self._auto_install).pack(side="left", padx=3)
        ttk.Button(toolbar, text="备份", command=lambda: self._backup("full")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="增量备份", command=lambda: self._backup("incremental")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="回滚", command=self._rollback).pack(side="left", padx=3)
        ttk.Button(toolbar, text="导出隔离区(zip)", command=lambda: self._export("zip")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="导出隔离区(Base64)", command=lambda: self._export("base64")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="设置", command=self._settings).pack(side="right", padx=3)
        self._daemon_btn = ttk.Button(toolbar, text="启动 IPC 守护", command=self._toggle_daemon)
        self._daemon_btn.pack(side="right", padx=3)
        ttk.Label(toolbar, text="待处理请求:").pack(side="right", padx=(8, 2))
        self._pending_var = tk.StringVar(value="0")
        ttk.Label(toolbar, textvariable=self._pending_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        left = ttk.Frame(body)
        body.add(left, weight=2)
        cols = ("name", "version", "launcher", "mods", "xb")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c, w, t in (("name", 200, "存档"), ("version", 90, "版本"),
                        ("launcher", 110, "启动器"), ("mods", 70, "模组数"),
                        ("xb", 60, "已装桥")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_details())

        right = ttk.Frame(body, width=380)
        body.add(right, weight=1)
        self.detail = tk.Text(right, height=14, wrap="word", state="disabled",
                              font=("Microsoft YaHei UI", 9))
        self.detail.pack(fill="both", expand=True, pady=(0, 4))
        ttk.Label(right, text="运行日志", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        self.logbox = tk.Text(right, height=10, wrap="word", state="disabled",
                              font=("Consolas", 8), bg="#1e1e1e", fg="#d4d4d4")
        self.logbox.pack(fill="both", expand=True)

        self._saves: list[dict[str, Any]] = []
        self._load_index()

    # ------------------------------------------------------------ helpers
    def _log(self, msg: str) -> None:
        self._log_q.put(f"[{threading.current_thread().name}] {msg}")

    def _drain_log(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                self.logbox.configure(state="normal")
                self.logbox.insert("end", msg + "\n")
                self.logbox.see("end")
                self.logbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    def _refresh_timer(self) -> None:
        n = len(self.ws.pending_requests())
        self._pending_var.set(str(n))
        self.after(2000, self._refresh_timer)

    def _load_index(self) -> None:
        index = self.ws.read_json(self.ws.save_index())
        if isinstance(index, dict):
            self._saves = index.get("saves") or []
        self._render_tree()

    def _render_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for s in self._saves:
            self.tree.insert("", "end", iid=s["id"], values=(
                s.get("display_name", s["name"]),
                s.get("version", ""),
                s.get("launcher", ""),
                s.get("mod_count", 0),
                "是" if s.get("has_xferbridge") else "否",
            ))

    def _selected_save(self) -> dict[str, Any] | None:
        sel = self.tree.selection()
        if not sel:
            return None
        sid = sel[0]
        return next((s for s in self._saves if s["id"] == sid), None)

    def _show_details(self) -> None:
        s = self._selected_save()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if s:
            self.detail.insert("end",
                f"存档: {s.get('name')}\n"
                f"路径: {s.get('path')}\n"
                f"启动器: {s.get('launcher')} / 实例: {s.get('instance')}\n"
                f"版本: {s.get('version') or '未知'}\n"
                f"模组数: {s.get('mod_count', 0)}  已装 XferBridge: {'是' if s.get('has_xferbridge') else '否'}\n"
                f"玩家: {s.get('player_name') or '未知'} ({s.get('player_uuid') or '无'})\n"
                f"上次游玩: {s.get('last_played', 0)}\n\n"
                f"mods 目录: {s.get('mods_dir') or '无'}")
        self.detail.configure(state="disabled")

    # ------------------------------------------------------------ actions
    def _run_bg(self, fn, done=None) -> None:
        def wrapper() -> None:
            try:
                result = fn()
                if done:
                    self.after(0, lambda: done(result))
            except Exception as e:  # noqa: BLE001
                log.exception("后台任务失败")
                self._log(f"✗ 操作失败: {e}")
                self.after(0, lambda: InfoDialog(self, "操作失败", str(e)))
        threading.Thread(target=wrapper, daemon=True).start()

    def _scan(self) -> None:
        self._log("开始扫描存档…")

        def work() -> dict:
            index = launchers.build_index(self.cfg.custom_paths)
            self.ws.write_json(self.ws.save_index(), index)
            return index

        def done(index: dict) -> None:
            self._saves = index.get("saves") or []
            self._render_tree()
            self._log(f"扫描完成：找到 {len(self._saves)} 个存档")
        self._run_bg(work, done)

    def _check_deps(self) -> None:
        if len(self._saves) < 2:
            InfoDialog(self, "提示", "至少需要 2 个存档才能做依赖检查，请先扫描。")
            return
        SavePairDialog(self, self._saves, "依赖检查 — 选择源/目标存档",
                       self._do_check_deps)

    def _do_check_deps(self, src_id: str, tgt_id: str) -> None:
        def work() -> dict:
            from ..transfer import _resolve_save_by_scan
            src = _resolve_save_by_scan(self.ws, src_id)
            tgt = _resolve_save_by_scan(self.ws, tgt_id)
            if not src or not tgt:
                raise FileNotFoundError("存档解析失败，请重新扫描")
            report = check_dependencies(src.mods, tgt.mods, src.id, tgt.id)
            downloader.enrich_missing(report.missing, src.version or "1.20.1", "forge")
            return {"src": src_id, "tgt": tgt_id, "report": report.to_json()}

        def done(r: dict) -> None:
            rep = r["report"]
            lines = [f"依赖检查：{r['src']} → {r['tgt']}",
                     f"缺失前置: {len(rep['missing'])}  版本不匹配: {len(rep['version_mismatch'])}"
                     f"  冲突: {len(rep['conflicts'])}  重复: {len(rep['duplicates'])}"
                     f"  依赖环: {len(rep['cycles'])}",
                     "目标缺 XferBridge: " + ("是" if rep["target_missing_xferbridge"] else "否"), ""]
            for m in rep["missing"]:
                dl = "; ".join(d.get("url", "") for d in m.get("downloads", []))
                lines.append(f"缺失 {m['mod_id']} (被 {', '.join(m['required_by'])} 需要) "
                             f"范围 {m['version_range']}\n  下载: {dl or '无'}")
            for c in rep["conflicts"]:
                lines.append(f"冲突 {c['mod_id']} ↔ {c['with']}: {c['reason']}")
            for d in rep["duplicates"]:
                lines.append(f"重复模组 {d['mod_id']}: {', '.join(d['files'])}")
            for cyc in rep["cycles"]:
                lines.append(f"依赖环: {' → '.join(cyc)}")
            InfoDialog(self, "依赖检查结果", "\n".join(lines) or "无异常", width=96, height=26)
        self._run_bg(work, done)

    def _auto_install(self) -> None:
        if len(self._saves) < 2:
            InfoDialog(self, "提示", "至少需要 2 个存档，请先扫描。")
            return
        SavePairDialog(self, self._saves, "自动安装 — 源(缺什么) → 目标(装到哪)",
                       self._do_auto_install)

    def _do_auto_install(self, src_id: str, tgt_id: str) -> None:
        prog = ProgressDialog(self, "分析缺失模组…")

        def work() -> list[dict]:
            from ..transfer import _resolve_save_by_scan
            src = _resolve_save_by_scan(self.ws, src_id)
            tgt = _resolve_save_by_scan(self.ws, tgt_id)
            if not src or not tgt:
                raise FileNotFoundError("存档解析失败")
            report = check_dependencies(src.mods, tgt.mods, src.id, tgt.id)
            prog.update_progress(10, f"解析下载源 ({len(report.missing)} 个缺失)…")
            downloader.enrich_missing(report.missing, src.version or "1.20.1", "forge")
            return [m for m in report.missing if m.get("can_auto_install")] or report.missing

        def done(missing: list[dict]) -> None:
            prog.close()
            if not missing:
                InfoDialog(self, "自动安装", "目标存档没有缺失模组。")
                return
            DisclaimerDialog(
                self,
                title=f"将为 {tgt_id} 自动下载 {len(missing)} 个模组",
                on_start=lambda: self._run_auto_download(tgt_id, missing),
            )

        self._run_bg(work, done)

    def _run_auto_download(self, tgt_id: str, mods: list[dict]) -> None:
        from ..transfer import _resolve_save_by_scan
        prog = ProgressDialog(self, "自动下载到 .staging…")
        tgt = _resolve_save_by_scan(self.ws, tgt_id)

        def work() -> dict:
            if not tgt or not tgt.mods_dir:
                raise FileNotFoundError("目标实例没有 mods 目录")
            from .. import staging as staging_mod
            staged_dir = staging_mod.staging_dir(tgt.mods_dir)
            staged_dir.mkdir(parents=True, exist_ok=True)
            total = len(mods)
            ok, fail = [], []
            for i, mod in enumerate(mods):
                dl = next((d for d in (mod.get("downloads") or []) if d.get("source") != "manual"), None)
                if not dl:
                    fail.append((mod.get("mod_id"), "无自动下载源"))
                    continue
                prog.update_progress(int(i / total * 90),
                                     f"下载 {dl.get('filename', mod['mod_id'])} ({i + 1}/{total})")
                try:
                    mirror = self.ws.staging / dl["filename"]
                    downloader.download_file(
                        dl["url"], mirror, expected_sha1=dl.get("sha1", ""),
                        expected_md5=dl.get("md5", ""), expected_size=int(dl.get("size", 0) or 0))
                    staged = staging_mod.stage_file(mirror, tgt.mods_dir, dl["filename"])
                    ok.append({"mod_id": mod["mod_id"], "file": dl["filename"], "staged": str(staged)})
                except downloader.DownloadError as e:
                    fail.append((mod.get("mod_id"), str(e)))
            return {"ok": ok, "fail": fail, "staged_dir": str(staged_dir)}

        def done(r: dict) -> None:
            prog.close()
            lines = [f"下载完成：成功 {len(r['ok'])}，失败 {len(r['fail'])}",
                     f"暂存目录: {r['staged_dir']}", ""]
            for o in r["ok"]:
                lines.append(f"✔ {o['file']}")
            for mid, reason in r["fail"]:
                lines.append(f"✗ {mid}: {reason}")
            lines.append("")
            lines.append("缺失模组已下载完毕，需要重启游戏才能生效。")
            InfoDialog(self, "下载结果", "\n".join(lines), width=96, height=24)
        self._run_bg(work, done)

    def _backup(self, kind: str) -> None:
        s = self._selected_save()
        if not s:
            InfoDialog(self, "提示", "请先在列表中选择一个存档。")
            return
        label = "manual" if kind == "full" else None

        def work() -> dict:
            if kind == "incremental":
                return backup_mod.incremental_backup(Path(s["path"]), self.ws.backups, s["id"]) or {}
            return backup_mod.full_backup(Path(s["path"]), self.ws.backups, s["id"], label="manual")

        def done(r: dict) -> None:
            self._log(f"备份完成: {r.get('archive')}")
            InfoDialog(self, "备份完成",
                       f"备份文件: {r.get('archive', '无变化(增量)')}\n"
                       f"文件数: {r.get('file_count', r.get('changed_count', 0))}")
        self._run_bg(work, done)

    def _rollback(self) -> None:
        s = self._selected_save()
        if not s:
            InfoDialog(self, "提示", "请先在列表中选择一个存档。")
            return
        baks = backup_mod.list_backups(self.ws.backups, s["id"])
        if not baks:
            InfoDialog(self, "提示", "该存档没有任何备份。")
            return
        lines = ["选择要回滚到的备份（输入序号）:", ""]
        for i, b in enumerate(baks):
            lines.append(f"{i}: {b['backup_id']}  {b.get('kind', '?')}  {b.get('created_at', '')}  文件{b.get('file_count', '')}")
        InfoDialog(self, f"可用备份（{s['name']}）", "\n".join(lines), width=100, height=min(30, len(lines) + 4))

        import tkinter.simpledialog as sd
        idx = sd.askinteger("回滚", "输入备份序号：", parent=self, minvalue=0, maxvalue=len(baks) - 1)
        if idx is None:
            return
        backup_id = baks[idx]["backup_id"]
        prog = ProgressDialog(self, "正在回滚…")

        def work() -> dict:
            return backup_mod.restore(Path(s["path"]), self.ws.backups, s["id"], backup_id)

        def done(r: dict) -> None:
            prog.close()
            self._log(f"回滚完成: {r['backup_id']} (链 {r['chain']})")
            InfoDialog(self, "回滚完成",
                       f"已恢复到 {r['backup_id']}\n回滚前状态已保存为 {r['pre_rollback_id']}")
        self._run_bg(work, done)

    def _export(self, fmt: str) -> None:
        s = self._selected_save()
        if not s:
            InfoDialog(self, "提示", "请先在列表中选择一个存档。")
            return

        def work() -> dict:
            if fmt == "base64":
                return quarantine_mod.export_base64(Path(s["path"]), self.ws.quarantine, s["id"])
            return quarantine_mod.export_zip(Path(s["path"]), self.ws.quarantine, s["id"])

        def done(r: dict) -> None:
            if fmt == "base64":
                InfoDialog(self, "Base64 导出",
                           f"已写入: {r.get('path')}\n\nBase64 内容（前 500 字符）：\n{(r.get('base64') or '')[:500]}",
                           width=100, height=20)
            else:
                self._log(f"隔离区导出: {r.get('archive')}")
                InfoDialog(self, "导出完成", f"已导出: {r.get('archive')}")
        self._run_bg(work, done)

    def _settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("设置")
        win.resizable(False, False)
        tk.Label(win, text="工作区目录（与游戏内模组一致）",
                 font=("Microsoft YaHei UI", 10)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ws_var = tk.StringVar(value=str(self.cfg.workspace))
        tk.Entry(win, textvariable=ws_var, width=52).grid(row=0, column=1, padx=10, pady=8)
        tk.Label(win, text="额外扫描路径（每行一个，如启动器目录）",
                 font=("Microsoft YaHei UI", 10)).grid(row=1, column=0, padx=10, pady=8, sticky="nw")
        paths = tk.Text(win, width=52, height=5, font=("Consolas", 9))
        paths.grid(row=1, column=1, padx=10, pady=8)
        paths.insert("1.0", "\n".join(self.cfg.custom_paths))

        def save() -> None:
            self.cfg.workspace = Path(ws_var.get().strip()) or default_workspace()
            self.cfg.custom_paths = [p.strip() for p in paths.get("1.0", "end").splitlines() if p.strip()]
            self.cfg.save()
            self.ws = Workspace(self.cfg.workspace)
            self._log(f"设置已保存，工作区: {self.cfg.workspace}")
            win.destroy()
        tk.Button(win, text="保存", width=12, command=save,
                  font=("Microsoft YaHei UI", 10)).grid(row=2, column=1, pady=12, sticky="e")

    # ------------------------------------------------------------ daemon
    def _toggle_daemon(self) -> None:
        if self._daemon_thread and self._daemon_thread.is_alive():
            self._daemon_stop.set()
            self._daemon_btn.configure(text="启动 IPC 守护")
            self._log("IPC 守护已停止")
            return
        self._daemon_stop.clear()
        self._daemon_btn.configure(text="停止 IPC 守护")

        def loop() -> None:
            self._log("IPC 守护已启动，监听请求…")
            while not self._daemon_stop.is_set():
                try:
                    n = ipc_mod.run_once(self.ws)
                    if n:
                        self._log(f"已处理 {n} 个请求")
                        self.after(0, self._load_index)
                except Exception as e:  # noqa: BLE001
                    self._log(f"守护异常: {e}")
                self._daemon_stop.wait(1.0)
            self._log("IPC 守护退出")

        self._daemon_thread = threading.Thread(target=loop, daemon=True)
        self._daemon_thread.start()

    def _on_close(self) -> None:
        self._daemon_stop.set()
        self.destroy()
