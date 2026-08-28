using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CursorTokenCore;

public record ModelTokenUsage(string Name, int Tokens, double Cents, int Tier, double? UsagePercent = null)
{
    public bool IsCursorModel => Tier == UsageParser.CursorModelTier;
}

public sealed class UsageSnapshot
{
    public double UsedPercent { get; set; }
    public double RemainingPercent { get; set; }
    public double? AutoPercentUsed { get; set; }
    public double? ApiPercentUsed { get; set; }
    public double? TotalPercentUsed { get; set; }
    public string MembershipType { get; set; } = "";
    public string? BillingCycleStart { get; set; }
    public string? BillingCycleEnd { get; set; }
    public int? DaysRemaining { get; set; }
    public double? DaysElapsed { get; set; }
    public double? EstimatedUsableDays { get; set; }
    public JsonBag Raw { get; set; } = JsonBag.Null;
    public int? TotalTokens { get; set; }
    public List<ModelTokenUsage> ModelUsages { get; set; } = [];
    public string BillingMode { get; set; } = "percent";
    public double? UsedCents { get; set; }
    public double? LimitCents { get; set; }
    public double? RemainingCents { get; set; }
    public double? OnDemandUsedCents { get; set; }
    public double? OnDemandLimitCents { get; set; }
    public double? PooledUsedCents { get; set; }
    public double? PooledLimitCents { get; set; }
    public string LimitType { get; set; } = "";
    public bool IsUnlimited { get; set; }
    public bool IsTeamAccount => UsageParser.IsTeamMembership(MembershipType, LimitType);
    public bool ShowsAmount => UsedCents is not null && LimitCents is > 0 && (BillingMode == "amount" || IsTeamAccount);
}

public static class UsageParser
{
    public const string CursorBase = "https://cursor.com";
    public const string UsageUrl = "https://cursor.com/dashboard/usage";
    public const string BillingUrl = "https://cursor.com/dashboard/billing";
    public const int CursorModelTier = 2;
    public static readonly string[] UsageEndpoints = ["/api/usage-summary", "/api/dashboard/usage-summary"];
    public const string AggregatedEndpoint = "/api/dashboard/get-aggregated-usage-events";
    public const string FilteredEndpoint = "/api/dashboard/get-filtered-usage-events";
    public const int UsageEventsPageSize = 100;
    public const int UsageEventsMaxPages = 50;

    static readonly HashSet<string> TeamMemberships = ["enterprise", "enterprise_trial", "team", "teams", "business"];
    static readonly Dictionary<string, string> MembershipLabels = new(StringComparer.OrdinalIgnoreCase)
    {
        ["pro"] = "Pro", ["pro_plus"] = "Pro+", ["pro+"] = "Pro+", ["ultra"] = "Ultra",
        ["free"] = "Free", ["hobby"] = "Hobby", ["enterprise"] = "Enterprise",
        ["enterprise_trial"] = "Enterprise", ["team"] = "Team", ["teams"] = "Team",
        ["business"] = "Business", ["unpaid"] = "Free",
    };

    public static string FormatMembershipType(string? raw)
    {
        var key = (raw ?? "").Trim();
        if (key.Length == 0) return "未知";
        return MembershipLabels.TryGetValue(key, out var label) ? label : key;
    }

    public static bool IsTeamMembership(string? membership, string? limitType = null)
    {
        if ((limitType ?? "").Trim().Equals("team", StringComparison.OrdinalIgnoreCase)) return true;
        return TeamMemberships.Contains((membership ?? "").Trim().ToLowerInvariant());
    }

    public static string DashboardUrl(UsageSnapshot? usage = null, string membership = "", string limitType = "")
    {
        if (usage is not null) { membership = usage.MembershipType; limitType = usage.LimitType; }
        return IsTeamMembership(membership, limitType) ? UsageUrl : BillingUrl;
    }

    public static string DashboardMenuLabel(UsageSnapshot? usage = null, string membership = "", string limitType = "")
    {
        if (usage is not null) { membership = usage.MembershipType; limitType = usage.LimitType; }
        return IsTeamMembership(membership, limitType) ? "打开用量" : "打开用量账单";
    }

    public static string DashboardButtonLabel(UsageSnapshot? usage = null, string membership = "", string limitType = "")
    {
        if (usage is not null) { membership = usage.MembershipType; limitType = usage.LimitType; }
        return IsTeamMembership(membership, limitType) ? "用量" : "账单";
    }

    public static string DashboardLinkLabel(UsageSnapshot? usage) =>
        usage?.IsTeamAccount == true ? "查看用量 →" : "查看用量账单 →";

