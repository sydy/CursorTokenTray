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
}

public sealed record DailyUsageRow(string Date, long Tokens, double Cents, int Count);
public sealed record ModelUsageRow(string Name, long Tokens, double Cents, int Count, int HeadlessCount);

public sealed class UsageReportFilter
{
    public string Kind { get; set; } = "";
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
    public List<DailyUsageRow> Daily { get; init; } = [];
    public List<ModelUsageRow> Models { get; init; } = [];
    public List<UsageEvent> Events { get; init; } = [];
}

public sealed record UsageEventsSyncResult(List<UsageEvent> Events, int Fetched, int TotalAvailable, bool Truncated);

public static class UsageEvents
{
    public const string KindIncluded = "included";
    public const string KindFree = "free";
    public const string KindOnDemand = "on_demand";
    public const string KindOther = "other";
    public const string CsvHeader = "日期(UTC),用户,类型,模型,Token,费用,云端Agent";

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

    public static string FormatTime(long timestampMs)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds(Math.Max(0, timestampMs)).UtcDateTime;
        return dt.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
    }

    public static string DateUtc(long timestampMs)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds(Math.Max(0, timestampMs)).UtcDateTime;
        return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
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

    public static UsageReport BuildReport(IEnumerable<UsageEvent> events, UsageReportFilter? filter = null)
    {
        filter ??= new UsageReportFilter();
        var kind = (filter.Kind ?? "").Trim().ToLowerInvariant();
        var model = (filter.Model ?? "").Trim();
        var owning = (filter.OwningUser ?? "").Trim();
        var selected = events.Where(ev =>
        {
            if (kind.Length > 0 && ev.Kind != kind) return false;
            if (model.Length > 0 && ev.Model != model) return false;
            if (filter.Headless is { } h && ev.IsHeadless != h) return false;
            if (owning.Length > 0 && ev.OwningUser != owning) return false;
            return true;
        }).OrderByDescending(ev => ev.TimestampMs).ToList();

        var dailyMap = new Dictionary<string, (long tokens, double cents, int count)>(StringComparer.Ordinal);
        var modelMap = new Dictionary<string, (long tokens, double cents, int count, int headless)>(StringComparer.Ordinal);
        var included = 0; var free = 0; var onDemand = 0; var other = 0; var headless = 0;
        long totalTokens = 0;
        double totalCents = 0;
        var hasCost = false;
        foreach (var ev in selected)
        {
            var cents = CostCents(ev);
            totalTokens += ev.Tokens;
            totalCents += cents;
            if (cents > 0) hasCost = true;
            if (ev.Kind == KindIncluded) included++;
            else if (ev.Kind == KindFree) free++;
            else if (ev.Kind == KindOnDemand) onDemand++;
            else other++;
            if (ev.IsHeadless) headless++;
            var day = DateUtc(ev.TimestampMs);
            dailyMap.TryGetValue(day, out var d);
            dailyMap[day] = (d.tokens + ev.Tokens, d.cents + cents, d.count + 1);
            var name = string.IsNullOrEmpty(ev.Model) ? "—" : ev.Model;
            modelMap.TryGetValue(name, out var m);
            modelMap[name] = (m.tokens + ev.Tokens, m.cents + cents, m.count + 1, m.headless + (ev.IsHeadless ? 1 : 0));
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
            Daily = dailyMap.OrderBy(kv => kv.Key).Select(kv => new DailyUsageRow(kv.Key, kv.Value.tokens, kv.Value.cents, kv.Value.count)).ToList(),
            Models = modelMap.Select(kv => new ModelUsageRow(kv.Key, kv.Value.tokens, kv.Value.cents, kv.Value.count, kv.Value.headless))
                .OrderByDescending(m => m.Tokens).ThenByDescending(m => m.Cents).ThenByDescending(m => m.Count).ToList(),
            Events = selected,
        };
    }

    public static string ToCsv(IEnumerable<UsageEvent> events)
    {
        var sb = new StringBuilder();
        sb.Append('\uFEFF');
        sb.AppendLine(CsvHeader);
        foreach (var ev in events)
        {
            sb.Append(EscapeCsv(FormatTime(ev.TimestampMs))).Append(',');
            sb.Append(EscapeCsv(ev.UserEmail)).Append(',');
            sb.Append(EscapeCsv(KindLabel(ev.Kind))).Append(',');
            sb.Append(EscapeCsv(ev.Model)).Append(',');
            sb.Append(EscapeCsv(ev.Tokens.ToString(CultureInfo.InvariantCulture))).Append(',');
            sb.Append(EscapeCsv(FormatCost(ev))).Append(',');
            sb.Append(EscapeCsv(ev.IsHeadless ? "是" : "否"));
            sb.AppendLine();
        }
        return sb.ToString();
    }

    public static UsageEvent? FromDict(JsonBag raw)
    {
        var ts = raw["timestamp_ms"].AsLong();
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
            ChargedCents = raw["charged_cents"].AsDouble(),
            TotalCents = raw["total_cents"].AsDouble(),
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
