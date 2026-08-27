"""Windows 飞出层 / 矢量菜单：短命子进程，托盘主进程不加载 Tk。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from platform_util import hidden_popen_kwargs

MODE_ENV = "CURSORTOKEN_MODE"
MENU_ACTIONS = ("status", "refresh", "web", "import", "settings", "quit")

_spawn_lock = threading.Lock()
_status_proc: subprocess.Popen[bytes] | None = None
_menu_proc: subprocess.Popen[bytes] | None = None


def popup_mode(argv: list[str] | None = None, env: dict[str, str] | None = None) -> str | None:
    args = sys.argv[1:] if argv is None else argv
    environ = os.environ if env is None else env
    mode = (environ.get(MODE_ENV) or "").strip().lower()
    if "--status" in args or mode == "status":
        return "status"
    if "--menu" in args or mode == "menu":
        return "menu"
    return None


def is_popup_process(argv: list[str] | None = None, env: dict[str, str] | None = None) -> bool:
    return popup_mode(argv, env) in ("status", "menu")


def popup_command(
    mode: str,
    *,
    executable: str | None = None,
    script: str | None = None,
    frozen: bool | None = None,
) -> list[str]:
    flag = "--status" if mode == "status" else "--menu"
    exe = executable or sys.executable
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        return [exe, flag]
    main_py = script or str(Path(__file__).resolve().parent / "main.py")
    return [exe, main_py, flag]


def _popen(cmd: list[str], *, capture: bool = False) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env[MODE_ENV] = "menu" if "--menu" in cmd else "status"
    kw: dict = {
        "env": env,
        "start_new_session": True,
        "close_fds": True,
        "cwd": str(Path(cmd[0]).resolve().parent) if os.path.isabs(cmd[0]) else None,
        **hidden_popen_kwargs(),
    }
    if capture:
        kw["stdout"] = subprocess.PIPE
        kw["stderr"] = subprocess.DEVNULL
    return subprocess.Popen(cmd, **kw)


def status_process_running() -> bool:
    proc = _status_proc
    return proc is not None and proc.poll() is None


def menu_process_running() -> bool:
    proc = _menu_proc
    return proc is not None and proc.poll() is None


def open_status_async() -> None:
    """后台拉起飞出层；已在运行则忽略。"""
    from platform_util import app_log

    global _status_proc
    with _spawn_lock:
        if status_process_running():
            app_log("status process already running")
            return
        cmd = popup_command("status")
        app_log(f"spawn status: {cmd}")
        _status_proc = _popen(cmd)


def run_menu_and_pick() -> str | None:
    """同步弹出矢量菜单，返回选中的 key。"""
    from platform_util import app_log

    global _menu_proc
    with _spawn_lock:
        if menu_process_running() or status_process_running():
            return None
        cmd = popup_command("menu")
        app_log(f"spawn menu: {cmd}")
        _menu_proc = _popen(cmd, capture=True)
        proc = _menu_proc
    try:
        out, _ = proc.communicate(timeout=300)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return None
    key = (out or b"").decode("utf-8", errors="replace").strip()
    if not key:
        return None
    if key in MENU_ACTIONS:
        return key
    if key.startswith("switch:") and key.split(":", 1)[1].strip():
        return key
    return None


def close_popup_processes() -> None:
    for attr in ("_status_proc", "_menu_proc"):
        proc = globals().get(attr)
        if proc is None or proc.poll() is not None:
            continue
        try:
            proc.terminate()
        except Exception:
            pass