    public static string FormatUsdCents(double? cents)
    {
        if (cents is null) return "—";
        var dollars = cents.Value / 100.0;
        if (dollars < 0) dollars = 0;
        if (Math.Abs(dollars - Math.Round(dollars)) < 0.005) return "$" + ((int)Math.Round(dollars)).ToString(CultureInfo.InvariantCulture);
        return "$" + dollars.ToString("0.00", CultureInfo.InvariantCulture);
    }

    public static string FormatSpendRange(double? used, double? limit) => $"{FormatUsdCents(used)} / {FormatUsdCents(limit)}";

    public static string FormatTokenCount(double? count)
    {
        if (count is null) return "—";
        var n = Math.Max(0, (int)Math.Round(count.Value));
        if (n >= 100_000_000) return (n / 100_000_000.0).ToString("0.0", CultureInfo.InvariantCulture) + "亿";
        if (n >= 10_000) return (n / 10_000.0).ToString("0.0", CultureInfo.InvariantCulture) + "万";
        return n.ToString(CultureInfo.InvariantCulture);
    }

    public static UsageSnapshot ParseUsageSummary(JsonBag payload, DateTimeOffset? now = null)
    {
        var clock = now ?? DateTimeOffset.UtcNow;
        var individual = Obj(payload["individualUsage"]);
        var team = Obj(payload["teamUsage"]);
        var plan = Obj(individual["plan"]);
        var overall = Obj(individual["overall"]);
        var pooled = Obj(team["pooled"]);
        var individualOd = Obj(individual["onDemand"]);
        var teamOd = Obj(team["onDemand"]);
        var auto = plan["autoPercentUsed"].AsDouble();
        var api = plan["apiPercentUsed"].AsDouble();
        var total = plan["totalPercentUsed"].AsDouble();
        auto ??= PercentFromDisplay(payload["autoModelSelectedDisplayMessage"].AsString());
        api ??= PercentFromDisplay(payload["namedModelSelectedDisplayMessage"].AsString());
        var membership = FormatMembershipType(payload["membershipType"].AsString() ?? payload["plan"].AsString() ?? "");
        var limitType = (payload["limitType"].AsString() ?? "").Trim();
        var isUnlimited = payload["isUnlimited"].AsBool();
        var planMeter = SpendMeter(plan);
        var planMeterBreakdown = SpendMeter(plan, true);
        var overallMeter = SpendMeter(overall);
        var pooledMeter = SpendMeter(pooled);
        var odBlock = OnDemandEnabled(individualOd) ? individualOd : teamOd;
        if (!OnDemandEnabled(odBlock) && OnDemandEnabled(teamOd)) odBlock = teamOd;
        var odMeter = OnDemandEnabled(odBlock) ? SpendMeter(odBlock) : null;

        var billingMode = "percent";
        double? usedCents = null, limitCents = null, remainingCents = null, usedPercent = null;
        if (isUnlimited) usedPercent = 0;
        else
        {
            // Team usage page "Your monthly usage $X / $Y" comes from overall/pooled/plan cents.
            // plan.totalPercentUsed is a separate cached metric and can freeze at 0% or 100%.
            if (IsTeamMembership(membership, limitType))
            {
                foreach (var meter in new[] { overallMeter, pooledMeter, planMeter })
                {
                    if (PercentFromSpendMeter(meter) is not { } applied) continue;
                    usedCents = applied.used;
                    limitCents = applied.limit;
                    remainingCents = applied.remaining;
                    usedPercent = applied.percent;
                    billingMode = "amount";
                    break;
                }
            }
            if (usedPercent is null)
            {
                if (total is not null)
                {
                    usedPercent = total;
                    var meter = MeterWithLimit(planMeter) ?? MeterWithLimit(overallMeter);
                    if (meter is { } m) { usedCents = m.used; limitCents = m.limit; remainingCents = m.remaining; }
                }
                else if (auto is not null || api is not null)
                {
                    usedPercent = new[] { auto, api }.Where(x => x is not null).Select(x => x!.Value).Max();
                    var meter = MeterWithLimit(planMeter) ?? MeterWithLimit(overallMeter);
                    if (meter is { } m) { usedCents = m.used; limitCents = m.limit; remainingCents = m.remaining; }
                }
                else
                {
                    var pickedSource = "";
                    foreach (var (meter, source) in new[] { (overallMeter, "overall"), (planMeter, "plan"), (planMeterBreakdown, "plan"), (pooledMeter, "pooled"), (odMeter, "on_demand") })
                    {
                        if (PercentFromSpendMeter(meter) is not { } applied) continue;
                        usedCents = applied.used;
                        limitCents = applied.limit;
                        remainingCents = applied.remaining;
                        usedPercent = applied.percent;
                        pickedSource = source;
                        break;
                    }
                    if (usedPercent is null) usedPercent = 0;
                    else if (pickedSource is "overall" or "pooled" or "on_demand" || IsTeamMembership(membership, limitType))
                        billingMode = "amount";
                    else { usedCents = limitCents = remainingCents = null; billingMode = "percent"; }
                }
            }
        }
        if (usedCents is null)
        {
            var fallback = MeterWithLimit(overallMeter) ?? MeterWithLimit(pooledMeter);
            if (fallback is { } f) { usedCents = f.used; limitCents = f.limit; remainingCents = f.remaining; }
        }
        var used = Numbers.ClampPercent(usedPercent ?? 0);
        var remaining = Numbers.ClampPercent(100 - used);
        if (remainingCents is null && usedCents is not null && limitCents is not null)
            remainingCents = Math.Max(0, limitCents.Value - usedCents.Value);
        var cycleStart = payload["billingCycleStart"].AsString() ?? payload["startOfMonth"].AsString();
        var cycleEnd = payload["billingCycleEnd"].AsString();
        double? pooledUsed = pooledMeter?.used, pooledLimit = pooledMeter?.limit;
        double? odUsed = odMeter?.used, odLimit = odMeter?.limit;
        return new UsageSnapshot
        {
            UsedPercent = Numbers.Round1(used),
            RemainingPercent = Numbers.Round1(remaining),
            AutoPercentUsed = auto is null ? null : Numbers.Round1(auto.Value),
            ApiPercentUsed = api is null ? null : Numbers.Round1(api.Value),
            TotalPercentUsed = total is null ? null : Numbers.Round1(total.Value),
            MembershipType = membership,
            BillingCycleStart = string.IsNullOrEmpty(cycleStart) ? null : cycleStart,
            BillingCycleEnd = string.IsNullOrEmpty(cycleEnd) ? null : cycleEnd,
            DaysRemaining = DaysUntil(cycleEnd, clock),
            DaysElapsed = DaysSince(cycleStart, clock) is { } e ? Numbers.Round2(e) : null,
            EstimatedUsableDays = EstimateUsableDays(used, remaining, DaysSince(cycleStart, clock)),
            Raw = payload,
            BillingMode = billingMode,
            UsedCents = usedCents,
            LimitCents = limitCents,
            RemainingCents = remainingCents,
            OnDemandUsedCents = odUsed,
            OnDemandLimitCents = odLimit,
            PooledUsedCents = pooledUsed,
            PooledLimitCents = pooledLimit,
            LimitType = limitType,
            IsUnlimited = isUnlimited,
        };
    }

