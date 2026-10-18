"""通用对话框：免责声明+验证码、进度、信息、双存档选择。"""
from __future__ import annotations

import random
import string
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

DISCLAIMER_TEXT = (
    "自动安装免责声明\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "1. 本工具将从 Modrinth 官方 API 下载第三方模组文件。\n"
    "2. 模组由第三方作者发布，工具仅负责下载与 SHA1/MD5 校验，\n"
    "   不对模组内容、安全性及兼容性负责。\n"
    "3. 安装缺失模组可能导致存档损坏、崩溃或数据丢失。\n"
    "4. 执行前工具会自动备份目标存档与 config 文件夹，\n"
    "   但请自行评估风险，重要存档建议额外手动备份。\n"
    "5. 下载文件先进入 .staging 暂存区，校验通过后才生效。\n"
    "6. 继续操作视为你已理解并接受以上风险。\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)


def _rand_captcha(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


class DisclaimerDialog(tk.Toplevel):
    """免责声明 + 「我已阅读并同意」勾选 + 随机验证码 + [开始自动下载]。"""

    def __init__(self, parent: tk.Misc, on_start: Callable[[], None],
                 title: str = "自动安装前置确认"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.on_start = on_start
        self.agreed = False

        box = tk.Text(self, width=64, height=16, wrap="word",
                      state="disabled", font=("Microsoft YaHei UI", 10))
        box.pack(padx=12, pady=(12, 6), fill="both", expand=True)
        box.configure(state="normal")
        box.insert("1.0", DISCLAIMER_TEXT)
        box.configure(state="disabled")

        self.agree_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(self, text="我已阅读并同意上述免责声明",
                             variable=self.agree_var, command=self._sync,
                             font=("Microsoft YaHei UI", 10))
        chk.pack(pady=(0, 6))

        cap_frame = tk.Frame(self)
        cap_frame.pack(pady=4)
        self.captcha = _rand_captcha()
        tk.Label(cap_frame, text=f"请输入验证码  {self.captcha}",
                 font=("Consolas", 12, "bold"), fg="#1f6feb").pack(side="left", padx=8)
        self.captcha_var = tk.StringVar()
        self.captcha_entry = tk.Entry(cap_frame, textvariable=self.captcha_var,
                                      width=12, font=("Consolas", 12))
        self.captcha_entry.pack(side="left", padx=8)
        self.captcha_entry.bind("<KeyRelease>", lambda e: self._sync())

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(6, 12))
        self.start_btn = tk.Button(btn_frame, text="开始自动下载", width=18,
                                   state="disabled", command=self._start,
                                   font=("Microsoft YaHei UI", 10))
        self.start_btn.pack(side="left", padx=6)
        tk.Button(btn_frame, text="取消", width=10, command=self.destroy,
                  font=("Microsoft YaHei UI", 10)).pack(side="left", padx=6)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _sync(self) -> None:
        ok = self.agree_var.get() and self.captcha_var.get().strip().upper() == self.captcha
        self.start_btn.configure(state="normal" if ok else "disabled")

    def _start(self) -> None:
        self.agreed = True
        self.on_start()
        self.destroy()


class ProgressDialog(tk.Toplevel):
    """带进度条与消息的对话框，线程安全（通过 after 更新）。"""

    def __init__(self, parent: tk.Misc, title: str = "处理中…"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self._msg = tk.StringVar(value="准备中…")
        tk.Label(self, textvariable=self._msg, font=("Microsoft YaHei UI", 10),
                 wraplength=420, justify="left").pack(padx=16, pady=(14, 6))
        self.bar = ttk.Progressbar(self, length=420, maximum=100)
        self.bar.pack(padx=16, pady=(0, 14))
        self._closed = False
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        self._closed = True
        self.destroy()

    def update_progress(self, percent: int, message: str) -> None:
        def _do() -> None:
            if self._closed:
                return
            self.bar["value"] = max(0, min(100, int(percent)))
            self._msg.set(message)
        try:
            self.after(0, _do)
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.after(0, self._close)
        except tk.TclError:
            pass


class SavePairDialog(tk.Toplevel):
    """选择「源存档 / 目标存档」两个下拉框。"""

    def __init__(self, parent: tk.Misc, saves: list[dict], title: str,
                 on_ok: Callable[[str, str], None]):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        names = {s["id"]: s.get("display_name", s["name"]) for s in saves}

        tk.Label(self, text="源存档（当前要迁移出的存档）",
                 font=("Microsoft YaHei UI", 10)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.src_var = tk.StringVar()
        src_cb = ttk.Combobox(self, textvariable=self.src_var, values=list(names.values()),
                              width=42, state="readonly")
        src_cb.grid(row=0, column=1, padx=10, pady=8)

        tk.Label(self, text="目标存档（要迁入的存档）",
                 font=("Microsoft YaHei UI", 10)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.tgt_var = tk.StringVar()
        tgt_cb = ttk.Combobox(self, textvariable=self.tgt_var, values=list(names.values()),
                              width=42, state="readonly")
        tgt_cb.grid(row=1, column=1, padx=10, pady=8)

        if names:
            src_cb.current(0)
            if len(names) > 1:
                tgt_cb.current(1)

        self._names = names
        self._reverse = {v: k for k, v in names.items()}
        btn = tk.Button(self, text="开始检查", width=14,
                        command=lambda: self._ok(on_ok), font=("Microsoft YaHei UI", 10))
        btn.grid(row=2, column=0, columnspan=2, pady=12)
        self._on_ok = on_ok

    def _ok(self, on_ok: Callable[[str, str], None]) -> None:
        src = self._reverse.get(self.src_var.get(), "")
        tgt = self._reverse.get(self.tgt_var.get(), "")
        if not src or not tgt:
            return
        self.destroy()
        on_ok(src, tgt)


class InfoDialog(tk.Toplevel):
    """滚动文本信息展示（依赖报告/备份列表等）。"""

    def __init__(self, parent: tk.Misc, title: str, text: str, width: int = 80, height: int = 22):
        super().__init__(parent)
        self.title(title)
        box = tk.Text(self, width=width, height=height, wrap="none",
                      font=("Consolas", 9))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", text)
        box.configure(state="disabled")
        tk.Button(self, text="关闭", width=12, command=self.destroy).pack(pady=6)
