"""Cursor Token 剩余进度 — 系统托盘 / 菜单栏入口。"""

from __future__ import annotations

import atexit
import sys

from platform_util import IS_MAC, IS_WIN, app_log, install_crash_logging, show_already_running
from settings_launch import is_settings_process


def main() -> int:
    install_crash_logging()
    app_log(
        f"start argv={sys.argv!r} frozen={bool(getattr(sys, 'frozen', False))} "
        f"platform={sys.platform}"
    )

    if not IS_WIN and not IS_MAC:
        app_log("unsupported platform, exit 1")
        print("本工具支持 Windows 与 macOS。")
        return 1

    if IS_MAC:
        try:
            import AppKit  # noqa: F401
        except ImportError:
            app_log("AppKit missing")
            print("macOS 需要先安装依赖：python3 -m pip install -r requirements.txt")
            print("（含 pyobjc-framework-Cocoa / pyobjc-framework-Quartz）")
            return 1

    # 设置窗走独立进程，必须在单实例锁之前返回，否则会误报「已在运行」。
    if is_settings_process():
        from settings_ui import run_settings_main

        app_log("enter settings process")
        return run_settings_main()

    from instance_lock import acquire, release

    if not acquire():
        app_log("instance lock busy, already running")
        show_already_running()
        return 0
    atexit.register(release)
    app_log("instance lock acquired, starting tray")

    # 必须在创建任何窗口 / tk / pystray 之前启用 DPI 感知与 AppID
    from app_icon import set_app_user_model_id
    from dpi_util import enable_dpi_awareness

    enable_dpi_awareness()
    set_app_user_model_id()

    from tray_app import TrayApp

    app = TrayApp()
    try:
        app.run()
    except Exception as exc:  # noqa: BLE001
        app_log(f"tray run failed: {exc}")
        raise
    finally:
        release()
        app_log("tray exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