    public static (List<ModelTokenUsage> models, int total) ParseAggregatedUsage(JsonBag payload, double? autoPercent = null, double? apiPercent = null)
    {
        var rows = new List<ModelTokenUsage>();
        foreach (var item in payload["aggregations"].Array)
        {
            var name = DisplayModelName(item["modelIntent"].AsString() ?? item["model"].AsString() ?? "");
            if (name.Length == 0) continue;
            var tokens = SumTokenFields(item);
            if (tokens <= 0) continue;
            rows.Add(new ModelTokenUsage(name, tokens, item["totalCents"].AsDouble() ?? 0, ModelTier(name, item["tier"])));
        }
        if (rows.Count == 0)
        {
            var totalOnly = SumTokenFields(payload);
            return ([], totalOnly > 0 ? totalOnly : 0);
        }
        var cursorRows = Allocate(rows.Where(m => m.IsCursorModel).ToList(), autoPercent);
        var otherRows = Allocate(rows.Where(m => !m.IsCursorModel).ToList(), apiPercent);
        cursorRows = cursorRows.OrderByDescending(m => m.UsagePercent ?? 0).ThenByDescending(m => m.Tokens).ToList();
        otherRows = otherRows.OrderByDescending(m => m.UsagePercent ?? 0).ThenByDescending(m => m.Tokens).ToList();
        var allocated = cursorRows.Concat(otherRows).ToList();
        var total = allocated.Sum(m => m.Tokens);
        var header = SumTokenFields(payload);
        if (header > total) total = header;
        return (allocated, total);
    }

    public static int TeamId(JsonBag payload)
    {
        foreach (var key in new[] { "teamId", "owningTeam" })
            if (payload[key].AsInt() is > 0 and var n) return n;
        var team = Obj(payload["teamUsage"]);
        if (team["teamId"].AsInt() is > 0 and var a) return a;
        if (team["id"].AsInt() is > 0 and var b) return b;
        return -1;
    }

    public static int UserId(JsonBag payload)
    {
        foreach (var key in new[] { "userId", "numericUserId", "currentUserId" })
            if (payload[key].AsInt() is > 0 and var n) return n;
        var individual = Obj(payload["individualUsage"]);
        if (individual["userId"].AsInt() is > 0 and var a) return a;
        if (individual["id"].AsInt() is > 0 and var b) return b;
        return -1;
    }

