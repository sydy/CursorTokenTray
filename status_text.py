"""用量文案（无 GUI 依赖，菜单栏进程可安全导入）。"""

from __future__ import annotations

from datetime import datetime, timezone

from cursor_api import (
    UsageSnapshot,
    format_membership_type,
    format_spend_range,
    format_token_count,
)


def format_summary_text(
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
    account_label: str | None = None,
) -> str:
    if error_message:
        return f"状态: {error_message} | 更新 {updated_at or '—'}"
    if usage is None:
        return "状态: 等待刷新…"
    auto = "—" if usage.auto_percent_used is None else f"{usage.auto_percent_used:.1f}%"
    api = "—" if usage.api_percent_used is None else f"{usage.api_percent_used:.1f}%"
    est = format_estimated_days(usage)
    tokens = ""
    if usage.total_tokens:
        tokens = f"消耗 {format_token_count(usage.total_tokens)} Token | "
    spend = ""
    if usage.shows_amount():
        spend = f"金额 {format_spend_range(usage.used_cents, usage.limit_cents)} | "
    plan = format_plan_caption(usage.membership_type, account_label)
    if usage.is_unlimited:
        plan = f"{plan} · 不限量"
    return (
        f"剩余 {usage.remaining_percent:.1f}% | {plan} | "
        f"{spend}{tokens}First-party {auto} | API {api} | 预计可用 {est} | 更新 {updated_at or '—'}"
    )


def format_estimated_days(usage: UsageSnapshot) -> str:
    est = usage.estimated_usable_days
    if est is None:
        if usage.used_percent < 0.2:
            return "用量过低，暂无法估算"
        if usage.days_elapsed is not None and usage.days_elapsed < 0.04:
            return "周期刚开始，统计中"
        return "暂无法估算"

    if est <= 0:
        text = "已耗尽"
    elif est < 1:
        text = f"约 {max(1, int(est * 24))} 小时"
    else:
        text = f"约 {est:.1f} 天".replace(".0 天", " 天")

    reset_left = usage.days_remaining
    if reset_left is not None and est > 0:
        if est >= reset_left:
            text += "  ·  可撑过本周期"
        else:
            text += "  ·  可能提前耗尽"
    return text


def status_pill_text(remaining: float | None, *, error: bool = False) -> str:
    """组合 4 左侧状态胶囊。"""
    if error:
        return "异常"
    if remaining is None:
        return "等待刷新"
    pct = float(remaining)
    if pct <= 0:
        return "已耗尽"
    if pct < 20:
        return "额度紧张"
    if pct < 50:
        return "略偏低"
    return "状态良好"


def format_plan_caption(membership: str | None, account_label: str | None = None) -> str:
    raw = (membership or "").strip()
    if not raw:
        name = "—"
    else:
        name = format_membership_type(raw)
        if "套餐" not in name:
            name = f"{name} 套餐"
    label = (account_label or "").strip()
    known = {name.lower(), raw.lower(), format_membership_type(raw).lower()}
    if label and label.lower() not in known:
        if name == "—":
            return label
        return f"{label} · {name}"
    return name


def format_estimate_caption(usage: UsageSnapshot) -> str:
    text = format_estimated_days(usage)
    if "可撑过本周期" in text:
        return "预计可撑过本周期"
    if "提前耗尽" in text:
        return "预计可能提前耗尽"
    if text == "已耗尽":
        return "额度已耗尽"
    return text


def format_reset_date(iso_value: str, include_time: bool = False) -> str:
    try:
        text = iso_value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if include_time and dt.tzinfo is not None:
            dt = dt.astimezone()
        text = f"{dt.month}月{dt.day}日"
        if include_time and (dt.hour or dt.minute):
            text += f" {dt.hour:02d}:{dt.minute:02d}"
        return text
    except ValueError:
        return iso_value


