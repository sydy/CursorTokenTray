"""按次用量明细：Dashboard get-filtered-usage-events 解析、汇总与 CSV。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cursor_api import (
    _as_dict,
    _as_float,
    _as_int,
    _sum_token_fields,
    format_usd_cents,
)

FILTERED_USAGE_ENDPOINT = "/api/dashboard/get-filtered-usage-events"
USAGE_EVENTS_PAGE_SIZE = 100
USAGE_EVENTS_MAX_PAGES = 50

KIND_INCLUDED = "included"
KIND_FREE = "free"
KIND_ON_DEMAND = "on_demand"
KIND_OTHER = "other"

KIND_LABELS = {
    KIND_INCLUDED: "套餐内",
    KIND_FREE: "免费",
    KIND_ON_DEMAND: "按需",
    KIND_OTHER: "其他",
}

CSV_HEADER = "日期(UTC),用户,类型,模型,Token,费用,云端Agent"


@dataclass(frozen=True)
class UsageEvent:
    id: str
    timestamp_ms: int
    model: str
    kind: str
    user_email: str
    owning_user: str
    tokens: int
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    charged_cents: float | None
    total_cents: float | None
    is_headless: bool
    is_chargeable: bool


@dataclass(frozen=True)
class DailyUsageRow:
    date: str
    tokens: int
    cents: float
    count: int


@dataclass(frozen=True)
class ModelUsageRow:
    name: str
    tokens: int
    cents: float
    count: int
    headless_count: int


@dataclass(frozen=True)
class ChartSlice:
    model: str
    tokens: int
    cents: float
    count: int


@dataclass(frozen=True)
class ChartBucket:
    key: str
    label: str
    tokens: int
    cents: float
    count: int
    slices: tuple[ChartSlice, ...]


@dataclass(frozen=True)
class UsageChartSeries:
    hourly: bool
    caption: str
    models: tuple[str, ...]
    buckets: tuple[ChartBucket, ...]


HOURLY_CHART_WINDOW_HOURS = 48
_MS_HOUR = 3_600_000
_MS_DAY = 86_400_000


@dataclass
class UsageReport:
    event_count: int
    total_tokens: int
    total_cents: float
    has_cost: bool
    included_count: int
    free_count: int
    on_demand_count: int
    other_count: int
    headless_count: int
    daily: tuple[DailyUsageRow, ...]
    models: tuple[ModelUsageRow, ...]
    events: tuple[UsageEvent, ...]


@dataclass(frozen=True)
class UsageReportFilter:
    kind: str = ""
    model: str = ""
    headless: bool | None = None
    owning_user: str = ""


def classify_usage_kind(
    kind: str | None,
    usage_based_costs: str | None = None,
    is_chargeable: bool = False,
) -> str:
    blob = f"{kind or ''} {usage_based_costs or ''}".strip().lower()
    if "free" in blob:
        return KIND_FREE
    if "included" in blob:
        return KIND_INCLUDED
    if (
        "usage_based" in blob
        or "usage-based" in blob
        or "ondemand" in blob
        or "on_demand" in blob
        or "on-demand" in blob
    ):
        return KIND_ON_DEMAND
    if is_chargeable:
        return KIND_ON_DEMAND
    return KIND_INCLUDED


def kind_label(kind: str | None) -> str:
    return KIND_LABELS.get((kind or "").strip().lower(), KIND_LABELS[KIND_OTHER])


def event_cost_cents(event: UsageEvent) -> float:
    if event.charged_cents is not None:
        return max(0.0, float(event.charged_cents))
    if event.total_cents is not None:
        return max(0.0, float(event.total_cents))
    return 0.0


def format_event_cost(event: UsageEvent) -> str:
    cents = event_cost_cents(event)
    if event.kind == KIND_FREE:
        return "免费"
    if event.kind == KIND_INCLUDED:
        if cents > 0:
            return f"{format_usd_cents(cents)} 套餐内"
        return "套餐内"
    if cents > 0:
        return format_usd_cents(cents)
    return "—"


def format_event_time(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(max(0, timestamp_ms) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def event_date_utc(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(max(0, timestamp_ms) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def event_hour_utc(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(_floor_hour_ms(timestamp_ms) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:00")


def chart_model_label(name: str) -> str:
    text = (name or "").strip()
    return text[7:] if text.startswith("cursor-") else text


def _floor_hour_ms(timestamp_ms: int) -> int:
    return max(0, timestamp_ms) // _MS_HOUR * _MS_HOUR


def _floor_day_ms(timestamp_ms: int) -> int:
    return max(0, timestamp_ms) // _MS_DAY * _MS_DAY


def _chart_models(events: list[UsageEvent]) -> tuple[str, ...]:
    totals: dict[str, list[int | float]] = {}
    for event in events:
        name = event.model or "—"
        row = totals.setdefault(name, [0, 0.0, 0])
        row[0] = int(row[0]) + event.tokens
        row[1] = float(row[1]) + event_cost_cents(event)
        row[2] = int(row[2]) + 1
    ranked = sorted(
        totals.items(),
        key=lambda kv: (-int(kv[1][0]), -float(kv[1][1]), -int(kv[1][2]), kv[0]),
    )
    return tuple(name for name, _ in ranked)


def _bucket_label(key: str, hourly: bool, multi_day: bool) -> str:
    if not hourly:
        return key[5:] if len(key) >= 10 else key
    hour = key[11:13] if len(key) >= 13 else key
    if multi_day:
        return f"{key[5:10]} {hour}"
    return hour


def _chart_caption(hourly: bool, keys: list[str]) -> str:
    if hourly:
        if not keys:
            return "按小时 Token（UTC）"
        first, last = keys[0], keys[-1]
        if first == last:
            return f"按小时 Token（UTC · {first}）"
        if first[:10] == last[:10]:
            return f"按小时 Token（UTC · {first[:10]} {first[11:]}–{last[11:]}）"
        return f"按小时 Token（UTC · {first} 至 {last}）"
    if not keys:
        return "按日 Token（UTC）"
    first, last = keys[0], keys[-1]
    if first == last:
        return f"按日 Token（UTC · {first}）"
    return f"按日 Token（UTC · {first} 至 {last}）"


def build_usage_chart(
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    hourly: bool = False,
    hidden_models: set[str] | frozenset[str] | None = None,
    hourly_window_hours: int = HOURLY_CHART_WINDOW_HOURS,
) -> UsageChartSeries:
    selected = list(events)
    models = _chart_models(selected)
    hidden = hidden_models or set()
    visible = [name for name in models if name not in hidden]
    if not selected:
        return UsageChartSeries(hourly=hourly, caption=_chart_caption(hourly, []), models=models, buckets=())

    if hourly:
        last_ms = _floor_hour_ms(max(ev.timestamp_ms for ev in selected))
        first_ms = _floor_hour_ms(min(ev.timestamp_ms for ev in selected))
        window = max(1, hourly_window_hours)
        span = (last_ms - first_ms) // _MS_HOUR + 1
        if span > window:
            first_ms = last_ms - (window - 1) * _MS_HOUR
        keys = [
            event_hour_utc(first_ms + i * _MS_HOUR)
            for i in range((last_ms - first_ms) // _MS_HOUR + 1)
        ]
        key_of = event_hour_utc
    else:
        last_ms = _floor_day_ms(max(ev.timestamp_ms for ev in selected))
        first_ms = _floor_day_ms(min(ev.timestamp_ms for ev in selected))
        keys = [
            event_date_utc(first_ms + i * _MS_DAY)
            for i in range((last_ms - first_ms) // _MS_DAY + 1)
        ]
        key_of = event_date_utc

    cells: dict[tuple[str, str], list[int | float]] = {}
    for event in selected:
        key = key_of(event.timestamp_ms)
        if key < keys[0] or key > keys[-1]:
            continue
        name = event.model or "—"
        if name not in visible:
            continue
        cell = cells.setdefault((key, name), [0, 0.0, 0])
        cell[0] = int(cell[0]) + event.tokens
        cell[1] = float(cell[1]) + event_cost_cents(event)
        cell[2] = int(cell[2]) + 1

    multi_day = hourly and keys[0][:10] != keys[-1][:10]
    buckets: list[ChartBucket] = []
    for key in keys:
        slices: list[ChartSlice] = []
        tokens = 0
        cents = 0.0
        count = 0
        for name in visible:
            cell = cells.get((key, name))
            if cell is None:
                continue
            slice_tokens = int(cell[0])
            slice_cents = float(cell[1])
            slice_count = int(cell[2])
            if slice_tokens <= 0 and slice_cents <= 0 and slice_count <= 0:
                continue
            slices.append(
                ChartSlice(model=name, tokens=slice_tokens, cents=slice_cents, count=slice_count)
            )
            tokens += slice_tokens
            cents += slice_cents
            count += slice_count
        buckets.append(
            ChartBucket(
                key=key,
                label=_bucket_label(key, hourly, multi_day),
                tokens=tokens,
                cents=cents,
                count=count,
                slices=tuple(slices),
            )
        )
    return UsageChartSeries(
        hourly=hourly,
        caption=_chart_caption(hourly, keys),
        models=models,
        buckets=tuple(buckets),
    )


def parse_filtered_usage_events(payload: dict[str, Any] | None) -> tuple[tuple[UsageEvent, ...], int]:
    data = payload if isinstance(payload, dict) else {}
    rows = data.get("usageEventsDisplay")
    if not isinstance(rows, list):
        rows = data.get("usageEvents")
    if not isinstance(rows, list):
        rows = []
    events = tuple(event for item in rows if (event := parse_usage_event(item)) is not None)
    total = _as_int(data.get("totalUsageEventsCount"))
    if total is None:
        paging = _as_dict(data.get("pagination"))
        total = _as_int(paging.get("numEvents") or paging.get("totalNumEvents") or paging.get("total"))
    if total is None or total < len(events):
        total = len(events)
    return events, total


def parse_usage_event(item: Any) -> UsageEvent | None:
    if not isinstance(item, dict):
        return None
    ts = _as_int64(item.get("timestamp") or item.get("timestampMs") or item.get("createdAt"))
    if ts is None or ts <= 0:
        return None
    token_usage = _as_dict(item.get("tokenUsage"))
    model = _display_model(str(item.get("model") or item.get("modelIntent") or ""))
    kind_raw = str(item.get("kind") or item.get("type") or "")
    costs_raw = str(item.get("usageBasedCosts") or item.get("cost") or "")
    is_chargeable = bool(item.get("isChargeable"))
    kind = classify_usage_kind(kind_raw, costs_raw, is_chargeable)
    input_tokens = max(0, _as_int(token_usage.get("inputTokens") or item.get("inputTokens")) or 0)
    output_tokens = max(0, _as_int(token_usage.get("outputTokens") or item.get("outputTokens")) or 0)
    cache_write = max(0, _as_int(token_usage.get("cacheWriteTokens") or item.get("cacheWriteTokens")) or 0)
    cache_read = max(0, _as_int(token_usage.get("cacheReadTokens") or item.get("cacheReadTokens")) or 0)
    tokens = _sum_token_fields(token_usage) if token_usage else 0
    if tokens <= 0:
        tokens = _sum_token_fields(item)
    if tokens <= 0:
        tokens = input_tokens + output_tokens + cache_write + cache_read
    charged = _as_float(item.get("chargedCents"))
    if charged is None:
        charged = parse_money_cents(item.get("usageBasedCosts"))
    total_cents = _as_float(token_usage.get("totalCents") or item.get("totalCents"))
    email = str(
        item.get("email")
        or item.get("userEmail")
        or item.get("user")
        or _as_dict(item.get("user")).get("email")
        or ""
    ).strip()
    owning = str(item.get("owningUser") or item.get("userId") or "").strip()
    given_id = str(item.get("id") or item.get("eventId") or "").strip()
    event_id = given_id or "|".join(
        [
            str(ts),
            owning,
            model,
            str(input_tokens),
            str(output_tokens),
            str(cache_write),
            str(cache_read),
            kind_raw,
        ]
    )
    return UsageEvent(
        id=event_id,
        timestamp_ms=ts,
        model=model,
        kind=kind,
        user_email=email,
        owning_user=owning,
        tokens=max(0, tokens),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_write_tokens=cache_write,
        cache_read_tokens=cache_read,
        charged_cents=charged,
        total_cents=total_cents,
        is_headless=bool(item.get("isHeadless") or item.get("isCloudAgent")),
        is_chargeable=is_chargeable,
    )


def parse_money_cents(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    lower = text.lower()
    if lower in {"included", "free", "n/a", "—", "-", "none"}:
        return None
    if "us$" in lower or "$" in text:
        cleaned = (
            text.replace("US$", "")
            .replace("us$", "")
            .replace("$", "")
            .replace(",", "")
            .replace("Included", "")
            .replace("included", "")
            .replace("Free", "")
            .replace("free", "")
            .strip()
        )
        n = _as_float(cleaned)
        if n is None:
            return None
        return n * 100.0
    return None


def build_usage_report(
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    filt: UsageReportFilter | None = None,
) -> UsageReport:
    filt = filt or UsageReportFilter()
    kind = (filt.kind or "").strip().lower()
    model = (filt.model or "").strip()
    owning = (filt.owning_user or "").strip()
    selected: list[UsageEvent] = []
    for event in events:
        if kind and event.kind != kind:
            continue
        if model and event.model != model:
            continue
        if filt.headless is not None and event.is_headless != filt.headless:
            continue
        if owning and event.owning_user != owning:
            continue
        selected.append(event)
    selected.sort(key=lambda e: e.timestamp_ms, reverse=True)

    daily_map: dict[str, list[int | float]] = {}
    model_map: dict[str, list[int | float]] = {}
    included = free = on_demand = other = headless = 0
    total_tokens = 0
    total_cents = 0.0
    has_cost = False
    for event in selected:
        cents = event_cost_cents(event)
        total_tokens += event.tokens
        total_cents += cents
        if cents > 0:
            has_cost = True
        if event.kind == KIND_INCLUDED:
            included += 1
        elif event.kind == KIND_FREE:
            free += 1
        elif event.kind == KIND_ON_DEMAND:
            on_demand += 1
        else:
            other += 1
        if event.is_headless:
            headless += 1
        day = event_date_utc(event.timestamp_ms)
        bucket = daily_map.setdefault(day, [0, 0.0, 0])
        bucket[0] = int(bucket[0]) + event.tokens
        bucket[1] = float(bucket[1]) + cents
        bucket[2] = int(bucket[2]) + 1
        row = model_map.setdefault(event.model or "—", [0, 0.0, 0, 0])
        row[0] = int(row[0]) + event.tokens
        row[1] = float(row[1]) + cents
        row[2] = int(row[2]) + 1
        if event.is_headless:
            row[3] = int(row[3]) + 1

    daily = tuple(
        DailyUsageRow(date=day, tokens=int(vals[0]), cents=float(vals[1]), count=int(vals[2]))
        for day, vals in sorted(daily_map.items())
    )
    models = tuple(
        sorted(
            (
                ModelUsageRow(
                    name=name,
                    tokens=int(vals[0]),
                    cents=float(vals[1]),
                    count=int(vals[2]),
                    headless_count=int(vals[3]),
                )
                for name, vals in model_map.items()
            ),
            key=lambda m: (m.tokens, m.cents, m.count),
            reverse=True,
        )
    )
    return UsageReport(
        event_count=len(selected),
        total_tokens=total_tokens,
        total_cents=total_cents,
        has_cost=has_cost,
        included_count=included,
        free_count=free,
        on_demand_count=on_demand,
        other_count=other,
        headless_count=headless,
        daily=daily,
        models=models,
        events=tuple(selected),
    )


def usage_events_to_csv(events: list[UsageEvent] | tuple[UsageEvent, ...]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["日期(UTC)", "用户", "类型", "模型", "Token", "费用", "云端Agent"])
    for event in events:
        writer.writerow(
            [
                format_event_time(event.timestamp_ms),
                event.user_email,
                kind_label(event.kind),
                event.model,
                str(event.tokens),
                format_event_cost(event),
                "是" if event.is_headless else "否",
            ]
        )
    return "\ufeff" + buf.getvalue()


def usage_event_from_dict(raw: dict[str, Any]) -> UsageEvent | None:
    try:
        ts = _as_int64(raw.get("timestamp_ms"))
        if ts is None:
            return None
        return UsageEvent(
            id=str(raw.get("id") or ""),
            timestamp_ms=ts,
            model=str(raw.get("model") or ""),
            kind=str(raw.get("kind") or KIND_OTHER),
            user_email=str(raw.get("user_email") or ""),
            owning_user=str(raw.get("owning_user") or ""),
            tokens=max(0, _as_int(raw.get("tokens")) or 0),
            input_tokens=max(0, _as_int(raw.get("input_tokens")) or 0),
            output_tokens=max(0, _as_int(raw.get("output_tokens")) or 0),
            cache_write_tokens=max(0, _as_int(raw.get("cache_write_tokens")) or 0),
            cache_read_tokens=max(0, _as_int(raw.get("cache_read_tokens")) or 0),
            charged_cents=_as_float(raw.get("charged_cents")),
            total_cents=_as_float(raw.get("total_cents")),
            is_headless=bool(raw.get("is_headless")),
            is_chargeable=bool(raw.get("is_chargeable")),
        )
    except (TypeError, ValueError):
        return None


def merge_usage_events(
    existing: list[UsageEvent] | tuple[UsageEvent, ...],
    incoming: list[UsageEvent] | tuple[UsageEvent, ...],
) -> list[UsageEvent]:
    by_id: dict[str, UsageEvent] = {}
    for event in existing:
        if event.id:
            by_id[event.id] = event
    for event in incoming:
        if event.id:
            by_id[event.id] = event
    return sorted(by_id.values(), key=lambda e: e.timestamp_ms, reverse=True)


def prune_usage_events(events: list[UsageEvent], min_timestamp_ms: int) -> list[UsageEvent]:
    return [e for e in events if e.timestamp_ms >= min_timestamp_ms]


def user_id_from_payload(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return -1
    for key in ("userId", "numericUserId", "currentUserId"):
        n = _as_int(payload.get(key))
        if n is not None and n > 0:
            return n
    individual = _as_dict(payload.get("individualUsage"))
    n = _as_int(individual.get("userId") or individual.get("id"))
    if n is not None and n > 0:
        return n
    return -1


def _display_model(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    return "auto" if name == "default" else name


def _as_int64(value: Any) -> int | None:
    num = _as_float(value)
    if num is None:
        return None
    return int(round(num))
