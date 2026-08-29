using System.Collections.Concurrent;
using System.Text.Json;

namespace CursorTokenCore;

public sealed record HistoryPoint(double Ts, double Remaining, double? Auto, double? Api);

public static class UsageHistory
{
    public const int KeepDays = 90;
    public static readonly TimeSpan PruneInterval = TimeSpan.FromHours(6);
    static readonly ConcurrentDictionary<string, long> LastPruneMs = new(StringComparer.OrdinalIgnoreCase);

    public static void AdoptLegacy(string accountId, string directory)
    {
        var dest = AppPaths.HistoryPath(accountId, directory);
        var legacy = Path.Combine(directory, "usage_history.jsonl");
        if (string.IsNullOrEmpty(accountId) || File.Exists(dest) || !File.Exists(legacy)) return;
        var others = Directory.GetFiles(directory, "usage_history.*.jsonl")
            .Where(p => !string.Equals(Path.GetFileName(p), "usage_history.jsonl", StringComparison.OrdinalIgnoreCase));
        if (others.Any(p => Path.GetFullPath(p) != Path.GetFullPath(dest))) return;
        File.Move(legacy, dest);
    }

    public static void Append(double remaining, double? auto = null, double? api = null, double? ts = null, string? accountId = null, string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        Directory.CreateDirectory(dir);
        var aid = (accountId ?? "").Trim();
        if (aid.Length == 0) aid = ConfigStore.Load(dir).ActiveAccount?.Id ?? "";
        if (aid.Length > 0) AdoptLegacy(aid, dir);
        var path = AppPaths.HistoryPath(string.IsNullOrEmpty(aid) ? null : aid, dir);
        var obj = new Dictionary<string, object?>
        {
            ["ts"] = ts ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
            ["remaining"] = Numbers.Round2(remaining),
            ["auto"] = auto is null ? null : Numbers.Round2(auto.Value),
            ["api"] = api is null ? null : Numbers.Round2(api.Value),
            ["account_id"] = aid,
        };
        File.AppendAllText(path, JsonSerializer.Serialize(obj) + "\n");
        if (ts is null) MaybePrune(path);
    }

    static void MaybePrune(string path)
    {
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var intervalMs = (long)PruneInterval.TotalMilliseconds;
        if (LastPruneMs.TryGetValue(path, out var prev) && now - prev < intervalMs) return;
        LastPruneMs[path] = now;
        Prune(path);
    }

    public static void Prune(string path, int keepDays = KeepDays)
    {
        if (!File.Exists(path)) return;
        var cutoff = DateTimeOffset.UtcNow.ToUnixTimeSeconds() - Math.Max(1, keepDays) * 86400L;
        var kept = new List<string>();
        foreach (var line in File.ReadAllLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                using var doc = JsonDocument.Parse(line);
                if (!doc.RootElement.TryGetProperty("ts", out var tsEl)) continue;
                if (tsEl.GetDouble() >= cutoff) kept.Add(line);
            }
            catch { }
        }
        File.WriteAllText(path, kept.Count == 0 ? "" : string.Join("\n", kept) + "\n");
    }

    public static List<HistoryPoint> LoadRecent(int days = 7, string? accountId = null, string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        var aid = (accountId ?? "").Trim();
        if (aid.Length == 0) aid = ConfigStore.Load(dir).ActiveAccount?.Id ?? "";
        if (aid.Length > 0) AdoptLegacy(aid, dir);
        var cutoff = DateTimeOffset.UtcNow.ToUnixTimeSeconds() - Math.Max(1, days) * 86400L;
        var points = new List<HistoryPoint>();
        var path = AppPaths.HistoryPath(string.IsNullOrEmpty(aid) ? null : aid, dir);
        if (!File.Exists(path)) return points;
        foreach (var line in File.ReadAllLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                using var doc = JsonDocument.Parse(line);
                var r = doc.RootElement;
                if (!r.TryGetProperty("ts", out var tsEl) || !r.TryGetProperty("remaining", out var remEl)) continue;
                var ts = tsEl.GetDouble();
                if (ts < cutoff) continue;
                points.Add(new HistoryPoint(ts, remEl.GetDouble(), Num(r, "auto"), Num(r, "api")));
            }
            catch { }
        }
        return points.OrderBy(p => p.Ts).ToList();
    }

    public static double? DailyAvgBurn(int days = 7, string? accountId = null, string? directory = null) =>
        DailyAvgBurn(LoadRecent(days, accountId, directory));

    public static double? DailyAvgBurn(IReadOnlyList<HistoryPoint> points)
    {
        if (points.Count < 2) return null;
        var first = points[0];
        var last = points[^1];
        var elapsed = (last.Ts - first.Ts) / 86400.0;
        if (elapsed < 0.04) return null;
        var delta = first.Remaining - last.Remaining;
        if (delta <= 0) return 0;
        return Numbers.Round2(delta / elapsed);
    }

    static double? Num(JsonElement r, string key) =>
        r.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
}

public static class AlertLogic
{
    public readonly record struct Notice(string Title, string Body);

    public static bool IsExhaustionRisk(UsageSnapshot snap)
    {
        if (snap.EstimatedUsableDays is null || snap.DaysRemaining is null) return false;
        if (snap.EstimatedUsableDays <= 0) return true;
        return snap.EstimatedUsableDays < snap.DaysRemaining;
    }

    public static List<Notice> Evaluate(AppConfig config, Account account, UsageSnapshot snapshot)
    {
        if (!config.NotifyEnabled) return [];
        var notices = new List<Notice>();
        var remaining = snapshot.RemainingPercent;
        var thresholds = config.AlertThresholds.Where(x => x is >= 1 and <= 100).Distinct().OrderByDescending(x => x).ToList();
        var notified = account.AlertNotifiedLevels.ToHashSet();
        var changed = false;
        var name = account.DisplayLabel;
        var who = string.IsNullOrEmpty(name) ? "套餐" : $"账号「{name}」";
        var still = notified.Where(lvl => remaining < lvl).ToHashSet();
        if (!still.SetEquals(notified)) { notified = still; changed = true; }
        var newly = thresholds.Where(lvl => remaining < lvl && !notified.Contains(lvl)).ToList();
        if (newly.Count > 0)
        {
            var hit = newly.Min();
            notices.Add(new Notice("额度告警", $"{who}剩余 {remaining:0.0}%，已低于 {hit}% 档。"));
            foreach (var lvl in newly) notified.Add(lvl);
            changed = true;
        }
        if (config.NotifyExhaustionRisk)
        {
            var atRisk = IsExhaustionRisk(snapshot);
            if (atRisk && !account.ExhaustionNotified)
            {
                notices.Add(new Notice("耗尽风险", $"{who}按当前速度可能提前耗尽（剩余 {remaining:0.0}%）。"));
                account.ExhaustionNotified = true;
                changed = true;
            }
            else if (!atRisk && account.ExhaustionNotified)
            {
                account.ExhaustionNotified = false;
                changed = true;
            }
        }
        if (changed)
        {
            account.AlertNotifiedLevels = notified.OrderBy(x => x).ToList();
            var minThr = thresholds.Count > 0 ? thresholds.Min() : 20;
            account.LowQuotaNotified = remaining < minThr;
        }
        return notices;
    }
}
