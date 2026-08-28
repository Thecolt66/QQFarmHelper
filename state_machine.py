# -*- coding: utf-8 -*-
"""
state_machine.py
QQ经典农场辅助工具的状态机。

它只负责“识别页面 → 点击对应按钮 → 等待跳转”。
真正的窗口寻找、截图、视觉识别、点击分别由：
    window_manager.py
    screen_capture.py
    vision.py
    clicker.py
提供。

页面逻辑：
    SELF_HOME:
        只检测并点击右下角“好友”。

    FRIEND_LIST:
        只检测右侧所有“拜访”按钮，选择最上方且最近未访问过的一行。

    FRIEND_HOME:
        只检测“一键摘取 / 一键务农”和右下角“回家”。
        farm_button 优先级最高：识别到“一键务农”就跳过，不点击。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, List
import json
import logging
import re
import time
from pathlib import Path

import cv2
import numpy as np

from window_manager import GameWindow, find_game_window, bring_to_front, DEFAULT_WINDOW_KEYWORDS, restart_game_window
from screen_capture import ScreenCapture
from vision import Vision, PageType, DEFAULT_ROIS, DEFAULT_THRESHOLDS, DEFAULT_CLICK_POINTS, resource_path
from clicker import Clicker


LOGGER = logging.getLogger("qq_farm_helper")


DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    "template_dir": "templates",
    "window_keywords": DEFAULT_WINDOW_KEYWORDS,
    "thresholds": DEFAULT_THRESHOLDS,
    "rois": DEFAULT_ROIS,
    "click_points": DEFAULT_CLICK_POINTS,

    "timing": {
        "loop_interval": 0.25,
        "after_click": 0.65,
        "after_visit_click": 1.80,
        "after_pick_click": 1.20,
        "after_home_click": 1.20,
        "page_wait_timeout": 6.0,
        "unknown_sleep": 1.00,
        "no_button_sleep": 1.50,
        "no_unvisited_sleep": 30.0
    },

    "behavior": {
        "skip_recently_visited": True,
        "visited_cache_seconds": 180,
        "all_visible_visited_action": "revisit_top",
        "allow_fallback_click": True,
        "max_visible_visit_buttons": 8,
        "stop_after_cycles": 0
    },

    "clicker": {
        "dry_run": False,
        "random_offset": 2,
        "click_down_up_delay": 0.05,
        "bring_front_before_click": True
    },

    "debug": {
        "save_unknown_screenshot": True,
        "save_error_screenshot": True,
        "debug_dir": "logs/runtime_debug"
    },

    "refresh": {
        "enabled": True,
        "interval_seconds": 180,
        "shortcut_path": "C:\\Users\\mayumo\\Desktop\\QQ经典农场-QQ小程序.lnk",
        "wait_timeout": 15,
        "reset_visited_cache": True
    },

    "advanced_pick": {
        "enabled": True,
        "max_clicks_per_friend": 12,
        "click_interval": 0.6,
        "stabilize_delay": 1.0,
        "use_mask_fallback": True,
        "use_star_hint": True
    },

    "farm": {
        "enabled": True,
        "daily_limit": 35,
        "stats_file": "logs/farm_stats.json"
    }
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_runtime_config(path: str | Path = "config_runtime.json") -> Dict[str, Any]:
    """
    优先读取 config_runtime.json。
    如果不存在，再尝试读取 config_v3.json。
    都不存在则使用内置默认配置。
    支持 PyInstaller 打包后的路径（sys._MEIPASS）。
    """
    path = Path(path)
    if not path.is_absolute():
        path = resource_path(path)

    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return deep_merge(DEFAULT_RUNTIME_CONFIG, json.load(f))

    v3 = resource_path("config_v3.json")
    if v3.exists():
        with v3.open("r", encoding="utf-8") as f:
            return deep_merge(DEFAULT_RUNTIME_CONFIG, json.load(f))

    return dict(DEFAULT_RUNTIME_CONFIG)


@dataclass
class BotStats:
    cycles: int = 0
    visits: int = 0
    picks: int = 0
    skips_farm: int = 0
    no_pick: int = 0
    unknown_pages: int = 0
    errors: int = 0


@dataclass
class FriendVisitRecord:
    last_seen: float
    hits: int = 1


class FarmStateMachine:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        dry_run: Optional[bool] = None,
    ) -> None:
        self.config = deep_merge(DEFAULT_RUNTIME_CONFIG, config or {})

        if dry_run is not None:
            self.config["clicker"]["dry_run"] = bool(dry_run)

        self.vision = Vision(
            template_dir=self.config.get("template_dir", "templates"),
            thresholds=self.config.get("thresholds", {}),
            rois=self.config.get("rois", {}),
        )

        self.capture = ScreenCapture()

        click_cfg = self.config.get("clicker", {})
        self.clicker = Clicker(
            dry_run=bool(click_cfg.get("dry_run", False)),
            random_offset=int(click_cfg.get("random_offset", 2)),
            click_down_up_delay=float(click_cfg.get("click_down_up_delay", 0.05)),
            bring_front_before_click=bool(click_cfg.get("bring_front_before_click", True)),
        )

        self.window: Optional[GameWindow] = None
        self.stats = BotStats()
        self.visited_rows: Dict[int, FriendVisitRecord] = {}
        self.last_refresh_time: float = time.time()

        # 一键务农每日计数（跨天重置，持久化到文件）
        farm_cfg = self.config.get("farm", {})
        self.farm_stats_path = Path(farm_cfg.get("stats_file", "logs/farm_stats.json"))
        self.farm_count_date, self.farm_count_today = self._load_farm_count()

        debug_dir = Path(self.config["debug"].get("debug_dir", "logs/runtime_debug"))
        debug_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir = debug_dir
        self._cleanup_old_debug_screenshots()

    # ---------- 基础工具 ----------

    def close(self) -> None:
        self.capture.close()

    def ensure_window(self) -> bool:
        if self.window is not None and self.window.is_valid:
            return True

        keywords = self.config.get("window_keywords", DEFAULT_WINDOW_KEYWORDS)
        self.window = find_game_window(keywords=keywords, min_width=300, min_height=300)

        if self.window:
            LOGGER.info("找到窗口：%s", self.window.title)
            bring_to_front(self.window.hwnd)
            return True

        LOGGER.warning("没有找到 QQ经典农场窗口")
        return False

    def grab(self) -> Optional[np.ndarray]:
        if not self.ensure_window() or self.window is None:
            return None

        try:
            return self.capture.capture_window(self.window, client_only=True, refresh=True)
        except Exception:
            LOGGER.exception("截图失败")
            self.stats.errors += 1
            return None

    def save_debug_frame(self, frame: np.ndarray, prefix: str) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self.debug_dir / f"{prefix}_{ts}.png"
        cv2.imwrite(str(path), frame)
        # 每次保存后清理超过3天的旧截图
        self._cleanup_old_debug_screenshots()
        return path

    def _cleanup_old_debug_screenshots(self) -> None:
        """清理超过3天的未知页面截图。"""
        try:
            cutoff = time.time() - 3 * 86400
            for png_file in self.debug_dir.glob("*.png"):
                m = re.search(r"(\d{8})_\d{6}", png_file.name)
                if m:
                    try:
                        file_time = time.mktime(time.strptime(m.group(1), "%Y%m%d"))
                        if file_time < cutoff:
                            png_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def sleep(self, key: str) -> None:
        seconds = float(self.config.get("timing", {}).get(key, 0.5))
        time.sleep(max(0.0, seconds))

    # ---------- 好友去重 ----------

    def purge_visited_cache(self) -> None:
        ttl = float(self.config.get("behavior", {}).get("visited_cache_seconds", 900))
        now = time.time()

        expired = [h for h, rec in self.visited_rows.items() if now - rec.last_seen > ttl]
        for h in expired:
            del self.visited_rows[h]

    @staticmethod
    def dhash(image_bgr: np.ndarray) -> int:
        """
        计算好友行截图的感知哈希，避免重复拜访同一行。
        不识别昵称，不依赖 OCR。
        """
        if image_bgr.size == 0:
            return 0

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
        diff = small[:, 1:] > small[:, :-1]

        value = 0
        for bit in diff.flatten():
            value = (value << 1) | int(bit)
        return int(value)

    @staticmethod
    def crop_friend_row(frame_bgr: np.ndarray, button_match) -> np.ndarray:
        """
        根据“拜访”按钮位置，裁取按钮左侧的整行好友信息。
        """
        if not getattr(button_match, "box", None):
            return frame_bgr[0:1, 0:1]

        h, w = frame_bgr.shape[:2]
        x1, y1, x2, y2 = button_match.box

        row_top = max(0, y1 - int(0.025 * h))
        row_bottom = min(h, y2 + int(0.025 * h))
        row_left = int(0.03 * w)
        row_right = int(0.70 * w)

        return frame_bgr[row_top:row_bottom, row_left:row_right].copy()

    def choose_visit_button(self, frame_bgr: np.ndarray, buttons: List[Any]) -> Optional[Any]:
        """
        选择“拜访”按钮。

        v4 逻辑：
            1. 优先选择最上方且近期没访问过的好友。
            2. 如果当前可见 5~6 个好友都访问过，不再卡住不动。
               默认策略是 revisit_top：直接重新访问最上方好友。
            3. 如果你想恢复旧逻辑，可以在 config_runtime.json 里设置：
               "all_visible_visited_action": "wait"
        """
        if not buttons:
            return None

        behavior = self.config.get("behavior", {})
        if not behavior.get("skip_recently_visited", True):
            return buttons[0]

        self.purge_visited_cache()

        # 先找未访问过的可见好友。
        for button in buttons:
            row = self.crop_friend_row(frame_bgr, button)
            row_hash = self.dhash(row)

            if row_hash not in self.visited_rows:
                self.visited_rows[row_hash] = FriendVisitRecord(last_seen=time.time())
                return button

        # 当前可见好友都访问过时，不要停住。
        action = behavior.get("all_visible_visited_action", "revisit_top")

        if action == "wait":
            return None

        if action == "clear_cache":
            self.visited_rows.clear()
            button = buttons[0]
            row = self.crop_friend_row(frame_bgr, button)
            row_hash = self.dhash(row)
            self.visited_rows[row_hash] = FriendVisitRecord(last_seen=time.time())
            LOGGER.info("当前可见好友都访问过，已清空访问缓存并重新访问最上方好友")
            return button

        # 默认 revisit_top：保留缓存，但仍访问最上方好友。
        button = buttons[0]
        row = self.crop_friend_row(frame_bgr, button)
        row_hash = self.dhash(row)
        rec = self.visited_rows.get(row_hash)
        if rec:
            rec.last_seen = time.time()
            rec.hits += 1
        else:
            self.visited_rows[row_hash] = FriendVisitRecord(last_seen=time.time())

        LOGGER.info("当前可见好友都访问过，重新访问最上方好友，避免程序停住")
        return button

    # ---------- 页面处理 ----------

    def step(self) -> None:
        """
        执行一次状态机步骤。
        main.py 会循环调用它。
        """
        # 定时刷新检查：到点就重启小程序，避免好友状态缓存不更新
        if self._should_refresh():
            self._do_refresh()
            return

        frame = self.grab()
        if frame is None:
            time.sleep(1.0)
            return

        detection = self.vision.detect_page_type(frame)
        page = detection.page_type

        LOGGER.info("page=%s score=%.3f", page, detection.score)

        if page == PageType.SELF_HOME:
            self.handle_self_home(frame)
        elif page == PageType.FRIEND_LIST:
            self.handle_friend_list(frame)
        elif page == PageType.FRIEND_HOME:
            self.handle_friend_home(frame)
        else:
            self.handle_unknown(frame, detection)

    def handle_self_home(self, frame: np.ndarray) -> None:
        """
        我的主页：点击右下角“好友”。
        """
        if self.window is None:
            return

        match = self.vision.detect_self_home_friend_menu(frame)

        if match.found:
            result = self.clicker.click_match(self.window, match)
            LOGGER.info("点击好友按钮：%s", result)
        else:
            # 兜底：只在页面已经被判定为 SELF_HOME 时使用相对坐标。
            if self.config.get("behavior", {}).get("allow_fallback_click", True):
                rx, ry = self.config["click_points"]["friend_menu"]
                result = self.clicker.click_relative(self.window, rx, ry)
                LOGGER.warning("好友按钮模板未命中，使用兜底坐标：%s", result)
            else:
                LOGGER.warning("好友按钮未识别，不点击")
                self.sleep("no_button_sleep")
                return

        self.sleep("after_click")

    def handle_friend_list(self, frame: np.ndarray) -> None:
        """
        好友列表：找所有“拜访”，点击最上面且最近没访问过的。
        """
        if self.window is None:
            return

        max_buttons = int(self.config.get("behavior", {}).get("max_visible_visit_buttons", 8))
        buttons = self.vision.find_visit_buttons(frame, max_results=max_buttons)

        if not buttons:
            LOGGER.warning("好友列表里没有识别到拜访按钮")
            self.sleep("no_button_sleep")
            return

        button = self.choose_visit_button(frame, buttons)
        if button is None:
            LOGGER.info("当前可见好友都在近期访问缓存里，暂停一会儿")
            time.sleep(float(self.config["timing"].get("no_unvisited_sleep", 30.0)))
            return

        result = self.clicker.click_match(self.window, button)
        LOGGER.info("点击拜访：%s score=%.3f center=%s", result, button.score, button.center)

        self.stats.visits += 1
        self.sleep("after_visit_click")

    def handle_friend_home(self, frame: np.ndarray) -> None:
        """
        好友家主页：
            1. 分别检测一键偷菜和一键务农。
            2. 一键偷菜：始终点击（模板或兜底）。
            3. 一键务农：每天限次（默认50次），未超限才点击。
            4. 点完一键偷菜后，检测高级作物的单独"可摘"标签，逐个点击。
            5. 最后回家。
        """
        if self.window is None:
            return

        steal_match, farm_match = self.vision.detect_action_buttons(frame)
        LOGGER.info(
            "偷菜 found=%s score=%.3f | 务农 found=%s score=%.3f",
            steal_match.found, steal_match.score,
            farm_match.found, farm_match.score,
        )

        allow_fallback = self.config.get("behavior", {}).get("allow_fallback_click", True)
        steal_clicked = False

        # ---- 1. 一键偷菜 ----
        # 逻辑：
        #   - 模板匹配到就点
        #   - 没匹配到但务农按钮命中：根据务农按钮的 x 位置判断单/双按钮
        #       * 务农在右侧(相对x>0.55) → 双按钮并排，偷菜在左侧，用兜底坐标点偷菜
        #       * 务农在中间(相对x<=0.55) → 单按钮模式，本页没有偷菜，跳过
        #   - 都没匹配到才用兜底坐标尝试
        if steal_match.found:
            result = self.clicker.click_match(self.window, steal_match)
            LOGGER.info("点击一键偷菜（模板匹配）：%s", result)
            self.stats.picks += 1
            steal_clicked = True
            self.sleep("after_pick_click")
        elif farm_match.found and farm_match.center:
            # 根据务农按钮 x 位置判断单/双按钮
            farm_rel_x = farm_match.center[0] / max(1, self.window.client_rect.width)
            if farm_rel_x > 0.55:
                # 双按钮模式：务农在右侧，偷菜在左侧，用兜底坐标点偷菜
                LOGGER.info(f"双按钮模式（务农相对x={farm_rel_x:.3f}），用兜底坐标点一键偷菜")
                rx, ry = self.config["click_points"]["steal_button"]
                result = self.clicker.click_relative(self.window, rx, ry)
                LOGGER.info("点击一键偷菜（兜底坐标）：%s", result)
                self.stats.picks += 1
                steal_clicked = True
                self.sleep("after_pick_click")
            else:
                # 单按钮模式：务农在中间，本页没有偷菜
                LOGGER.info(f"单按钮模式（务农相对x={farm_rel_x:.3f}），本页无一键偷菜，跳过")
        elif allow_fallback:
            rx, ry = self.config["click_points"]["steal_button"]
            result = self.clicker.click_relative(self.window, rx, ry)
            LOGGER.warning("一键偷菜模板未命中且无务农按钮，使用兜底坐标点击：%s", result)
            self.stats.picks += 1
            steal_clicked = True
            self.sleep("after_pick_click")
        else:
            LOGGER.info("一键偷菜未识别且禁用兜底，跳过")
            self.stats.no_pick += 1

        # ---- 2. 一键务农（每日限次） ----
        farm_cfg = self.config.get("farm", {})
        farm_enabled = bool(farm_cfg.get("enabled", True))
        farm_limit = int(farm_cfg.get("daily_limit", 50))

        if farm_enabled and farm_match.found and self._can_farm_today(farm_limit):
            result = self.clicker.click_match(self.window, farm_match)
            self._inc_farm_count()
            LOGGER.info(
                "点击一键务农：%s（今日 %d/%d）",
                result, self.farm_count_today, farm_limit,
            )
            self.stats.skips_farm += 1  # 复用统计字段表示务农次数
            self.sleep("after_pick_click")
        elif farm_enabled and farm_match.found:
            LOGGER.info("今日一键务农已达上限 %d 次，跳过", farm_limit)
        elif farm_match.found and not farm_enabled:
            LOGGER.info("一键务农功能已禁用，跳过")

        # ---- 3. 高级作物单独摘取 ----
        advanced_clicks = self._click_advanced_pick_labels() if steal_clicked else 0
        if advanced_clicks > 0:
            LOGGER.info("高级作物单独摘取完成，共点击 %d 次", advanced_clicks)

        # 重新截图后再找回家，避免摘取后画面变化
        frame2 = self.grab()
        if frame2 is None:
            return

        home = self.vision.detect_friend_home_home_button(frame2)
        if home.found:
            result = self.clicker.click_match(self.window, home)
            LOGGER.info("点击回家：%s", result)
        else:
            if self.config.get("behavior", {}).get("allow_fallback_click", True):
                rx, ry = self.config["click_points"]["home"]
                result = self.clicker.click_relative(self.window, rx, ry)
                LOGGER.warning("回家按钮模板未命中，使用兜底坐标：%s", result)
            else:
                LOGGER.warning("回家按钮未识别，不点击")
                self.sleep("no_button_sleep")
                return

        self.stats.cycles += 1
        self.sleep("after_home_click")

    def _load_farm_count(self) -> tuple:
        """从文件加载今日务农次数，跨天自动重置为0。"""
        today = time.strftime("%Y-%m-%d")
        try:
            if self.farm_stats_path.exists():
                with open(self.farm_stats_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today:
                    return today, int(data.get("count", 0))
        except Exception:
            pass
        return today, 0

    def _save_farm_count(self) -> None:
        """持久化今日务农次数到文件。"""
        try:
            self.farm_stats_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.farm_stats_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"date": self.farm_count_date, "count": self.farm_count_today},
                    f, ensure_ascii=False,
                )
        except Exception:
            pass

    def _can_farm_today(self, daily_limit: int = 50) -> bool:
        """检查今天是否还能点击一键务农（跨天自动重置）。"""
        today = time.strftime("%Y-%m-%d")
        if today != self.farm_count_date:
            self.farm_count_date = today
            self.farm_count_today = 0
            self._save_farm_count()
        return self.farm_count_today < daily_limit

    def _inc_farm_count(self) -> None:
        """务农次数+1并保存。"""
        self.farm_count_today += 1
        self._save_farm_count()

    def _click_advanced_pick_labels(self) -> int:
        """
        高级作物单独摘取：循环检测并点击"可摘"标签，直到没有为止。
        使用 A+B+E 三层兜底检测。返回实际点击次数。
        """
        cfg = self.config.get("advanced_pick", {})
        if not cfg.get("enabled", True):
            return 0
        if self.window is None:
            return 0

        max_clicks = int(cfg.get("max_clicks_per_friend", 12))
        click_interval = float(cfg.get("click_interval", 0.6))
        stabilize_delay = float(cfg.get("stabilize_delay", 1.0))
        use_mask = bool(cfg.get("use_mask_fallback", True))
        use_star = bool(cfg.get("use_star_hint", True))

        # 先等一键摘取的动画稳定
        time.sleep(stabilize_delay)

        clicks = 0
        consecutive_empty = 0

        while clicks < max_clicks and consecutive_empty < 2:
            frame = self.grab()
            if frame is None:
                break

            targets, method = self.vision.detect_pick_targets(
                frame, use_mask_fallback=use_mask, use_star_hint=use_star
            )

            if not targets:
                consecutive_empty += 1
                LOGGER.debug("高级摘取：未检测到目标 (empty=%d/2)", consecutive_empty)
                time.sleep(0.4)
                continue

            consecutive_empty = 0
            target = targets[0]  # 每次只点第一个，点完重新检测
            result = self.clicker.click_match(self.window, target)
            clicks += 1
            LOGGER.info(
                "高级摘取 [%s] 点击 #%d: score=%.3f center=%s result=%s",
                method, clicks, target.score, target.center, result
            )
            time.sleep(click_interval)

        return clicks

    def _should_refresh(self) -> bool:
        """检查是否到了定时刷新时间。"""
        cfg = self.config.get("refresh", {})
        if not cfg.get("enabled", True):
            return False
        interval = float(cfg.get("interval_seconds", 300))
        return (time.time() - self.last_refresh_time) >= interval

    def _do_refresh(self) -> None:
        """执行小程序重启刷新：关闭旧窗口 → 从桌面快捷方式启动 → 等待就绪。"""
        cfg = self.config.get("refresh", {})
        shortcut = cfg.get("shortcut_path", "")
        wait_timeout = float(cfg.get("wait_timeout", 15))

        LOGGER.info("定时刷新触发：重启小程序窗口")

        old_hwnd = self.window.hwnd if self.window else None
        keywords = self.config.get("window_keywords", DEFAULT_WINDOW_KEYWORDS)

        new_win = restart_game_window(
            hwnd=old_hwnd or 0,
            shortcut_path=shortcut,
            wait_timeout=wait_timeout,
            keywords=keywords,
        )

        if new_win is None:
            LOGGER.error("刷新失败：重启后未找到游戏窗口，保留原窗口引用")
            self.last_refresh_time = time.time()
            return

        self.window = new_win
        self.last_refresh_time = time.time()
        LOGGER.info("刷新成功：新窗口 hwnd=%s title=%s", new_win.hwnd, new_win.title)

        # 重置好友访问缓存，刷新后重新遍历
        if cfg.get("reset_visited_cache", True):
            self.visited_rows.clear()
            LOGGER.info("已重置好友访问缓存")

        # 等页面加载稳定
        time.sleep(2.0)

    def handle_unknown(self, frame: np.ndarray, detection) -> None:
        self.stats.unknown_pages += 1
        LOGGER.warning("未知页面 score=%.3f evidence=%s", detection.score, detection.evidence)

        if self.config.get("debug", {}).get("save_unknown_screenshot", True):
            path = self.save_debug_frame(frame, "unknown")
            LOGGER.warning("未知页面截图已保存：%s", path)

        self.sleep("unknown_sleep")

    # ---------- 循环 ----------

    def run_loop(self, should_pause, should_stop) -> None:
        """
        should_pause 和 should_stop 是函数，返回 bool。
        由 main.py 的热键控制。
        """
        LOGGER.info("状态机启动")
        try:
            while not should_stop():
                if should_pause():
                    time.sleep(0.2)
                    continue

                try:
                    self.step()
                except Exception:
                    self.stats.errors += 1
                    LOGGER.exception("状态机 step 异常")
                    time.sleep(1.0)

                stop_after = int(self.config.get("behavior", {}).get("stop_after_cycles", 0))
                if stop_after > 0 and self.stats.cycles >= stop_after:
                    LOGGER.info("达到 stop_after_cycles=%s，停止", stop_after)
                    break

                time.sleep(float(self.config.get("timing", {}).get("loop_interval", 0.25)))
        finally:
            self.close()
            LOGGER.info("状态机结束：%s", self.stats)
