using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace CursorTokenCore;

public sealed class DeletedAccount
{
    public string Id { get; set; } = "";
    public string DeletedAt { get; set; } = "";
}

public sealed class SyncAccount
{
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public string Token { get; set; } = "";
    public string MembershipType { get; set; } = "";
    public string AccountKind { get; set; } = AccountValidity.LongTerm;
    public string TempStartAt { get; set; } = "";
    public int TempValidDays { get; set; }
    public int TempValidHours { get; set; }
    public double ActualCny { get; set; }
    public string Channel { get; set; } = "";
    public string SyncUpdatedAt { get; set; } = "";
    public double? LastRemaining { get; set; }
    public string LastError { get; set; } = "";
    public string UsageUpdatedAt { get; set; } = "";
    public string BillingCycleStart { get; set; } = "";
    public string BillingCycleEnd { get; set; } = "";
}

public sealed class SyncUsage
{
    public string AccountId { get; set; } = "";
    public List<HistoryPoint> History { get; set; } = [];
    public List<UsageEvent> Events { get; set; } = [];
    public List<UsageEvent> TeamEvents { get; set; } = [];
}

public sealed class SyncSettings
{
    public int RefreshIntervalMinutes { get; set; } = 10;
    public List<int> AlertThresholds { get; set; } = [50, 20, 5];
    public bool NotifyEnabled { get; set; } = true;
    public bool NotifyExhaustionRisk { get; set; } = true;
    public string TrayDisplayMode { get; set; } = "ring";
    public double MonthlyPlanUsd { get; set; }
    public double UsdCnyRate { get; set; } = UsageEvents.DefaultUsdCnyRate;
}

public sealed class SyncSnapshot
{
    public int Version { get; set; } = 1;
    public string UpdatedAt { get; set; } = "";
    public string DeviceId { get; set; } = "";
    public string ActiveAccountId { get; set; } = "";
    public List<SyncAccount> Accounts { get; set; } = [];
    public List<DeletedAccount> Deleted { get; set; } = [];
    public SyncSettings? Settings { get; set; }
    public List<SyncUsage>? Usage { get; set; }
}

public sealed class SyncStatus
{
    public bool Ok { get; set; }
    public bool Changed { get; set; }
    public bool Pushed { get; set; }
    public string Message { get; set; } = "";
    public string Path { get; set; } = "";
}

public static class AccountSync
{
    public const string Format = "cursortokentray.accounts.v1";
    public const string FormatV2 = "cursortokentray.sync.v2";
    public const string Filename = "CursorTokenTray.accounts.sync";
    public const string Kdf = "pbkdf2-sha256";
    public const int DefaultIterations = 210_000;
    public const int KeyLen = 32;
    public const int SaltLen = 16;
    public const int NonceLen = 12;
    public const int TagLen = 16;
    static readonly HashSet<string> FileSuffixes = new(StringComparer.OrdinalIgnoreCase) { ".sync", ".json" };

    public static string NowIso(DateTimeOffset? now = null)
    {
        var stamp = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        return stamp.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");
    }

    public static DateTimeOffset? ParseIso(string? value)
    {
        var text = (value ?? "").Trim();
        if (text.Length == 0) return null;
        if (DateTimeOffset.TryParse(text, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal,
                out var stamp))
            return stamp;
        return null;
    }

    public static int CompareIso(string? left, string? right)
    {
        var a = ParseIso(left);
        var b = ParseIso(right);
        if (a is null && b is null) return 0;
        if (a is null) return -1;
        if (b is null) return 1;
        return a.Value.CompareTo(b.Value);
    }

    public static string NewerIso(string? left, string? right) =>
        CompareIso(left, right) >= 0 ? left ?? "" : right ?? "";

