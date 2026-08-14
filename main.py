"""Cursor Token 剩余进度 — 系统托盘入口。"""

from __future__ import annotations

import atexit
import sys


def main() -> int:
    if sys.platform != "win32":
        print("本工具仅支持 Windows。")
        return 1

    from instance_lock import acquire, release

    if not acquire():
        # 已在运行：提示用户去托盘找，避免误以为「启动不了」
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "CursorToken 已在后台运行。\n请查看右下角系统托盘（或点 ^ 展开隐藏图标）。",
                "CursorToken 剩余进度",
                0x40,
            )
        except Exception:
            print("CursorToken 已在运行，请查看系统托盘。")
        return 0
    atexit.register(release)

    # 必须在创建任何窗口 / tk / pystray 之前启用 DPI 感知与 AppID
    from app_icon import set_app_user_model_id
    from dpi_util import enable_dpi_awareness

    enable_dpi_awareness()
    set_app_user_model_id()

    from tray_app import TrayApp

    app = TrayApp()
    try:
        app.run()
    finally:
        release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
