# -*- coding: utf-8 -*-
"""
main_gui.py
QQFarmHelper 2.0 图形界面入口（农场主题现代版）

运行：
    python main_gui.py
"""

from __future__ import annotations

import logging
import threading
import math
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from state_machine import FarmStateMachine, load_runtime_config

APP_NAME = "QQFarmHelper"
APP_SUBTITLE = "QQ 经典农场 · 自动辅助工具"

# ========== 农场主题配色 ==========
PRIMARY = "#4ade80"        # 农场绿
PRIMARY_DARK = "#16a34a"   # 深绿
PRIMARY_DIM = "#0d5c2e"    # 暗绿
GOLD = "#fbbf24"           # 农作物金
GOLD_DIM = "#92600a"       # 暗金

BG_ROOT = "#0c120d"        # 深绿黑背景
BG_CARD = "#15201a"        # 卡片背景
BG_CARD_HOVER = "#1c2b22"  # 卡片悬停
BG_LOG = "#0a0f0b"         # 日志背景
BORDER = "#24352a"         # 边框

TEXT_PRIMARY = "#e8f0e9"   # 主文字
TEXT_SECONDARY = "#6b8070"  # 次文字
TEXT_MUTED = "#4a5c4e"      # 弱化文字

SUCCESS = "#4ade80"
WARNING = "#fbbf24"
ERROR = "#f87171"
INFO = "#60a5fa"


