"""Windows 单实例锁：互斥量 + PID 文件，避免重复托盘进程。"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from config import CONFIG_DIR, ensure_config_dir

MUTEX_NAME = "Local\\CursorTokenTray_SingleInstance_v2"
PID_PATH = CONFIG_DIR / "instance.pid"
ERROR_ALREADY_EXISTS = 183


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    k32 = _kernel32()
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _read_stored_pid() -> int:
    try:
        if not PID_PATH.is_file():
            return 0
        text = PID_PATH.read_text(encoding="utf-8").strip()
        return int(text) if text.isdigit() else 0
    except (OSError, ValueError):
        return 0


def _write_pid() -> None:
    ensure_config_dir()
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    try:
        if PID_PATH.is_file():
            PID_PATH.unlink()
    except OSError:
        pass


def acquire() -> bool:
    """获取单实例锁。已有存活实例时返回 False。"""
    k32 = _kernel32()
    try:
        k32.SetLastError(0)
    except Exception:
        pass
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    acquire._mutex = handle  # type: ignore[attr-defined]
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        if handle:
            try:
                k32.CloseHandle(handle)
            except Exception:
                pass
            acquire._mutex = None  # type: ignore[attr-defined]
        return False

    old_pid = _read_stored_pid()
    if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
        if handle:
            try:
                k32.CloseHandle(handle)
            except Exception:
                pass
            acquire._mutex = None  # type: ignore[attr-defined]
        return False

    _write_pid()
    return True


def release() -> None:
    _clear_pid()
    handle = getattr(acquire, "_mutex", None)
    if handle:
        try:
            _kernel32().CloseHandle(handle)
        except Exception:
            pass
        acquire._mutex = None  # type: ignore[attr-defined]
