# -*- coding: utf-8 -*-
"""
debug_match.py 模板匹配调试脚本
在真实游戏画面上详细输出每个按钮模板的匹配分数、位置和尺度。
运行：python debug_match.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np

from window_manager import find_game_window, DEFAULT_WINDOW_KEYWORDS
from screen_capture import ScreenCapture
from vision import Vision, DEFAULT_THRESHOLDS, DEFAULT_ROIS, REFERENCE_RESOLUTION


def main():
    print("=" * 70)
    print("模板匹配调试")
    print("=" * 70)

    # 1. 找窗口
    win = find_game_window(keywords=DEFAULT_WINDOW_KEYWORDS)
    if not win:
        print("❌ 未找到游戏窗口")
        return
    print(f"✅ 窗口: {win.title!r}")
    print(f"   客户区尺寸: {win.client_rect.width}x{win.client_rect.height}")

    # 2. 截图
    cap = ScreenCapture()
    frame = cap.capture_window(win, client_only=True, refresh=True)
    print(f"✅ 截图: {frame.shape[1]}x{frame.shape[0]}")

    out_dir = Path("logs")
    out_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(out_dir / "debug_match_raw.png"), frame)
    print(f"   原始截图已保存: logs/debug_match_raw.png")

    # 3. 初始化视觉模块
    vision = Vision(template_dir="templates")

    # 4. 计算尺度
    scales = vision._get_adaptive_scales(frame.shape)
    print(f"\n📐 参考分辨率: {REFERENCE_RESOLUTION}")
    print(f"📐 多尺度范围: {scales}")

    # 5. 检查 ROI
    roi_name = "friend_action_buttons"
    roi = DEFAULT_ROIS[roi_name]
    h, w = frame.shape[:2]
    x1 = int(w * roi[0])
    y1 = int(h * roi[1])
    x2 = int(w * roi[2])
    y2 = int(h * roi[3])
    roi_w = x2 - x1
    roi_h = y2 - y1
    print(f"\n🎯 ROI [{roi_name}]:")
    print(f"   相对坐标: {roi}")
    print(f"   绝对区域: ({x1},{y1})-({x2},{y2})  尺寸: {roi_w}x{roi_h}")

    # 在截图上画 ROI 框
    debug_frame = frame.copy()
    cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
    cv2.putText(debug_frame, "ROI", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # 6. 逐个模板详细匹配
    templates_to_test = [
        ("pick_button", DEFAULT_THRESHOLDS.get("pick_button", 0.80)),
        ("pick_hand", DEFAULT_THRESHOLDS.get("pick_hand", 0.76)),
        ("farm_button", DEFAULT_THRESHOLDS.get("farm_button", 0.72)),
    ]

    roi_img = frame[y1:y2, x1:x2].copy()

    for tpl_name, threshold in templates_to_test:
        print(f"\n{'─' * 50}")
        print(f"🔍 模板: {tpl_name}  (阈值={threshold})")

        try:
            tpl = vision.store.get(tpl_name)
        except Exception as e:
            print(f"   ❌ 模板加载失败: {e}")
            continue

        print(f"   模板尺寸: {tpl.shape[1]}x{tpl.shape[0]}")

        # 检查模板是否比 ROI 大
        if tpl.shape[0] > roi_h or tpl.shape[1] > roi_w:
            print(f"   ⚠️  模板比 ROI 大，原始尺度无法匹配！")

        best_score = -1
        best_loc = None
        best_scale = None

        for scale in scales:
            if scale <= 0:
                continue
            new_w = max(1, int(round(tpl.shape[1] * scale)))
            new_h = max(1, int(round(tpl.shape[0] * scale)))
            tpl_scaled = cv2.resize(tpl, (new_w, new_h), interpolation=cv2.INTER_AREA)

            if new_h > roi_h or new_w > roi_w:
                print(f"   scale={scale:.3f} ({new_w}x{new_h}) -> 比ROI大，跳过")
                continue

            tpl_gray = cv2.cvtColor(tpl_scaled, cv2.COLOR_BGR2GRAY)
            roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            marker = " ✅" if max_val >= threshold else ""
            print(f"   scale={scale:.3f} ({new_w}x{new_h}) -> max_score={max_val:.4f}{marker}")

            if max_val > best_score:
                best_score = max_val
                best_loc = max_loc
                best_scale = scale
                best_size = (new_w, new_h)

        if best_loc is not None:
            abs_x = x1 + best_loc[0]
            abs_y = y1 + best_loc[1]
            hit = "✅ 命中" if best_score >= threshold else "❌ 未命中"
            print(f"\n   🏆 最佳: scale={best_scale:.3f} score={best_score:.4f} {hit}")
            print(f"      位置: ROI内({best_loc[0]},{best_loc[1]}) -> 绝对({abs_x},{abs_y})")
            print(f"      中心: ({abs_x + best_size[0]//2}, {abs_y + best_size[1]//2})")

            # 画框
            color = (0, 255, 0) if best_score >= threshold else (0, 0, 255)
            cv2.rectangle(debug_frame, (abs_x, abs_y),
                          (abs_x + best_size[0], abs_y + best_size[1]), color, 2)
            cv2.putText(debug_frame, f"{tpl_name} {best_score:.2f}",
                        (abs_x, max(20, abs_y - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        else:
            print(f"\n   ❌ 所有尺度都无法匹配（模板可能比ROI大）")

    # 7. 保存标注后的截图
    cv2.imwrite(str(out_dir / "debug_match_result.png"), debug_frame)
    print(f"\n{'=' * 70}")
    print(f"📊 标注后的截图已保存: logs/debug_match_result.png")
    print(f"   请查看该图片，确认 ROI 框是否覆盖了底部按钮区域")
    print(f"   如果 ROI 位置不对，需要调整 vision.py 里的 friend_action_buttons ROI")
    print(f"   如果 ROI 正确但分数低，需要调整模板截取方式或降低阈值")
    print("=" * 70)


if __name__ == "__main__":
    main()
