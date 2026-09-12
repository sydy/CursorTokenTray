"""CursorTokenTray 云同步 API。客户端只上传口令加密信封，服务器不解密。"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import settings
from .auth import (
    LIMITER,
    bearer_user,
    client_ip,
    create_user,
    get_user_by_email,
    issue_refresh,
    now_iso,
    revoke_refresh,
    rotate_refresh,
    token_payload,
    validate_email,
    validate_password,
    verify_password,
)
from .db import get_conn, lock

SUPPORTED_FORMATS = {"cursortokentray.accounts.v1", "cursortokentray.sync.v2"}

app = FastAPI(title="CursorTokenTray Sync", version="1.0.0", docs_url=None, redoc_url=None)


class AuthBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=settings.PASSWORD_MAX)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=512)


class LogoutBody(BaseModel):
    refresh_token: str = Field(default="", max_length=512)


class SyncPutBody(BaseModel):
    revision: int = Field(ge=0)
    envelope: dict


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/auth/register")
def register(body: AuthBody, request: Request):
    LIMITER.check(f"auth:{client_ip(request)}", settings.AUTH_RATE_PER_MIN)
    email = validate_email(body.email)
    password = validate_password(body.password)
    user = create_user(email, password)
    return token_payload(user, issue_refresh(user["id"]))


@app.post("/v1/auth/login")
def login(body: AuthBody, request: Request):
    LIMITER.check(f"auth:{client_ip(request)}", settings.AUTH_RATE_PER_MIN)
    email = validate_email(body.email)
    password = validate_password(body.password)
    user = get_user_by_email(email)
    if user is None or not verify_password(user["password_hash"], password):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    return token_payload(user, issue_refresh(user["id"]))


@app.post("/v1/auth/refresh")
def refresh(body: RefreshBody, request: Request):
    LIMITER.check(f"auth:{client_ip(request)}", settings.AUTH_RATE_PER_MIN)
    access, raw = rotate_refresh(body.refresh_token.strip())
    payload = {"access_token": access, "refresh_token": raw, "expires_in": settings.ACCESS_MINUTES * 60}
    return payload


@app.post("/v1/auth/logout")
def logout(body: LogoutBody, request: Request):
    raw = (body.refresh_token or "").strip()
    if raw:
        revoke_refresh(raw)
    return {"ok": True}


@app.get("/v1/me")
def me(request: Request):
    user = bearer_user(request)
    return {"id": user["id"], "email": user["email"]}


@app.get("/v1/sync")
def get_sync(request: Request):
    user = bearer_user(request)
    LIMITER.check(f"sync:{user['id']}", settings.SYNC_RATE_PER_MIN)
    with lock():
        row = get_conn().execute(
            "SELECT revision, envelope, updated_at FROM sync_blobs WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
    if row is None:
        return {"revision": 0, "updated_at": "", "envelope": None}
    try:
        envelope = json.loads(row["envelope"])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="云端同步数据损坏") from exc
    return {"revision": int(row["revision"]), "updated_at": row["updated_at"], "envelope": envelope}


@app.put("/v1/sync")
def put_sync(body: SyncPutBody, request: Request):
    user = bearer_user(request)
    LIMITER.check(f"sync:{user['id']}", settings.SYNC_RATE_PER_MIN)
    envelope = validate_envelope(body.envelope)
    stamp = now_iso()
    with lock():
        conn = get_conn()
        row = conn.execute(
            "SELECT revision FROM sync_blobs WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        current = int(row["revision"]) if row else 0
        if body.revision != current:
            raise HTTPException(status_code=409, detail="同步冲突，请重试")
        next_rev = current + 1
        payload = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        if row is None:
            conn.execute(
                "INSERT INTO sync_blobs (user_id, revision, envelope, updated_at) VALUES (?, ?, ?, ?)",
                (user["id"], next_rev, payload, stamp),
            )
        else:
            conn.execute(
                "UPDATE sync_blobs SET revision = ?, envelope = ?, updated_at = ? WHERE user_id = ?",
                (next_rev, payload, stamp, user["id"]),
            )
        conn.commit()
    return {"revision": next_rev, "updated_at": stamp}


def validate_envelope(envelope: dict) -> dict:
    fmt = str(envelope.get("format") or "")
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="不是 CursorTokenTray 账号同步文件")
    if str(envelope.get("kdf") or "") != "pbkdf2-sha256":
        raise HTTPException(status_code=400, detail="不支持的同步文件密钥算法")
    for key in ("salt", "nonce", "ciphertext"):
        if not str(envelope.get(key) or "").strip():
            raise HTTPException(status_code=400, detail="同步文件损坏")
    try:
        iterations = int(envelope.get("iterations") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="同步文件损坏") from exc
    if iterations < 1000:
        raise HTTPException(status_code=400, detail="KDF 迭代次数过低")
    return {
        "format": fmt,
        "kdf": "pbkdf2-sha256",
        "iterations": iterations,
        "salt": str(envelope["salt"]),
        "nonce": str(envelope["nonce"]),
        "ciphertext": str(envelope["ciphertext"]),
    }
