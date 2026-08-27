"""Windows 空闲内存回收：清渲染缓存并把工作集还给系统。

过夜挂着不用时，Python/Tk/PIL 的堆不会自己缩小。任务管理器里的「内存」
是工作集；不主动 trim，数字会一直停在白天高峰。
"""

from __future__ import annotations

import gc
import sys
import threading

_lock = threading.Lock()
_last_trim_mono = 0.0
# 后台刷新默认 10 分钟一次；同窗口内重复 trim 没有收益，还会抖一下页面。
MIN_TRIM_INTERVAL_SEC = 60.0


def clear_icon_caches() -> None:
    """丢掉过夜用不到的 Pillow 图标 / 字体缓存。托盘已交给系统的 HICON 不受影响。"""
    try:
        from icon_renderer import clear_icon_caches as _clear

        _clear()
    except Exception:
        pass


def trim_working_set() -> bool:
    """把未碰的页面还给 Windows。非 Windows 为空操作。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_process = kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        empty = psapi.EmptyWorkingSet
        empty.argtypes = [wintypes.HANDLE]
        empty.restype = wintypes.BOOL
        return bool(empty(get_process()))
    except Exception:
        return False


def release_idle_memory(*, force: bool = False) -> bool:
    """空闲时：gc + 清图标缓存 + 压缩工作集。

    ``force=True`` 用于刚拆掉 Tk 之后，必须立刻还内存。
    默认按 ``MIN_TRIM_INTERVAL_SEC`` 节流，避免刷新线程连打。
    """
    import time

    global _last_trim_mono
    now = time.monotonic()
    with _lock:
        if not force and now - _last_trim_mono < MIN_TRIM_INTERVAL_SEC:
            return False
        _last_trim_mono = now
    gc.collect()
    clear_icon_caches()
    return trim_working_set() if sys.platform == "win32" else True
