"""Cursor Token 剩余进度 — 系统托盘 / 菜单栏入口。"""

from __future__ import annotations

import atexit
import sys

from platform_util import IS_MAC, IS_WIN, app_log, install_crash_logging, show_already_running
from settings_launch import is_settings_process


def main() -> int:
    print("提示：Python 入口已弃用，仅作夹具对照。日常请使用 Windows 的 CursorTokenTray.exe 或 macOS 的 CursorTokenTray.app。", file=sys.stderr)
    install_crash_logging()
    app_log(
        f"start argv={sys.argv!r} frozen={bool(getattr(sys, 'frozen', False))} "
        f"platform={sys.platform}"
    )

    if not IS_WIN and not IS_MAC:
        app_log("unsupported platform, exit 1")
        print("本工具支持 Windows 与 macOS。")
        return 1

    # `--settings` 在独立进程里跑原生设置窗（Windows Win32 / macOS AppKit）。
    # 必须在 import 托盘循环之前返回。
    if is_settings_process():
        app_log("enter settings process")
        if IS_MAC:
            from macos_settings import run_macos_settings

            return run_macos_settings()
        from win_settings import run_settings_main

        return run_settings_main()

    if IS_MAC:
        try:
            import AppKit  # noqa: F401
        except ImportError:
            app_log("AppKit missing")
            print("macOS 需要先安装依赖：python3 -m pip install -r requirements.txt")
            print("（含 pyobjc-framework-Cocoa / pyobjc-framework-Quartz）")
            return 1

    from instance_lock import acquire, release

    if not acquire():
        app_log("instance lock busy, already running")
        show_already_running()
        return 0
    atexit.register(release)
    app_log("instance lock acquired, starting tray")

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
