using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CursorTokenCore;

public sealed class UsageEvent
{
    public string Id { get; set; } = "";
    public long TimestampMs { get; set; }
    public string Model { get; set; } = "";
    public string Kind { get; set; } = UsageEvents.KindOther;
    public string UserEmail { get; set; } = "";
    public string OwningUser { get; set; } = "";
    public int Tokens { get; set; }
    public int InputTokens { get; set; }
    public int OutputTokens { get; set; }
    public int CacheWriteTokens { get; set; }
    public int CacheReadTokens { get; set; }
    public double? ChargedCents { get; set; }
    public double? TotalCents { get; set; }
    public bool IsHeadless { get; set; }
    public bool IsChargeable { get; set; }
    [JsonIgnore]
    public double AllocatedCny { get; set; }
}

public sealed record DailyUsageRow(string Date, long Tokens, double Cents, int Count, double Cny = 0);
public sealed record ModelUsageRow(string Name, long Tokens, double Cents, int Count, int HeadlessCount, double Cny = 0);
public sealed record ChartSlice(string Model, long Tokens, double Cents, int Count);
public sealed record ChartBucket(string Key, string Label, long Tokens, double Cents, int Count, List<ChartSlice> Slices);
public sealed class UsageChartSeries
{
    public bool Hourly { get; init; }
    public string Caption { get; init; } = "";
    public List<string> Models { get; init; } = [];
    public List<ChartBucket> Buckets { get; init; } = [];
}

public sealed class UsageReportFilter
{
    public string Kind { get; set; } = "";
    public string Category { get; set; } = "";
    public string Model { get; set; } = "";
    public bool? Headless { get; set; }
    public string OwningUser { get; set; } = "";
}

public sealed class UsageReport
{
    public int EventCount { get; init; }
    public long TotalTokens { get; init; }
    public double TotalCents { get; init; }
    public bool HasCost { get; init; }
    public int IncludedCount { get; init; }
    public int FreeCount { get; init; }
    public int OnDemandCount { get; init; }
    public int OtherCount { get; init; }
    public int HeadlessCount { get; init; }
    public int FirstPartyCount { get; init; }
    public int ApiCount { get; init; }
    public int GrokBotCount { get; init; }
    public List<DailyUsageRow> Daily { get; init; } = [];
    public List<ModelUsageRow> Models { get; init; } = [];
    public List<UsageEvent> Events { get; init; } = [];
    public double TotalCny { get; init; }
    public double PlanCny { get; init; }
    public double OnDemandCny { get; init; }
    public double UsdCnyRate { get; init; }
    public double MonthlyPlanUsd { get; init; }
    public double ActualCny { get; init; }
    public bool UsesActualCny { get; init; }
}

public readonly record struct CnySpendSettings(double MonthlyPlanUsd, double UsdCnyRate, string MembershipType, double ActualCny = 0)
{
    public static CnySpendSettings Default => new(0, UsageEvents.DefaultUsdCnyRate, "");
}

public sealed class AccountCompareCategory
{
    public string Category { get; init; } = "";
    public int Count { get; init; }
    public long Tokens { get; init; }
    public double Cny { get; init; }
    public double? CnyPerMillion => UsageEvents.UnitCny(Cny, Tokens > 0 ? Tokens / 1_000_000.0 : 0);
    public double? CnyPerRequest => UsageEvents.UnitCny(Cny, Count);
}

public sealed class AccountCompareInput
{
    public string AccountId { get; set; } = "";
    public string Label { get; set; } = "";
    public string Channel { get; set; } = "";
    public string MembershipType { get; set; } = "";
    public string AccountKind { get; set; } = "long_term";
    public string TempStartAt { get; set; } = "";
    public int TempValidDays { get; set; }
    public int TempValidHours { get; set; }
    public string BillingCycleStart { get; set; } = "";
    public string BillingCycleEnd { get; set; } = "";
    public double? LastRemaining { get; set; }
    public List<UsageEvent> Events { get; set; } = [];
    public CnySpendSettings? Spend { get; set; }
}

public sealed class AccountCompareRow
{
    public string AccountId { get; init; } = "";
    public string Label { get; init; } = "";
    public string Channel { get; init; } = "";
    public string MembershipType { get; init; } = "";
    public string WindowSource { get; init; } = "";
    public long WindowStartMs { get; init; }
    public long WindowEndMs { get; init; }
    public double WindowDays { get; init; }
    public double PlanCny { get; init; }
    public double DailyHoldingCny { get; init; }
    public double WindowPlanCny { get; init; }
    public double OnDemandCny { get; init; }
    public double TotalCny { get; init; }
    public int EventCount { get; init; }
    public long TotalTokens { get; init; }
    public AccountCompareCategory FirstParty { get; init; } = new() { Category = UsageEvents.CategoryFirstParty };
    public AccountCompareCategory Api { get; init; } = new() { Category = UsageEvents.CategoryApi };
    public AccountCompareCategory GrokBot { get; init; } = new() { Category = UsageEvents.CategoryGrokBot };
    public double? LastRemaining { get; init; }
    public bool UsesActualCny { get; init; }
    public string ChannelLabel => UsageEvents.ChannelLabel(Channel);
    public string WindowLabel => UsageEvents.WindowLabel(WindowSource);
    public double? CnyPerMillion => UsageEvents.UnitCny(TotalCny, TotalTokens > 0 ? TotalTokens / 1_000_000.0 : 0);
    public double? CnyPerRequest => UsageEvents.UnitCny(TotalCny, EventCount);
}

public sealed class AccountCompareGroup
{
    public string Channel { get; init; } = "";
    public List<AccountCompareRow> Rows { get; init; } = [];
    public double DailyHoldingCny { get; init; }
    public double TotalCny { get; init; }
    public int EventCount { get; init; }
    public long TotalTokens { get; init; }
    public AccountCompareCategory FirstParty { get; init; } = new() { Category = UsageEvents.CategoryFirstParty };
    public AccountCompareCategory Api { get; init; } = new() { Category = UsageEvents.CategoryApi };
    public AccountCompareCategory GrokBot { get; init; } = new() { Category = UsageEvents.CategoryGrokBot };
    public string ChannelLabel => UsageEvents.ChannelLabel(Channel);
    public double? CnyPerMillion => UsageEvents.UnitCny(TotalCny, TotalTokens > 0 ? TotalTokens / 1_000_000.0 : 0);
    public double? CnyPerRequest => UsageEvents.UnitCny(TotalCny, EventCount);
}

