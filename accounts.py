"""多账号：列表、当前号、与旧版 session_token 兼容。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cursor_api import account_id_from_token, normalize_workos_token, session_token_variants

ACCOUNT_KEYS = (
    "id",
    "label",
    "token",
    "membership_type",
    "last_remaining",
    "last_error",
    "updated_at",
    "alert_notified_levels",
    "auth_error_notified",
    "exhaustion_notified",
    "low_quota_notified",
)


def empty_account(*, token: str = "", account_id: str = "", label: str = "") -> dict[str, Any]:
    return {
        "id": account_id,
        "label": label,
        "token": token,
        "membership_type": "",
        "last_remaining": None,
        "last_error": "",
        "updated_at": "",
        "alert_notified_levels": [],
        "auth_error_notified": False,
        "exhaustion_notified": False,
        "low_quota_notified": False,
    }


def sanitize_account(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    token = _normalize_token(str(raw.get("token") or ""))
    if not token:
        return None
    account_id = str(raw.get("id") or "").strip() or account_id_from_token(token)
    if not account_id:
        return None
    acc = empty_account(token=token, account_id=account_id)
    acc["label"] = str(raw.get("label") or "").strip()
    acc["membership_type"] = str(raw.get("membership_type") or "").strip()
    acc["last_error"] = str(raw.get("last_error") or "")
    acc["updated_at"] = str(raw.get("updated_at") or "")
    remaining = raw.get("last_remaining")
    if remaining is None or remaining == "":
        acc["last_remaining"] = None
    else:
        try:
            acc["last_remaining"] = round(float(remaining), 2)
        except (TypeError, ValueError):
            acc["last_remaining"] = None
    levels = raw.get("alert_notified_levels") or []
    if not isinstance(levels, list):
        levels = []
    acc["alert_notified_levels"] = sorted(
        {int(x) for x in levels if _is_int_like(x) and 1 <= int(x) <= 100}
    )
    acc["auth_error_notified"] = bool(raw.get("auth_error_notified", False))
    acc["exhaustion_notified"] = bool(raw.get("exhaustion_notified", False))
    acc["low_quota_notified"] = bool(raw.get("low_quota_notified", False))
    return acc


def display_label(account: dict[str, Any] | None) -> str:
    if not account:
        return ""
    label = str(account.get("label") or "").strip()
    if label:
        return label
    memb = str(account.get("membership_type") or "").strip()
    if memb:
        return memb
    aid = str(account.get("id") or "").strip()
    if aid.startswith("tok_"):
        return "未命名账号"
    if len(aid) > 14:
        return aid[:12] + "…"
    return aid or "未命名账号"


def format_account_caption(account: dict[str, Any] | None, *, is_active: bool = False) -> str:
    if not account:
        return "暂无账号"
    name = display_label(account)
    memb = str(account.get("membership_type") or "").strip()
    parts = [name]
    if memb and memb.lower() != name.lower():
        parts.append(memb)
    remaining = account.get("last_remaining")
    if remaining is not None:
        try:
            parts.append(f"剩余 {float(remaining):.0f}%")
        except (TypeError, ValueError):
            pass
    err = str(account.get("last_error") or "").strip()
    if err and remaining is None:
        parts.append("已失效")
    text = " · ".join(parts)
    if is_active:
        text += "  (当前)"
    return text


def list_accounts(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows = cfg.get("accounts") or []
    if not isinstance(rows, list):
        return []
    return [a for a in rows if isinstance(a, dict) and a.get("id") and a.get("token")]


def active_account(cfg: dict[str, Any]) -> dict[str, Any] | None:
    active_id = str(cfg.get("active_account_id") or "").strip()
    accounts = list_accounts(cfg)
    for acc in accounts:
        if acc.get("id") == active_id:
            return acc
    return accounts[0] if accounts else None


def find_account(cfg: dict[str, Any], account_id: str) -> dict[str, Any] | None:
    target = str(account_id or "").strip()
    if not target:
        return None
    for acc in list_accounts(cfg):
        if acc.get("id") == target:
            return acc
    return None


def upsert_account(
    cfg: dict[str, Any],
    token: str,
    *,
    label: str | None = None,
    membership_type: str | None = None,
    remaining: float | None = None,
    error: str | None = None,
    activate: bool = True,
) -> tuple[dict[str, Any], bool]:
    """写入或更新账号。返回 (account, created)。"""
    token = _normalize_token(token)
    if not token:
        raise ValueError("Token 为空")
    account_id = account_id_from_token(token)
    if not account_id:
        raise ValueError("无法从 Token 识别账号")

    accounts = list_accounts(cfg)
    existing = next((a for a in accounts if a.get("id") == account_id), None)
    created = existing is None
    if existing is None:
        existing = empty_account(token=token, account_id=account_id)
        if not accounts:
            _copy_legacy_flags(cfg, existing)
        accounts.append(existing)
    existing["token"] = token
    if label is not None:
        existing["label"] = str(label).strip()
    if membership_type is not None:
        existing["membership_type"] = str(membership_type).strip()
    if remaining is not None:
        existing["last_remaining"] = round(float(remaining), 2)
        existing["last_error"] = ""
    if error is not None:
        existing["last_error"] = str(error)
    cfg["accounts"] = accounts
    if activate:
        cfg["active_account_id"] = account_id
    sync_legacy_fields(cfg)
    return existing, created


def set_active_account(cfg: dict[str, Any], account_id: str) -> bool:
    acc = find_account(cfg, account_id)
    if acc is None:
        return False
    cfg["active_account_id"] = acc["id"]
    sync_legacy_fields(cfg)
    return True


def rename_account(cfg: dict[str, Any], account_id: str, label: str) -> bool:
    acc = find_account(cfg, account_id)
    if acc is None:
        return False
    acc["label"] = str(label or "").strip()
    return True


def remove_account(cfg: dict[str, Any], account_id: str) -> bool:
    target = str(account_id or "").strip()
    accounts = list_accounts(cfg)
    kept = [a for a in accounts if a.get("id") != target]
    if len(kept) == len(accounts):
        return False
    cfg["accounts"] = kept
    if str(cfg.get("active_account_id") or "") == target:
        cfg["active_account_id"] = str(kept[0]["id"]) if kept else ""
    sync_legacy_fields(cfg)
    return True


def existing_token_variants(cfg: dict[str, Any]) -> set[str]:
    skip: set[str] = set()
    for acc in list_accounts(cfg):
        for variant in session_token_variants(str(acc.get("token") or "")):
            skip.add(variant)
        token = str(acc.get("token") or "").strip()
        if token:
            skip.add(token)
    return skip


def sync_legacy_fields(cfg: dict[str, Any]) -> None:
    """session_token 与顶层告警去重字段跟随当前账号，兼容旧读取路径。"""
    acc = active_account(cfg)
    if acc is None:
        cfg["session_token"] = ""
        cfg["active_account_id"] = ""
        cfg["accounts"] = []
        cfg["alert_notified_levels"] = []
        cfg["auth_error_notified"] = False
        cfg["exhaustion_notified"] = False
        cfg["low_quota_notified"] = False
        return
    cfg["active_account_id"] = str(acc.get("id") or "")
    cfg["session_token"] = str(acc.get("token") or "")
    cfg["alert_notified_levels"] = list(acc.get("alert_notified_levels") or [])
    cfg["auth_error_notified"] = bool(acc.get("auth_error_notified", False))
    cfg["exhaustion_notified"] = bool(acc.get("exhaustion_notified", False))
    cfg["low_quota_notified"] = bool(acc.get("low_quota_notified", False))
    cfg["accounts"] = list_accounts(cfg)


def normalize_account_state(cfg: dict[str, Any], *, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """把旧版单 Token 配置迁成账号列表，并让 session_token 与当前号一致。"""
    source = raw if isinstance(raw, dict) else cfg
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_accounts = source.get("accounts", cfg.get("accounts"))
    if isinstance(raw_accounts, list):
        for item in raw_accounts:
            acc = sanitize_account(item)
            if acc is None or acc["id"] in seen:
                continue
            seen.add(acc["id"])
            accounts.append(acc)

    token = _normalize_token(str(cfg.get("session_token") or source.get("session_token") or ""))
    active_id = str(cfg.get("active_account_id") or source.get("active_account_id") or "").strip()
    cfg["accounts"] = accounts

    if token:
        active = next((a for a in accounts if a.get("id") == active_id), None)
        if active is None or str(active.get("token") or "") != token:
            acc, _created = upsert_account(cfg, token, activate=True)
            if len(accounts) == 0:
                _copy_legacy_flags(cfg, acc)
            accounts = list_accounts(cfg)
            active_id = str(acc.get("id") or "")

    cfg["accounts"] = accounts
    if accounts:
        ids = {str(a.get("id") or "") for a in accounts}
        if active_id not in ids:
            active_id = str(accounts[0]["id"])
        cfg["active_account_id"] = active_id
    else:
        cfg["active_account_id"] = ""
    sync_legacy_fields(cfg)
    return cfg


def apply_snapshot_to_account(
    account: dict[str, Any],
    *,
    membership_type: str | None = None,
    remaining: float | None = None,
    error: str | None = None,
    updated_at: str | None = None,
) -> None:
    if membership_type is not None:
        account["membership_type"] = str(membership_type).strip()
    if remaining is not None:
        account["last_remaining"] = round(float(remaining), 2)
    if error is not None:
        account["last_error"] = str(error)
    elif remaining is not None:
        account["last_error"] = ""
    if updated_at is not None:
        account["updated_at"] = str(updated_at)


def _normalize_token(token: str) -> str:
    raw = (token or "").strip()
    if not raw:
        return ""
    try:
        return normalize_workos_token(raw)
    except Exception:
        return raw


def _copy_legacy_flags(cfg: dict[str, Any], account: dict[str, Any]) -> None:
    levels = cfg.get("alert_notified_levels") or []
    if not isinstance(levels, list):
        levels = []
    account["alert_notified_levels"] = sorted(
        {int(x) for x in levels if _is_int_like(x) and 1 <= int(x) <= 100}
    )
    account["auth_error_notified"] = bool(cfg.get("auth_error_notified", False))
    account["exhaustion_notified"] = bool(cfg.get("exhaustion_notified", False))
    account["low_quota_notified"] = bool(cfg.get("low_quota_notified", False))


def _is_int_like(value: Any) -> bool:
    try:
        int(float(value))
        return True
    except (TypeError, ValueError):
        return False


def clone_accounts(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    out["accounts"] = [deepcopy(a) for a in list_accounts(cfg)]
    return out