    public static long? IsoToMs(string? iso)
    {
        var dt = ParseIso(iso);
        return dt is null ? null : (long)(dt.Value.ToUnixTimeMilliseconds());
    }

    public static double? EstimateUsableDays(double usedPercent, double remainingPercent, double? daysElapsed)
    {
        if (daysElapsed is null) return null;
        if (remainingPercent <= 0) return 0;
        if (daysElapsed < 0.04) return null;
        if (usedPercent < 0.2) return null;
        var burn = usedPercent / daysElapsed.Value;
        if (burn <= 1e-6) return null;
        return Numbers.Round1(remainingPercent / burn);
    }

    static JsonBag Obj(JsonBag v) => v.IsObject ? v : JsonBag.Null;
    static bool OnDemandEnabled(JsonBag block)
    {
        if (!block.IsObject || block.IsEmpty) return false;
        if (block.Has("enabled")) return block["enabled"].AsBool();
        return SpendMeter(block) is not null;
    }

    record Meter(double used, double limit, double? remaining);

    static Meter? SpendMeter(JsonBag block, bool allowBreakdown = false)
    {
        if (!block.IsObject || block.IsEmpty) return null;
        var used = block["used"].AsDouble();
        var limit = block["limit"].AsDouble();
        var remaining = block["remaining"].AsDouble();
        if ((limit is null or <= 0) && allowBreakdown) limit = Obj(block["breakdown"])["total"].AsDouble();
        if (used is null && remaining is not null && limit is not null) used = Math.Max(0, limit.Value - remaining.Value);
        if (used is null || limit is null) return null;
        return new Meter(used.Value, limit.Value, remaining);
    }

    static Meter? MeterWithLimit(Meter? meter) => meter is { limit: > 0 } ? meter : null;

    record SpendPercent(double used, double limit, double? remaining, double percent);

    static SpendPercent? PercentFromSpendMeter(Meter? meter)
    {
        var picked = MeterWithLimit(meter);
        if (picked is null) return null;
        return new SpendPercent(picked.used, picked.limit, picked.remaining, Numbers.ClampPercent(picked.used / picked.limit * 100));
    }

    static double? PercentFromDisplay(string? message)
    {
        var text = message ?? "";
        var idx = text.IndexOf('%');
        if (idx <= 0) return null;
        var before = text[..idx];
        var start = 0;
        for (var i = 0; i < before.Length; i++)
        {
            var ch = before[i];
            if (char.IsDigit(ch) || ch == '.') continue;
            start = i + 1;
        }
        var raw = before[start..].Trim();
        if (raw.Length == 0) return null;
        return double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? Numbers.ClampPercent(v) : null;
    }

    static int SumTokenFields(JsonBag item)
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

    static string DisplayModelName(string raw)
    {
        var name = raw.Trim();
        return name is "" ? "" : name is "default" ? "auto" : name;
    }

    static int ModelTier(string name, JsonBag tier)
    {
        if (tier.AsInt() is { } t) return t;
        var key = name.ToLowerInvariant();
        if (key is "auto" or "default" || key.StartsWith("cursor-") || key.StartsWith("composer-")) return CursorModelTier;
        return 1;
    }

    static List<ModelTokenUsage> Allocate(List<ModelTokenUsage> models, double? categoryPercent)
    {
        if (models.Count == 0) return [];
        var centsSum = models.Sum(m => m.Cents);
        var tokensSum = models.Sum(m => m.Tokens);
        return models.Select(model =>
        {
            double share = 0;
            if (centsSum > 1e-6) share = model.Cents / centsSum;
            else if (tokensSum > 0) share = model.Tokens / (double)tokensSum;
            double? pct = categoryPercent is null ? null : Numbers.Round1(share * categoryPercent.Value);
            return model with { UsagePercent = pct };
        }).ToList();
    }

    static DateTimeOffset? ParseIso(string? iso)
    {
        if (string.IsNullOrEmpty(iso)) return null;
        var text = iso.Replace("Z", "+00:00");
        if (DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var dt))
            return dt.ToUniversalTime();
        return null;
    }

    static int? DaysUntil(string? iso, DateTimeOffset now)
    {
        var end = ParseIso(iso);
        if (end is null) return null;
        return Math.Max(0, (int)((end.Value - now).TotalDays));
    }

    static double? DaysSince(string? iso, DateTimeOffset now)
    {
        var start = ParseIso(iso);
        if (start is null) return null;
        var hours = (now - start.Value).TotalHours;
        if (hours < 0) return 0;
        return hours / 24.0;
    }
}
