"""云同步 HTTP 客户端。服务端地址写死，口令只用于本地加解密。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable

from account_sync import (
    apply_snapshot_to_config,
    decrypt_envelope,
    encrypt_envelope,
    ensure_device_id,
    merge_snapshots,
    now_iso,
    snapshot_from_config,
    snapshot_identity,
    sync_ready,
)

API_BASE = "https://sync.harker.cn"
TIMEOUT = 60

Requester = Callable[[str, str, dict[str, str] | None, dict[str, Any] | None], tuple[int, Any]]


class CloudSyncError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def apply_session(cfg: dict[str, Any], email: str, password: str, tokens: dict[str, Any]) -> None:
    cfg["cloud_email"] = str(email or "").strip().lower()
    cfg["cloud_access_token"] = str(tokens.get("access_token") or "")
    cfg["cloud_refresh_token"] = str(tokens.get("refresh_token") or "")
    cfg["sync_secret"] = password
    cfg["sync_enabled"] = bool(cfg["cloud_access_token"] or cfg["cloud_refresh_token"])
    cfg["sync_last_error"] = ""


def clear_session(cfg: dict[str, Any], *, keep_email: bool = True) -> None:
    if not keep_email:
        cfg["cloud_email"] = ""
    cfg["cloud_access_token"] = ""
    cfg["cloud_refresh_token"] = ""
    cfg["sync_secret"] = ""
    cfg["cloud_revision"] = 0
    cfg["sync_enabled"] = False


def _http(method: str, url: str, headers: dict[str, str] | None, body: dict[str, Any] | None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw or exc.reason}
        return exc.code, payload
    except urllib.error.URLError as exc:
        raise CloudSyncError("无法连接同步服务器") from exc


def _detail(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
    return fallback


def request_json(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    requester: Requester | None = None,
    base: str = API_BASE,
) -> tuple[int, Any]:
    http = requester or _http
    return http(method, base.rstrip("/") + path, headers, body)


def register(email: str, password: str, *, requester: Requester | None = None, base: str = API_BASE) -> dict[str, Any]:
    status, payload = request_json("POST", "/v1/auth/register", body={"email": email, "password": password}, requester=requester, base=base)
    if status >= 400:
        raise CloudSyncError(_detail(payload, "注册失败"), status)
    return payload


def login(email: str, password: str, *, requester: Requester | None = None, base: str = API_BASE) -> dict[str, Any]:
    status, payload = request_json("POST", "/v1/auth/login", body={"email": email, "password": password}, requester=requester, base=base)
    if status >= 400:
        raise CloudSyncError(_detail(payload, "登录失败"), status)
    return payload


def logout(cfg: dict[str, Any], *, requester: Requester | None = None, base: str = API_BASE) -> None:
    refresh = str(cfg.get("cloud_refresh_token") or "")
    if refresh:
        try:
            request_json("POST", "/v1/auth/logout", body={"refresh_token": refresh}, requester=requester, base=base)
        except CloudSyncError:
            pass
    clear_session(cfg)


def _refresh(cfg: dict[str, Any], requester: Requester | None, base: str) -> bool:
    refresh = str(cfg.get("cloud_refresh_token") or "").strip()
    if not refresh:
        return False
    status, payload = request_json("POST", "/v1/auth/refresh", body={"refresh_token": refresh}, requester=requester, base=base)
    if status >= 400:
        clear_session(cfg)
        return False
    cfg["cloud_access_token"] = str(payload.get("access_token") or "")
    if payload.get("refresh_token"):
        cfg["cloud_refresh_token"] = str(payload["refresh_token"])
    return bool(cfg["cloud_access_token"])


def _authed(
    cfg: dict[str, Any],
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    requester: Requester | None = None,
    base: str = API_BASE,
) -> tuple[int, Any]:
    headers = {"Authorization": "Bearer " + str(cfg.get("cloud_access_token") or "")}
    status, payload = request_json(method, path, headers=headers, body=body, requester=requester, base=base)
    if status != 401:
        return status, payload
    if not _refresh(cfg, requester, base):
        return status, payload
    headers = {"Authorization": "Bearer " + str(cfg.get("cloud_access_token") or "")}
    return request_json(method, path, headers=headers, body=body, requester=requester, base=base)


def empty_snapshot() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "device_id": "",
        "active_account_id": "",
        "accounts": [],
        "deleted": [],
        "settings": None,
        "usage": None,
    }


def reconcile(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
    write: bool = True,
    requester: Requester | None = None,
    base: str = API_BASE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    status = {
        "ok": False,
        "changed": False,
        "pushed": False,
        "message": "",
        "path": API_BASE,
    }
    reason = sync_ready(cfg)
    if reason:
        status["message"] = reason
        cfg["sync_last_error"] = reason
        return cfg, status

    ensure_device_id(cfg)
    stamp = now_iso(now)
    passphrase = str(cfg.get("sync_secret") or "")
    local = snapshot_from_config(cfg)
    local["device_id"] = str(cfg.get("sync_device_id") or "")
    try:
        code, payload = _authed(cfg, "GET", "/v1/sync", requester=requester, base=base)
        if code >= 400:
            raise CloudSyncError(_detail(payload, "无法读取云端同步数据"), code)
        revision = int(payload.get("revision") or 0)
        envelope = payload.get("envelope")
        remote = decrypt_envelope(envelope, passphrase) if envelope else empty_snapshot()
        merged = merge_snapshots(local, remote)
        changed = apply_snapshot_to_config(cfg, merged)
        if write and snapshot_identity(merged) != snapshot_identity(remote):
            to_write = dict(merged)
            to_write["updated_at"] = stamp
            to_write["device_id"] = str(cfg.get("sync_device_id") or "")
            put_body = {"revision": revision, "envelope": encrypt_envelope(to_write, passphrase)}
            put_code, put_payload = _authed(cfg, "PUT", "/v1/sync", body=put_body, requester=requester, base=base)
            if put_code == 409:
                code, payload = _authed(cfg, "GET", "/v1/sync", requester=requester, base=base)
                if code >= 400:
                    raise CloudSyncError(_detail(payload, "同步冲突，请重试"), code)
                revision = int(payload.get("revision") or 0)
                envelope = payload.get("envelope")
                remote = decrypt_envelope(envelope, passphrase) if envelope else empty_snapshot()
                local = snapshot_from_config(cfg)
                local["device_id"] = str(cfg.get("sync_device_id") or "")
                merged = merge_snapshots(local, remote)
                changed = apply_snapshot_to_config(cfg, merged) or changed
                if snapshot_identity(merged) != snapshot_identity(remote):
                    to_write = dict(merged)
                    to_write["updated_at"] = stamp
                    to_write["device_id"] = str(cfg.get("sync_device_id") or "")
                    put_body = {"revision": revision, "envelope": encrypt_envelope(to_write, passphrase)}
                    put_code, put_payload = _authed(cfg, "PUT", "/v1/sync", body=put_body, requester=requester, base=base)
            if put_code >= 400:
                raise CloudSyncError(_detail(put_payload, "无法写入云端同步数据"), put_code)
            cfg["cloud_revision"] = int(put_payload.get("revision") or revision + 1)
            status["pushed"] = True
        else:
            cfg["cloud_revision"] = revision
        cfg["sync_last_at"] = stamp
        cfg["sync_last_error"] = ""
        status["ok"] = True
        status["changed"] = changed
        if changed and status["pushed"]:
            status["message"] = "已合并并对齐云端"
        elif changed:
            status["message"] = "已从云端导入账号、设置和用量"
        elif status["pushed"]:
            status["message"] = "已上传到云端"
        else:
            status["message"] = "账号、设置和用量已与云端一致"
        return cfg, status
    except CloudSyncError as exc:
        if exc.status == 401:
            clear_session(cfg)
            message = "登录已过期，请重新登录"
        else:
            message = str(exc) or "同步失败"
        cfg["sync_last_error"] = message
        status["message"] = message
        return cfg, status
    except Exception as exc:
        message = str(exc) or "同步失败"
        cfg["sync_last_error"] = message
        status["message"] = message
        return cfg, status
