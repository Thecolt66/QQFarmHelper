# -*- coding: utf-8 -*-
"""
diagnose.py 快速诊断脚本
运行：python diagnose.py
会依次检查：窗口查找 → 截图 → 页面识别 → 模板加载 → 按钮检测
"""

import sys
import time
from pathlib import Path

# 确保能 import 项目模块
sys.path.insert(0, str(Path(__file__).parent))

from window_manager import find_game_window, DEFAULT_WINDOW_KEYWORDS, print_candidate_windows
from screen_capture import ScreenCapture
from vision import Vision, PageType
from state_machine import load_runtime_config


def main():
    print("=" * 60)
    print("QQFarmHelper 诊断脚本")
    print("=" * 60)

    # 1. 窗口查找
    print("\n[1/5] 查找游戏窗口...")
    print(f"  关键词: {DEFAULT_WINDOW_KEYWORDS}")
    print("  所有候选窗口:")
    print_candidate_windows(DEFAULT_WINDOW_KEYWORDS)

    win = find_game_window(keywords=DEFAULT_WINDOW_KEYWORDS)
    if not win:
        print("  ❌ 未找到游戏窗口！请确认 QQ经典农场 已打开。")
        return
    print(f"  ✅ 找到窗口: title={win.title!r}")
    print(f"  hwnd={win.hwnd}, client={win.client_rect.width}x{win.client_rect.height}")

    # 2. 截图
    print("\n[2/5] 测试截图...")
    cap = ScreenCapture()
    try:
        frame = cap.capture_window(win, client_only=True, refresh=True)
        print(f"  ✅ 截图成功: shape={frame.shape}")
        # 保存截图供查看
        out = Path("logs/diagnose_screenshot.png")
        out.parent.mkdir(exist_ok=True)
        import cv2
        cv2.imwrite(str(out), frame)
        print(f"  截图已保存: {out.resolve()}")
    except Exception as e:
        print(f"  ❌ 截图失败: {e}")
        return

    # 3. 加载配置和视觉模块
    print("\n[3/5] 加载配置和模板...")
    try:
        config = load_runtime_config("config_runtime.json")
        print(f"  ✅ 配置加载成功")
        print(f"  refresh.enabled = {config.get('refresh', {}).get('enabled')}")
        print(f"  advanced_pick.enabled = {config.get('advanced_pick', {}).get('enabled')}")
    except Exception as e:
        print(f"  ❌ 配置加载失败: {e}")
        return

    vision = Vision(
        template_dir=config.get("template_dir", "templates"),
        thresholds=config.get("thresholds", {}),
        rois=config.get("rois", {}),
    )

    # 检查所有模板是否能加载
    template_names = [
        "friend_menu", "friend_tab", "visit_button", "home_button",
        "pick_button", "pick_hand", "farm_button",
        "crop_pick_label", "ready_star",
    ]
    for name in template_names:
        try:
            tpl = vision.store.get(name)
            print(f"  ✅ {name}: {tpl.shape[1]}x{tpl.shape[0]}")
        except FileNotFoundError:
            print(f"  ⚠️  {name}: 模板文件不存在（可选模板会自动跳过）")
        except Exception as e:
            print(f"  ❌ {name}: 加载失败 - {e}")

    # 4. 页面识别
    print("\n[4/5] 页面识别...")
    det = vision.detect_page_type(frame)
    print(f"  页面类型: {det.page_type} (score={det.score:.3f})")
    if det.evidence:
        print(f"  依据: {det.evidence.template_name} score={det.evidence.score:.3f}")

    # 5. 页面内按钮检测
    print("\n[5/5] 页面内按钮检测...")
    if det.page_type == PageType.SELF_HOME:
        r = vision.detect_self_home_friend_menu(frame)
        print(f"  好友按钮: found={r.found} score={r.score:.3f} center={r.center}")
    elif det.page_type == PageType.FRIEND_LIST:
        buttons = vision.find_visit_buttons(frame)
        print(f"  拜访按钮数量: {len(buttons)}")
        for i, b in enumerate(buttons[:3], 1):
            print(f"    #{i}: score={b.score:.3f} center={b.center}")
    elif det.page_type == PageType.FRIEND_HOME:
        home = vision.detect_friend_home_home_button(frame)
        print(f"  回家按钮: found={home.found} score={home.score:.3f}")
        state, action = vision.detect_pick_or_farm(frame)
        print(f"  摘取/务农: state={state} best={action.template_name} score={action.score:.3f}")
        # 高级作物检测
        targets, method = vision.detect_pick_targets(frame)
        print(f"  高级作物可摘: {len(targets)} 个 (方法={method})")
        for i, t in enumerate(targets[:3], 1):
            print(f"    #{i}: score={t.score:.3f} center={t.center}")
    else:
        print("  ⚠️  未知页面，无法检测按钮。请确认游戏在主界面/好友列表/好友农场页面。")

    print("\n" + "=" * 60)
    print("诊断完成。如果以上全部 ✅，程序应该能正常运行。")
    print("如果有 ❌ 或 ⚠️，请把上面的输出发给开发者。")
    print("=" * 60)


if __name__ == "__main__":
    main()
