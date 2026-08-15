"""用量文案（无 GUI 依赖，菜单栏进程可安全导入）。"""

from __future__ import annotations

from datetime import datetime

from cursor_api import UsageSnapshot, format_token_count


def format_summary_text(
    usage: UsageSnapshot | None,
    error_message: str | None,
    updated_at: str | None,
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
    return (
        f"剩余 {usage.remaining_percent:.1f}% | 计划 {usage.membership_type} | "
        f"{tokens}First-party {auto} | API {api} | 预计可用 {est} | 更新 {updated_at or '—'}"
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


def format_reset_date(iso_value: str) -> str:
    try:
        text = iso_value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return f"{dt.month}月{dt.day}日"
    except ValueError:
        return iso_value
