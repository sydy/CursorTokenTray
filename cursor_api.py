"""Cursor 用量接口客户端（非官方，可能变更）。"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CURSOR_BASE = "https://cursor.com"
USAGE_ENDPOINTS = ("/api/usage-summary", "/api/dashboard/usage-summary")
AGGREGATED_USAGE_ENDPOINT = "/api/dashboard/get-aggregated-usage-events"
SPENDING_URL = "https://cursor.com/dashboard/spending"
BILLING_URL = "https://cursor.com/dashboard/billing"

# Dashboard Included Usage：tier 2 = Cursor 模型，其余为其他模型
CURSOR_MODEL_TIER = 2
_MODEL_NAME_ALIASES = {"default": "auto"}

# HTTP 头必须是 latin-1；复制时常见脏字符
_TOKEN_JUNK = (
    "\u2026",  # …
    "\u2022",  # •
    "\ufeff",  # BOM
    "\u200b",  # zero-width space
    "\u200c",
    "\u200d",
    "\xa0",  # nbsp
)


@dataclass(frozen=True)
class ModelTokenUsage:
    name: str
    tokens: int
    cents: float
    tier: int
    usage_percent: float | None = None

    @property
    def is_cursor_model(self) -> bool:
        return self.tier == CURSOR_MODEL_TIER


@dataclass
class UsageSnapshot:
    used_percent: float
    remaining_percent: float
    auto_percent_used: float | None
    api_percent_used: float | None
    total_percent_used: float | None
    membership_type: str
    billing_cycle_start: str | None
    billing_cycle_end: str | None
    days_remaining: int | None
    days_elapsed: float | None
    estimated_usable_days: float | None
    raw: dict[str, Any]
    total_tokens: int | None = None
    model_usages: tuple[ModelTokenUsage, ...] = ()


AUTH_ERROR_MESSAGE = "Token 已过期或无效，请重新粘贴 WorkosCursorSessionToken"


def is_auth_error_message(message: str | None) -> bool:
    if not message:
        return False
    text = message.lower()
    keys = (
        "token 已过期",
        "token 无效",
        "未配置 token",
        "未配置 session",
        "workoscursorsessiontoken",
        "unauthorized",
        "forbidden",
    )
    if any(key in text for key in keys):
        return True
    return ("过期" in message or "无效" in message) and ("token" in text or "Token" in message)


class CursorApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_auth_error(self) -> bool:
        if self.status_code in (401, 403):
            return True
        return is_auth_error_message(str(self))


def normalize_workos_token(token: str) -> str:
    value = (token or "").strip().strip('"').strip("'")
    if not value:
        return ""

    for ch in _TOKEN_JUNK:
        value = value.replace(ch, "")

    # 允许粘贴整段 Cookie：WorkosCursorSessionToken=xxx; 其他=...
    match = re.search(
        r"(?:^|[;\s])WorkosCursorSessionToken=([^;\s]+)",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        value = match.group(1).strip()
    elif value.lower().startswith("workoscursorsessiontoken="):
        value = value.split("=", 1)[1].strip()

    value = "".join(value.split())  # 去掉换行/空格

    if "%3A%3A" in value or "%3a%3a" in value:
        pass
    elif "::" in value:
        value = value.replace("::", "%3A%3A", 1)
    elif _looks_like_jwt(value):
        user_id = _extract_user_id_from_jwt(value)
        if user_id:
            value = f"{user_id}%3A%3A{value}"

    # urllib 请求头只接受 latin-1
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as err:
        bad = value[err.start : err.end]
        if "\ufffd" in value or any(ord(ch) > 255 for ch in bad):
            raise CursorApiError(
                "读到的 Token 已损坏（常见于 Chrome Cookie 解密失败，不是复制漏了）。"
                "请再点一次「导入」，钥匙串弹窗选「始终允许」；"
                "或改用 Safari / Firefox，或在开发者工具里完整复制 WorkosCursorSessionToken。",
                status_code=401,
            ) from err
        raise CursorApiError(
            "Token 含非法字符（可能复制不完整，出现了省略号等）。"
            "请在浏览器 Cookies 里双击完整复制 WorkosCursorSessionToken 的值后重试。"
            f"（非法片段: {bad!r}）",
            status_code=401,
        ) from err

    return value


def session_token_variants(token: str) -> list[str]:
    """Dashboard 对 Cookie 形态不统一，把常见写法都试一遍。"""
    variants: list[str] = []

    def add(value: str | None) -> None:
        text = (value or "").strip()
        if text and text not in variants:
            variants.append(text)

    raw = (token or "").strip()
    try:
        add(normalize_workos_token(raw))
    except CursorApiError:
        pass
    add(raw)
    jwt = raw
    if "%3A%3A" in raw:
        jwt = raw.split("%3A%3A", 1)[-1]
        add(raw.replace("%3A%3A", "::", 1))
    elif "%3a%3a" in raw:
        jwt = raw.split("%3a%3a", 1)[-1]
        add(raw.replace("%3a%3a", "::", 1))
    elif "::" in raw:
        jwt = raw.split("::", 1)[-1]
        add(raw.replace("::", "%3A%3A", 1))
    if _looks_like_jwt(jwt):
        add(jwt)
        payload = _jwt_payload(jwt)
        sub = str((payload or {}).get("sub") or "")
        if sub:
            user_id = sub.split("|")[-1]
            add(f"{user_id}%3A%3A{jwt}")
            add(f"{user_id}::{jwt}")
            if sub != user_id:
                add(f"{sub}%3A%3A{jwt}")
                add(f"{sub}::{jwt}")
    return variants[:4]


def account_id_from_token(token: str) -> str:
    """从 WorkOS Token 提取稳定账号 ID（JWT user_id，否则哈希）。"""
    try:
        value = normalize_workos_token(token)
    except CursorApiError:
        value = (token or "").strip()
    if not value:
        return ""

    jwt = value
    prefix = ""
    for sep in ("%3A%3A", "%3a%3a", "::"):
        if sep in value:
            prefix, jwt = value.split(sep, 1)
            break
    if _looks_like_jwt(jwt):
        uid = _extract_user_id_from_jwt(jwt)
        if uid:
            return _safe_account_id(uid)
    if prefix.strip():
        return _safe_account_id(prefix.split("|")[-1])
    if _looks_like_jwt(value):
        uid = _extract_user_id_from_jwt(value)
        if uid:
            return _safe_account_id(uid)
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"tok_{digest}"


def _safe_account_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")
    return (cleaned or "account")[:80]


def fetch_usage_summary(session_token: str, timeout: float = 30.0) -> UsageSnapshot:
    token = normalize_workos_token(session_token)
    if not token:
        raise CursorApiError("未配置 Session Token", status_code=401)

    last_error: Exception | None = None
    snapshot: UsageSnapshot | None = None
    for endpoint in USAGE_ENDPOINTS:
        try:
            payload = _request_json("GET", endpoint, token, timeout=timeout)
            snapshot = parse_usage_summary(payload)
            break
        except CursorApiError as err:
            last_error = err
            if err.status_code not in (404, 405):
                raise
    if snapshot is None:
        assert last_error is not None
        raise last_error

    try:
        attach_aggregated_tokens(snapshot, token, timeout=timeout)
    except Exception:
        # 明细失败不影响套餐剩余；飞出层仍显示百分比
        pass
    return snapshot


def attach_aggregated_tokens(
    snapshot: UsageSnapshot,
    token: str,
    timeout: float = 30.0,
) -> None:
    start_ms = _iso_to_ms(snapshot.billing_cycle_start)
    if start_ms is None:
        return
    end_ms = _iso_to_ms(snapshot.billing_cycle_end)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if end_ms is None or end_ms > now_ms:
        end_ms = now_ms
    if end_ms < start_ms:
        end_ms = start_ms

    payload = _request_json(
        "POST",
        AGGREGATED_USAGE_ENDPOINT,
        token,
        body={"teamId": -1, "startDate": start_ms, "endDate": end_ms},
        timeout=timeout,
    )
    models, total = parse_aggregated_usage(
        payload,
        auto_percent=snapshot.auto_percent_used,
        api_percent=snapshot.api_percent_used,
    )
    snapshot.model_usages = models
    snapshot.total_tokens = total


def parse_aggregated_usage(
    payload: dict[str, Any],
    *,
    auto_percent: float | None = None,
    api_percent: float | None = None,
) -> tuple[tuple[ModelTokenUsage, ...], int]:
    rows: list[ModelTokenUsage] = []
    for item in payload.get("aggregations") or []:
        if not isinstance(item, dict):
            continue
        name = _display_model_name(str(item.get("modelIntent") or item.get("model") or ""))
        if not name:
            continue
        tokens = _sum_token_fields(item)
        if tokens <= 0:
            continue
        cents = _as_float(item.get("totalCents")) or 0.0
        tier = _model_tier(name, item.get("tier"))
        rows.append(ModelTokenUsage(name=name, tokens=tokens, cents=cents, tier=tier))

    if not rows:
        total = _sum_token_fields(payload)
        return (), total if total > 0 else 0

    cursor_rows = [m for m in rows if m.is_cursor_model]
    other_rows = [m for m in rows if not m.is_cursor_model]
    cursor_rows = _allocate_usage_percents(cursor_rows, auto_percent)
    other_rows = _allocate_usage_percents(other_rows, api_percent)
    cursor_rows.sort(key=lambda m: (m.usage_percent or 0.0, m.tokens), reverse=True)
    other_rows.sort(key=lambda m: (m.usage_percent or 0.0, m.tokens), reverse=True)
    allocated = (*cursor_rows, *other_rows)
    total = sum(m.tokens for m in allocated)
    header_total = _sum_token_fields(payload)
    if header_total > total:
        total = header_total
    return tuple(allocated), total


def format_token_count(count: int | float | None) -> str:
    """与 Dashboard Included Usage 一致：万 / 亿，保留 1 位小数。"""
    if count is None:
        return "—"
    try:
        n = int(round(float(count)))
    except (TypeError, ValueError):
        return "—"
    n = max(0, n)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def parse_usage_summary(payload: dict[str, Any]) -> UsageSnapshot:
    individual = payload.get("individualUsage") or {}
    plan = individual.get("plan") or {}

    auto = _as_float(plan.get("autoPercentUsed"))
    api = _as_float(plan.get("apiPercentUsed"))
    total = _as_float(plan.get("totalPercentUsed"))

    used_percent = total
    if used_percent is None:
        used_percent = auto
    if used_percent is None:
        used = _as_float(plan.get("used"))
        limit = _as_float(plan.get("limit"))
        if used is not None and limit and limit > 0:
            used_percent = min(100.0, max(0.0, used / limit * 100.0))
    if used_percent is None:
        used_percent = 0.0

    used_percent = min(100.0, max(0.0, float(used_percent)))
    remaining_percent = min(100.0, max(0.0, 100.0 - used_percent))

    cycle_start = payload.get("billingCycleStart") or payload.get("startOfMonth")
    cycle_end = payload.get("billingCycleEnd")
    days_remaining = _days_until(cycle_end)
    days_elapsed = _days_since(cycle_start)
    estimated = _estimate_usable_days(used_percent, remaining_percent, days_elapsed)

    membership = str(payload.get("membershipType") or payload.get("plan") or "未知")

    return UsageSnapshot(
        used_percent=round(used_percent, 1),
        remaining_percent=round(remaining_percent, 1),
        auto_percent_used=None if auto is None else round(auto, 1),
        api_percent_used=None if api is None else round(api, 1),
        total_percent_used=None if total is None else round(total, 1),
        membership_type=membership,
        billing_cycle_start=_iso_or_none(cycle_start),
        billing_cycle_end=_iso_or_none(cycle_end),
        days_remaining=days_remaining,
        days_elapsed=None if days_elapsed is None else round(days_elapsed, 2),
        estimated_usable_days=estimated,
        raw=payload,
    )


def _ssl_context() -> ssl.SSLContext:
    """打包进 .app 后系统 CA 经常找不到，必须自带 certifi。"""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _request_json(
    method: str,
    endpoint: str,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = f"{CURSOR_BASE}{endpoint}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": f"WorkosCursorSessionToken={token}",
        "Origin": "https://cursor.com",
        "Referer": "https://cursor.com/dashboard",
        "User-Agent": "Mozilla/5.0 CursorTokenTray/1.0",
    }
    data = None if body is None else json.dumps(body).encode("utf-8")
    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            if not text:
                return {}
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise CursorApiError("接口返回格式异常")
            return payload
    except UnicodeEncodeError as err:
        raise CursorApiError(
            "请求头编码失败：Token 可能含非 ASCII 字符，请重新完整复制 Cookie 值。"
        ) from err
    except HTTPError as err:
        detail = ""
        try:
            detail = err.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        msg = f"HTTP {err.code}"
        if err.code in (401, 403):
            msg = AUTH_ERROR_MESSAGE
        elif detail:
            # 避免把超长 HTML/奇怪字符塞进托盘提示
            safe = detail.encode("ascii", "replace").decode("ascii")
            msg = f"HTTP {err.code}: {safe}"
        raise CursorApiError(msg, status_code=err.code) from err
    except URLError as err:
        raise CursorApiError(f"网络错误: {err.reason}") from err
    except json.JSONDecodeError as err:
        raise CursorApiError("接口返回非 JSON") from err


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    num = _as_float(value)
    if num is None:
        return None
    return int(round(num))


def _iso_to_ms(iso_value: Any) -> int | None:
    dt = _parse_iso(iso_value)
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def _sum_token_fields(item: dict[str, Any]) -> int:
    keys = (
        "inputTokens",
        "outputTokens",
        "cacheWriteTokens",
        "cacheReadTokens",
        "totalInputTokens",
        "totalOutputTokens",
        "totalCacheWriteTokens",
        "totalCacheReadTokens",
    )
    total = 0
    found = False
    for key in keys:
        n = _as_int(item.get(key))
        if n is None:
            continue
        found = True
        total += max(0, n)
    if found:
        return total
    n = _as_int(item.get("totalTokens"))
    return max(0, n) if n is not None else 0


def _display_model_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    return _MODEL_NAME_ALIASES.get(name, name)


def _model_tier(name: str, tier: Any) -> int:
    t = _as_int(tier)
    if t is not None:
        return t
    key = name.lower()
    if key in {"auto", "default"} or key.startswith("cursor-") or key.startswith("composer-"):
        return CURSOR_MODEL_TIER
    return 1


def _allocate_usage_percents(
    models: list[ModelTokenUsage],
    category_percent: float | None,
) -> list[ModelTokenUsage]:
    if not models:
        return []
    cents_sum = sum(m.cents for m in models)
    tokens_sum = sum(m.tokens for m in models)
    cat = 0.0 if category_percent is None else float(category_percent)
    out: list[ModelTokenUsage] = []
    for model in models:
        share = 0.0
        if cents_sum > 1e-6:
            share = model.cents / cents_sum
        elif tokens_sum > 0:
            share = model.tokens / tokens_sum
        pct = None if category_percent is None else round(share * cat, 1)
        out.append(
            ModelTokenUsage(
                name=model.name,
                tokens=model.tokens,
                cents=model.cents,
                tier=model.tier,
                usage_percent=pct,
            )
        )
    return out


def _iso_or_none(value: Any) -> str | None:
    if not value:
        return None
    return str(value)


def _parse_iso(iso_value: Any) -> datetime | None:
    if not iso_value:
        return None
    try:
        text = str(iso_value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _days_until(iso_value: Any) -> int | None:
    end = _parse_iso(iso_value)
    if end is None:
        return None
    delta = end - datetime.now(timezone.utc)
    return max(0, delta.days)


def _days_since(iso_value: Any) -> float | None:
    start = _parse_iso(iso_value)
    if start is None:
        return None
    delta = datetime.now(timezone.utc) - start
    hours = delta.total_seconds() / 3600.0
    if hours < 0:
        return 0.0
    return hours / 24.0


def _estimate_usable_days(
    used_percent: float,
    remaining_percent: float,
    days_elapsed: float | None,
) -> float | None:
    """按当前周期平均消耗速度估算剩余额度还能用多久。"""
    if days_elapsed is None:
        return None
    if remaining_percent <= 0:
        return 0.0
    # 周期刚开始或几乎未消耗时无法可靠估算
    if days_elapsed < 0.04:  # 约 1 小时内
        return None
    if used_percent < 0.2:
        return None
    burn_per_day = used_percent / days_elapsed
    if burn_per_day <= 1e-6:
        return None
    return round(remaining_percent / burn_per_day, 1)


def _looks_like_jwt(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(parts)


def _jwt_payload(jwt: str) -> dict[str, Any] | None:
    try:
        payload_part = jwt.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        padded = padded.replace("-", "+").replace("_", "/")
        payload = json.loads(base64.b64decode(padded).decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _extract_user_id_from_jwt(jwt: str) -> str:
    payload = _jwt_payload(jwt)
    if not payload:
        return ""
    sub = str(payload.get("sub") or "")
    return sub.split("|")[-1] if sub else ""
