"""单实例锁：Windows 用互斥量，macOS/Unix 用文件锁。"""

from __future__ import annotations

import os
from pathlib import Path

from config import CONFIG_DIR, ensure_config_dir
from platform_util import IS_WIN

MUTEX_NAME = "Local\\CursorTokenTray_SingleInstance_v2"
PID_PATH = CONFIG_DIR / "instance.pid"
LOCK_PATH = CONFIG_DIR / "instance.lock"
ERROR_ALREADY_EXISTS = 183


def _kernel32():
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def _pid_alive_win(pid: int) -> bool:
    if pid <= 0:
        return False
    k32 = _kernel32()
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        import ctypes

        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _pid_alive_unix(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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
    if IS_WIN:
        return _acquire_win()
    return _acquire_unix()


def release() -> None:
    if IS_WIN:
        _release_win()
        return
    _release_unix()


def _acquire_win() -> bool:
    import ctypes

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
    if old_pid and old_pid != os.getpid() and _pid_alive_win(old_pid):
        if handle:
            try:
                k32.CloseHandle(handle)
            except Exception:
                pass
            acquire._mutex = None  # type: ignore[attr-defined]
        return False

    _write_pid()
    return True


def _release_win() -> None:
    _clear_pid()
    handle = getattr(acquire, "_mutex", None)
    if handle:
        try:
            _kernel32().CloseHandle(handle)
        except Exception:
            pass
        acquire._mutex = None  # type: ignore[attr-defined]


def _acquire_unix() -> bool:
    import fcntl

    ensure_config_dir()
    try:
        fp = LOCK_PATH.open("a+", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fp.close()
        return False
    except OSError:
        fp.close()
        return False

    old_pid = _read_stored_pid()
    if old_pid and old_pid != os.getpid() and _pid_alive_unix(old_pid):
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fp.close()
        return False

    fp.seek(0)
    fp.truncate()
    fp.write(str(os.getpid()))
    fp.flush()
    acquire._lock_fp = fp  # type: ignore[attr-defined]
    _write_pid()
    return True


def _release_unix() -> None:
    import fcntl

    _clear_pid()
    fp = getattr(acquire, "_lock_fp", None)
    if fp is not None:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fp.close()
        except OSError:
            pass
        acquire._lock_fp = None  # type: ignore[attr-defined]
    try:
        if LOCK_PATH.is_file():
            LOCK_PATH.unlink()
    except OSError:
        pass