def format_cycle_remaining(end_iso: str | None, days_remaining: int | None, now: datetime | None = None) -> str:
    if not end_iso:
        return f"还剩 {days_remaining} 天" if days_remaining is not None else ""
    try:
        text = end_iso.replace("Z", "+00:00")
        end = datetime.fromisoformat(text)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        delta = end - clock.astimezone(end.tzinfo)
    except ValueError:
        return f"还剩 {days_remaining} 天" if days_remaining is not None else ""
    seconds = delta.total_seconds()
    if seconds <= 0:
        return "已到期"
    hours = int(seconds // 3600)
    if hours < 24:
        if hours < 1:
            minutes = max(1, int(seconds // 60))
            return f"还剩 {minutes} 分钟"
        return f"还剩 {hours} 小时"
    days = days_remaining if days_remaining is not None else int(seconds // 86400)
    return f"还剩 {days} 天"


def cycle_end_label(usage: UsageSnapshot) -> str:
    return "到期" if usage.billing_cycle_end_overridden else "重置"


def build_status_lines(
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None = None,
    account_label: str | None = None,
) -> list[tuple[str, str]]:
    """状态明细行（Windows 飞出层 / macOS 原生面板共用）。"""
    if error_message:
        return [("状态", error_message)]
    if usage is None:
        return [("状态", "等待刷新…")]

    rows: list[tuple[str, str]] = []
    if usage.is_unlimited:
        rows.append(("剩余", "不限量"))
    elif usage.shows_amount():
        rows.append(
            (
                "剩余",
                f"{usage.remaining_percent:.1f}%（{format_spend_range(usage.used_cents, usage.limit_cents)}）",
            )
        )
    else:
        rows.append(("剩余", f"{usage.remaining_percent:.1f}%（已用 {usage.used_percent:.1f}%）"))
    label = (account_label or "").strip()
    memb = format_membership_type(usage.membership_type) if usage.membership_type else ""
    if label and label.lower() != memb.lower():
        rows.append(("账号", label))
    plan = memb or "—"
    if usage.is_unlimited:
        plan = f"{plan} · 不限量"
    rows.append(("计划", plan))
    if usage.shows_amount():
        rows.append(("金额", format_spend_range(usage.used_cents, usage.limit_cents)))
    if (
        usage.pooled_used_cents is not None
        and usage.pooled_limit_cents is not None
        and usage.pooled_limit_cents > 0
        and (
            usage.used_cents != usage.pooled_used_cents
            or usage.limit_cents != usage.pooled_limit_cents
        )
    ):
        rows.append(("团队额度", format_spend_range(usage.pooled_used_cents, usage.pooled_limit_cents)))
    if (
        usage.on_demand_used_cents is not None
        and usage.on_demand_limit_cents is not None
        and usage.on_demand_limit_cents > 0
        and (
            usage.used_cents != usage.on_demand_used_cents
            or usage.limit_cents != usage.on_demand_limit_cents
        )
    ):
        rows.append(
            ("按需用量", format_spend_range(usage.on_demand_used_cents, usage.on_demand_limit_cents))
        )
    if usage.total_tokens:
        rows.append(("消耗 Token", format_token_count(usage.total_tokens)))
    if usage.auto_percent_used is not None or usage.api_percent_used is not None:
        auto = "—" if usage.auto_percent_used is None else f"{usage.auto_percent_used:.1f}%"
        api = "—" if usage.api_percent_used is None else f"{usage.api_percent_used:.1f}%"
        rows.append(("明细", f"First-party {auto} · API {api}"))

    if usage.billing_cycle_end:
        end_text = format_reset_date(
            usage.billing_cycle_end, include_time=usage.billing_cycle_end_overridden
        )
        remaining = format_cycle_remaining(usage.billing_cycle_end, usage.days_remaining)
        label = cycle_end_label(usage)
        if remaining:
            rows.append((label, f"{end_text}（{remaining}）"))
        else:
            rows.append((label, end_text))
        rows.append(("预计可用", format_estimated_days(usage)))
    elif usage.estimated_usable_days is not None:
        rows.append(("预计可用", format_estimated_days(usage)))

    rows.append(("更新", updated_at or datetime.now().strftime("%H:%M:%S")))
    return rows
