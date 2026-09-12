"""按次用量明细：Dashboard get-filtered-usage-events 解析、汇总与 CSV。"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cursor_api import (
    _as_dict,
    _as_float,
    _as_int,
    _iso_to_ms,
    _parse_iso,
    _sum_token_fields,
    format_usd_cents,
    is_first_party_model,
    is_grok_bot_model,
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

CATEGORY_FIRST_PARTY = "first_party"
CATEGORY_API = "api"
CATEGORY_GROK_BOT = "grok_bot"

CATEGORY_LABELS = {
    CATEGORY_FIRST_PARTY: "First-party",
    CATEGORY_API: "API",
    CATEGORY_GROK_BOT: "Grok Bot",
}

CHANNEL_SELF_PAY = "self_pay"
CHANNEL_THIRD_PARTY = "third_party"
CHANNEL_LABELS = {
    CHANNEL_SELF_PAY: "自费",
    CHANNEL_THIRD_PARTY: "第三方",
    "": "未标",
}
CHANNEL_ORDER = (CHANNEL_SELF_PAY, CHANNEL_THIRD_PARTY, "")
HOLDING_DAYS = 30.0
WINDOW_CYCLE = "cycle"
WINDOW_VALIDITY = "validity"
WINDOW_FALLBACK = "fallback"
WINDOW_LABELS = {
    WINDOW_CYCLE: "本周期",
    WINDOW_VALIDITY: "有效期",
    WINDOW_FALLBACK: "近30天",
}

DISPLAY_TZ = timezone(timedelta(hours=8))
TZ_LABEL = "北京时间"
CSV_HEADER = f"日期({TZ_LABEL}),用户,类型,模型,Token,费用,实付,云端Agent"
DEFAULT_USD_CNY_RATE = 7.50
_PLAN_USD = {
    "pro": 20.0,
    "pro_plus": 60.0,
    "pro+": 60.0,
    "ultra": 200.0,
}


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
    allocated_cny: float = 0.0


@dataclass(frozen=True)
class DailyUsageRow:
    date: str
    tokens: int
    cents: float
    count: int
    cny: float = 0.0


@dataclass(frozen=True)
class ModelUsageRow:
    name: str
    tokens: int
    cents: float
    count: int
    headless_count: int
    cny: float = 0.0


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
    total_cny: float = 0.0
    plan_cny: float = 0.0
    on_demand_cny: float = 0.0
    usd_cny_rate: float = 0.0
    monthly_plan_usd: float = 0.0
    first_party_count: int = 0
    api_count: int = 0
    grok_bot_count: int = 0
    actual_cny: float = 0.0
    uses_actual_cny: bool = False


@dataclass(frozen=True)
class UsageReportFilter:
    kind: str = ""
    category: str = ""
    model: str = ""
    headless: bool | None = None
    owning_user: str = ""


@dataclass(frozen=True)
class CnySpendSettings:
    monthly_plan_usd: float = 0.0
    usd_cny_rate: float = DEFAULT_USD_CNY_RATE
    membership_type: str = ""
    actual_cny: float = 0.0


@dataclass(frozen=True)
class AccountCompareCategory:
    category: str
    count: int = 0
    tokens: int = 0
    cny: float = 0.0

    @property
    def cny_per_million(self) -> float | None:
        return unit_cny(self.cny, self.tokens / 1_000_000.0 if self.tokens else 0.0)

    @property
    def cny_per_request(self) -> float | None:
        return unit_cny(self.cny, float(self.count))


@dataclass
class AccountCompareInput:
    account_id: str
    label: str = ""
    channel: str = ""
    membership_type: str = ""
    account_kind: str = "long_term"
    temp_start_at: str = ""
    temp_valid_days: int = 0
    temp_valid_hours: int = 0
    billing_cycle_start: str = ""
    billing_cycle_end: str = ""
    last_remaining: float | None = None
    events: tuple[UsageEvent, ...] | list[UsageEvent] = ()
    spend: CnySpendSettings | None = None


@dataclass
class AccountCompareRow:
    account_id: str
    label: str
    channel: str
    membership_type: str
    window_source: str
    window_start_ms: int
    window_end_ms: int
    window_days: float
    plan_cny: float
    daily_holding_cny: float
    window_plan_cny: float
    on_demand_cny: float
    total_cny: float
    event_count: int
    total_tokens: int
    first_party: AccountCompareCategory
    api: AccountCompareCategory
    grok_bot: AccountCompareCategory
    last_remaining: float | None = None
    uses_actual_cny: bool = False

    @property
    def channel_label(self) -> str:
        return channel_label(self.channel)

    @property
    def window_label(self) -> str:
        return WINDOW_LABELS.get(self.window_source, WINDOW_LABELS[WINDOW_FALLBACK])

    @property
    def cny_per_million(self) -> float | None:
        return unit_cny(self.total_cny, self.total_tokens / 1_000_000.0 if self.total_tokens else 0.0)

    @property
    def cny_per_request(self) -> float | None:
        return unit_cny(self.total_cny, float(self.event_count))


@dataclass
class AccountCompareGroup:
    channel: str
    rows: tuple[AccountCompareRow, ...]
    daily_holding_cny: float
    total_cny: float
    event_count: int
    total_tokens: int
    first_party: AccountCompareCategory
    api: AccountCompareCategory
    grok_bot: AccountCompareCategory

    @property
    def channel_label(self) -> str:
        return channel_label(self.channel)

    @property
    def cny_per_million(self) -> float | None:
        return unit_cny(self.total_cny, self.total_tokens / 1_000_000.0 if self.total_tokens else 0.0)

    @property
    def cny_per_request(self) -> float | None:
        return unit_cny(self.total_cny, float(self.event_count))


@dataclass
class AccountCompareReport:
    rows: tuple[AccountCompareRow, ...]
    groups: tuple[AccountCompareGroup, ...]
    holding_days: float = HOLDING_DAYS


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


def classify_usage_category(model: str | None) -> str:
    name = (model or "").strip()
    if is_grok_bot_model(name):
        return CATEGORY_GROK_BOT
    if is_first_party_model(name):
        return CATEGORY_FIRST_PARTY
    return CATEGORY_API


def category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get((category or "").strip().lower(), CATEGORY_LABELS[CATEGORY_API])


def sanitize_account_channel(raw: Any) -> str:
    key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "")
    if key in {"self_pay", "self", "selfpay", "自费"}:
        return CHANNEL_SELF_PAY
    if key in {"third_party", "third", "thirdparty", "第三方"}:
        return CHANNEL_THIRD_PARTY
    return ""


def channel_label(channel: str | None) -> str:
    return CHANNEL_LABELS.get(sanitize_account_channel(channel), CHANNEL_LABELS[""])


def unit_cny(amount: float, denom: float) -> float | None:
    if denom <= 1e-12:
        return None
    return max(0.0, float(amount)) / denom


def format_cny_unit(amount: float | None, suffix: str) -> str:
    if amount is None:
        return "—"
    return f"{format_cny(amount)}{suffix}"


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


def clamp_usd_cny_rate(rate: float | None) -> float:
    try:
        n = float(rate) if rate is not None else DEFAULT_USD_CNY_RATE
    except (TypeError, ValueError):
        return DEFAULT_USD_CNY_RATE
    if n != n or n in (float("inf"), float("-inf")):
        return DEFAULT_USD_CNY_RATE
    return min(100.0, max(0.01, n))


def clamp_monthly_plan_usd(usd: float | None) -> float:
    try:
        n = float(usd) if usd is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if n != n or n in (float("inf"), float("-inf")) or n < 0:
        return 0.0
    return min(10_000.0, n)


def clamp_actual_cny(amount: float | None) -> float:
    try:
        n = float(amount) if amount is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if n != n or n in (float("inf"), float("-inf")) or n < 0:
        return 0.0
    return min(1_000_000.0, n)


def default_monthly_plan_usd(membership: str | None) -> float:
    key = (membership or "").strip().lower().replace(" ", "")
    if key.endswith("套餐"):
        key = key[:-2]
    return _PLAN_USD.get(key, 0.0)


def resolve_monthly_plan_usd(monthly_plan_usd: float | None, membership: str | None = None) -> float:
    stored = clamp_monthly_plan_usd(monthly_plan_usd)
    if stored > 0:
        return stored
    return default_monthly_plan_usd(membership)


def plan_cny_amount(spend: CnySpendSettings | None) -> float:
    if spend is None:
        return 0.0
    actual = clamp_actual_cny(spend.actual_cny)
    if actual > 0:
        return actual
    rate = clamp_usd_cny_rate(spend.usd_cny_rate)
    return resolve_monthly_plan_usd(spend.monthly_plan_usd, spend.membership_type) * rate


def is_plan_covered_kind(kind: str | None) -> bool:
    key = (kind or "").strip().lower()
    return key not in {KIND_ON_DEMAND, KIND_FREE}


def format_cny(amount: float | None) -> str:
    if amount is None:
        return "—"
    n = max(0.0, float(amount))
    return f"¥{n:.2f}"


def resolve_compare_window(
    *,
    account_kind: str = "",
    temp_start_at: str = "",
    temp_valid_days: int = 0,
    temp_valid_hours: int = 0,
    billing_cycle_start: str = "",
    billing_cycle_end: str = "",
    now_ms: int | None = None,
) -> tuple[int, int, str]:
    now = int(now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp() * 1000)
    kind = str(account_kind or "").strip().lower().replace("-", "_")
    if kind in {"temporary", "temp", "short"}:
        start = _iso_to_ms(temp_start_at)
        end = _temp_end_ms(temp_start_at, temp_valid_days, temp_valid_hours)
        if start is not None:
            return start, min(end or now, now), WINDOW_VALIDITY
    start = _iso_to_ms(billing_cycle_start)
    if start is not None:
        end = _iso_to_ms(billing_cycle_end) or now
        return start, min(end, now), WINDOW_CYCLE
    return now - 30 * _MS_DAY, now, WINDOW_FALLBACK


def _temp_end_ms(start_at: str, days: int, hours: int) -> int | None:
    start = _parse_iso(start_at)
    if start is None:
        return None
    try:
        d = max(0, min(999, int(days)))
        h = max(0, min(23, int(hours)))
    except (TypeError, ValueError):
        return None
    if d == 0 and h == 0:
        return None
    return int((start + timedelta(days=d, hours=h)).timestamp() * 1000)


def compare_window_days(start_ms: int, end_ms: int) -> float:
    span = max(0, int(end_ms) - int(start_ms))
    days = span / float(_MS_DAY)
    return max(days, 1.0 / 24.0)


def empty_compare_category(category: str) -> AccountCompareCategory:
    return AccountCompareCategory(category=category)


def build_account_compare_row(item: AccountCompareInput, *, now_ms: int | None = None) -> AccountCompareRow:
    start_ms, end_ms, source = resolve_compare_window(
        account_kind=item.account_kind,
        temp_start_at=item.temp_start_at,
        temp_valid_days=item.temp_valid_days,
        temp_valid_hours=item.temp_valid_hours,
        billing_cycle_start=item.billing_cycle_start,
        billing_cycle_end=item.billing_cycle_end,
        now_ms=now_ms,
    )
    window_days = compare_window_days(start_ms, end_ms)
    window_events = [
        ev for ev in item.events if start_ms <= ev.timestamp_ms <= end_ms
    ]
    spend = item.spend or CnySpendSettings()
    rate = clamp_usd_cny_rate(spend.usd_cny_rate)
    actual = clamp_actual_cny(spend.actual_cny)
    monthly = resolve_monthly_plan_usd(spend.monthly_plan_usd, spend.membership_type)
    uses_actual = actual > 0
    plan_cny = actual if uses_actual else monthly * rate
    daily_holding = plan_cny / HOLDING_DAYS if plan_cny > 0 else 0.0
    window_plan = daily_holding * window_days
    included = [ev for ev in window_events if is_plan_covered_kind(ev.kind)]
    included_cost_sum = sum(event_cost_cents(ev) for ev in included)
    included_count = len(included)
    cats = {
        CATEGORY_FIRST_PARTY: [0, 0, 0.0],
        CATEGORY_API: [0, 0, 0.0],
        CATEGORY_GROK_BOT: [0, 0, 0.0],
    }
    on_demand_cny = 0.0
    total_cny = 0.0
    total_tokens = 0
    for ev in window_events:
        amount = allocate_event_cny(ev, included_cost_sum, included_count, window_plan, rate)
        total_cny += amount
        total_tokens += ev.tokens
        if ev.kind == KIND_ON_DEMAND:
            on_demand_cny += amount
        bucket = classify_usage_category(ev.model)
        row = cats[bucket]
        row[0] += 1
        row[1] += ev.tokens
        row[2] += amount
    return AccountCompareRow(
        account_id=item.account_id,
        label=item.label or item.account_id,
        channel=sanitize_account_channel(item.channel),
        membership_type=item.membership_type,
        window_source=source,
        window_start_ms=start_ms,
        window_end_ms=end_ms,
        window_days=window_days,
        plan_cny=plan_cny,
        daily_holding_cny=daily_holding,
        window_plan_cny=window_plan,
        on_demand_cny=on_demand_cny,
        total_cny=total_cny,
        event_count=len(window_events),
        total_tokens=total_tokens,
        first_party=AccountCompareCategory(
            CATEGORY_FIRST_PARTY, cats[CATEGORY_FIRST_PARTY][0], cats[CATEGORY_FIRST_PARTY][1], cats[CATEGORY_FIRST_PARTY][2]
        ),
        api=AccountCompareCategory(CATEGORY_API, cats[CATEGORY_API][0], cats[CATEGORY_API][1], cats[CATEGORY_API][2]),
        grok_bot=AccountCompareCategory(
            CATEGORY_GROK_BOT, cats[CATEGORY_GROK_BOT][0], cats[CATEGORY_GROK_BOT][1], cats[CATEGORY_GROK_BOT][2]
        ),
        last_remaining=item.last_remaining,
        uses_actual_cny=uses_actual,
    )


def compare_input_from_account(
    account: dict[str, Any],
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    *,
    monthly_plan_usd: float = 0.0,
    usd_cny_rate: float = DEFAULT_USD_CNY_RATE,
) -> AccountCompareInput:
    return AccountCompareInput(
        account_id=str(account.get("id") or ""),
        label=str(account.get("label") or ""),
        channel=str(account.get("channel") or ""),
        membership_type=str(account.get("membership_type") or ""),
        account_kind=str(account.get("account_kind") or "long_term"),
        temp_start_at=str(account.get("temp_start_at") or ""),
        temp_valid_days=int(account.get("temp_valid_days") or 0),
        temp_valid_hours=int(account.get("temp_valid_hours") or 0),
        billing_cycle_start=str(account.get("billing_cycle_start") or ""),
        billing_cycle_end=str(account.get("billing_cycle_end") or ""),
        last_remaining=account.get("last_remaining"),
        events=tuple(events),
        spend=CnySpendSettings(
            monthly_plan_usd=monthly_plan_usd,
            usd_cny_rate=usd_cny_rate,
            membership_type=str(account.get("membership_type") or ""),
            actual_cny=float(account.get("actual_cny") or 0),
        ),
    )


def build_account_compare_report(
    items: list[AccountCompareInput] | tuple[AccountCompareInput, ...],
    *,
    now_ms: int | None = None,
) -> AccountCompareReport:
    rows = tuple(build_account_compare_row(item, now_ms=now_ms) for item in items)
    grouped: dict[str, list[AccountCompareRow]] = {key: [] for key in CHANNEL_ORDER}
    for row in rows:
        grouped.setdefault(row.channel, []).append(row)
    groups: list[AccountCompareGroup] = []
    for channel in CHANNEL_ORDER:
        bucket = grouped.get(channel) or []
        if not bucket:
            continue
        groups.append(_sum_compare_group(channel, bucket))
    return AccountCompareReport(rows=rows, groups=tuple(groups))


def _sum_compare_group(channel: str, rows: list[AccountCompareRow]) -> AccountCompareGroup:
    def add_cat(name: str, parts: list[AccountCompareCategory]) -> AccountCompareCategory:
        return AccountCompareCategory(
            name,
            sum(p.count for p in parts),
            sum(p.tokens for p in parts),
            sum(p.cny for p in parts),
        )

    return AccountCompareGroup(
        channel=channel,
        rows=tuple(rows),
        daily_holding_cny=sum(r.daily_holding_cny for r in rows),
        total_cny=sum(r.total_cny for r in rows),
        event_count=sum(r.event_count for r in rows),
        total_tokens=sum(r.total_tokens for r in rows),
        first_party=add_cat(CATEGORY_FIRST_PARTY, [r.first_party for r in rows]),
        api=add_cat(CATEGORY_API, [r.api for r in rows]),
        grok_bot=add_cat(CATEGORY_GROK_BOT, [r.grok_bot for r in rows]),
    )


def account_compare_to_csv(report: AccountCompareReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "账号",
            "渠道",
            "套餐",
            "窗口",
            "窗口天数",
            "日均持有",
            "窗口实付",
            "请求",
            "Token",
            "¥/百万Token",
            "¥/次",
            "First-party次数",
            "First-party Token",
            "First-party实付",
            "First-party ¥/百万",
            "First-party ¥/次",
            "API次数",
            "API Token",
            "API实付",
            "API ¥/百万",
            "API ¥/次",
            "Grok Bot次数",
            "Grok Bot Token",
            "Grok Bot实付",
            "Grok Bot ¥/百万",
            "Grok Bot ¥/次",
        ]
    )
    for row in report.rows:
        writer.writerow(_compare_csv_cells(row.label, row.channel_label, row.membership_type, row.window_label, row.window_days, row))
    for group in report.groups:
        writer.writerow(
            _compare_csv_cells(
                f"{group.channel_label}合计",
                group.channel_label,
                "",
                "",
                0,
                group,
            )
        )
    return buf.getvalue()


def _compare_csv_cells(name: str, channel: str, membership: str, window: str, days: float, row) -> list[Any]:
    def cat_cells(cat: AccountCompareCategory) -> list[Any]:
        return [
            cat.count,
            cat.tokens,
            f"{cat.cny:.4f}",
            "" if cat.cny_per_million is None else f"{cat.cny_per_million:.4f}",
            "" if cat.cny_per_request is None else f"{cat.cny_per_request:.4f}",
        ]

    return [
        name,
        channel,
        membership,
        window,
        f"{days:.2f}" if days else "",
        f"{row.daily_holding_cny:.4f}",
        f"{row.total_cny:.4f}",
        row.event_count,
        row.total_tokens,
        "" if row.cny_per_million is None else f"{row.cny_per_million:.4f}",
        "" if row.cny_per_request is None else f"{row.cny_per_request:.4f}",
        *cat_cells(row.first_party),
        *cat_cells(row.api),
        *cat_cells(row.grok_bot),
    ]


def format_event_cny(event: UsageEvent, amount: float | None = None) -> str:
    if event.kind == KIND_FREE:
        return "—"
    return format_cny(event.allocated_cny if amount is None else amount)


def allocate_event_cny(
    event: UsageEvent,
    included_cost_sum: float,
    included_count: int,
    plan_cny: float,
    rate: float,
) -> float:
    if event.kind == KIND_FREE:
        return 0.0
    if event.kind == KIND_ON_DEMAND:
        return event_cost_cents(event) / 100.0 * rate
    cents = event_cost_cents(event)
    if included_cost_sum > 1e-9:
        return plan_cny * (cents / included_cost_sum)
    if included_count > 0 and plan_cny > 0:
        return plan_cny / included_count
    return 0.0


def _cny_by_id(
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    spend: CnySpendSettings | None,
) -> tuple[dict[str, float], float, float, float, float, float, bool]:
    if spend is None:
        return {}, 0.0, 0.0, 0.0, 0.0, 0.0, False
    rate = clamp_usd_cny_rate(spend.usd_cny_rate)
    monthly = resolve_monthly_plan_usd(spend.monthly_plan_usd, spend.membership_type)
    actual = clamp_actual_cny(spend.actual_cny)
    uses_actual = actual > 0
    plan_cny = actual if uses_actual else monthly * rate
    included = [ev for ev in events if is_plan_covered_kind(ev.kind)]
    included_cost_sum = sum(event_cost_cents(ev) for ev in included)
    included_count = len(included)
    by_id: dict[str, float] = {}
    on_demand_cny = 0.0
    for i, ev in enumerate(events):
        amount = allocate_event_cny(ev, included_cost_sum, included_count, plan_cny, rate)
        key = ev.id or f"#{i}"
        by_id[key] = amount
        if ev.kind == KIND_ON_DEMAND:
            on_demand_cny += amount
    return by_id, plan_cny, on_demand_cny, monthly, rate, actual, uses_actual


def format_event_time(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(max(0, timestamp_ms) / 1000.0, tz=DISPLAY_TZ)
    return dt.strftime("%Y-%m-%d %H:%M")


def event_date(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(max(0, timestamp_ms) / 1000.0, tz=DISPLAY_TZ)
    return dt.strftime("%Y-%m-%d")


def event_hour(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(_floor_hour_ms(timestamp_ms) / 1000.0, tz=DISPLAY_TZ)
    return dt.strftime("%Y-%m-%d %H:00")


def chart_model_label(name: str) -> str:
    text = (name or "").strip()
    return text[7:] if text.startswith("cursor-") else text


def _floor_hour_ms(timestamp_ms: int) -> int:
    return max(0, timestamp_ms) // _MS_HOUR * _MS_HOUR


def _floor_day_ms(timestamp_ms: int) -> int:
    shifted = max(0, timestamp_ms) + 8 * _MS_HOUR
    return (shifted // _MS_DAY * _MS_DAY) - 8 * _MS_HOUR


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
    kind = "按小时 Token" if hourly else "按日 Token"
    if not keys:
        return f"{kind}（{TZ_LABEL}）"
    first, last = keys[0], keys[-1]
    if first == last:
        return f"{kind}（{TZ_LABEL} · {first}）"
    if hourly and first[:10] == last[:10]:
        return f"{kind}（{TZ_LABEL} · {first[:10]} {first[11:]}–{last[11:]}）"
    return f"{kind}（{TZ_LABEL} · {first} 至 {last}）"


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
            event_hour(first_ms + i * _MS_HOUR)
            for i in range((last_ms - first_ms) // _MS_HOUR + 1)
        ]
        key_of = event_hour
    else:
        last_ms = _floor_day_ms(max(ev.timestamp_ms for ev in selected))
        first_ms = _floor_day_ms(min(ev.timestamp_ms for ev in selected))
        keys = [
            event_date(first_ms + i * _MS_DAY)
            for i in range((last_ms - first_ms) // _MS_DAY + 1)
        ]
        key_of = event_date

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
    spend: CnySpendSettings | None = None,
) -> UsageReport:
    filt = filt or UsageReportFilter()
    kind = (filt.kind or "").strip().lower()
    category = (filt.category or "").strip().lower()
    model = (filt.model or "").strip()
    owning = (filt.owning_user or "").strip()
    source = list(events)
    cny_by_id, plan_cny, on_demand_cny, monthly, rate, actual, uses_actual = _cny_by_id(source, spend)
    selected: list[UsageEvent] = []
    for i, event in enumerate(source):
        if kind and event.kind != kind:
            continue
        if category and classify_usage_category(event.model) != category:
            continue
        if model and event.model != model:
            continue
        if filt.headless is not None and event.is_headless != filt.headless:
            continue
        if owning and event.owning_user != owning:
            continue
        key = event.id or f"#{i}"
        selected.append(replace(event, allocated_cny=cny_by_id.get(key, 0.0)))
    selected.sort(key=lambda e: e.timestamp_ms, reverse=True)

    daily_map: dict[str, list[int | float]] = {}
    model_map: dict[str, list[int | float]] = {}
    included = free = on_demand = other = headless = 0
    first_party = api = grok_bot = 0
    total_tokens = 0
    total_cents = 0.0
    total_cny = 0.0
    has_cost = False
    for event in selected:
        cents = event_cost_cents(event)
        total_tokens += event.tokens
        total_cents += cents
        total_cny += event.allocated_cny
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
        bucket = classify_usage_category(event.model)
        if bucket == CATEGORY_GROK_BOT:
            grok_bot += 1
        elif bucket == CATEGORY_FIRST_PARTY:
            first_party += 1
        else:
            api += 1
        if event.is_headless:
            headless += 1
        day = event_date(event.timestamp_ms)
        bucket = daily_map.setdefault(day, [0, 0.0, 0, 0.0])
        bucket[0] = int(bucket[0]) + event.tokens
        bucket[1] = float(bucket[1]) + cents
        bucket[2] = int(bucket[2]) + 1
        bucket[3] = float(bucket[3]) + event.allocated_cny
        row = model_map.setdefault(event.model or "—", [0, 0.0, 0, 0, 0.0])
        row[0] = int(row[0]) + event.tokens
        row[1] = float(row[1]) + cents
        row[2] = int(row[2]) + 1
        if event.is_headless:
            row[3] = int(row[3]) + 1
        row[4] = float(row[4]) + event.allocated_cny

    daily = tuple(
        DailyUsageRow(
            date=day,
            tokens=int(vals[0]),
            cents=float(vals[1]),
            count=int(vals[2]),
            cny=float(vals[3]),
        )
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
                    cny=float(vals[4]),
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
        first_party_count=first_party,
        api_count=api,
        grok_bot_count=grok_bot,
        actual_cny=actual,
        uses_actual_cny=uses_actual,
        daily=daily,
        models=models,
        events=tuple(selected),
        total_cny=total_cny,
        plan_cny=plan_cny,
        on_demand_cny=on_demand_cny,
        usd_cny_rate=rate,
        monthly_plan_usd=monthly,
    )


def usage_events_to_csv(
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    spend: CnySpendSettings | None = None,
    allocation_base: list[UsageEvent] | tuple[UsageEvent, ...] | None = None,
) -> str:
    cny_by_id: dict[str, float] = {}
    if spend is not None:
        cny_by_id, _, _, _, _, _, _ = _cny_by_id(allocation_base if allocation_base is not None else events, spend)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER.split(","))
    for i, event in enumerate(events):
        key = event.id or f"#{i}"
        if spend is not None:
            cny_text = format_event_cny(event, cny_by_id.get(key, 0.0))
        elif event.allocated_cny:
            cny_text = format_event_cny(event)
        else:
            cny_text = "—"
        writer.writerow(
            [
                format_event_time(event.timestamp_ms),
                event.user_email,
                kind_label(event.kind),
                event.model,
                str(event.tokens),
                format_event_cost(event),
                cny_text,
                "是" if event.is_headless else "否",
            ]
        )
    return "\ufeff" + buf.getvalue()


def usage_event_from_dict(raw: dict[str, Any]) -> UsageEvent | None:
    try:
        ts = _as_int64(raw.get("timestamp_ms"))
        if ts is None:
            ts = _iso_to_ms(raw.get("timestamp"))
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
            charged_cents=_as_float(raw.get("charged_cents", raw.get("chargedCents"))),
            total_cents=_as_float(raw.get("total_cents", raw.get("totalCents"))),
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


USAGE_EVENT_KEEP_DAYS = 120


def event_to_dict(event: UsageEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp_ms": event.timestamp_ms,
        "model": event.model,
        "kind": event.kind,
        "user_email": event.user_email,
        "owning_user": event.owning_user,
        "tokens": event.tokens,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "cache_write_tokens": event.cache_write_tokens,
        "cache_read_tokens": event.cache_read_tokens,
        "charged_cents": event.charged_cents,
        "total_cents": event.total_cents,
        "is_headless": event.is_headless,
        "is_chargeable": event.is_chargeable,
    }


def events_cache_path(account_id: str, team_scope: bool = False, directory: Path | None = None) -> Path:
    from config import CONFIG_DIR
    from cursor_api import _safe_account_id

    root = directory or CONFIG_DIR
    aid = _safe_account_id(account_id)
    name = f"usage_events.{aid}.team.jsonl" if team_scope else f"usage_events.{aid}.jsonl"
    return root / name


def load_cached_events(account_id: str, team_scope: bool = False, directory: Path | None = None) -> list[UsageEvent]:
    path = events_cache_path(account_id, team_scope, directory)
    if not path.is_file():
        return []
    events: list[UsageEvent] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            ev = usage_event_from_dict(raw)
            if ev is not None:
                events.append(ev)
    except OSError:
        return []
    return merge_usage_events(events, [])


def save_cached_events(
    events: list[UsageEvent] | tuple[UsageEvent, ...],
    account_id: str,
    team_scope: bool = False,
    directory: Path | None = None,
) -> None:
    aid = str(account_id or "").strip()
    if not aid:
        return
    path = events_cache_path(aid, team_scope, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=USAGE_EVENT_KEEP_DAYS)).timestamp() * 1000)
    pruned = prune_usage_events(list(events), cutoff)
    lines = [json.dumps(event_to_dict(ev), ensure_ascii=False) for ev in pruned]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


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