# ========== 顶部渐变标题栏 ==========
class GradientHeader(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, height=90, fg_color="transparent", **kwargs)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, height=90, highlightthickness=0, bd=0, bg=BG_ROOT)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None, **kwargs):
        if not hasattr(self, "canvas"):
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.delete("all")
        # 绿色渐变背景
        for i in range(h):
            ratio = i / max(1, h)
            r = int(12 + (21 - 12) * ratio)
            g = int(18 + (32 - 18) * ratio)
            b = int(13 + (26 - 13) * ratio)
            self.canvas.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")
        # 底部装饰线
        self.canvas.create_line(0, h - 1, w, h - 1, fill=PRIMARY_DIM, width=2)
        # 左侧图标圆点（装饰）
        self.canvas.create_oval(20, 28, 44, 52, fill=PRIMARY, outline="")
        self.canvas.create_oval(26, 34, 38, 46, fill=BG_ROOT, outline="")
        self.canvas.create_text(32, 40, text="🌱", font=("Segoe UI Emoji", 14))
        # 标题
        self.canvas.create_text(
            56, 32, text=APP_NAME,
            fill=TEXT_PRIMARY, font=("Microsoft YaHei UI", 18, "bold"),
            anchor="w",
        )
        # 副标题
        self.canvas.create_text(
            56, 58, text=APP_SUBTITLE,
            fill=TEXT_SECONDARY, font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        # 右侧版本标签
        self.canvas.create_text(
            w - 16, 40, text="v2.0",
            fill=PRIMARY, font=("Consolas", 11, "bold"),
            anchor="e",
        )


# ========== 状态指示灯 ==========
class StatusLED(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.canvas = tk.Canvas(self, width=14, height=14, highlightthickness=0, bd=0, bg=BG_CARD)
        self.canvas.pack(side=tk.LEFT)
        self.color = TEXT_MUTED
        self.pulse = 0
        self._animating = False
        self._draw_static()

    def _draw_static(self):
        self.canvas.delete("all")
        self.canvas.create_oval(1, 1, 13, 13, fill=self.color, outline="")

    def set_color(self, color: str):
        self.color = color
        self._animating = False
        self._draw_static()

    def pulse_on(self, color: str):
        self.color = color
        self.pulse = 0
        self._animating = True
        self._animate()

    def pulse_off(self):
        self._animating = False
        self.color = TEXT_MUTED
        self._draw_static()

    def _animate(self):
        if not self._animating:
            return
        self.pulse = (self.pulse + 1) % 20
        brightness = 0.45 + 0.55 * math.sin(self.pulse * math.pi / 10)
        r = min(255, int(int(self.color[1:3], 16) * brightness))
        g = min(255, int(int(self.color[3:5], 16) * brightness))
        b = min(255, int(int(self.color[5:7], 16) * brightness))
        glow = f"#{r:02x}{g:02x}{b:02x}"
        self.canvas.delete("all")
        self.canvas.create_oval(0, 0, 14, 14, fill=glow, outline=self.color, width=1)
        self.after(80, self._animate)


# ========== 统计卡片（支持可选进度条） ==========
class StatCard(ctk.CTkFrame):
    def __init__(self, master, label: str, accent: str = PRIMARY,
                 show_progress: bool = False, **kwargs):
        super().__init__(master, fg_color=BG_CARD, corner_radius=14,
                         border_width=1, border_color=BORDER, **kwargs)
        self.pack_propagate(False)
        self.accent = accent
        self.show_progress = show_progress

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        # 标签
        ctk.CTkLabel(
            inner, text=label,
            font=("Microsoft YaHei UI", 9),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w")

        # 数值
        self.value_var = tk.StringVar(value="0")
        self.value_label = ctk.CTkLabel(
            inner, textvariable=self.value_var,
            font=("Consolas", 28, "bold"),
            text_color=accent,
        )
        self.value_label.pack(anchor="w", pady=(2, 0))

        # 进度条（可选）
        if show_progress:
            self.progress_var = tk.StringVar(value="0/35")
            ctk.CTkLabel(
                inner, textvariable=self.progress_var,
                font=("Consolas", 9),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", pady=(0, 4))
            self.progress_bar = ctk.CTkProgressBar(
                inner, height=6, corner_radius=3,
                fg_color=BG_LOG, progress_color=accent,
            )
            self.progress_bar.pack(fill=tk.X, pady=(0, 2))
            self.progress_bar.set(0)

    def set_value(self, val: int):
        self.value_var.set(str(val))

    def set_progress(self, current: int, total: int):
        if hasattr(self, "progress_var"):
            self.progress_var.set(f"{current}/{total}")
        if hasattr(self, "progress_bar"):
            self.progress_bar.set(min(1.0, current / max(1, total)))


# ========== 主界面 ==========
class QQFarmHelperGUI:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("520x680")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG_ROOT)

        self.paused = True
        self.stopped = False
        self.worker: threading.Thread | None = None
        self.bot: FarmStateMachine | None = None
        self.last_error = ""
        self.started_once = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.after(500, self.refresh_ui)

    def _build_ui(self) -> None:
        # 顶部标题栏
        GradientHeader(self.root).pack(fill=tk.X)

        # 主内容区
        content = ctk.CTkFrame(self.root, fg_color=BG_ROOT)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 14))

        # ---- 状态行 ----
        status_row = ctk.CTkFrame(content, fg_color=BG_CARD, corner_radius=10,
                                   border_width=1, border_color=BORDER)
        status_row.pack(fill=tk.X, pady=(0, 12))
        status_inner = ctk.CTkFrame(status_row, fg_color="transparent")
        status_inner.pack(fill=tk.X, padx=12, pady=8)

        self.led = StatusLED(status_inner)
        self.led.pack(side=tk.LEFT, padx=(0, 8))

        self.status_var = tk.StringVar(value="未启动")
        ctk.CTkLabel(
            status_inner, textvariable=self.status_var,
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        self.time_var = tk.StringVar(value="循环 0 | 异常 0 | 务农 0/35")
        ctk.CTkLabel(
            status_inner, textvariable=self.time_var,
            font=("Consolas", 10),
            text_color=TEXT_SECONDARY,
        ).pack(side=tk.RIGHT)

        # ---- 统计卡片 2x2 ----
        stats_grid = ctk.CTkFrame(content, fg_color="transparent")
        stats_grid.pack(fill=tk.X, pady=(0, 12))

        # 第一行
        row1 = ctk.CTkFrame(stats_grid, fg_color="transparent")
        row1.pack(fill=tk.X, pady=(0, 8))

        self.card_visits = StatCard(row1, "访问好友", accent=INFO, height=90)
        self.card_visits.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.card_picks = StatCard(row1, "摘取次数", accent=GOLD, height=90)
        self.card_picks.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

        # 第二行
        row2 = ctk.CTkFrame(stats_grid, fg_color="transparent")
        row2.pack(fill=tk.X)

        self.card_skips = StatCard(row2, "今日务农", accent=PRIMARY,
                                    show_progress=True, height=100)
        self.card_skips.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.card_empty = StatCard(row2, "空地/无菜", accent=TEXT_SECONDARY, height=100)
        self.card_empty.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

        # ---- 日志区 ----
        log_frame = ctk.CTkFrame(content, fg_color=BG_CARD, corner_radius=14,
                                  border_width=1, border_color=BORDER)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill=tk.X, padx=14, pady=(10, 4))
        ctk.CTkLabel(
            log_header, text="运行日志",
            font=("Microsoft YaHei UI", 10, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            log_header, text="实时输出",
            font=("Consolas", 8),
            text_color=TEXT_MUTED,
        ).pack(side=tk.RIGHT)

        self.log_text = ctk.CTkTextbox(
            log_frame,
            fg_color=BG_LOG,
            text_color=TEXT_PRIMARY,
            font=("Consolas", 10),
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
            height=120,
            scrollbar_button_color=PRIMARY_DIM,
            scrollbar_button_hover_color=PRIMARY_DARK,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self._log("系统就绪，等待启动...")

        # ---- 按钮区 ----
        button_frame = ctk.CTkFrame(content, fg_color="transparent")
        button_frame.pack(fill=tk.X, pady=(0, 8))

        self.btn_start = ctk.CTkButton(
            button_frame, text="▶  开始运行",
            fg_color=PRIMARY_DARK, hover_color=PRIMARY,
            text_color="white", corner_radius=12,
            font=("Microsoft YaHei UI", 13, "bold"),
            height=46, command=self.on_start,
        )
        self.btn_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.btn_pause = ctk.CTkButton(
            button_frame, text="⏸  暂停",
            fg_color="#2d3a30", hover_color="#3d4d40",
            text_color=TEXT_PRIMARY, corner_radius=12,
            font=("Microsoft YaHei UI", 12, "bold"),
            height=46, command=self.on_pause,
        )
        self.btn_pause.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.btn_exit = ctk.CTkButton(
            button_frame, text="⏹  退出",
            fg_color="#7f1d1d", hover_color="#991b1b",
            text_color="white", corner_radius=12,
            font=("Microsoft YaHei UI", 12, "bold"),
            height=46, command=self.on_exit,
        )
        self.btn_exit.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ---- 底部提示 ----
        self.tip_var = tk.StringVar(value="提示：先打开 QQ经典农场 窗口，再点击开始运行")
        ctk.CTkLabel(
            content, textvariable=self.tip_var,
            font=("Microsoft YaHei UI", 9),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"  {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def setup_logging(self) -> None:
        """配置日志：输出到文件、控制台和 GUI 日志框，级别 INFO。"""
        from pathlib import Path
        import re

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        # 1. 文件日志（按日期命名，追加写入，保留最近3天）
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        today_str = time.strftime("%Y-%m-%d")
        log_file = log_dir / f"gui_runtime_{today_str}.log"
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # 清理超过3天的旧日志文件
        try:
            cutoff = time.time() - 3 * 86400
            for old_file in log_dir.glob("gui_runtime_*.log"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", old_file.name)
                if m:
                    try:
                        file_time = time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
                        if file_time < cutoff:
                            old_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. 控制台日志
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 3. GUI 日志框
        class _GUILogHandler(logging.Handler):
            def __init__(self, gui):
                super().__init__()
                self.gui = gui

            def emit(self, record):
                msg = self.format(record)
                try:
                    self.gui.root.after(0, lambda m=msg: self.gui._log(m))
                except Exception:
                    pass

        gui_handler = _GUILogHandler(self)
        gui_handler.setLevel(logging.INFO)
        gui_handler.setFormatter(formatter)
        root_logger.addHandler(gui_handler)

    def is_worker_alive(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def on_start(self) -> None:
        self.setup_logging()

        if self.is_worker_alive():
            self.paused = False
            self._log("已恢复运行")
            self.led.pulse_on(SUCCESS)
            return

        self.paused = False
        self.stopped = False
        self.last_error = ""
        self.started_once = True

        try:
            config = load_runtime_config("config_runtime.json")
            self.bot = FarmStateMachine(config=config)
        except Exception as e:
            self.last_error = repr(e)
            messagebox.showerror("启动失败", f"初始化失败：\n{e}")
            self.paused = True
            return

        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()
        self._log("启动成功，正在运行...")
        self.led.pulse_on(SUCCESS)

    def on_pause(self) -> None:
        if not self.started_once:
            self._log("尚未启动")
            return

        self.paused = True
        self._log("已暂停")
        self.led.set_color(WARNING)

    def on_exit(self) -> None:
        self.paused = False
        self.stopped = True
        self.status_var.set("正在退出...")
        self._log("正在退出...")
        self.led.set_color(ERROR)

        try:
            if self.bot is not None:
                self.bot.close()
        except Exception:
            pass

        self.root.after(300, self.root.destroy)

    def _run_worker(self) -> None:
        try:
            assert self.bot is not None
            self.bot.run_loop(
                should_pause=lambda: self.paused,
                should_stop=lambda: self.stopped,
            )
        except Exception as e:
            self.last_error = repr(e)
        finally:
            self.paused = True

    def refresh_ui(self) -> None:
        if self.stopped:
            return

        alive = self.is_worker_alive()

        if not self.started_once:
            self.status_var.set("未启动")
            self.led.set_color(TEXT_MUTED)
        elif self.last_error:
            self.status_var.set("异常")
            self.led.set_color(ERROR)
        elif alive and self.paused:
            self.status_var.set("已暂停")
            self.led.set_color(WARNING)
        elif alive and not self.paused:
            self.status_var.set("运行中")
        elif self.started_once and not alive:
            self.status_var.set("已结束")
            self._log("后台任务已结束")
            self.led.set_color(TEXT_MUTED)

        if self.bot is not None:
            s = self.bot.stats
            farm_limit = int(self.bot.config.get("farm", {}).get("daily_limit", 35))
            farm_count = getattr(self.bot, "farm_count_today", 0)
            self.card_visits.set_value(s.visits)
            self.card_picks.set_value(s.picks)
            self.card_skips.set_value(farm_count)
            self.card_skips.set_progress(farm_count, farm_limit)
            self.card_empty.set_value(s.no_pick)
            self.time_var.set(
                f"循环 {s.cycles} | 异常 {s.errors} | 务农 {farm_count}/{farm_limit}"
            )

        self.root.after(500, self.refresh_ui)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")

    root = ctk.CTk()
    QQFarmHelperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
