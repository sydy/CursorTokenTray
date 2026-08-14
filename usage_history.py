"""用量历史：JSONL 本地落盘，供飞出层折线与日均消耗。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from config import CONFIG_DIR, ensure_config_dir

HISTORY_PATH = CONFIG_DIR / "usage_history.jsonl"
KEEP_DAYS = 90


@dataclass
class HistoryPoint:
    ts: float
    remaining: float
    auto: float | None
    api: float | None


def append(
    *,
    remaining: float,
    auto: float | None = None,
    api: float | None = None,
    ts: float | None = None,
) -> None:
    ensure_config_dir()
    point = {
        "ts": float(ts if ts is not None else datetime.now(timezone.utc).timestamp()),
        "remaining": round(float(remaining), 2),
        "auto": None if auto is None else round(float(auto), 2),
        "api": None if api is None else round(float(api), 2),
    }
    try:
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(point, ensure_ascii=False) + "\n")
    except OSError:
        return
    # 剪枝节流：最多每 6 小时全量整理一次
    now = time.monotonic()
    last = float(getattr(append, "_last_prune", 0.0) or 0.0)
    if now - last >= 6 * 3600:
        append._last_prune = now  # type: ignore[attr-defined]
        _prune_file()


def load_recent(days: int = 7) -> list[HistoryPoint]:
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, days) * 86400
    points: list[HistoryPoint] = []
    for raw in _iter_raw():
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


def daily_avg_burn(days: int = 7) -> float | None:
    """近 N 日剩余百分比平均日消耗（正数表示每天大约少多少 %）。"""
    points = load_recent(days)
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


def _iter_raw() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as f:
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


def _prune_file() -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).timestamp()
    kept = [r for r in _iter_raw() if float(r.get("ts", 0) or 0) >= cutoff]
    try:
        with HISTORY_PATH.open("w", encoding="utf-8") as f:
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