public sealed class AccountCompareReport
{
    public List<AccountCompareRow> Rows { get; init; } = [];
    public List<AccountCompareGroup> Groups { get; init; } = [];
    public double HoldingDays { get; init; } = UsageEvents.HoldingDays;
}

public sealed record UsageEventsSyncResult(List<UsageEvent> Events, int Fetched, int TotalAvailable, bool Truncated);

public static class UsageEvents
{
    public const string KindIncluded = "included";
    public const string KindFree = "free";
    public const string KindOnDemand = "on_demand";
    public const string KindOther = "other";
    public const string CategoryFirstParty = "first_party";
    public const string CategoryApi = "api";
    public const string CategoryGrokBot = "grok_bot";
    public const string ChannelSelfPay = "self_pay";
    public const string ChannelThirdParty = "third_party";
    public const double HoldingDays = 30;
    public const string WindowCycle = "cycle";
    public const string WindowValidity = "validity";
    public const string WindowFallback = "fallback";
    static readonly string[] ChannelOrder = [ChannelSelfPay, ChannelThirdParty, ""];
    public const string TzLabel = "北京时间";
    public const string CsvHeader = "日期(北京时间),用户,类型,模型,Token,费用,实付,云端Agent";
    public const double DefaultUsdCnyRate = 7.50;
    public const int HourlyChartWindowHours = 48;
    const long MsHour = 3_600_000;
    const long MsDay = 86_400_000;
    const long MsBeijingOffset = 8 * MsHour;
    static readonly TimeSpan DisplayOffset = TimeSpan.FromHours(8);

    static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    public static string KindLabel(string? kind) => (kind ?? "").Trim().ToLowerInvariant() switch
    {
        KindIncluded => "套餐内",
        KindFree => "免费",
        KindOnDemand => "按需",
        _ => "其他",
    };

    public static string ClassifyCategory(string? model) => UsageParser.UsageCategory(model);

    public static string CategoryLabel(string? category) => (category ?? "").Trim().ToLowerInvariant() switch
    {
        CategoryFirstParty => "First-party",
        CategoryGrokBot => "Grok Bot",
        _ => "API",
    };

    public static double ClampActualCny(double amount)
    {
        if (double.IsNaN(amount) || double.IsInfinity(amount) || amount < 0) return 0;
        return Math.Min(amount, 1_000_000);
    }

    public static (double planCny, double monthly, double rate, double actual, bool usesActual) ResolvePlanCny(CnySpendSettings spend)
    {
        var rate = ClampUsdCnyRate(spend.UsdCnyRate);
        var monthly = ResolveMonthlyPlanUsd(spend.MonthlyPlanUsd, spend.MembershipType);
        var actual = ClampActualCny(spend.ActualCny);
        return actual > 0 ? (actual, monthly, rate, actual, true) : (monthly * rate, monthly, rate, 0, false);
    }

    public static string ClassifyKind(string? kind, string? usageBasedCosts = null, bool isChargeable = false)
    {
        var blob = $"{kind} {usageBasedCosts}".Trim().ToLowerInvariant();
        if (blob.Contains("free")) return KindFree;
        if (blob.Contains("included")) return KindIncluded;
        if (blob.Contains("usage_based") || blob.Contains("usage-based") || blob.Contains("ondemand")
            || blob.Contains("on_demand") || blob.Contains("on-demand"))
            return KindOnDemand;
        return isChargeable ? KindOnDemand : KindIncluded;
    }

    public static double CostCents(UsageEvent ev)
    {
        if (ev.ChargedCents is { } charged) return Math.Max(0, charged);
        if (ev.TotalCents is { } total) return Math.Max(0, total);
        return 0;
    }

    public static string FormatCost(UsageEvent ev)
    {
        var cents = CostCents(ev);
        if (ev.Kind == KindFree) return "免费";
        if (ev.Kind == KindIncluded)
            return cents > 0 ? UsageParser.FormatUsdCents(cents) + " 套餐内" : "套餐内";
        return cents > 0 ? UsageParser.FormatUsdCents(cents) : "—";
    }

    public static double ClampUsdCnyRate(double rate)
    {
        if (double.IsNaN(rate) || double.IsInfinity(rate)) return DefaultUsdCnyRate;
        return Math.Clamp(rate, 0.01, 100);
    }

    public static double ClampMonthlyPlanUsd(double usd)
    {
        if (double.IsNaN(usd) || double.IsInfinity(usd) || usd < 0) return 0;
        return Math.Min(usd, 10_000);
    }

    public static double DefaultMonthlyPlanUsd(string? membership)
    {
        var key = (membership ?? "").Trim().ToLowerInvariant().Replace(" ", "");
        if (key.EndsWith("套餐", StringComparison.Ordinal)) key = key[..^2];
        return key switch
        {
            "pro" => 20,
            "pro+" or "pro_plus" or "proplus" => 60,
            "ultra" => 200,
            _ => 0,
        };
    }

    public static double ResolveMonthlyPlanUsd(double monthlyPlanUsd, string? membership = null)
    {
        var stored = ClampMonthlyPlanUsd(monthlyPlanUsd);
        return stored > 0 ? stored : DefaultMonthlyPlanUsd(membership);
    }

    public static bool IsPlanCovered(string? kind)
    {
        var key = (kind ?? "").Trim().ToLowerInvariant();
        return key is not KindOnDemand and not KindFree;
    }