    public static string ResolveSyncPath(string path)
    {
        var raw = (path ?? "").Trim();
        if (raw.Length == 0) return "";
        var expanded = raw.StartsWith('~')
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), raw[1..].TrimStart('/', '\\'))
            : raw;
        var suffix = Path.GetExtension(expanded);
        if (raw.EndsWith('/') || raw.EndsWith('\\') || Directory.Exists(expanded) || !FileSuffixes.Contains(suffix))
            return Path.Combine(expanded, Filename);
        return expanded;
    }

    public static string EnsureDeviceId(AppConfig cfg)
    {
        if (!string.IsNullOrWhiteSpace(cfg.SyncDeviceId)) return cfg.SyncDeviceId.Trim();
        cfg.SyncDeviceId = Guid.NewGuid().ToString();
        return cfg.SyncDeviceId;
    }

    public static List<DeletedAccount> SanitizeDeleted(IEnumerable<DeletedAccount>? raw)
    {
        var best = new Dictionary<string, string>(StringComparer.Ordinal);
        if (raw is not null)
        {
            foreach (var item in raw)
            {
                var id = (item.Id ?? "").Trim();
                var deletedAt = (item.DeletedAt ?? "").Trim();
                if (id.Length == 0 || deletedAt.Length == 0) continue;
                if (!best.TryGetValue(id, out var prev) || CompareIso(deletedAt, prev) >= 0)
                    best[id] = deletedAt;
            }
        }
        return best.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => new DeletedAccount { Id = kv.Key, DeletedAt = kv.Value }).ToList();
    }

    public static void RememberDeleted(AppConfig cfg, string accountId, string? deletedAt = null)
    {
        var id = (accountId ?? "").Trim();
        if (id.Length == 0) return;
        var rows = SanitizeDeleted(cfg.DeletedAccounts).Where(r => r.Id != id).ToList();
        rows.Add(new DeletedAccount { Id = id, DeletedAt = deletedAt ?? NowIso() });
        cfg.DeletedAccounts = SanitizeDeleted(rows);
    }

    public static void ForgetDeleted(AppConfig cfg, string accountId)
    {
        var id = (accountId ?? "").Trim();
        cfg.DeletedAccounts = SanitizeDeleted(cfg.DeletedAccounts).Where(r => r.Id != id).ToList();
    }

    public static void TouchAccount(Account account, string? stamp = null) =>
        account.SyncUpdatedAt = stamp ?? NowIso();

    public static SyncAccount SnapshotAccount(Account account) => new()
    {
        Id = (account.Id ?? "").Trim(),
        Label = (account.Label ?? "").Trim(),
        Token = (account.Token ?? "").Trim(),
        MembershipType = (account.MembershipType ?? "").Trim(),
        AccountKind = AccountValidity.SanitizeKind(account.AccountKind),
        TempStartAt = (account.TempStartAt ?? "").Trim(),
        TempValidDays = AccountValidity.ClampDays(account.TempValidDays),
        TempValidHours = AccountValidity.ClampHours(account.TempValidHours),
        ActualCny = UsageEvents.ClampActualCny(account.ActualCny),
        Channel = UsageEvents.SanitizeChannel(account.Channel),
        SyncUpdatedAt = (account.SyncUpdatedAt ?? "").Trim(),
        LastRemaining = account.LastRemaining,
        LastError = account.LastError ?? "",
        UsageUpdatedAt = (account.UsageUpdatedAt ?? "").Trim(),
        BillingCycleStart = (account.BillingCycleStart ?? "").Trim(),
        BillingCycleEnd = (account.BillingCycleEnd ?? "").Trim(),
    };

    public static SyncAccount SnapshotAccount(SyncAccount account) => new()
    {
        Id = (account.Id ?? "").Trim(),
        Label = (account.Label ?? "").Trim(),
        Token = (account.Token ?? "").Trim(),
        MembershipType = (account.MembershipType ?? "").Trim(),
        AccountKind = AccountValidity.SanitizeKind(account.AccountKind),
        TempStartAt = (account.TempStartAt ?? "").Trim(),
        TempValidDays = AccountValidity.ClampDays(account.TempValidDays),
        TempValidHours = AccountValidity.ClampHours(account.TempValidHours),
        ActualCny = UsageEvents.ClampActualCny(account.ActualCny),
        Channel = UsageEvents.SanitizeChannel(account.Channel),
        SyncUpdatedAt = (account.SyncUpdatedAt ?? "").Trim(),
        LastRemaining = account.LastRemaining,
        LastError = account.LastError ?? "",
        UsageUpdatedAt = (account.UsageUpdatedAt ?? "").Trim(),
        BillingCycleStart = (account.BillingCycleStart ?? "").Trim(),
        BillingCycleEnd = (account.BillingCycleEnd ?? "").Trim(),
    };

    static bool HasUsageFields(SyncAccount row) =>
        !string.IsNullOrWhiteSpace(row.UsageUpdatedAt)
        || row.LastRemaining is not null
        || !string.IsNullOrWhiteSpace(row.BillingCycleStart)
        || !string.IsNullOrWhiteSpace(row.BillingCycleEnd)
        || !string.IsNullOrWhiteSpace(row.LastError);

    static SyncAccount CombineAccounts(SyncAccount left, SyncAccount right)
    {
        var identCmp = CompareIso(left.SyncUpdatedAt, right.SyncUpdatedAt);
        var ident = identCmp > 0 ? left : identCmp < 0 ? right : (left.Token.Length > 0 || right.Token.Length == 0 ? left : right);
        var usageCmp = CompareIso(left.UsageUpdatedAt, right.UsageUpdatedAt);
        SyncAccount usage;
        if (usageCmp > 0) usage = left;
        else if (usageCmp < 0) usage = right;
        else usage = left.LastRemaining is not null || right.LastRemaining is null ? left : right;
        var merged = SnapshotAccount(ident);
        merged.LastRemaining = usage.LastRemaining;
        merged.LastError = usage.LastError;
        merged.UsageUpdatedAt = usage.UsageUpdatedAt;
        merged.BillingCycleStart = usage.BillingCycleStart;
        merged.BillingCycleEnd = usage.BillingCycleEnd;
        return merged;
    }

    static List<HistoryPoint> MergeHistory(IEnumerable<HistoryPoint>? left, IEnumerable<HistoryPoint>? right)
    {
        var best = new Dictionary<long, HistoryPoint>();
        foreach (var src in (left ?? []).Concat(right ?? []))
        {
            var key = (long)Math.Round(src.Ts * 1000);
            if (!best.TryGetValue(key, out var prev)
                || ((src.Auto is not null || src.Api is not null) && prev.Auto is null && prev.Api is null))
                best[key] = src;
        }
        return best.OrderBy(kv => kv.Key).Select(kv => kv.Value).ToList();
    }

    static SyncUsage SnapshotUsage(SyncUsage raw) => new()
    {
        AccountId = (raw.AccountId ?? "").Trim(),
        History = [.. raw.History],
        Events = UsageEvents.Merge(raw.Events, []),
        TeamEvents = UsageEvents.Merge(raw.TeamEvents, []),
    };

    public static List<SyncUsage>? MergeUsage(IEnumerable<SyncUsage>? local, IEnumerable<SyncUsage>? remote, ISet<string> keepIds)
    {
        if (local is null && remote is null) return null;
        var rows = new Dictionary<string, SyncUsage>(StringComparer.Ordinal);
        foreach (var src in (local ?? []).Concat(remote ?? []))
        {
            var row = SnapshotUsage(src);
            if (row.AccountId.Length == 0 || (keepIds.Count > 0 && !keepIds.Contains(row.AccountId))) continue;
            if (!rows.TryGetValue(row.AccountId, out var prev))
            {
                rows[row.AccountId] = row;
                continue;
            }
            rows[row.AccountId] = new SyncUsage
            {
                AccountId = row.AccountId,
                History = MergeHistory(prev.History, row.History),
                Events = UsageEvents.Merge(prev.Events, row.Events),
                TeamEvents = UsageEvents.Merge(prev.TeamEvents, row.TeamEvents),
            };
        }
        return rows.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => kv.Value).ToList();
    }

    static List<SyncUsage> SnapshotUsageFromFiles(IEnumerable<string> accountIds, string? directory = null)
    {
        var cutoff = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - 120L * 86400 * 1000;
        var rows = new List<SyncUsage>();
        foreach (var aid in accountIds)
        {
            if (string.IsNullOrWhiteSpace(aid)) continue;
            var history = UsageHistory.LoadRecent(UsageHistory.KeepDays, aid, directory);
            var events = UsageEvents.Prune(UsageEvents.Load(aid, false, directory), cutoff);
            var team = UsageEvents.Prune(UsageEvents.Load(aid, true, directory), cutoff);
            if (history.Count == 0 && events.Count == 0 && team.Count == 0) continue;
            rows.Add(new SyncUsage { AccountId = aid, History = history, Events = events, TeamEvents = team });
        }
        return rows;
    }

    static bool ApplyUsageToFiles(IEnumerable<SyncUsage>? usage, ISet<string> keepIds, string? directory = null)
    {
        if (usage is null) return false;
        var changed = false;
        foreach (var src in usage)
        {
            var row = SnapshotUsage(src);
            if (row.AccountId.Length == 0 || !keepIds.Contains(row.AccountId)) continue;
            UsageHistory.Replace(row.History, row.AccountId, directory);
            UsageEvents.Save(row.Events, row.AccountId, false, directory);
            UsageEvents.Save(row.TeamEvents, row.AccountId, true, directory);
            changed = true;
        }
        return changed;
    }

    static string UsageIdentity(IEnumerable<SyncUsage>? usage)
    {
        if (usage is null) return "";
        return string.Join("|", usage.OrderBy(u => u.AccountId, StringComparer.Ordinal).Select(u =>
        {
            var hist = string.Join(",", u.History.OrderBy(p => p.Ts).Select(p => $"{p.Ts}:{p.Remaining}:{p.Auto}:{p.Api}"));
            var events = string.Join(",", u.Events.Select(e => e.Id).OrderBy(x => x, StringComparer.Ordinal));
            var team = string.Join(",", u.TeamEvents.Select(e => e.Id).OrderBy(x => x, StringComparer.Ordinal));
            return $"{u.AccountId}\n{hist}\n{events}\n{team}";
        }));
    }

    public static SyncSettings SnapshotSettings(AppConfig cfg) => new()
    {
        RefreshIntervalMinutes = Math.Max(1, cfg.RefreshIntervalMinutes),
        AlertThresholds = cfg.AlertThresholds.Count == 0 ? [50, 20, 5] : [.. cfg.AlertThresholds],
        NotifyEnabled = cfg.NotifyEnabled,
        NotifyExhaustionRisk = cfg.NotifyExhaustionRisk,
        TrayDisplayMode = cfg.TrayDisplayMode is "ring" or "number" or "dot" ? cfg.TrayDisplayMode : "ring",
        MonthlyPlanUsd = UsageEvents.ClampMonthlyPlanUsd(cfg.MonthlyPlanUsd),
        UsdCnyRate = UsageEvents.ClampUsdCnyRate(cfg.UsdCnyRate),
    };

    public static SyncSettings SnapshotSettings(SyncSettings settings) => new()
    {
        RefreshIntervalMinutes = Math.Max(1, settings.RefreshIntervalMinutes),
        AlertThresholds = settings.AlertThresholds.Count == 0 ? [50, 20, 5] : [.. settings.AlertThresholds],
        NotifyEnabled = settings.NotifyEnabled,
        NotifyExhaustionRisk = settings.NotifyExhaustionRisk,
        TrayDisplayMode = settings.TrayDisplayMode is "ring" or "number" or "dot" ? settings.TrayDisplayMode : "ring",
        MonthlyPlanUsd = UsageEvents.ClampMonthlyPlanUsd(settings.MonthlyPlanUsd),
        UsdCnyRate = UsageEvents.ClampUsdCnyRate(settings.UsdCnyRate),
    };

    public static void ApplySettings(AppConfig cfg, SyncSettings? settings)
    {
        if (settings is null) return;
        var row = SnapshotSettings(settings);
        cfg.RefreshIntervalMinutes = row.RefreshIntervalMinutes;
        cfg.AlertThresholds = row.AlertThresholds;
        cfg.NotifyEnabled = row.NotifyEnabled;
        cfg.NotifyExhaustionRisk = row.NotifyExhaustionRisk;
        cfg.TrayDisplayMode = row.TrayDisplayMode;
        cfg.MonthlyPlanUsd = row.MonthlyPlanUsd;
        cfg.UsdCnyRate = row.UsdCnyRate;
    }

    public static string SettingsIdentity(SyncSettings? settings)
    {
        if (settings is null) return "";
        var row = SnapshotSettings(settings);
        return $"{row.RefreshIntervalMinutes}\n{string.Join(",", row.AlertThresholds)}\n{row.NotifyEnabled}\n{row.NotifyExhaustionRisk}\n{row.TrayDisplayMode}\n{row.MonthlyPlanUsd}\n{row.UsdCnyRate}";
    }

    public static SyncSnapshot SnapshotFromConfig(AppConfig cfg)
    {
        var accounts = new List<SyncAccount>();
        foreach (var acc in cfg.Accounts)
        {
            var row = SnapshotAccount(acc);
            if (row.Id.Length == 0 || row.Token.Length == 0) continue;
            accounts.Add(row);
        }
        return new SyncSnapshot
        {
            Version = 1,
            UpdatedAt = cfg.SyncLastAt ?? "",
            DeviceId = cfg.SyncDeviceId ?? "",
            ActiveAccountId = cfg.ActiveAccountId ?? "",
            Accounts = accounts,
            Deleted = SanitizeDeleted(cfg.DeletedAccounts),
            Settings = SnapshotSettings(cfg),
            Usage = SnapshotUsageFromFiles(accounts.Select(a => a.Id)),
        };
    }

    public static string SnapshotIdentity(SyncSnapshot snap)
    {
        var accounts = snap.Accounts.OrderBy(a => a.Id, StringComparer.Ordinal)
            .Select(a => $"{a.Id}\n{a.Label}\n{a.Token}\n{a.MembershipType}\n{a.AccountKind}\n{a.TempStartAt}\n{a.TempValidDays}\n{a.TempValidHours}\n{a.ActualCny}\n{a.Channel}\n{a.SyncUpdatedAt}\n{a.LastRemaining}\n{a.LastError}\n{a.UsageUpdatedAt}\n{a.BillingCycleStart}\n{a.BillingCycleEnd}");
        var deleted = snap.Deleted.OrderBy(d => d.Id, StringComparer.Ordinal)
            .Select(d => $"{d.Id}\n{d.DeletedAt}");
        return $"{snap.ActiveAccountId}\n{string.Join("|", accounts)}\n{string.Join("|", deleted)}\n{SettingsIdentity(snap.Settings)}\n{UsageIdentity(snap.Usage)}";
    }

    public static SyncSnapshot MergeSnapshots(SyncSnapshot local, SyncSnapshot remote)
    {
        var tombstones = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var row in SanitizeDeleted(local.Deleted).Concat(SanitizeDeleted(remote.Deleted)))
        {
            if (!tombstones.TryGetValue(row.Id, out var prev) || CompareIso(row.DeletedAt, prev) >= 0)
                tombstones[row.Id] = row.DeletedAt;
        }

        var chosen = new Dictionary<string, SyncAccount>(StringComparer.Ordinal);
        foreach (var src in local.Accounts.Concat(remote.Accounts))
        {
            var acc = SnapshotAccount(src);
            if (acc.Id.Length == 0 || acc.Token.Length == 0) continue;
            if (tombstones.TryGetValue(acc.Id, out var tomb) && CompareIso(tomb, acc.SyncUpdatedAt) >= 0)
                continue;
            if (!chosen.TryGetValue(acc.Id, out var prev))
            {
                chosen[acc.Id] = acc;
                continue;
            }
            chosen[acc.Id] = CombineAccounts(prev, acc);
        }

        foreach (var id in tombstones.Keys.ToList())
            if (chosen.ContainsKey(id)) tombstones.Remove(id);

        var remoteNewer = CompareIso(remote.UpdatedAt, local.UpdatedAt) > 0;
        var active = remoteNewer ? remote.ActiveAccountId : local.ActiveAccountId;
        var settings = remoteNewer
            ? remote.Settings ?? local.Settings
            : local.Settings ?? remote.Settings;
        if (!chosen.ContainsKey(active ?? ""))
            active = chosen.Keys.OrderBy(x => x, StringComparer.Ordinal).FirstOrDefault() ?? "";

        return new SyncSnapshot
        {
            Version = 1,
            UpdatedAt = NewerIso(local.UpdatedAt, remote.UpdatedAt),
            DeviceId = string.IsNullOrEmpty(local.DeviceId) ? remote.DeviceId : local.DeviceId,
            ActiveAccountId = active ?? "",
            Accounts = chosen.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => kv.Value).ToList(),
            Deleted = tombstones.OrderBy(kv => kv.Key, StringComparer.Ordinal)
                .Select(kv => new DeletedAccount { Id = kv.Key, DeletedAt = kv.Value }).ToList(),
            Settings = settings is null ? null : SnapshotSettings(settings),
            Usage = MergeUsage(local.Usage, remote.Usage, chosen.Keys.ToHashSet(StringComparer.Ordinal)),
        };
    }

    public static bool ApplySnapshotToConfig(AppConfig cfg, SyncSnapshot snap)
    {
        string Before() => string.Join("|", cfg.Accounts.Select(a =>
            $"{a.Id}\n{a.Token}\n{a.Label}\n{a.MembershipType}\n{a.AccountKind}\n{a.TempStartAt}\n{a.TempValidDays}\n{a.TempValidHours}\n{a.ActualCny}\n{a.Channel}\n{a.SyncUpdatedAt}\n{a.LastRemaining}\n{a.UsageUpdatedAt}\n{a.BillingCycleStart}\n{a.BillingCycleEnd}"));
        var before = Before();
        var beforeSettings = SettingsIdentity(SnapshotSettings(cfg));
        var existing = cfg.Accounts.ToDictionary(a => a.Id, StringComparer.Ordinal);
        var merged = new List<Account>();
        foreach (var row in snap.Accounts)
        {
            var ident = SnapshotAccount(row);
            if (ident.Id.Length == 0 || ident.Token.Length == 0) continue;
            if (!existing.TryGetValue(ident.Id, out var old))
            {
                var created = new Account
                {
                    Id = ident.Id,
                    Token = ident.Token,
                    Label = ident.Label,
                    MembershipType = ident.MembershipType,
                    AccountKind = ident.AccountKind,
                    TempStartAt = ident.TempStartAt,
                    TempValidDays = ident.TempValidDays,
                    TempValidHours = ident.TempValidHours,
                    ActualCny = ident.ActualCny,
                    Channel = ident.Channel,
                    SyncUpdatedAt = ident.SyncUpdatedAt,
                };
                ApplyUsageFields(created, ident);
                merged.Add(created);
                continue;
            }
            old.Token = ident.Token;
            old.Label = ident.Label;
            if (ident.MembershipType.Length > 0) old.MembershipType = ident.MembershipType;
            old.AccountKind = ident.AccountKind;
            old.TempStartAt = ident.TempStartAt;
            old.TempValidDays = ident.TempValidDays;
            old.TempValidHours = ident.TempValidHours;
            old.ActualCny = ident.ActualCny;
            old.Channel = ident.Channel;
            old.SyncUpdatedAt = ident.SyncUpdatedAt;
            ApplyUsageFields(old, ident);
            merged.Add(old);
        }
        cfg.Accounts = merged;
        cfg.DeletedAccounts = SanitizeDeleted(snap.Deleted);
        var ids = merged.Select(a => a.Id).ToHashSet(StringComparer.Ordinal);
        if (ids.Contains(snap.ActiveAccountId)) cfg.ActiveAccountId = snap.ActiveAccountId;
        else cfg.ActiveAccountId = merged.Count > 0 ? merged[0].Id : "";
        ApplySettings(cfg, snap.Settings);
        var usageChanged = ApplyUsageToFiles(snap.Usage, ids);
        cfg.SyncLegacyFields();
        return before != Before() || beforeSettings != SettingsIdentity(SnapshotSettings(cfg)) || usageChanged;
    }

    static void ApplyUsageFields(Account account, SyncAccount ident)
    {
        if (!HasUsageFields(ident)) return;
        account.LastRemaining = ident.LastRemaining;
        account.LastError = ident.LastError ?? "";
        account.UsageUpdatedAt = ident.UsageUpdatedAt ?? "";
        account.BillingCycleStart = ident.BillingCycleStart ?? "";
        account.BillingCycleEnd = ident.BillingCycleEnd ?? "";
        var stamp = ParseIso(account.UsageUpdatedAt);
        if (stamp is not null)
            account.UpdatedAt = stamp.Value.ToLocalTime().ToString("HH:mm:ss");
    }

    public static byte[] DeriveKey(string passphrase, byte[] salt, int iterations = DefaultIterations)
    {
        if (string.IsNullOrEmpty(passphrase)) throw new CursorApiException("同步口令不能为空");
        if (iterations < 1000) throw new CursorApiException("KDF 迭代次数过低");
        return Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(passphrase), salt, iterations, HashAlgorithmName.SHA256, KeyLen);
    }

    public static string CanonicalJson(SyncSnapshot snap)
    {
        static string Q(string value)
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(value ?? "", new JsonSerializerOptions
            {
                Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            });
            return Encoding.UTF8.GetString(bytes);
        }
        var accounts = string.Join(",", snap.Accounts.Select(a =>
        {
            var extra = "";
            if (AccountValidity.SanitizeKind(a.AccountKind) != AccountValidity.LongTerm
                || !string.IsNullOrEmpty(a.TempStartAt)
                || a.TempValidDays != 0
                || a.TempValidHours != 0)
            {
                extra += $",\"account_kind\":{Q(AccountValidity.SanitizeKind(a.AccountKind))},\"temp_start_at\":{Q(a.TempStartAt ?? "")},\"temp_valid_days\":{a.TempValidDays},\"temp_valid_hours\":{a.TempValidHours}";
            }
            if (a.ActualCny != 0)
                extra += $",\"actual_cny\":{CanonicalNumber(a.ActualCny)}";
            if (!string.IsNullOrEmpty(a.Channel))
                extra += $",\"channel\":{Q(a.Channel)}";
            if (a.LastRemaining is { } remaining)
                extra += $",\"last_remaining\":{CanonicalNumber(remaining)}";
            if (!string.IsNullOrEmpty(a.LastError))
                extra += $",\"last_error\":{Q(a.LastError)}";
            if (!string.IsNullOrEmpty(a.UsageUpdatedAt))
                extra += $",\"usage_updated_at\":{Q(a.UsageUpdatedAt)}";
            if (!string.IsNullOrEmpty(a.BillingCycleStart))
                extra += $",\"billing_cycle_start\":{Q(a.BillingCycleStart)}";
            if (!string.IsNullOrEmpty(a.BillingCycleEnd))
                extra += $",\"billing_cycle_end\":{Q(a.BillingCycleEnd)}";
            return $"{{\"id\":{Q(a.Id)},\"label\":{Q(a.Label)},\"membership_type\":{Q(a.MembershipType)},\"sync_updated_at\":{Q(a.SyncUpdatedAt)},\"token\":{Q(a.Token)}{extra}}}";
        }));
        var deleted = string.Join(",", snap.Deleted.Select(d =>
            $"{{\"deleted_at\":{Q(d.DeletedAt)},\"id\":{Q(d.Id)}}}")
        );
        var settings = "";
        if (snap.Settings is { } s)
        {
            var row = SnapshotSettings(s);
            var thresholds = string.Join(",", row.AlertThresholds);
            settings = $",\"settings\":{{\"alert_thresholds\":[{thresholds}],\"monthly_plan_usd\":{CanonicalNumber(row.MonthlyPlanUsd)},\"notify_enabled\":{(row.NotifyEnabled ? "true" : "false")},\"notify_exhaustion_risk\":{(row.NotifyExhaustionRisk ? "true" : "false")},\"refresh_interval_minutes\":{row.RefreshIntervalMinutes},\"tray_display_mode\":{Q(row.TrayDisplayMode)},\"usd_cny_rate\":{CanonicalNumber(row.UsdCnyRate)}}}";
        }
        var usage = "";
        if (snap.Usage is { Count: > 0 } rows)
        {
            var packed = string.Join(",", rows.Select(u =>
            {
                var hist = string.Join(",", u.History.Select(p =>
                {
                    var auto = p.Auto is { } av ? CanonicalNumber(av) : "null";
                    var api = p.Api is { } pv ? CanonicalNumber(pv) : "null";
                    return $"{{\"api\":{api},\"auto\":{auto},\"remaining\":{CanonicalNumber(p.Remaining)},\"ts\":{CanonicalNumber(p.Ts)}}}";
                }));
                var evs = string.Join(",", u.Events.Select(CanonicalEvent));
                var team = string.Join(",", u.TeamEvents.Select(CanonicalEvent));
                return $"{{\"account_id\":{Q(u.AccountId)},\"events\":[{evs}],\"history\":[{hist}],\"team_events\":[{team}]}}";
            }));
            usage = $",\"usage\":[{packed}]";
        }
        return $"{{\"accounts\":[{accounts}],\"active_account_id\":{Q(snap.ActiveAccountId)},\"deleted\":[{deleted}],\"device_id\":{Q(snap.DeviceId)}{settings},\"updated_at\":{Q(snap.UpdatedAt)}{usage},\"version\":{snap.Version}}}";
    }

    static string CanonicalEvent(UsageEvent ev)
    {
        static string Q(string value)
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(value ?? "", new JsonSerializerOptions
            {
                Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            });
            return Encoding.UTF8.GetString(bytes);
        }
        var charged = ev.ChargedCents is { } c ? CanonicalNumber(c) : "null";
        var total = ev.TotalCents is { } t ? CanonicalNumber(t) : "null";
        return $"{{\"cache_read_tokens\":{ev.CacheReadTokens},\"cache_write_tokens\":{ev.CacheWriteTokens},\"charged_cents\":{charged},\"id\":{Q(ev.Id)},\"input_tokens\":{ev.InputTokens},\"is_chargeable\":{(ev.IsChargeable ? "true" : "false")},\"is_headless\":{(ev.IsHeadless ? "true" : "false")},\"kind\":{Q(ev.Kind)},\"model\":{Q(ev.Model)},\"output_tokens\":{ev.OutputTokens},\"owning_user\":{Q(ev.OwningUser)},\"timestamp_ms\":{ev.TimestampMs},\"tokens\":{ev.Tokens},\"total_cents\":{total},\"user_email\":{Q(ev.UserEmail)}}}";
    }

    public static Dictionary<string, object> EncryptEnvelope(SyncSnapshot payload, string passphrase, byte[]? salt = null, byte[]? nonce = null, int iterations = DefaultIterations)
    {
        var saltB = salt ?? RandomNumberGenerator.GetBytes(SaltLen);
        var nonceB = nonce ?? RandomNumberGenerator.GetBytes(NonceLen);
        if (saltB.Length != SaltLen || nonceB.Length != NonceLen) throw new CursorApiException("salt/nonce 长度不正确");
        var raw = Encoding.UTF8.GetBytes(CanonicalJson(payload));
        var key = DeriveKey(passphrase, saltB, iterations);
        var ciphertext = new byte[raw.Length];
        var tag = new byte[TagLen];
        using var aes = new AesGcm(key, TagLen);
        aes.Encrypt(nonceB, raw, ciphertext, tag);
        var blob = new byte[ciphertext.Length + tag.Length];
        Buffer.BlockCopy(ciphertext, 0, blob, 0, ciphertext.Length);
        Buffer.BlockCopy(tag, 0, blob, ciphertext.Length, tag.Length);
        return new Dictionary<string, object>
        {
            ["format"] = payload.Settings is null && (payload.Usage is null || payload.Usage.Count == 0) ? Format : FormatV2,
            ["kdf"] = Kdf,
            ["iterations"] = iterations,
            ["salt"] = Convert.ToBase64String(saltB),
            ["nonce"] = Convert.ToBase64String(nonceB),
            ["ciphertext"] = Convert.ToBase64String(blob),
        };
    }

    public static SyncSnapshot DecryptEnvelope(JsonElement envelope, string passphrase)
    {
        var format = Str(envelope, "format");
        if (format != Format && format != FormatV2) throw new CursorApiException("不是 CursorTokenTray 账号同步文件");
        if (Str(envelope, "kdf") != Kdf) throw new CursorApiException("不支持的同步文件密钥算法");
        byte[] salt, nonce, blob;
        int iterations;
        try
        {
            iterations = envelope.TryGetProperty("iterations", out var it) && it.TryGetInt32(out var n) ? n : 0;
            salt = Convert.FromBase64String(Str(envelope, "salt"));
            nonce = Convert.FromBase64String(Str(envelope, "nonce"));
            blob = Convert.FromBase64String(Str(envelope, "ciphertext"));
        }
        catch { throw new CursorApiException("同步文件损坏"); }
        if (salt.Length != SaltLen || nonce.Length != NonceLen || blob.Length < TagLen)
            throw new CursorApiException("同步文件损坏");
        var key = DeriveKey(passphrase, salt, iterations);
        var cipher = blob[..^TagLen];
        var tag = blob[^TagLen..];
        var plain = new byte[cipher.Length];
        try
        {
            using var aes = new AesGcm(key, TagLen);
            aes.Decrypt(nonce, cipher, tag, plain);
        }
        catch
        {
            throw new CursorApiException("同步口令不正确或文件已损坏");
        }
        using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(plain));
        return ParseSnapshot(doc.RootElement);
    }

    public static SyncSnapshot ParseSnapshot(JsonElement raw)
    {
        var snap = new SyncSnapshot
        {
            Version = 1,
            UpdatedAt = Str(raw, "updated_at"),
            DeviceId = Str(raw, "device_id"),
            ActiveAccountId = Str(raw, "active_account_id"),
        };
        if (raw.TryGetProperty("accounts", out var arr) && arr.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in arr.EnumerateArray())
            {
                var acc = new SyncAccount
                {
                    Id = Str(item, "id").Trim(),
                    Label = Str(item, "label").Trim(),
                    Token = Str(item, "token").Trim(),
                    MembershipType = Str(item, "membership_type").Trim(),
                    AccountKind = AccountValidity.SanitizeKind(Str(item, "account_kind")),
                    TempStartAt = Str(item, "temp_start_at").Trim(),
                    TempValidDays = AccountValidity.ClampDays(IntVal(item, "temp_valid_days")),
                    TempValidHours = AccountValidity.ClampHours(IntVal(item, "temp_valid_hours")),
                    ActualCny = UsageEvents.ClampActualCny(DoubleVal(item, "actual_cny")),
                    Channel = UsageEvents.SanitizeChannel(Str(item, "channel")),
                    SyncUpdatedAt = Str(item, "sync_updated_at").Trim(),
                    LastRemaining = item.TryGetProperty("last_remaining", out var lr) && lr.ValueKind == JsonValueKind.Number ? lr.GetDouble() : null,
                    LastError = Str(item, "last_error"),
                    UsageUpdatedAt = Str(item, "usage_updated_at").Trim(),
                    BillingCycleStart = Str(item, "billing_cycle_start").Trim(),
                    BillingCycleEnd = Str(item, "billing_cycle_end").Trim(),
                };
                if (acc.Id.Length > 0) snap.Accounts.Add(acc);
            }
        }
        if (raw.TryGetProperty("deleted", out var del) && del.ValueKind == JsonValueKind.Array)
        {
            var rows = new List<DeletedAccount>();
            foreach (var item in del.EnumerateArray())
                rows.Add(new DeletedAccount { Id = Str(item, "id").Trim(), DeletedAt = Str(item, "deleted_at").Trim() });
            snap.Deleted = SanitizeDeleted(rows);
        }
        if (raw.TryGetProperty("settings", out var set) && set.ValueKind == JsonValueKind.Object)
        {
            var mode = Str(set, "tray_display_mode").Trim().ToLowerInvariant();
            var thresholds = ConfigStore.ParseThresholds(set.TryGetProperty("alert_thresholds", out var at) ? at : default);
            snap.Settings = SnapshotSettings(new SyncSettings
            {
                RefreshIntervalMinutes = Math.Max(1, IntVal(set, "refresh_interval_minutes") ?? 10),
                AlertThresholds = thresholds,
                NotifyEnabled = set.TryGetProperty("notify_enabled", out var ne) && ne.ValueKind == JsonValueKind.False ? false : true,
                NotifyExhaustionRisk = set.TryGetProperty("notify_exhaustion_risk", out var nr) && nr.ValueKind == JsonValueKind.False ? false : true,
                TrayDisplayMode = mode is "ring" or "number" or "dot" ? mode : "ring",
                MonthlyPlanUsd = UsageEvents.ClampMonthlyPlanUsd(DoubleVal(set, "monthly_plan_usd")),
                UsdCnyRate = UsageEvents.ClampUsdCnyRate(DoubleVal(set, "usd_cny_rate") == 0 ? UsageEvents.DefaultUsdCnyRate : DoubleVal(set, "usd_cny_rate")),
            });
        }
        if (raw.TryGetProperty("usage", out var usageEl) && usageEl.ValueKind == JsonValueKind.Array)
        {
            var rows = new List<SyncUsage>();
            foreach (var item in usageEl.EnumerateArray())
            {
                var row = new SyncUsage { AccountId = Str(item, "account_id").Trim() };
                if (row.AccountId.Length == 0) continue;
                if (item.TryGetProperty("history", out var hist) && hist.ValueKind == JsonValueKind.Array)
                {
                    foreach (var p in hist.EnumerateArray())
                    {
                        if (!p.TryGetProperty("ts", out var ts) || ts.ValueKind != JsonValueKind.Number) continue;
                        if (!p.TryGetProperty("remaining", out var rem) || rem.ValueKind != JsonValueKind.Number) continue;
                        row.History.Add(new HistoryPoint(ts.GetDouble(), rem.GetDouble(), NumOpt(p, "auto"), NumOpt(p, "api")));
                    }
                }
                if (item.TryGetProperty("events", out var evs) && evs.ValueKind == JsonValueKind.Array)
                    row.Events = UsageEvents.Merge(ParseEvents(evs), []);
                if (item.TryGetProperty("team_events", out var team) && team.ValueKind == JsonValueKind.Array)
                    row.TeamEvents = UsageEvents.Merge(ParseEvents(team), []);
                rows.Add(row);
            }
            snap.Usage = rows;
        }
        return snap;
    }

    static List<UsageEvent> ParseEvents(JsonElement arr)
    {
        var events = new List<UsageEvent>();
        foreach (var item in arr.EnumerateArray())
        {
            try
            {
                var ev = UsageEvents.FromDict(JsonBag.Parse(item.GetRawText()));
                if (ev is not null) events.Add(ev);
            }
            catch { }
        }
        return events;
    }

    static double? NumOpt(JsonElement raw, string key)
    {
        if (!raw.TryGetProperty(key, out var v) || v.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined) return null;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var d)) return d;
        return null;
    }

    static string Str(JsonElement raw, string key) =>
        raw.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

    static int? IntVal(JsonElement raw, string key)
    {
        if (!raw.TryGetProperty(key, out var v)) return null;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var n)) return n;
        if (v.ValueKind == JsonValueKind.String && int.TryParse(v.GetString(), out n)) return n;
        return null;
    }

    static double DoubleVal(JsonElement raw, string key)
    {
        if (!raw.TryGetProperty(key, out var v)) return 0;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var d)) return d;
        if (v.ValueKind == JsonValueKind.String
            && double.TryParse((v.GetString() ?? "").Replace("，", "."), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d))
            return d;
        return 0;
    }

    static string CanonicalNumber(double value)
    {
        var text = value.ToString("0.######", System.Globalization.CultureInfo.InvariantCulture);
        return string.IsNullOrEmpty(text) ? "0" : text;
    }

    public static JsonElement? ReadEnvelope(string path)
    {
        if (!File.Exists(path)) return null;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            return doc.RootElement.Clone();
        }
        catch
        {
            throw new CursorApiException("无法读取同步文件");
        }
    }

    public static void WriteEnvelope(string path, Dictionary<string, object> envelope)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");
        var json = JsonSerializer.Serialize(envelope, new JsonSerializerOptions { WriteIndented = true });
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, json);
        if (File.Exists(path))
        {
            try { File.Replace(tmp, path, null); }
            catch
            {
                File.Copy(tmp, path, true);
                try { File.Delete(tmp); } catch { }
            }
        }
        else File.Move(tmp, path, true);
    }

    public static string SyncReady(AppConfig cfg)
    {
        if (!cfg.SyncEnabled || !cfg.CloudLoggedIn) return "请先登录云同步";
        if (string.IsNullOrWhiteSpace(cfg.SyncSecret)) return "请重新登录以解锁同步密钥";
        return "";
    }

    public static SyncStatus Reconcile(AppConfig cfg, DateTimeOffset? now = null, bool write = true) =>
        CloudSync.Reconcile(cfg, now, write);

    public static string ExportToFile(AppConfig cfg, string path, string? passphrase = null)
    {
        var secret = (passphrase ?? cfg.SyncSecret ?? "").Trim();
        if (secret.Length == 0) throw new CursorApiException("请设置同步口令");
        var dest = FileSuffixes.Contains(Path.GetExtension(path)) ? path : ResolveSyncPath(path);
        var snap = SnapshotFromConfig(cfg);
        snap.UpdatedAt = NowIso();
        snap.DeviceId = EnsureDeviceId(cfg);
        WriteEnvelope(dest, EncryptEnvelope(snap, secret));
        return dest;
    }

    public static void ImportFromFile(AppConfig cfg, string path, string? passphrase = null)
    {
        var secret = (passphrase ?? cfg.SyncSecret ?? "").Trim();
        if (secret.Length == 0) throw new CursorApiException("请设置同步口令");
        var envelope = ReadEnvelope(path) ?? throw new CursorApiException("找不到同步文件");
        var remote = DecryptEnvelope(envelope, secret);
        var merged = MergeSnapshots(SnapshotFromConfig(cfg), remote);
        ApplySnapshotToConfig(cfg, merged);
        cfg.SyncLastAt = NowIso();
        cfg.SyncLastError = "";
    }
}
