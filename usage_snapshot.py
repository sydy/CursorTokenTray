"""托盘与飞出层子进程之间的最近一次用量快照（无 GUI）。"""

from __future__ import annotations

import json
from typing import Any

from config import CONFIG_DIR, ensure_config_dir
from cursor_api import ModelTokenUsage, UsageSnapshot

SNAPSHOT_PATH = CONFIG_DIR / "last_status.json"


def write_status_snapshot(
    *,
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
    account_label: str | None = None,
) -> None:
    ensure_config_dir()
    payload = {
        "error_message": error_message,
        "updated_at": updated_at,
        "account_label": account_label or "",
        "usage": None if usage is None else _usage_to_dict(usage),
    }
    try:
        SNAPSHOT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def read_status_snapshot() -> tuple[UsageSnapshot | None, str | None, str | None]:
    if not SNAPSHOT_PATH.exists():
        return None, None, None
    try:
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None, None, None
    if not isinstance(raw, dict):
        return None, None, None
    err = raw.get("error_message")
    updated = raw.get("updated_at")
    usage_raw = raw.get("usage")
    usage = _usage_from_dict(usage_raw) if isinstance(usage_raw, dict) else None
    return usage, (None if err is None else str(err)), (None if updated is None else str(updated))


def read_account_label() -> str:
    if not SNAPSHOT_PATH.exists():
        return ""
    try:
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("account_label") or "")


def _usage_to_dict(usage: UsageSnapshot) -> dict[str, Any]:
    return {
        "used_percent": usage.used_percent,
        "remaining_percent": usage.remaining_percent,
        "auto_percent_used": usage.auto_percent_used,
        "api_percent_used": usage.api_percent_used,
        "total_percent_used": usage.total_percent_used,
        "membership_type": usage.membership_type,
        "billing_cycle_start": usage.billing_cycle_start,
        "billing_cycle_end": usage.billing_cycle_end,
        "days_remaining": usage.days_remaining,
        "days_elapsed": usage.days_elapsed,
        "estimated_usable_days": usage.estimated_usable_days,
        "total_tokens": usage.total_tokens,
        "model_usages": [
            {
                "name": item.name,
                "tokens": item.tokens,
                "cents": item.cents,
                "tier": item.tier,
                "usage_percent": item.usage_percent,
            }
            for item in usage.model_usages
        ],
    }


def _usage_from_dict(data: dict[str, Any]) -> UsageSnapshot | None:
    try:
        models = []
        for item in data.get("model_usages") or ():
            if not isinstance(item, dict):
                continue
            models.append(
                ModelTokenUsage(
                    name=str(item.get("name") or ""),
                    tokens=int(item.get("tokens") or 0),
                    cents=float(item.get("cents") or 0),
                    tier=int(item.get("tier") or 0),
                    usage_percent=(
                        None
                        if item.get("usage_percent") is None
                        else float(item.get("usage_percent"))
                    ),
                )
            )
        return UsageSnapshot(
            used_percent=float(data.get("used_percent") or 0),
            remaining_percent=float(data.get("remaining_percent") or 0),
            auto_percent_used=_opt_float(data.get("auto_percent_used")),
            api_percent_used=_opt_float(data.get("api_percent_used")),
            total_percent_used=_opt_float(data.get("total_percent_used")),
            membership_type=str(data.get("membership_type") or ""),
            billing_cycle_start=data.get("billing_cycle_start"),
            billing_cycle_end=data.get("billing_cycle_end"),
            days_remaining=_opt_int(data.get("days_remaining")),
            days_elapsed=_opt_float(data.get("days_elapsed")),
            estimated_usable_days=_opt_float(data.get("estimated_usable_days")),
            raw={},
            total_tokens=_opt_int(data.get("total_tokens")),
            model_usages=tuple(models),
        )
    except (TypeError, ValueError):
        return None


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