    public static string SanitizeChannel(string? raw)
    {
        var key = (raw ?? "").Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "");
        if (key is "self_pay" or "self" or "selfpay" or "自费") return ChannelSelfPay;
        if (key is "third_party" or "third" or "thirdparty" or "第三方") return ChannelThirdParty;
        return "";
    }

    public static string ChannelLabel(string? channel) => SanitizeChannel(channel) switch
    {
        ChannelSelfPay => "自费",
        ChannelThirdParty => "第三方",
        _ => "未标",
    };

    public static string WindowLabel(string? source) => (source ?? "").Trim().ToLowerInvariant() switch
    {
        WindowCycle => "本周期",
        WindowValidity => "有效期",
        _ => "近30天",
    };

    public static double? UnitCny(double amount, double denom)
    {
        if (denom <= 1e-12) return null;
        return Math.Max(0, amount) / denom;
    }

    public static string FormatCnyUnit(double? amount, string suffix) =>
        amount is null ? "—" : FormatCny(amount) + suffix;

    public static (long startMs, long endMs, string source) ResolveCompareWindow(
        string accountKind = "",
        string tempStartAt = "",
        int tempValidDays = 0,
        int tempValidHours = 0,
        string billingCycleStart = "",
        string billingCycleEnd = "",
        long? nowMs = null)
    {
        var now = nowMs ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var kind = (accountKind ?? "").Trim().ToLowerInvariant().Replace("-", "_");
        if (kind is "temporary" or "temp" or "short")
        {
            var start = UsageParser.IsoToMs(tempStartAt);
            if (start is not null)
            {
                var end = TempEndMs(tempStartAt, tempValidDays, tempValidHours) ?? now;
                return (start.Value, Math.Min(end, now), WindowValidity);
            }
        }
        var cycleStart = UsageParser.IsoToMs(billingCycleStart);
        if (cycleStart is not null)
        {
            var end = UsageParser.IsoToMs(billingCycleEnd) ?? now;
            return (cycleStart.Value, Math.Min(end, now), WindowCycle);
        }
        return (now - 30 * MsDay, now, WindowFallback);
    }

    static long? TempEndMs(string startAt, int days, int hours)
    {
        var iso = AccountValidity.ComputeEndIso(startAt, days, hours);
        return UsageParser.IsoToMs(iso);
    }

    public static double CompareWindowDays(long startMs, long endMs)
    {
        var span = Math.Max(0, endMs - startMs);
        return Math.Max(span / (double)MsDay, 1.0 / 24.0);
    }

    public static AccountCompareInput CompareInputFromAccount(Account account, IEnumerable<UsageEvent> events, double monthlyPlanUsd, double usdCnyRate) =>
        new()
        {
            AccountId = account.Id,
            Label = account.Label,
            Channel = account.Channel,
            MembershipType = account.MembershipType,
            AccountKind = account.AccountKind,
            TempStartAt = account.TempStartAt,
            TempValidDays = account.TempValidDays,
            TempValidHours = account.TempValidHours,
            BillingCycleStart = account.BillingCycleStart,
            BillingCycleEnd = account.BillingCycleEnd,
            LastRemaining = account.LastRemaining,
            Events = events.ToList(),
            Spend = new CnySpendSettings(monthlyPlanUsd, usdCnyRate, account.MembershipType, account.ActualCny),
        };

    public static AccountCompareRow BuildAccountCompareRow(AccountCompareInput item, long? nowMs = null)
    {
        var (startMs, endMs, source) = ResolveCompareWindow(
            item.AccountKind, item.TempStartAt, item.TempValidDays, item.TempValidHours,
            item.BillingCycleStart, item.BillingCycleEnd, nowMs);
        var windowDays = CompareWindowDays(startMs, endMs);
        var windowEvents = item.Events.Where(ev => ev.TimestampMs >= startMs && ev.TimestampMs <= endMs).ToList();
        var spend = item.Spend ?? CnySpendSettings.Default;
        var resolved = ResolvePlanCny(spend);
        var dailyHolding = resolved.planCny > 0 ? resolved.planCny / HoldingDays : 0;
        var windowPlan = dailyHolding * windowDays;
        var included = windowEvents.Where(ev => IsPlanCovered(ev.Kind)).ToList();
        var includedCostSum = included.Sum(CostCents);
        var includedCount = included.Count;
        var cats = new Dictionary<string, (int count, long tokens, double cny)>(StringComparer.Ordinal)
        {
            [CategoryFirstParty] = (0, 0, 0),
            [CategoryApi] = (0, 0, 0),
            [CategoryGrokBot] = (0, 0, 0),
        };
        var onDemandCny = 0.0;
        var totalCny = 0.0;
        var totalTokens = 0L;
        foreach (var ev in windowEvents)
        {
            var amount = AllocateEventCny(ev, includedCostSum, includedCount, windowPlan, resolved.rate);
            totalCny += amount;
            totalTokens += ev.Tokens;
            if (ev.Kind == KindOnDemand) onDemandCny += amount;
            var bucket = ClassifyCategory(ev.Model);
            var row = cats.GetValueOrDefault(bucket);
            cats[bucket] = (row.count + 1, row.tokens + ev.Tokens, row.cny + amount);
        }
        AccountCompareCategory Cat(string name)
        {
            var row = cats.GetValueOrDefault(name);
            return new AccountCompareCategory { Category = name, Count = row.count, Tokens = row.tokens, Cny = row.cny };
        }
        return new AccountCompareRow
        {
            AccountId = item.AccountId,
            Label = string.IsNullOrWhiteSpace(item.Label) ? item.AccountId : item.Label,
            Channel = SanitizeChannel(item.Channel),
            MembershipType = item.MembershipType,
            WindowSource = source,
            WindowStartMs = startMs,
            WindowEndMs = endMs,
            WindowDays = windowDays,
            PlanCny = resolved.planCny,
            DailyHoldingCny = dailyHolding,
            WindowPlanCny = windowPlan,
            OnDemandCny = onDemandCny,
            TotalCny = totalCny,
            EventCount = windowEvents.Count,
            TotalTokens = totalTokens,
            FirstParty = Cat(CategoryFirstParty),
            Api = Cat(CategoryApi),
            GrokBot = Cat(CategoryGrokBot),
            LastRemaining = item.LastRemaining,
            UsesActualCny = resolved.usesActual,
        };
    }

    public static AccountCompareReport BuildAccountCompareReport(IEnumerable<AccountCompareInput> items, long? nowMs = null)
    {
        var rows = items.Select(item => BuildAccountCompareRow(item, nowMs)).ToList();
        var grouped = ChannelOrder.ToDictionary(k => k, _ => new List<AccountCompareRow>(), StringComparer.Ordinal);
        foreach (var row in rows)
        {
            if (!grouped.TryGetValue(row.Channel, out var bucket))
            {
                bucket = [];
                grouped[row.Channel] = bucket;
            }
            bucket.Add(row);
        }
        var groups = new List<AccountCompareGroup>();
        foreach (var channel in ChannelOrder)
        {
            if (!grouped.TryGetValue(channel, out var bucket) || bucket.Count == 0) continue;
            groups.Add(SumCompareGroup(channel, bucket));
        }
        return new AccountCompareReport { Rows = rows, Groups = groups, HoldingDays = HoldingDays };
    }

    static AccountCompareGroup SumCompareGroup(string channel, List<AccountCompareRow> rows)
    {
        static AccountCompareCategory Add(string name, IEnumerable<AccountCompareCategory> parts) =>
            new()
            {
                Category = name,
                Count = parts.Sum(p => p.Count),
                Tokens = parts.Sum(p => p.Tokens),
                Cny = parts.Sum(p => p.Cny),
            };
        return new AccountCompareGroup
        {
            Channel = channel,
            Rows = rows,
            DailyHoldingCny = rows.Sum(r => r.DailyHoldingCny),
            TotalCny = rows.Sum(r => r.TotalCny),
            EventCount = rows.Sum(r => r.EventCount),
            TotalTokens = rows.Sum(r => r.TotalTokens),
            FirstParty = Add(CategoryFirstParty, rows.Select(r => r.FirstParty)),
            Api = Add(CategoryApi, rows.Select(r => r.Api)),
            GrokBot = Add(CategoryGrokBot, rows.Select(r => r.GrokBot)),
        };
    }

    public static string AccountCompareToCsv(AccountCompareReport report)
    {
        var sb = new StringBuilder();
        sb.AppendLine("账号,渠道,套餐,窗口,窗口天数,日均持有,窗口实付,请求,Token,¥/百万Token,¥/次,First-party次数,First-party Token,First-party实付,First-party ¥/百万,First-party ¥/次,API次数,API Token,API实付,API ¥/百万,API ¥/次,Grok Bot次数,Grok Bot Token,Grok Bot实付,Grok Bot ¥/百万,Grok Bot ¥/次");
        foreach (var row in report.Rows)
            sb.AppendLine(CompareCsvCells(row.Label, row.ChannelLabel, row.MembershipType, row.WindowLabel, row.WindowDays, row.DailyHoldingCny, row.TotalCny, row.EventCount, row.TotalTokens, row.CnyPerMillion, row.CnyPerRequest, row.FirstParty, row.Api, row.GrokBot));
        foreach (var group in report.Groups)
            sb.AppendLine(CompareCsvCells(group.ChannelLabel + "合计", group.ChannelLabel, "", "", 0, group.DailyHoldingCny, group.TotalCny, group.EventCount, group.TotalTokens, group.CnyPerMillion, group.CnyPerRequest, group.FirstParty, group.Api, group.GrokBot));
        return sb.ToString();
    }

    static string CompareCsvCells(
        string name, string channel, string membership, string window, double days,
        double dailyHolding, double totalCny, int eventCount, long totalTokens,
        double? perMillion, double? perRequest,
        AccountCompareCategory firstParty, AccountCompareCategory api, AccountCompareCategory grokBot)
    {
        static string[] CatCells(AccountCompareCategory cat) =>
        [
            cat.Count.ToString(CultureInfo.InvariantCulture),
            cat.Tokens.ToString(CultureInfo.InvariantCulture),
            cat.Cny.ToString("0.0000", CultureInfo.InvariantCulture),
            cat.CnyPerMillion is { } m ? m.ToString("0.0000", CultureInfo.InvariantCulture) : "",
            cat.CnyPerRequest is { } r ? r.ToString("0.0000", CultureInfo.InvariantCulture) : "",
        ];
        var cols = new List<string>
        {
            EscapeCsv(name),
            EscapeCsv(channel),
            EscapeCsv(membership),
            EscapeCsv(window),
            days > 0 ? days.ToString("0.00", CultureInfo.InvariantCulture) : "",
            dailyHolding.ToString("0.0000", CultureInfo.InvariantCulture),
            totalCny.ToString("0.0000", CultureInfo.InvariantCulture),
            eventCount.ToString(CultureInfo.InvariantCulture),
            totalTokens.ToString(CultureInfo.InvariantCulture),
            perMillion is { } pm ? pm.ToString("0.0000", CultureInfo.InvariantCulture) : "",
            perRequest is { } pr ? pr.ToString("0.0000", CultureInfo.InvariantCulture) : "",
        };
        cols.AddRange(CatCells(firstParty));
        cols.AddRange(CatCells(api));
        cols.AddRange(CatCells(grokBot));
        return string.Join(",", cols);
    }

    public static string FormatCny(double? yuan)
    {
        if (yuan is null) return "—";
        var n = Math.Max(0, yuan.Value);
        return "¥" + n.ToString("0.00", CultureInfo.InvariantCulture);
    }

    public static string FormatEventCny(UsageEvent ev, double? amount = null)
    {
        if (ev.Kind == KindFree) return "—";
        return FormatCny(amount ?? ev.AllocatedCny);
    }

    public static double AllocateEventCny(UsageEvent ev, double includedCostSum, int includedCount, double planCny, double rate)
    {
        if (ev.Kind == KindFree) return 0;
        if (ev.Kind == KindOnDemand) return CostCents(ev) / 100.0 * rate;
        var cents = CostCents(ev);
        if (includedCostSum > 1e-9) return planCny * (cents / includedCostSum);
        if (includedCount > 0 && planCny > 0) return planCny / includedCount;
        return 0;
    }

    static (Dictionary<string, double> byId, double planCny, double onDemandCny, double monthly, double rate, double actual, bool usesActual) CnyById(
        IList<UsageEvent> events, CnySpendSettings? spend)
    {
        if (spend is null) return ([], 0, 0, 0, 0, 0, false);
        var resolved = ResolvePlanCny(spend.Value);
        var rate = resolved.rate;
        var monthly = resolved.monthly;
        var included = events.Where(ev => IsPlanCovered(ev.Kind)).ToList();
        var includedCostSum = included.Sum(CostCents);
        var includedCount = included.Count;
        var planCny = resolved.planCny;
        var byId = new Dictionary<string, double>(StringComparer.Ordinal);
        var onDemandCny = 0.0;
        for (var i = 0; i < events.Count; i++)
        {
            var ev = events[i];
            var amount = AllocateEventCny(ev, includedCostSum, includedCount, planCny, rate);
            var key = ev.Id.Length > 0 ? ev.Id : $"#{i}";
            byId[key] = amount;
            if (ev.Kind == KindOnDemand) onDemandCny += amount;
        }
        return (byId, planCny, onDemandCny, monthly, rate, resolved.actual, resolved.usesActual);
    }

    public static string FormatTime(long timestampMs)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds(Math.Max(0, timestampMs)).ToOffset(DisplayOffset);
        return dt.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
    }

    public static string EventDate(long timestampMs)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds(Math.Max(0, timestampMs)).ToOffset(DisplayOffset);
        return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }

    public static string EventHour(long timestampMs)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds(FloorHourMs(timestampMs)).ToOffset(DisplayOffset);
        return dt.ToString("yyyy-MM-dd HH:00", CultureInfo.InvariantCulture);
    }

    public static string ChartModelLabel(string? name)
    {
        var text = (name ?? "").Trim();
        return text.StartsWith("cursor-", StringComparison.Ordinal) ? text[7..] : text;
    }

    public static UsageChartSeries BuildChart(
        IEnumerable<UsageEvent> events,
        bool hourly,
        IEnumerable<string>? hiddenModels = null,
        int hourlyWindowHours = HourlyChartWindowHours)
    {
        var selected = events as IList<UsageEvent> ?? events.ToList();
        var models = ChartModels(selected);
        var hidden = hiddenModels is null ? new HashSet<string>(StringComparer.Ordinal) : new HashSet<string>(hiddenModels, StringComparer.Ordinal);
        var visible = models.Where(n => !hidden.Contains(n)).ToList();
        var visibleSet = visible.ToHashSet(StringComparer.Ordinal);
        if (selected.Count == 0)
            return new UsageChartSeries { Hourly = hourly, Caption = ChartCaption(hourly, Array.Empty<string>()), Models = models, Buckets = [] };

        List<string> keys;
        Func<long, string> keyOf;
        if (hourly)
        {
            var lastMs = FloorHourMs(selected.Max(ev => ev.TimestampMs));
            var firstMs = FloorHourMs(selected.Min(ev => ev.TimestampMs));
            var window = Math.Max(1, hourlyWindowHours);
            var span = (lastMs - firstMs) / MsHour + 1;
            if (span > window) firstMs = lastMs - (window - 1) * MsHour;
            var count = (int)((lastMs - firstMs) / MsHour + 1);
            keys = Enumerable.Range(0, count).Select(i => EventHour(firstMs + i * MsHour)).ToList();
            keyOf = EventHour;
        }
        else
        {
            var lastMs = FloorDayMs(selected.Max(ev => ev.TimestampMs));
            var firstMs = FloorDayMs(selected.Min(ev => ev.TimestampMs));
            var count = (int)((lastMs - firstMs) / MsDay + 1);
            keys = Enumerable.Range(0, count).Select(i => EventDate(firstMs + i * MsDay)).ToList();
            keyOf = EventDate;
        }

        var cells = new Dictionary<(string key, string model), (long tokens, double cents, int count)>();
        foreach (var ev in selected)
        {
            var key = keyOf(ev.TimestampMs);
            if (string.CompareOrdinal(key, keys[0]) < 0 || string.CompareOrdinal(key, keys[^1]) > 0) continue;
            var name = string.IsNullOrEmpty(ev.Model) ? "—" : ev.Model;
            if (!visibleSet.Contains(name)) continue;
            cells.TryGetValue((key, name), out var cell);
            cells[(key, name)] = (cell.tokens + ev.Tokens, cell.cents + CostCents(ev), cell.count + 1);
        }

        var multiDay = hourly && keys[0][..10] != keys[^1][..10];
        var buckets = new List<ChartBucket>(keys.Count);
        foreach (var key in keys)
        {
            var slices = new List<ChartSlice>();
            long tokens = 0;
            var cents = 0.0;
            var count = 0;
            foreach (var name in visible)
            {
                if (!cells.TryGetValue((key, name), out var cell)) continue;
                if (cell.tokens <= 0 && cell.cents <= 0 && cell.count <= 0) continue;
                slices.Add(new ChartSlice(name, cell.tokens, cell.cents, cell.count));
                tokens += cell.tokens;
                cents += cell.cents;
                count += cell.count;
            }
            buckets.Add(new ChartBucket(key, BucketLabel(key, hourly, multiDay), tokens, cents, count, slices));
        }
        return new UsageChartSeries
        {
            Hourly = hourly,
            Caption = ChartCaption(hourly, keys),
            Models = models,
            Buckets = buckets,
        };
    }

    static long FloorHourMs(long timestampMs) => Math.Max(0, timestampMs) / MsHour * MsHour;
    static long FloorDayMs(long timestampMs)
    {
        var shifted = Math.Max(0, timestampMs) + MsBeijingOffset;
        return shifted / MsDay * MsDay - MsBeijingOffset;
    }

    public static List<string> ChartModels(IEnumerable<UsageEvent> events)
    {
        var totals = new Dictionary<string, (long tokens, double cents, int count)>(StringComparer.Ordinal);
        foreach (var ev in events)
        {
            var name = string.IsNullOrEmpty(ev.Model) ? "—" : ev.Model;
            totals.TryGetValue(name, out var row);
            totals[name] = (row.tokens + ev.Tokens, row.cents + CostCents(ev), row.count + 1);
        }
        return totals
            .OrderByDescending(kv => kv.Value.tokens)
            .ThenByDescending(kv => kv.Value.cents)
            .ThenByDescending(kv => kv.Value.count)
            .ThenBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => kv.Key)
            .ToList();
    }

    static string BucketLabel(string key, bool hourly, bool multiDay)
    {
        if (!hourly) return key.Length >= 10 ? key[5..] : key;
        var hour = key.Length >= 13 ? key[11..13] : key;
        return multiDay ? $"{key[5..10]} {hour}" : hour;
    }

    static string ChartCaption(bool hourly, IReadOnlyList<string> keys)
    {
        var kind = hourly ? "按小时 Token" : "按日 Token";
        if (keys.Count == 0) return $"{kind}（{TzLabel}）";
        var first = keys[0];
        var last = keys[^1];
        if (first == last) return $"{kind}（{TzLabel} · {first}）";
        if (hourly && first[..10] == last[..10])
            return $"{kind}（{TzLabel} · {first[..10]} {first[11..]}–{last[11..]}）";
        return $"{kind}（{TzLabel} · {first} 至 {last}）";
    }

    public static (List<UsageEvent> events, int totalCount) ParsePage(JsonBag payload)
    {
        var rows = payload["usageEventsDisplay"].Array;
        if (!rows.Any()) rows = payload["usageEvents"].Array;
        var events = rows.Select(ParseEvent).Where(e => e is not null).Cast<UsageEvent>().ToList();
        var total = payload["totalUsageEventsCount"].AsInt();
        if (total is null)
        {
            var paging = payload["pagination"].IsObject ? payload["pagination"] : JsonBag.Null;
            total = paging["numEvents"].AsInt() ?? paging["totalNumEvents"].AsInt() ?? paging["total"].AsInt();
        }
        if (total is null || total < events.Count) total = events.Count;
        return (events, total.Value);
    }

    public static UsageEvent? ParseEvent(JsonBag item)
    {
        if (!item.IsObject) return null;
        var ts = item["timestamp"].AsLong() ?? item["timestampMs"].AsLong() ?? item["createdAt"].AsLong();
        if (ts is null or <= 0) return null;
        var tokenUsage = item["tokenUsage"].IsObject ? item["tokenUsage"] : JsonBag.Null;
        var model = DisplayModel(item["model"].AsString() ?? item["modelIntent"].AsString() ?? "");
        var kindRaw = item["kind"].AsString() ?? item["type"].AsString() ?? "";
        var costsRaw = item["usageBasedCosts"].AsString() ?? item["cost"].AsString() ?? "";
        var isChargeable = item["isChargeable"].AsBool();
        var kind = ClassifyKind(kindRaw, costsRaw, isChargeable);
        var input = Math.Max(0, tokenUsage["inputTokens"].AsInt() ?? item["inputTokens"].AsInt() ?? 0);
        var output = Math.Max(0, tokenUsage["outputTokens"].AsInt() ?? item["outputTokens"].AsInt() ?? 0);
        var cacheWrite = Math.Max(0, tokenUsage["cacheWriteTokens"].AsInt() ?? item["cacheWriteTokens"].AsInt() ?? 0);
        var cacheRead = Math.Max(0, tokenUsage["cacheReadTokens"].AsInt() ?? item["cacheReadTokens"].AsInt() ?? 0);
        var tokens = SumTokens(tokenUsage);
        if (tokens <= 0) tokens = SumTokens(item);
        if (tokens <= 0) tokens = input + output + cacheWrite + cacheRead;
        var charged = item["chargedCents"].AsDouble() ?? ParseMoneyCents(item["usageBasedCosts"]);
        var totalCents = tokenUsage["totalCents"].AsDouble() ?? item["totalCents"].AsDouble();
        var email = (item["email"].AsString() ?? item["userEmail"].AsString() ?? item["user"].AsString()
            ?? (item["user"].IsObject ? item["user"]["email"].AsString() : null) ?? "").Trim();
        var owning = (item["owningUser"].AsString() ?? item["userId"].AsString() ?? "").Trim();
        var givenId = (item["id"].AsString() ?? item["eventId"].AsString() ?? "").Trim();
        var id = givenId.Length > 0 ? givenId : string.Join("|", ts.Value, owning, model, input, output, cacheWrite, cacheRead, kindRaw);
        return new UsageEvent
        {
            Id = id,
            TimestampMs = ts.Value,
            Model = model,
            Kind = kind,
            UserEmail = email,
            OwningUser = owning,
            Tokens = Math.Max(0, tokens),
            InputTokens = input,
            OutputTokens = output,
            CacheWriteTokens = cacheWrite,
            CacheReadTokens = cacheRead,
            ChargedCents = charged,
            TotalCents = totalCents,
            IsHeadless = item["isHeadless"].AsBool() || item["isCloudAgent"].AsBool(),
            IsChargeable = isChargeable,
        };
    }

    public static double? ParseMoneyCents(JsonBag value)
    {
        if (value.AsDouble() is { } n && value.AsString() is null) return n;
        var text = (value.AsString() ?? "").Trim();
        if (text.Length == 0) return null;
        var lower = text.ToLowerInvariant();
        if (lower is "included" or "free" or "n/a" or "—" or "-" or "none") return null;
        if (!lower.Contains("us$") && !text.Contains('$')) return null;
        var cleaned = text.Replace("US$", "", StringComparison.OrdinalIgnoreCase)
            .Replace("$", "")
            .Replace(",", "")
            .Replace("Included", "", StringComparison.OrdinalIgnoreCase)
            .Replace("Free", "", StringComparison.OrdinalIgnoreCase)
            .Trim();
        return double.TryParse(cleaned, NumberStyles.Float, CultureInfo.InvariantCulture, out var dollars)
            ? dollars * 100.0 : null;
    }

    public static UsageReport BuildReport(IEnumerable<UsageEvent> events, UsageReportFilter? filter = null, CnySpendSettings? spend = null)
    {
        filter ??= new UsageReportFilter();
        var kind = (filter.Kind ?? "").Trim().ToLowerInvariant();
        var category = (filter.Category ?? "").Trim().ToLowerInvariant();
        var model = (filter.Model ?? "").Trim();
        var owning = (filter.OwningUser ?? "").Trim();
        var source = events as IList<UsageEvent> ?? events.ToList();
        var (cnyById, planCny, onDemandCny, monthly, rate, actual, usesActual) = CnyById(source, spend);
        var selected = new List<UsageEvent>();
        for (var i = 0; i < source.Count; i++)
        {
            var ev = source[i];
            if (kind.Length > 0 && ev.Kind != kind) continue;
            if (category.Length > 0 && ClassifyCategory(ev.Model) != category) continue;
            if (model.Length > 0 && ev.Model != model) continue;
            if (filter.Headless is { } h && ev.IsHeadless != h) continue;
            if (owning.Length > 0 && ev.OwningUser != owning) continue;
            var key = ev.Id.Length > 0 ? ev.Id : $"#{i}";
            ev.AllocatedCny = cnyById.TryGetValue(key, out var cny) ? cny : 0;
            selected.Add(ev);
        }
        selected = selected.OrderByDescending(ev => ev.TimestampMs).ToList();

        var dailyMap = new Dictionary<string, (long tokens, double cents, int count, double cny)>(StringComparer.Ordinal);
        var modelMap = new Dictionary<string, (long tokens, double cents, int count, int headless, double cny)>(StringComparer.Ordinal);
        var included = 0; var free = 0; var onDemand = 0; var other = 0; var headless = 0;
        var firstParty = 0; var api = 0; var grokBot = 0;
        long totalTokens = 0;
        double totalCents = 0;
        double totalCny = 0;
        var hasCost = false;
        foreach (var ev in selected)
        {
            var cents = CostCents(ev);
            totalTokens += ev.Tokens;
            totalCents += cents;
            totalCny += ev.AllocatedCny;
            if (cents > 0) hasCost = true;
            if (ev.Kind == KindIncluded) included++;
            else if (ev.Kind == KindFree) free++;
            else if (ev.Kind == KindOnDemand) onDemand++;
            else other++;
            switch (ClassifyCategory(ev.Model))
            {
                case CategoryGrokBot: grokBot++; break;
                case CategoryFirstParty: firstParty++; break;
                default: api++; break;
            }
            if (ev.IsHeadless) headless++;
            var day = EventDate(ev.TimestampMs);
            dailyMap.TryGetValue(day, out var d);
            dailyMap[day] = (d.tokens + ev.Tokens, d.cents + cents, d.count + 1, d.cny + ev.AllocatedCny);
            var name = string.IsNullOrEmpty(ev.Model) ? "—" : ev.Model;
            modelMap.TryGetValue(name, out var m);
            modelMap[name] = (m.tokens + ev.Tokens, m.cents + cents, m.count + 1, m.headless + (ev.IsHeadless ? 1 : 0), m.cny + ev.AllocatedCny);
        }
        return new UsageReport
        {
            EventCount = selected.Count,
            TotalTokens = totalTokens,
            TotalCents = totalCents,
            HasCost = hasCost,
            IncludedCount = included,
            FreeCount = free,
            OnDemandCount = onDemand,
            OtherCount = other,
            HeadlessCount = headless,
            FirstPartyCount = firstParty,
            ApiCount = api,
            GrokBotCount = grokBot,
            ActualCny = actual,
            UsesActualCny = usesActual,
            Daily = dailyMap.OrderBy(kv => kv.Key).Select(kv => new DailyUsageRow(kv.Key, kv.Value.tokens, kv.Value.cents, kv.Value.count, kv.Value.cny)).ToList(),
            Models = modelMap.Select(kv => new ModelUsageRow(kv.Key, kv.Value.tokens, kv.Value.cents, kv.Value.count, kv.Value.headless, kv.Value.cny))
                .OrderByDescending(m => m.Tokens).ThenByDescending(m => m.Cents).ThenByDescending(m => m.Count).ToList(),
            Events = selected,
            TotalCny = totalCny,
            PlanCny = planCny,
            OnDemandCny = onDemandCny,
            UsdCnyRate = rate,
            MonthlyPlanUsd = monthly,
        };
    }

    public static string ToCsv(IEnumerable<UsageEvent> events, CnySpendSettings? spend = null, IEnumerable<UsageEvent>? allocationBase = null)
    {
        var rows = events as IList<UsageEvent> ?? events.ToList();
        Dictionary<string, double> cnyById = [];
        if (spend is not null)
        {
            var baseEvents = allocationBase as IList<UsageEvent> ?? allocationBase?.ToList() ?? rows;
            cnyById = CnyById(baseEvents, spend).byId;
        }
        var sb = new StringBuilder();
        sb.Append('\uFEFF');
        sb.AppendLine(CsvHeader);
        for (var i = 0; i < rows.Count; i++)
        {
            var ev = rows[i];
            string cnyText;
            if (spend is not null)
            {
                var key = ev.Id.Length > 0 ? ev.Id : $"#{i}";
                cnyText = FormatEventCny(ev, cnyById.GetValueOrDefault(key));
            }
            else if (ev.AllocatedCny > 0)
                cnyText = FormatEventCny(ev);
            else
                cnyText = "—";
            sb.Append(EscapeCsv(FormatTime(ev.TimestampMs))).Append(',');
            sb.Append(EscapeCsv(ev.UserEmail)).Append(',');
            sb.Append(EscapeCsv(KindLabel(ev.Kind))).Append(',');
            sb.Append(EscapeCsv(ev.Model)).Append(',');
            sb.Append(EscapeCsv(ev.Tokens.ToString(CultureInfo.InvariantCulture))).Append(',');
            sb.Append(EscapeCsv(FormatCost(ev))).Append(',');
            sb.Append(EscapeCsv(cnyText)).Append(',');
            sb.Append(EscapeCsv(ev.IsHeadless ? "是" : "否"));
            sb.AppendLine();
        }
        return sb.ToString();
    }

    public static UsageEvent? FromDict(JsonBag raw)
    {
        long? ts = raw["timestamp_ms"].AsLong() ?? raw["timestampMs"].AsLong();
        if (ts is null)
        {
            var stamp = raw["timestamp"].AsString();
            if (!string.IsNullOrEmpty(stamp) && stamp.Contains('T'))
                ts = UsageParser.IsoToMs(stamp);
            else
                ts = raw["timestamp"].AsLong();
        }
        if (ts is null) return null;
        return new UsageEvent
        {
            Id = raw["id"].AsString() ?? "",
            TimestampMs = ts.Value,
            Model = raw["model"].AsString() ?? "",
            Kind = raw["kind"].AsString() ?? KindOther,
            UserEmail = raw["user_email"].AsString() ?? "",
            OwningUser = raw["owning_user"].AsString() ?? "",
            Tokens = Math.Max(0, raw["tokens"].AsInt() ?? 0),
            InputTokens = Math.Max(0, raw["input_tokens"].AsInt() ?? 0),
            OutputTokens = Math.Max(0, raw["output_tokens"].AsInt() ?? 0),
            CacheWriteTokens = Math.Max(0, raw["cache_write_tokens"].AsInt() ?? 0),
            CacheReadTokens = Math.Max(0, raw["cache_read_tokens"].AsInt() ?? 0),
            ChargedCents = raw["charged_cents"].AsDouble() ?? raw["chargedCents"].AsDouble(),
            TotalCents = raw["total_cents"].AsDouble() ?? raw["totalCents"].AsDouble(),
            IsHeadless = raw["is_headless"].AsBool(),
            IsChargeable = raw["is_chargeable"].AsBool(),
        };
    }

    public static List<UsageEvent> Merge(IEnumerable<UsageEvent> existing, IEnumerable<UsageEvent> incoming)
    {
        var byId = new Dictionary<string, UsageEvent>(StringComparer.Ordinal);
        foreach (var ev in existing)
            if (ev.Id.Length > 0) byId[ev.Id] = ev;
        foreach (var ev in incoming)
            if (ev.Id.Length > 0) byId[ev.Id] = ev;
        return byId.Values.OrderByDescending(e => e.TimestampMs).ToList();
    }

    public static List<UsageEvent> Prune(IEnumerable<UsageEvent> events, long minTimestampMs) =>
        events.Where(e => e.TimestampMs >= minTimestampMs).OrderByDescending(e => e.TimestampMs).ToList();

    public static List<UsageEvent> Load(string accountId, bool teamScope, string? directory = null)
    {
        var path = AppPaths.UsageEventsPath(accountId, teamScope, directory);
        var events = new List<UsageEvent>();
        if (!File.Exists(path)) return events;
        foreach (var line in File.ReadAllLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                var ev = FromDict(JsonBag.Parse(line));
                if (ev is not null) events.Add(ev);
            }
            catch { }
        }
        return Merge(events, []);
    }

    public static void Save(IEnumerable<UsageEvent> events, string accountId, bool teamScope, string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        Directory.CreateDirectory(dir);
        var path = AppPaths.UsageEventsPath(accountId, teamScope, dir);
        var lines = events.Select(ev => JsonSerializer.Serialize(ev, JsonOpts));
        File.WriteAllText(path, string.Join("\n", lines) + (events.Any() ? "\n" : ""));
    }

    public static async Task<UsageEventsSyncResult> SyncAsync(
        CursorClient client,
        string token,
        string accountId,
        UsageSnapshot? usage,
        bool teamScope,
        string? directory = null,
        CancellationToken ct = default)
    {
        var existing = Load(accountId, teamScope, directory);
        var nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var cycleStart = UsageParser.IsoToMs(usage?.BillingCycleStart) ?? nowMs - 30L * 86400 * 1000;
        var cycleEnd = UsageParser.IsoToMs(usage?.BillingCycleEnd) ?? nowMs;
        if (cycleEnd > nowMs) cycleEnd = nowMs;
        var watermark = existing.Count > 0 ? existing.Max(e => e.TimestampMs) : 0L;
        var startMs = cycleStart;
        long? stopAt = null;
        if (watermark > 0)
        {
            startMs = Math.Max(cycleStart, watermark - 60_000);
            stopAt = watermark;
        }
        var teamId = usage is null ? -1 : UsageParser.TeamId(usage.Raw);
        int? team = teamId > 0 ? teamId : null;
        int? userId = null;
        if (!teamScope)
        {
            var uid = usage is null ? -1 : UsageParser.UserId(usage.Raw);
            if (uid <= 0)
            {
                uid = existing
                    .Select(e => int.TryParse(e.OwningUser, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : 0)
                    .Where(n => n > 0)
                    .GroupBy(n => n)
                    .OrderByDescending(g => g.Count())
                    .Select(g => g.Key)
                    .FirstOrDefault();
            }
            if (uid > 0) userId = uid;
            else if (teamId > 0)
            {
                // Team feed without userId is the whole org; do not pollute the personal cache.
                return new UsageEventsSyncResult(existing, 0, existing.Count, false);
            }
        }
        var fetched = await client.FetchUsageEvents(token, startMs, cycleEnd, team, teamScope ? null : userId, stopAt, ct: ct);
        var merged = Merge(existing, fetched.events);
        if (!teamScope && userId is > 0)
        {
            var uidText = userId.Value.ToString(CultureInfo.InvariantCulture);
            merged = merged.Where(e => e.OwningUser.Length == 0 || e.OwningUser == uidText).ToList();
        }
        var minTs = Math.Min(cycleStart, nowMs - 120L * 86400 * 1000);
        var pruned = Prune(merged, minTs);
        Save(pruned, accountId, teamScope, directory);
        return new UsageEventsSyncResult(pruned, fetched.events.Count, fetched.totalCount, fetched.truncated);
    }

    static int SumTokens(JsonBag item)
    {
        string[] keys = ["inputTokens", "outputTokens", "cacheWriteTokens", "cacheReadTokens", "totalInputTokens", "totalOutputTokens", "totalCacheWriteTokens", "totalCacheReadTokens"];
        var total = 0;
        var found = false;
        foreach (var key in keys)
        {
            if (item[key].AsInt() is { } n)
            {
                found = true;
                total += Math.Max(0, n);
            }
        }
        if (found) return total;
        return item["totalTokens"].AsInt() is { } t ? Math.Max(0, t) : 0;
    }

    static string DisplayModel(string raw)
    {
        var name = raw.Trim();
        return name is "" ? "" : name is "default" ? "auto" : name;
    }

    static string EscapeCsv(string value)
    {
        if (value.IndexOfAny([',', '"', '\n', '\r']) < 0) return value;
        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }
}
