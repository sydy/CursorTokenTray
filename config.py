"""本地配置读写。"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from platform_util import app_config_dir

APP_NAME = "CursorToken剩余进度"
CONFIG_DIR = app_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "session_token": "",
    "refresh_interval_minutes": 10,
    "low_quota_threshold": 20,  # 兼容旧版；迁移到 alert_thresholds
    "alert_thresholds": [50, 20, 5],
    "notify_enabled": True,
    "notify_exhaustion_risk": True,
    "autostart_enabled": True,
    "tray_display_mode": "ring",  # ring | number | dot
    # 去重状态
    "low_quota_notified": False,
    "auth_error_notified": False,
    "alert_notified_levels": [],
    "exhaustion_notified": False,
}

_VALID_DISPLAY_MODES = frozenset({"ring", "number", "dot"})


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_config_dir()
    if not CONFIG_PATH.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg)
        return cfg

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    cfg = _normalize_config(cfg, raw=data)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_config_dir()
    normalized = _normalize_config({**deepcopy(DEFAULT_CONFIG), **cfg}, raw=cfg)
    to_save = deepcopy(DEFAULT_CONFIG)
    to_save.update({k: v for k, v in normalized.items() if k in DEFAULT_CONFIG})
    # 原子写入，避免断电/崩溃截断 config.json
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, CONFIG_PATH)


def update_config(**kwargs: Any) -> dict[str, Any]:
    cfg = load_config()
    for key, value in kwargs.items():
        if key in DEFAULT_CONFIG:
            cfg[key] = value
    save_config(cfg)
    return cfg


def _normalize_config(cfg: dict[str, Any], *, raw: dict[str, Any]) -> dict[str, Any]:
    cfg["refresh_interval_minutes"] = max(1, int(cfg.get("refresh_interval_minutes", 10)))
    cfg["low_quota_threshold"] = min(100, max(1, int(cfg.get("low_quota_threshold", 20))))
    cfg["notify_enabled"] = bool(cfg.get("notify_enabled", True))
    cfg["notify_exhaustion_risk"] = bool(cfg.get("notify_exhaustion_risk", True))
    cfg["autostart_enabled"] = bool(cfg.get("autostart_enabled", True))
    cfg["low_quota_notified"] = bool(cfg.get("low_quota_notified", False))
    cfg["auth_error_notified"] = bool(cfg.get("auth_error_notified", False))
    cfg["exhaustion_notified"] = bool(cfg.get("exhaustion_notified", False))

    # 只保留规范化后的 WorkosCursorSessionToken（避免整段 Cookie 入库）
    raw_token = str(cfg.get("session_token") or "").strip()
    try:
        from cursor_api import normalize_workos_token

        cfg["session_token"] = normalize_workos_token(raw_token) if raw_token else ""
    except Exception:
        cfg["session_token"] = raw_token

    mode = str(cfg.get("tray_display_mode") or "ring").strip().lower()
    cfg["tray_display_mode"] = mode if mode in _VALID_DISPLAY_MODES else "ring"

    # 旧版仅有 low_quota_threshold、且未写过 alert_thresholds → 迁移为单档
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
