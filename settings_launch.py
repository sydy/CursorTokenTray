"""独立设置进程的启动参数与拉起逻辑（无 GUI 依赖）。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from platform_util import hidden_popen_kwargs

MODE_ENV = "CURSORTOKEN_MODE"
FOCUS_ENV = "CURSORTOKEN_FOCUS_TOKEN"
IMPORT_ENV = "CURSORTOKEN_START_IMPORT"


def is_settings_process(argv: list[str] | None = None, env: dict[str, str] | None = None) -> bool:
    """打包后的 .app 有时吃掉 argv，因此同时认环境变量。"""
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if env is None else env
    return "--settings" in args or environ.get(MODE_ENV) == "settings"


def settings_flags(argv: list[str] | None = None, env: dict[str, str] | None = None) -> tuple[bool, bool]:
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if env is None else env
    focus = "--focus-token" in args or environ.get(FOCUS_ENV) == "1"
    start_import = "--start-import" in args or environ.get(IMPORT_ENV) == "1"
    return focus, start_import


def settings_env(*, focus_token: bool = False, start_import: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env[MODE_ENV] = "settings"
    if focus_token:
        env[FOCUS_ENV] = "1"
    else:
        env.pop(FOCUS_ENV, None)
    if start_import:
        env[IMPORT_ENV] = "1"
    else:
        env.pop(IMPORT_ENV, None)
    return env


def settings_command(
    *,
    focus_token: bool = False,
    start_import: bool = False,
    executable: str | None = None,
    script: str | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """构造 `CursorTokenTray --settings` / `python main.py --settings` 命令行。"""
    exe = executable or sys.executable
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        cmd = [exe, "--settings"]
    else:
        main_py = script or str(Path(__file__).resolve().parent / "main.py")
        cmd = [exe, main_py, "--settings"]
    if focus_token:
        cmd.append("--focus-token")
    if start_import:
        cmd.append("--start-import")
    return cmd


_spawn_lock = threading.Lock()
_settings_proc: subprocess.Popen[bytes] | None = None
_wait_thread: threading.Thread | None = None


def settings_process_running() -> bool:
    proc = _settings_proc
    return proc is not None and proc.poll() is None


def spawn_settings_process(
    *,
    focus_token: bool = False,
    start_import: bool = False,
    on_config_changed: Callable[[dict[str, Any]], None] | None = None,
) -> int | None:
    """启动独立设置进程。运行期间轮询 config，点「应用」即可刷新托盘。"""
    from config import load_config, poll_config_changes
    from platform_util import app_log

    global _settings_proc
    with _spawn_lock:
        if _settings_proc is not None and _settings_proc.poll() is None:
            app_log("settings process already running")
            return None
        cmd = settings_command(focus_token=focus_token, start_import=start_import)
        env = settings_env(focus_token=focus_token, start_import=start_import)
        app_log(f"spawn settings: {cmd}")
        _settings_proc = subprocess.Popen(
            cmd,
            env=env,
            start_new_session=True,
            close_fds=True,
            cwd=str(Path(cmd[0]).resolve().parent) if os.path.isabs(cmd[0]) else None,
            **hidden_popen_kwargs(),
        )
        proc = _settings_proc
    try:
        poll_config_changes(lambda: proc.poll() is None, on_change=on_config_changed)
    except Exception as exc:  # noqa: BLE001
        app_log(f"settings config poll failed: {exc}")
        proc.wait()
    rc = int(proc.returncode if proc.returncode is not None else proc.wait())
    app_log(f"settings process exited rc={rc}")
    if on_config_changed is not None:
        try:
            on_config_changed(load_config())
        except Exception:
            pass
    return rc


def open_settings_async(
    *,
    on_saved: Callable[[dict[str, Any]], None] | None = None,
    focus_token: bool = False,
    start_import: bool = False,
) -> None:
    """后台拉起设置进程；已在运行则忽略。"""
    global _wait_thread

    def worker() -> None:
        try:
            spawn_settings_process(
                focus_token=focus_token,
                start_import=start_import,
                on_config_changed=on_saved,
            )
        except Exception as exc:  # noqa: BLE001
            from platform_util import app_log, show_error_alert

            app_log(f"spawn settings failed: {exc}")
            show_error_alert("设置", f"无法打开设置：{exc}")

    with _spawn_lock:
        if settings_process_running() or (_wait_thread is not None and _wait_thread.is_alive()):
            return
        _wait_thread = threading.Thread(target=worker, daemon=True, name="settings-proc")
        _wait_thread.start()
