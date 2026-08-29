"""本地配置读写。"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator


def app_config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "CursorTokenTray"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CursorTokenTray"
    return Path.home() / ".config" / "CursorTokenTray"


APP_NAME = "CursorToken剩余进度"
CONFIG_DIR = app_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "session_token": "",
    "accounts": [],
    "active_account_id": "",
    "refresh_interval_minutes": 10,
    "low_quota_threshold": 20,  # 兼容旧版；迁移到 alert_thresholds
    "alert_thresholds": [50, 20, 5],
    "notify_enabled": True,
    "notify_exhaustion_risk": True,
    "autostart_enabled": True,
    "tray_display_mode": "ring",  # ring | number | dot
    # 去重状态（跟随当前账号；兼容旧读取路径）
    "low_quota_notified": False,
    "auth_error_notified": False,
    "alert_notified_levels": [],
    "exhaustion_notified": False,
}

_VALID_DISPLAY_MODES = frozenset({"ring", "number", "dot"})
_THREAD_LOCK = threading.RLock()


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _interprocess_lock() -> Iterator[None]:
    """避免并发写 config.json。"""
    ensure_config_dir()
    fp = (CONFIG_DIR / "config.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            fp.seek(0)
            if fp.read(1) == b"":
                fp.write(b"0")
                fp.flush()
            fp.seek(0)
            msvcrt.locking(fp.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fp.seek(0)
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fp.close()


def load_config() -> dict[str, Any]:
    with _THREAD_LOCK, _interprocess_lock():
        return _load_unlocked()


def save_config(cfg: dict[str, Any]) -> None:
    with _THREAD_LOCK, _interprocess_lock():
        _save_unlocked(cfg)


def _load_unlocked() -> dict[str, Any]:
    ensure_config_dir()
    if not CONFIG_PATH.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        _save_unlocked(cfg)
        return cfg

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    return _normalize_config(cfg, raw=data)


def _save_unlocked(cfg: dict[str, Any]) -> None:
    ensure_config_dir()
    normalized = _normalize_config({**deepcopy(DEFAULT_CONFIG), **cfg}, raw=cfg)
    to_save = deepcopy(DEFAULT_CONFIG)
    to_save.update({k: v for k, v in normalized.items() if k in DEFAULT_CONFIG})
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, CONFIG_PATH)


def _normalize_config(cfg: dict[str, Any], *, raw: dict[str, Any]) -> dict[str, Any]:
    cfg["refresh_interval_minutes"] = max(1, int(cfg.get("refresh_interval_minutes", 10)))
    cfg["low_quota_threshold"] = min(100, max(1, int(cfg.get("low_quota_threshold", 20))))
    cfg["notify_enabled"] = bool(cfg.get("notify_enabled", True))
    cfg["notify_exhaustion_risk"] = bool(cfg.get("notify_exhaustion_risk", True))
    cfg["autostart_enabled"] = bool(cfg.get("autostart_enabled", True))
    cfg["low_quota_notified"] = bool(cfg.get("low_quota_notified", False))
    cfg["auth_error_notified"] = bool(cfg.get("auth_error_notified", False))
    cfg["exhaustion_notified"] = bool(cfg.get("exhaustion_notified", False))

    raw_token = str(cfg.get("session_token") or "").strip()
    try:
        from cursor_api import normalize_workos_token

        cfg["session_token"] = normalize_workos_token(raw_token) if raw_token else ""
    except Exception:
        cfg["session_token"] = raw_token

    mode = str(cfg.get("tray_display_mode") or "ring").strip().lower()
    cfg["tray_display_mode"] = mode if mode in _VALID_DISPLAY_MODES else "ring"

    if "alert_thresholds" not in raw and "low_quota_threshold" in raw:
        cfg["alert_thresholds"] = [int(cfg["low_quota_threshold"])]
    else:
        cfg["alert_thresholds"] = _parse_thresholds(cfg.get("alert_thresholds"))

    levels = cfg.get("alert_notified_levels") or []
    if not isinstance(levels, list):
        levels = []
    cfg["alert_notified_levels"] = sorted(
        {int(x) for x in levels if _is_int_like(x) and 1 <= int(x) <= 100}
    )

    from accounts import normalize_account_state

    normalize_account_state(cfg, raw=raw)
    return cfg


def _parse_thresholds(value: Any) -> list[int]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("，", ",").split(",") if p.strip()]
        nums = [int(float(p)) for p in parts if _is_int_like(p)]
    elif isinstance(value, (list, tuple)):
        nums = [int(x) for x in value if _is_int_like(x)]
    else:
        nums = list(DEFAULT_CONFIG["alert_thresholds"])
    cleaned = sorted({n for n in nums if 1 <= n <= 100}, reverse=True)
    return cleaned or list(DEFAULT_CONFIG["alert_thresholds"])


def _is_int_like(value: Any) -> bool:
    try:
        int(float(value))
        return True
    except (TypeError, ValueError):
        return False
