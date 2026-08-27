"""用量历史：JSONL 本地落盘，供飞出层折线与日均消耗。按账号分文件。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import ensure_config_dir
from cursor_api import _safe_account_id

KEEP_DAYS = 90


@dataclass
class HistoryPoint:
    ts: float
    remaining: float
    auto: float | None
    api: float | None


def _config_dir() -> Path:
    from config import CONFIG_DIR

    return CONFIG_DIR


def history_path(account_id: str | None = None) -> Path:
    aid = str(account_id or "").strip()
    root = _config_dir()
    if not aid:
        return root / "usage_history.jsonl"
    return root / f"usage_history.{_safe_account_id(aid)}.jsonl"


def adopt_legacy_history(account_id: str) -> None:
    """把旧的全局 usage_history.jsonl 归到第一个迁移出来的账号。"""
    dest = history_path(account_id)
    legacy = _config_dir() / "usage_history.jsonl"
    if not account_id or dest.exists() or not legacy.exists():
        return
    others = [p for p in _config_dir().glob("usage_history.*.jsonl") if p.resolve() != dest.resolve()]
    if others:
        return
    try:
        legacy.replace(dest)
    except OSError:
        try:
            dest.write_bytes(legacy.read_bytes())
        except OSError:
            return


def append(
    *,
    remaining: float,
    auto: float | None = None,
    api: float | None = None,
    ts: float | None = None,
    account_id: str | None = None,
) -> None:
    ensure_config_dir()
    aid = str(account_id or "").strip() or _active_account_id()
    if aid:
        adopt_legacy_history(aid)
    path = history_path(aid or None)
    point = {
        "ts": float(ts if ts is not None else datetime.now(timezone.utc).timestamp()),
        "remaining": round(float(remaining), 2),
        "auto": None if auto is None else round(float(auto), 2),
        "api": None if api is None else round(float(api), 2),
        "account_id": aid,
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(point, ensure_ascii=False) + "\n")
    except OSError:
        return
    now = time.monotonic()
    last = float(getattr(append, "_last_prune", 0.0) or 0.0)
    if now - last >= 6 * 3600:
        append._last_prune = now  # type: ignore[attr-defined]
        _prune_file(path)


def load_recent(days: int = 7, *, account_id: str | None = None) -> list[HistoryPoint]:
    aid = str(account_id or "").strip() or _active_account_id()
    if aid:
        adopt_legacy_history(aid)
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, days) * 86400
    points: list[HistoryPoint] = []
    for raw in _iter_raw(history_path(aid)):
        try:
            ts = float(raw.get("ts", 0))
            if ts < cutoff:
                continue
            points.append(
                HistoryPoint(
                    ts=ts,
                    remaining=float(raw.get("remaining", 0)),
                    auto=_opt_float(raw.get("auto")),
                    api=_opt_float(raw.get("api")),
                )
            )
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda p: p.ts)
    return points


def daily_avg_burn(days: int = 7, *, account_id: str | None = None) -> float | None:
    """近 N 日剩余百分比平均日消耗（正数表示每天大约少多少 %）。"""
    points = load_recent(days, account_id=account_id)
    if len(points) < 2:
        return None
    first, last = points[0], points[-1]
    elapsed_days = (last.ts - first.ts) / 86400.0
    if elapsed_days < 0.04:
        return None
    delta = first.remaining - last.remaining
    if delta <= 0:
        return 0.0
    return round(delta / elapsed_days, 2)


def _active_account_id() -> str:
    try:
        from accounts import active_account
        from config import load_config

        acc = active_account(load_config())
        return str(acc.get("id") or "") if acc else ""
    except Exception:
        return ""


def _iter_raw(path: Path | None = None) -> list[dict[str, Any]]:
    target = history_path(None) if path is None else path
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    rows.append(data)
    except OSError:
        return []
    return rows


def _prune_file(path: Path | None = None) -> None:
    target = history_path(None) if path is None else path
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).timestamp()
    kept = [r for r in _iter_raw(target) if float(r.get("ts", 0) or 0) >= cutoff]
    try:
        with target.open("w", encoding="utf-8") as f:
            for row in kept:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
