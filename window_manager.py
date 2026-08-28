# -*- coding: utf-8 -*-
"""
window_manager.py
自动寻找 QQ经典农场窗口，并返回“客户区”坐标。

依赖：
    pip install pywin32

说明：
    - 优先使用客户区 client rect，避免把 Win11 标题栏算进截图。
    - 所有坐标均为屏幕物理像素坐标。
    - 程序启动时会尝试设置 DPI Awareness，减少 Windows 缩放导致的坐标偏差。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
import ctypes
import logging
import os
import time

import win32con
import win32gui

LOGGER = logging.getLogger("qq_farm_helper.window")


DEFAULT_WINDOW_KEYWORDS = [
    "QQ经典农场",
    "MuMu",
    "雷电模拟器",
    "腾讯手游助手",
]


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def tuple(self) -> Tuple[int, int, int, int]:
        """返回 left, top, right, bottom。"""
        return (self.left, self.top, self.right, self.bottom)

    @property
    def mss_dict(self) -> dict:
        """返回 mss 截图可用的 region dict。"""
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    title: str
    window_rect: Rect
    client_rect: Rect

    @property
    def is_valid(self) -> bool:
        return bool(self.hwnd) and win32gui.IsWindow(self.hwnd)


def set_dpi_awareness() -> None:
    """
    设置进程 DPI 感知，避免 125%/150% 缩放下截图坐标和点击坐标错位。
    多次调用也没关系。
    """
    try:
        # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            # Windows 7+
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _get_window_rect(hwnd: int) -> Rect:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return Rect(left, top, max(0, right - left), max(0, bottom - top))


def _get_client_rect_on_screen(hwnd: int) -> Rect:
    """
    获取窗口客户区在屏幕上的位置。
    客户区不包含标题栏、边框。推荐截图和相对坐标都基于客户区。
    """
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
    screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return Rect(
        screen_left,
        screen_top,
        max(0, screen_right - screen_left),
        max(0, screen_bottom - screen_top),
    )


def is_normal_window(hwnd: int, min_width: int = 300, min_height: int = 300) -> bool:
    if not win32gui.IsWindow(hwnd):
        return False
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if win32gui.IsIconic(hwnd):
        return False

    title = win32gui.GetWindowText(hwnd).strip()
    if not title:
        return False

    rect = _get_window_rect(hwnd)
    if rect.width < min_width or rect.height < min_height:
        return False

    return True


def enum_candidate_windows(
    keywords: Optional[Iterable[str]] = None,
    min_width: int = 300,
    min_height: int = 300,
) -> List[GameWindow]:
    """
    枚举符合关键词的窗口。
    keywords 为空时，返回所有可见普通窗口。
    """
    set_dpi_awareness()

    keywords = list(keywords or [])
    lowered_keywords = [k.lower() for k in keywords if k]

    results: List[GameWindow] = []

    def callback(hwnd: int, _extra) -> None:
        try:
            if not is_normal_window(hwnd, min_width=min_width, min_height=min_height):
                return

            title = win32gui.GetWindowText(hwnd).strip()
            title_lower = title.lower()

            if lowered_keywords and not any(k in title_lower for k in lowered_keywords):
                return

            window_rect = _get_window_rect(hwnd)
            client_rect = _get_client_rect_on_screen(hwnd)

            # 客户区太小的一般不是游戏窗口
            if client_rect.width < min_width or client_rect.height < min_height:
                return

            results.append(
                GameWindow(
                    hwnd=hwnd,
                    title=title,
                    window_rect=window_rect,
                    client_rect=client_rect,
                )
            )
        except Exception:
            # 枚举窗口时个别窗口会异常，直接跳过
            return

    win32gui.EnumWindows(callback, None)

    # 排序策略：
    # 1. 标题短的优先（"QQ经典农场" 5字 优先于 "QQ农场辅助...浏览器" 长标题）
    # 2. 标题相同/接近时，面积大的优先
    results.sort(key=lambda w: (len(w.title), -w.client_rect.width * w.client_rect.height))
    return results


def find_game_window(
    keywords: Optional[Iterable[str]] = None,
    min_width: int = 300,
    min_height: int = 300,
) -> Optional[GameWindow]:
    """
    返回最可能的 QQ经典农场窗口。
    """
    candidates = enum_candidate_windows(
        keywords=keywords or DEFAULT_WINDOW_KEYWORDS,
        min_width=min_width,
        min_height=min_height,
    )
    return candidates[0] if candidates else None


def refresh_window(hwnd: int) -> Optional[GameWindow]:
    """
    已知 hwnd 时，重新读取窗口位置。
    窗口被拖动、缩放后需要调用这个。
    """
    try:
        if not is_normal_window(hwnd):
            return None
        return GameWindow(
            hwnd=hwnd,
            title=win32gui.GetWindowText(hwnd).strip(),
            window_rect=_get_window_rect(hwnd),
            client_rect=_get_client_rect_on_screen(hwnd),
        )
    except Exception:
        return None


def bring_to_front(hwnd: int, restore: bool = True) -> bool:
    """
    尝试把窗口置前。
    注意：Windows 有前台窗口限制，偶尔可能失败。
    """
    try:
        if restore and win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)

        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def wait_for_game_window(
    keywords: Optional[Iterable[str]] = None,
    timeout: float = 10.0,
    interval: float = 0.5,
    min_width: int = 300,
    min_height: int = 300,
) -> Optional[GameWindow]:
    """
    在 timeout 秒内等待游戏窗口出现。
    """
    start = time.time()
    while time.time() - start <= timeout:
        win = find_game_window(
            keywords=keywords or DEFAULT_WINDOW_KEYWORDS,
            min_width=min_width,
            min_height=min_height,
        )
        if win:
            return win
        time.sleep(interval)
    return None


def print_candidate_windows(keywords: Optional[Iterable[str]] = None) -> None:
    """
    调试用：打印候选窗口，方便确认关键词是否正确。
    """
    candidates = enum_candidate_windows(keywords=keywords)
    for i, w in enumerate(candidates, 1):
        print(
            f"[{i}] hwnd={w.hwnd} title={w.title!r} "
            f"client={w.client_rect.left},{w.client_rect.top},"
            f"{w.client_rect.width}x{w.client_rect.height}"
        )


def close_game_window(hwnd: int) -> bool:
    """
    向窗口发送 WM_CLOSE，优雅关闭小程序窗口。
    关闭后等待 0.8 秒让窗口真正消失。
    """
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        time.sleep(0.8)
        return True
    except Exception:
        return False


def launch_from_shortcut(shortcut_path: str | Path) -> bool:
    """
    通过桌面快捷方式（.lnk）启动 QQ 经典农场小程序。
    使用 os.startfile，Windows 原生支持。
    """
    try:
        shortcut_path = str(shortcut_path)
        if not os.path.exists(shortcut_path):
            LOGGER.warning(f"快捷方式不存在: {shortcut_path}")
            return False
        os.startfile(shortcut_path)
        return True
    except Exception as e:
        LOGGER.warning(f"启动快捷方式失败: {e}")
        return False


def restart_game_window(
    hwnd: int,
    shortcut_path: str | Path,
    wait_timeout: float = 15.0,
    keywords: Optional[Iterable[str]] = None,
) -> Optional[GameWindow]:
    """
    一键重启：关闭旧窗口 → 从快捷方式启动 → 等待新窗口出现。
    返回新的 GameWindow，超时返回 None。
    """
    # 1. 关闭旧窗口
    if hwnd and win32gui.IsWindow(hwnd):
        close_game_window(hwnd)

    # 2. 启动新窗口
    if not launch_from_shortcut(shortcut_path):
        return None

    # 3. 等待窗口出现（小程序启动需要几秒）
    return wait_for_game_window(
        keywords=keywords or DEFAULT_WINDOW_KEYWORDS,
        timeout=wait_timeout,
        interval=0.5,
    )


if __name__ == "__main__":
    print_candidate_windows(DEFAULT_WINDOW_KEYWORDS)
