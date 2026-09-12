"""账号多端同步：口令加密信封 + 按账号时间戳合并。

登录后由 cloud_sync 把信封上传到 https://sync.harker.cn。
加密密钥由登录密码在本地派生，服务器只存密文。
同步账号身份和跨设备设置，不覆盖本机告警去重与用量缓存。
导出 / 导入仍使用同一加密格式作备份。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from accounts import (
    clamp_temp_valid_days,
    clamp_temp_valid_hours,
    empty_account,
    list_accounts,
    sanitize_account,
    sanitize_account_kind,
    sync_legacy_fields,
)

SYNC_FORMAT = "cursortokentray.accounts.v1"
SYNC_FORMAT_V2 = "cursortokentray.sync.v2"
SYNC_FORMATS = {SYNC_FORMAT, SYNC_FORMAT_V2}
SYNC_FILENAME = "CursorTokenTray.accounts.sync"
SYNC_KDF = "pbkdf2-sha256"
DEFAULT_ITERATIONS = 210_000
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
SYNC_FILE_SUFFIXES = {".sync", ".json"}

SYNC_CONFIG_KEYS = (
    "sync_enabled",
    "sync_secret",
    "sync_device_id",
    "sync_last_at",
    "sync_last_error",
    "cloud_email",
    "cloud_access_token",
    "cloud_refresh_token",
    "cloud_revision",
    "deleted_accounts",
)


def now_iso(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def compare_iso(left: Any, right: Any) -> int:
    a = parse_iso(left)
    b = parse_iso(right)
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def newer_iso(left: Any, right: Any) -> str:
    return str(left or "") if compare_iso(left, right) >= 0 else str(right or "")


def resolve_sync_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return ""
    p = Path(raw).expanduser()
    if raw.endswith(("/", "\\")) or (p.exists() and p.is_dir()) or p.suffix.lower() not in SYNC_FILE_SUFFIXES:
        return str(p / SYNC_FILENAME)
    return str(p)


def ensure_device_id(cfg: dict[str, Any]) -> str:
    current = str(cfg.get("sync_device_id") or "").strip()
    if current:
        return current
    current = str(uuid.uuid4())
    cfg["sync_device_id"] = current
    return current


def sanitize_deleted(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    best: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id") or "").strip()
        deleted_at = str(item.get("deleted_at") or "").strip()
        if not aid or not deleted_at:
            continue
        prev = best.get(aid, "")
        if compare_iso(deleted_at, prev) >= 0:
            best[aid] = deleted_at
    return [{"id": aid, "deleted_at": best[aid]} for aid in sorted(best)]


def remember_deleted(cfg: dict[str, Any], account_id: str, deleted_at: str | None = None) -> None:
    aid = str(account_id or "").strip()
    if not aid:
        return
    rows = sanitize_deleted(cfg.get("deleted_accounts"))
    stamp = deleted_at or now_iso()
    rows = [r for r in rows if r["id"] != aid]
    rows.append({"id": aid, "deleted_at": stamp})
    cfg["deleted_accounts"] = sanitize_deleted(rows)


def forget_deleted(cfg: dict[str, Any], account_id: str) -> None:
    aid = str(account_id or "").strip()
    rows = [r for r in sanitize_deleted(cfg.get("deleted_accounts")) if r["id"] != aid]
    cfg["deleted_accounts"] = rows


def touch_account(account: dict[str, Any], stamp: str | None = None) -> None:
    account["sync_updated_at"] = stamp or now_iso()


def _snapshot_actual_cny(account: dict[str, Any]) -> float:
    from usage_report import clamp_actual_cny

    return clamp_actual_cny(account.get("actual_cny", account.get("actualCny")))


def _snapshot_channel(account: dict[str, Any]) -> str:
    from usage_report import sanitize_account_channel

    return sanitize_account_channel(account.get("channel"))


def snapshot_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(account.get("id") or "").strip(),
        "label": str(account.get("label") or "").strip(),
        "token": str(account.get("token") or "").strip(),
        "membership_type": str(account.get("membership_type") or "").strip(),
        "account_kind": sanitize_account_kind(account.get("account_kind")),
        "temp_start_at": str(account.get("temp_start_at") or "").strip(),
        "temp_valid_days": clamp_temp_valid_days(account.get("temp_valid_days")),
        "temp_valid_hours": clamp_temp_valid_hours(account.get("temp_valid_hours")),
        "actual_cny": _snapshot_actual_cny(account),
        "channel": _snapshot_channel(account),
        "sync_updated_at": str(account.get("sync_updated_at") or "").strip(),
    }


def snapshot_settings(raw: Any) -> dict[str, Any]:
    from config import _VALID_DISPLAY_MODES, _parse_thresholds
    from usage_report import clamp_monthly_plan_usd, clamp_usd_cny_rate

    source = raw if isinstance(raw, dict) else {}
    mode = str(source.get("tray_display_mode") or "ring").strip().lower()
    if mode not in _VALID_DISPLAY_MODES:
        mode = "ring"
    try:
        interval = max(1, int(source.get("refresh_interval_minutes") or 10))
    except (TypeError, ValueError):
        interval = 10
    return {
        "refresh_interval_minutes": interval,
        "alert_thresholds": _parse_thresholds(source.get("alert_thresholds")),
        "notify_enabled": bool(source.get("notify_enabled", True)),
        "notify_exhaustion_risk": bool(source.get("notify_exhaustion_risk", True)),
        "tray_display_mode": mode,
        "monthly_plan_usd": clamp_monthly_plan_usd(source.get("monthly_plan_usd")),
        "usd_cny_rate": clamp_usd_cny_rate(source.get("usd_cny_rate")),
    }


def apply_settings(cfg: dict[str, Any], settings: Any) -> None:
    if not isinstance(settings, dict):
        return
    row = snapshot_settings(settings)
    cfg["refresh_interval_minutes"] = row["refresh_interval_minutes"]
    cfg["alert_thresholds"] = row["alert_thresholds"]
    cfg["notify_enabled"] = row["notify_enabled"]
    cfg["notify_exhaustion_risk"] = row["notify_exhaustion_risk"]
    cfg["tray_display_mode"] = row["tray_display_mode"]
    cfg["monthly_plan_usd"] = row["monthly_plan_usd"]
    cfg["usd_cny_rate"] = row["usd_cny_rate"]


def snapshot_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    accounts = []
    for acc in list_accounts(cfg):
        row = snapshot_account(acc)
        if not row["id"] or not row["token"]:
            continue
        accounts.append(row)
    return {
        "version": 1,
        "updated_at": str(cfg.get("sync_last_at") or ""),
        "device_id": str(cfg.get("sync_device_id") or ""),
        "active_account_id": str(cfg.get("active_account_id") or ""),
        "accounts": accounts,
        "deleted": sanitize_deleted(cfg.get("deleted_accounts")),
        "settings": snapshot_settings(cfg),
    }


def snapshot_identity(snap: dict[str, Any]) -> tuple:
    accounts = tuple(
        (
            a["id"],
            a["label"],
            a["token"],
            a["membership_type"],
            a.get("account_kind") or "",
            a.get("temp_start_at") or "",
            int(a.get("temp_valid_days") or 0),
            int(a.get("temp_valid_hours") or 0),
            _snapshot_actual_cny(a),
            _snapshot_channel(a),
            a["sync_updated_at"],
        )
        for a in sorted(snap.get("accounts") or [], key=lambda x: x.get("id") or "")
    )
    deleted = tuple(
        (d["id"], d["deleted_at"])
        for d in sorted(snap.get("deleted") or [], key=lambda x: x.get("id") or "")
    )
    settings = snap.get("settings")
    settings_key = tuple(sorted(snapshot_settings(settings).items())) if isinstance(settings, dict) else ()
    return (str(snap.get("active_account_id") or ""), accounts, deleted, settings_key)


def merge_snapshots(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    tombstones: dict[str, str] = {}
    for row in sanitize_deleted(local.get("deleted")) + sanitize_deleted(remote.get("deleted")):
        prev = tombstones.get(row["id"], "")
        if compare_iso(row["deleted_at"], prev) >= 0:
            tombstones[row["id"]] = row["deleted_at"]

    chosen: dict[str, dict[str, Any]] = {}
    for src in (local.get("accounts") or []) + (remote.get("accounts") or []):
        if not isinstance(src, dict):
            continue
        acc = snapshot_account(src)
        if not acc["id"] or not acc["token"]:
            continue
        tomb = tombstones.get(acc["id"])
        if tomb and compare_iso(tomb, acc["sync_updated_at"]) >= 0:
            continue
        prev = chosen.get(acc["id"])
        if prev is None:
            chosen[acc["id"]] = acc
            continue
        cmp = compare_iso(acc["sync_updated_at"], prev["sync_updated_at"])
        if cmp > 0:
            chosen[acc["id"]] = acc
        elif cmp == 0 and not prev["token"] and acc["token"]:
            chosen[acc["id"]] = acc

    for aid in list(tombstones):
        if aid in chosen:
            tombstones.pop(aid, None)

    if compare_iso(remote.get("updated_at"), local.get("updated_at")) > 0:
        active = str(remote.get("active_account_id") or "")
        settings = remote.get("settings") if remote.get("settings") is not None else local.get("settings")
    else:
        active = str(local.get("active_account_id") or "")
        settings = local.get("settings") if local.get("settings") is not None else remote.get("settings")
    if active not in chosen:
        active = next(iter(sorted(chosen)), "")

    return {
        "version": 1,
        "updated_at": newer_iso(local.get("updated_at"), remote.get("updated_at")),
        "device_id": str(local.get("device_id") or remote.get("device_id") or ""),
        "active_account_id": active,
        "accounts": [chosen[k] for k in sorted(chosen)],
        "deleted": [{"id": aid, "deleted_at": tombstones[aid]} for aid in sorted(tombstones)],
        "settings": snapshot_settings(settings) if isinstance(settings, dict) else None,
    }


def apply_snapshot_to_config(cfg: dict[str, Any], snap: dict[str, Any]) -> bool:
    """把合并结果写回配置。保留本机用量缓存与告警去重。返回是否改了账号列表。"""
    before = [
        (
            a.get("id"),
            a.get("token"),
            a.get("label"),
            a.get("membership_type"),
            a.get("account_kind"),
            a.get("temp_start_at"),
            a.get("temp_valid_days"),
            a.get("temp_valid_hours"),
            a.get("actual_cny"),
            a.get("channel"),
            a.get("sync_updated_at"),
        )
        for a in list_accounts(cfg)
    ]
    before_settings = snapshot_settings(cfg)
    existing = {str(a.get("id") or ""): a for a in list_accounts(cfg)}
    merged_accounts: list[dict[str, Any]] = []
    for row in snap.get("accounts") or []:
        if not isinstance(row, dict):
            continue
        ident = snapshot_account(row)
        if not ident["id"] or not ident["token"]:
            continue
        old = existing.get(ident["id"])
        if old is None:
            acc = empty_account(token=ident["token"], account_id=ident["id"], label=ident["label"])
            acc["membership_type"] = ident["membership_type"]
            _apply_identity(acc, ident)
            merged_accounts.append(acc)
            continue
        old["token"] = ident["token"]
        old["label"] = ident["label"]
        if ident["membership_type"]:
            old["membership_type"] = ident["membership_type"]
        _apply_identity(old, ident)
        merged_accounts.append(old)

    cfg["accounts"] = merged_accounts
    cfg["deleted_accounts"] = sanitize_deleted(snap.get("deleted"))
    active = str(snap.get("active_account_id") or "").strip()
    ids = {str(a.get("id") or "") for a in merged_accounts}
    if active in ids:
        cfg["active_account_id"] = active
    elif merged_accounts:
        cfg["active_account_id"] = str(merged_accounts[0]["id"])
    else:
        cfg["active_account_id"] = ""
    apply_settings(cfg, snap.get("settings"))
    sync_legacy_fields(cfg)
    after = [
        (
            a.get("id"),
            a.get("token"),
            a.get("label"),
            a.get("membership_type"),
            a.get("account_kind"),
            a.get("temp_start_at"),
            a.get("temp_valid_days"),
            a.get("temp_valid_hours"),
            a.get("actual_cny"),
            a.get("channel"),
            a.get("sync_updated_at"),
        )
        for a in list_accounts(cfg)
    ]
    return before != after or before_settings != snapshot_settings(cfg)


def _apply_identity(account: dict[str, Any], ident: dict[str, Any]) -> None:
    if ident.get("membership_type"):
        account["membership_type"] = ident["membership_type"]
    account["account_kind"] = sanitize_account_kind(ident.get("account_kind"))
    account["temp_start_at"] = str(ident.get("temp_start_at") or "").strip()
    account["temp_valid_days"] = clamp_temp_valid_days(ident.get("temp_valid_days"))
    account["temp_valid_hours"] = clamp_temp_valid_hours(ident.get("temp_valid_hours"))
    account["actual_cny"] = _snapshot_actual_cny(ident)
    account["channel"] = _snapshot_channel(ident)
    account["sync_updated_at"] = ident["sync_updated_at"]


def derive_key(passphrase: str, salt: bytes, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    secret = (passphrase or "").encode("utf-8")
    if not secret:
        raise ValueError("同步口令不能为空")
    if iterations < 1000:
        raise ValueError("KDF 迭代次数过低")
    return hashlib.pbkdf2_hmac("sha256", secret, salt, iterations, dklen=KEY_LEN)


def _aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).encrypt(nonce, plaintext, None)


def _aes_gcm_decrypt(key: bytes, nonce: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).decrypt(nonce, blob, None)


def encrypt_envelope(
    payload: dict[str, Any],
    passphrase: str,
    *,
    salt: bytes | None = None,
    nonce: bytes | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict[str, Any]:
    salt_b = salt if salt is not None else secrets.token_bytes(SALT_LEN)
    nonce_b = nonce if nonce is not None else secrets.token_bytes(NONCE_LEN)
    if len(salt_b) != SALT_LEN or len(nonce_b) != NONCE_LEN:
        raise ValueError("salt/nonce 长度不正确")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = derive_key(passphrase, salt_b, iterations)
    blob = _aes_gcm_encrypt(key, nonce_b, raw)
    fmt = SYNC_FORMAT_V2 if payload.get("settings") is not None else SYNC_FORMAT
    return {
        "format": fmt,
        "kdf": SYNC_KDF,
        "iterations": iterations,
        "salt": base64.b64encode(salt_b).decode("ascii"),
        "nonce": base64.b64encode(nonce_b).decode("ascii"),
        "ciphertext": base64.b64encode(blob).decode("ascii"),
    }


def decrypt_envelope(envelope: dict[str, Any], passphrase: str) -> dict[str, Any]:
    if str(envelope.get("format") or "") not in SYNC_FORMATS:
        raise ValueError("不是 CursorTokenTray 账号同步文件")
    if str(envelope.get("kdf") or "") != SYNC_KDF:
        raise ValueError("不支持的同步文件密钥算法")
    try:
        iterations = int(envelope.get("iterations") or 0)
        salt = base64.b64decode(str(envelope.get("salt") or ""), validate=True)
        nonce = base64.b64decode(str(envelope.get("nonce") or ""), validate=True)
        blob = base64.b64decode(str(envelope.get("ciphertext") or ""), validate=True)
    except Exception as exc:
        raise ValueError("同步文件损坏") from exc
    if len(salt) != SALT_LEN or len(nonce) != NONCE_LEN or len(blob) < TAG_LEN:
        raise ValueError("同步文件损坏")
    key = derive_key(passphrase, salt, iterations)
    try:
        raw = _aes_gcm_decrypt(key, nonce, blob)
    except Exception as exc:
        raise ValueError("同步口令不正确或文件已损坏") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("同步文件内容无法解析") from exc
    if not isinstance(payload, dict):
        raise ValueError("同步文件内容无法解析")
    payload["accounts"] = [snapshot_account(a) for a in payload.get("accounts") or [] if isinstance(a, dict)]
    payload["deleted"] = sanitize_deleted(payload.get("deleted"))
    payload["active_account_id"] = str(payload.get("active_account_id") or "")
    payload["updated_at"] = str(payload.get("updated_at") or "")
    payload["device_id"] = str(payload.get("device_id") or "")
    payload["version"] = 1
    if isinstance(payload.get("settings"), dict):
        payload["settings"] = snapshot_settings(payload["settings"])
    else:
        payload["settings"] = None
    return payload


def read_envelope(path: str) -> dict[str, Any] | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取同步文件") from exc
    if not isinstance(data, dict):
        raise ValueError("同步文件内容无法解析")
    return data


def write_envelope(path: str, envelope: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    text = json.dumps(envelope, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def sync_ready(cfg: dict[str, Any]) -> str:
    if not cfg.get("sync_enabled"):
        return "请先登录云同步"
    if not str(cfg.get("cloud_access_token") or cfg.get("cloud_refresh_token") or "").strip():
        return "请先登录云同步"
    if not str(cfg.get("sync_secret") or "").strip():
        return "请重新登录以解锁同步密钥"
    return ""


def reconcile(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
    write: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """拉取云端、合并、必要时写回。返回 (cfg, status)。"""
    from cloud_sync import reconcile as cloud_reconcile

    return cloud_reconcile(cfg, now=now, write=write)


def export_to_file(cfg: dict[str, Any], path: str, passphrase: str | None = None) -> str:
    secret = (passphrase if passphrase is not None else str(cfg.get("sync_secret") or "")).strip()
    if not secret:
        raise ValueError("请设置同步口令")
    dest = resolve_sync_path(path) if Path(path).suffix.lower() not in SYNC_FILE_SUFFIXES else path
    snap = snapshot_from_config(cfg)
    snap["updated_at"] = now_iso()
    snap["device_id"] = ensure_device_id(cfg)
    write_envelope(dest, encrypt_envelope(snap, secret))
    return dest


def import_from_file(cfg: dict[str, Any], path: str, passphrase: str | None = None) -> dict[str, Any]:
    secret = (passphrase if passphrase is not None else str(cfg.get("sync_secret") or "")).strip()
    if not secret:
        raise ValueError("请设置同步口令")
    envelope = read_envelope(path)
    if envelope is None:
        raise ValueError("找不到同步文件")
    remote = decrypt_envelope(envelope, secret)
    local = snapshot_from_config(cfg)
    merged = merge_snapshots(local, remote)
    apply_snapshot_to_config(cfg, merged)
    cfg["sync_last_at"] = now_iso()
    cfg["sync_last_error"] = ""
    return cfg


def normalize_sync_config(cfg: dict[str, Any], *, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else cfg
    cfg["sync_secret"] = str(source.get("sync_secret", cfg.get("sync_secret", "")) or "")
    cfg["sync_device_id"] = str(source.get("sync_device_id", cfg.get("sync_device_id", "")) or "").strip()
    cfg["sync_last_at"] = str(source.get("sync_last_at", cfg.get("sync_last_at", "")) or "").strip()
    cfg["sync_last_error"] = str(source.get("sync_last_error", cfg.get("sync_last_error", "")) or "")
    cfg["cloud_email"] = str(source.get("cloud_email", cfg.get("cloud_email", "")) or "").strip().lower()
    cfg["cloud_access_token"] = str(source.get("cloud_access_token", cfg.get("cloud_access_token", "")) or "")
    cfg["cloud_refresh_token"] = str(source.get("cloud_refresh_token", cfg.get("cloud_refresh_token", "")) or "")
    try:
        cfg["cloud_revision"] = max(0, int(source.get("cloud_revision", cfg.get("cloud_revision", 0)) or 0))
    except (TypeError, ValueError):
        cfg["cloud_revision"] = 0
    logged_in = bool(cfg["cloud_access_token"] or cfg["cloud_refresh_token"])
    cfg["sync_enabled"] = bool(source.get("sync_enabled", cfg.get("sync_enabled", False))) and logged_in
    cfg["deleted_accounts"] = sanitize_deleted(source.get("deleted_accounts", cfg.get("deleted_accounts")))
    cfg.pop("sync_path", None)
    return cfg
