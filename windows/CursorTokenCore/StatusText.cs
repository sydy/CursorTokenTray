using System.Globalization;

namespace CursorTokenCore;

public static class StatusText
{
    public static string FormatSummary(UsageSnapshot? usage, string? error, string? updatedAt, string? accountLabel = null)
    {
        if (error is not null) return $"状态: {error} | 更新 {updatedAt ?? "—"}";
        if (usage is null) return "状态: 等待刷新…";
        var auto = usage.AutoPercentUsed is null ? "—" : usage.AutoPercentUsed.Value.ToString("0.0", CultureInfo.InvariantCulture) + "%";
        var api = usage.ApiPercentUsed is null ? "—" : usage.ApiPercentUsed.Value.ToString("0.0", CultureInfo.InvariantCulture) + "%";
        var est = FormatEstimatedDays(usage);
        var tokens = usage.TotalTokens is > 0 ? $"消耗 {UsageParser.FormatTokenCount(usage.TotalTokens)} Token | " : "";
        var spend = usage.ShowsAmount ? $"金额 {UsageParser.FormatSpendRange(usage.UsedCents, usage.LimitCents)} | " : "";
        var plan = FormatPlanCaption(usage.MembershipType, accountLabel);
        if (usage.IsUnlimited) plan += " · 不限量";
        return $"剩余 {usage.RemainingPercent.ToString("0.0", CultureInfo.InvariantCulture)}% | {plan} | {spend}{tokens}First-party {auto} | API {api} | 预计可用 {est} | 更新 {updatedAt ?? "—"}";
    }

    public static string FormatEstimatedDays(UsageSnapshot usage)
    {
        if (usage.EstimatedUsableDays is null)
        {
            if (usage.UsedPercent < 0.2) return "用量过低，暂无法估算";
            if (usage.DaysElapsed is < 0.04) return "周期刚开始，统计中";
            return "暂无法估算";
        }
        var est = usage.EstimatedUsableDays.Value;
        string text;
        if (est <= 0) text = "已耗尽";
        else if (est < 1) text = $"约 {Math.Max(1, (int)(est * 24))} 小时";
        else text = $"约 {est.ToString("0.0", CultureInfo.InvariantCulture)} 天".Replace(".0 天", " 天");
        if (usage.DaysRemaining is { } resetLeft && est > 0)
            text += est >= resetLeft ? "  ·  可撑过本周期" : "  ·  可能提前耗尽";
        return text;
    }

    public static string StatusPillText(double? remaining, bool error = false)
    {
        if (error) return "异常";
        if (remaining is null) return "等待刷新";
        if (remaining <= 0) return "已耗尽";
        if (remaining < 20) return "额度紧张";
        if (remaining < 50) return "略偏低";
        return "状态良好";
    }

    public static string FormatPlanCaption(string? membership, string? accountLabel = null)
    {
        var raw = (membership ?? "").Trim();
        string name;
        if (raw.Length == 0) name = "—";
        else
        {
            name = UsageParser.FormatMembershipType(raw);
            if (!name.Contains("套餐")) name += " 套餐";
        }
        var label = (accountLabel ?? "").Trim();
        var known = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { name, raw, UsageParser.FormatMembershipType(raw) };
        if (label.Length > 0 && !known.Contains(label))
            return name == "—" ? label : $"{label} · {name}";
        return name;
    }

    public static string FormatEstimateCaption(UsageSnapshot usage)
    {
        var text = FormatEstimatedDays(usage);
        if (text.Contains("可撑过本周期")) return "预计可撑过本周期";
        if (text.Contains("提前耗尽")) return "预计可能提前耗尽";
        if (text == "已耗尽") return "额度已耗尽";
        return text;
    }

    public static string FormatResetDate(string iso)
    {
        var text = iso.Replace("Z", "+00:00");
        if (!DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var dt))
            return iso;
        return $"{dt.Month}月{dt.Day}日";
    }

    public static List<(string, string)> BuildStatusLines(UsageSnapshot? usage, string? error, string? updatedAt = null, string? accountLabel = null)
    {
        if (error is not null) return [("状态", error)];
        if (usage is null) return [("状态", "等待刷新…")];
        var rows = new List<(string, string)>();
        if (usage.IsUnlimited) rows.Add(("剩余", "不限量"));
        else if (usage.ShowsAmount)
            rows.Add(("剩余", $"{usage.RemainingPercent.ToString("0.0", CultureInfo.InvariantCulture)}%（{UsageParser.FormatSpendRange(usage.UsedCents, usage.LimitCents)}）"));
        else
            rows.Add(("剩余", $"{usage.RemainingPercent.ToString("0.0", CultureInfo.InvariantCulture)}%（已用 {usage.UsedPercent.ToString("0.0", CultureInfo.InvariantCulture)}%）"));
        var label = (accountLabel ?? "").Trim();
        var memb = string.IsNullOrEmpty(usage.MembershipType) ? "" : UsageParser.FormatMembershipType(usage.MembershipType);
        if (label.Length > 0 && !label.Equals(memb, StringComparison.OrdinalIgnoreCase)) rows.Add(("账号", label));
        var plan = string.IsNullOrEmpty(memb) ? "—" : memb;
        if (usage.IsUnlimited) plan += " · 不限量";
        rows.Add(("计划", plan));
        if (usage.ShowsAmount) rows.Add(("金额", UsageParser.FormatSpendRange(usage.UsedCents, usage.LimitCents)));
        if (usage.PooledUsedCents is { } pu && usage.PooledLimitCents is { } pl && pl > 0 && (usage.UsedCents != pu || usage.LimitCents != pl))
            rows.Add(("团队额度", UsageParser.FormatSpendRange(pu, pl)));
        if (usage.OnDemandUsedCents is { } ou && usage.OnDemandLimitCents is { } ol && ol > 0 && (usage.UsedCents != ou || usage.LimitCents != ol))
            rows.Add(("按需用量", UsageParser.FormatSpendRange(ou, ol)));
        if (usage.TotalTokens is > 0) rows.Add(("消耗 Token", UsageParser.FormatTokenCount(usage.TotalTokens)));
        if (usage.AutoPercentUsed is not null || usage.ApiPercentUsed is not null)
        {
            var auto = usage.AutoPercentUsed is null ? "—" : usage.AutoPercentUsed.Value.ToString("0.0", CultureInfo.InvariantCulture) + "%";
            var api = usage.ApiPercentUsed is null ? "—" : usage.ApiPercentUsed.Value.ToString("0.0", CultureInfo.InvariantCulture) + "%";
            rows.Add(("明细", $"First-party {auto} · API {api}"));
        }
        if (usage.BillingCycleEnd is { } end)
        {
            var endText = FormatResetDate(end);
            rows.Add(("重置", usage.DaysRemaining is { } d ? $"{endText}（还剩 {d} 天）" : endText));
            rows.Add(("预计可用", FormatEstimatedDays(usage)));
        }
        else if (usage.EstimatedUsableDays is not null) rows.Add(("预计可用", FormatEstimatedDays(usage)));
        rows.Add(("更新", updatedAt ?? DateTime.Now.ToString("HH:mm:ss")));
        return rows;
    }
}
