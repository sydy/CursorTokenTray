using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;

namespace CursorTokenCore;

public sealed class Account
{
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public string Token { get; set; } = "";
    public string MembershipType { get; set; } = "";
    public double? LastRemaining { get; set; }
    public string LastError { get; set; } = "";
    public string UpdatedAt { get; set; } = "";
    public List<int> AlertNotifiedLevels { get; set; } = [];
    public bool AuthErrorNotified { get; set; }
    public bool ExhaustionNotified { get; set; }
    public bool LowQuotaNotified { get; set; }
    /// <summary>True when the on-disk <c>enc:v1:</c> blob could not be decrypted. <see cref="Token"/> is empty; <see cref="StoredToken"/> keeps the blob so a save cannot clobber it.</summary>
    public bool TokenDecryptFailed { get; set; }
    public string StoredToken { get; set; } = "";

    public string DisplayLabel
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(Label)) return Label.Trim();
            if (!string.IsNullOrWhiteSpace(MembershipType)) return MembershipType.Trim();
            var aid = Id.Trim();
            if (aid.StartsWith("tok_")) return "未命名账号";
            if (aid.Length > 14) return aid[..12] + "…";
            return aid.Length == 0 ? "未命名账号" : aid;
        }
    }

    public string Caption(bool isActive)
    {
        var parts = new List<string> { DisplayLabel };
        var memb = MembershipType.Trim();
        if (memb.Length > 0 && !memb.Equals(DisplayLabel, StringComparison.OrdinalIgnoreCase)) parts.Add(memb);
        if (LastRemaining is { } r) parts.Add($"剩余 {r:0}%");
        if (!string.IsNullOrWhiteSpace(LastError) && LastRemaining is null) parts.Add("已失效");
        var text = string.Join(" · ", parts);
        if (isActive) text += "  (当前)";
        return text;
    }
}

public sealed class AppConfig
{
    public string SessionToken { get; set; } = "";
    public List<Account> Accounts { get; set; } = [];
    public string ActiveAccountId { get; set; } = "";
    public int RefreshIntervalMinutes { get; set; } = 10;
    public int LowQuotaThreshold { get; set; } = 20;
    public List<int> AlertThresholds { get; set; } = [50, 20, 5];
    public bool NotifyEnabled { get; set; } = true;
    public bool NotifyExhaustionRisk { get; set; } = true;
    public bool AutostartEnabled { get; set; } = true;
    public string TrayDisplayMode { get; set; } = "ring";
    public bool LowQuotaNotified { get; set; }
    public bool AuthErrorNotified { get; set; }
    public List<int> AlertNotifiedLevels { get; set; } = [];
    public bool ExhaustionNotified { get; set; }
    /// <summary>True when config.json existed but could not be parsed. Save will not clobber it unless the user adds an account.</summary>
    public bool LoadError { get; set; }
    /// <summary>True when a stored <c>enc:v1:</c> session token could not be decrypted.</summary>
    public bool DecryptError { get; set; }
    public string StoredSessionToken { get; set; } = "";

    public Account? ActiveAccount =>
        Accounts.FirstOrDefault(a => a.Id == ActiveAccountId) ?? Accounts.FirstOrDefault();

    public (Account acc, bool created) UpsertAccount(string rawToken, string? label = null, string? membershipType = null, double? remaining = null, string? error = null, bool activate = true)
    {
        string token;
        try { token = Token.Normalize(rawToken); }
        catch { token = rawToken.Trim(); }
        if (token.Length == 0) throw new CursorApiException("Token 为空");
        var accountId = Token.AccountId(token);
        if (accountId.Length == 0) throw new CursorApiException("无法从 Token 识别账号");
        var existing = Accounts.FirstOrDefault(a => a.Id == accountId);
        var created = existing is null;
        if (existing is null)
        {
            existing = new Account { Id = accountId, Token = token };
            if (Accounts.Count == 0) CopyLegacyFlags(existing);
            Accounts.Add(existing);
        }
        existing.Token = token;
        if (label is not null) existing.Label = label.Trim();
        if (membershipType is not null) existing.MembershipType = membershipType.Trim();
        if (remaining is not null) { existing.LastRemaining = Numbers.Round2(remaining.Value); existing.LastError = ""; }
        if (error is not null) existing.LastError = error;
        if (activate) ActiveAccountId = accountId;
        SyncLegacyFields();
        return (existing, created);
    }

    public bool SetActiveAccount(string id)
    {
        if (!Accounts.Any(a => a.Id == id)) return false;
        ActiveAccountId = id;
        SyncLegacyFields();
        return true;
    }

    public bool RenameAccount(string id, string label)
    {
        var acc = Accounts.FirstOrDefault(a => a.Id == id);
        if (acc is null) return false;
        acc.Label = label.Trim();
        return true;
    }

    public bool RemoveAccount(string id)
    {
        var n = Accounts.RemoveAll(a => a.Id == id);
        if (n == 0) return false;
        if (ActiveAccountId == id) ActiveAccountId = Accounts.FirstOrDefault()?.Id ?? "";
        SyncLegacyFields();
        return true;
    }

    public HashSet<string> ExistingTokenVariants()
    {
        var skip = new HashSet<string>();
        foreach (var acc in Accounts)
        {
            foreach (var v in Token.Variants(acc.Token)) skip.Add(v);
            if (!string.IsNullOrWhiteSpace(acc.Token)) skip.Add(acc.Token.Trim());
        }
        return skip;
    }

    public void ApplySnapshot(string accountId, string? membershipType = null, double? remaining = null, string? error = null, string? updatedAt = null)
    {
        var acc = Accounts.FirstOrDefault(a => a.Id == accountId);
        if (acc is null) return;
        if (membershipType is not null) acc.MembershipType = membershipType.Trim();
        if (remaining is not null) acc.LastRemaining = Numbers.Round2(remaining.Value);
        if (error is not null) acc.LastError = error;
        else if (remaining is not null) acc.LastError = "";
        if (updatedAt is not null) acc.UpdatedAt = updatedAt;
    }

    public void SyncLegacyFields()
    {
        var acc = ActiveAccount;
        if (acc is null)
        {
            SessionToken = ActiveAccountId = "";
            Accounts = [];
            AlertNotifiedLevels = [];
            AuthErrorNotified = ExhaustionNotified = LowQuotaNotified = false;
            return;
        }
        ActiveAccountId = acc.Id;
        SessionToken = acc.Token;
        AlertNotifiedLevels = [.. acc.AlertNotifiedLevels];
        AuthErrorNotified = acc.AuthErrorNotified;
        ExhaustionNotified = acc.ExhaustionNotified;
        LowQuotaNotified = acc.LowQuotaNotified;
    }

    void CopyLegacyFlags(Account account)
    {
        account.AlertNotifiedLevels = AlertNotifiedLevels.Where(x => x is >= 1 and <= 100).OrderBy(x => x).ToList();
        account.AuthErrorNotified = AuthErrorNotified;
        account.ExhaustionNotified = ExhaustionNotified;
        account.LowQuotaNotified = LowQuotaNotified;
    }
}

public static class AppPaths
{
    public const string AppName = "CursorTokenTray";

    public static string ConfigDirectory(string? overrideDir = null)
    {
        if (!string.IsNullOrEmpty(overrideDir)) return overrideDir;
        var appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        return Path.Combine(appdata, AppName);
    }

    public static string ConfigPath(string? dir = null) => Path.Combine(ConfigDirectory(dir), "config.json");
    public static string HistoryPath(string? accountId, string? dir = null)
    {
        var root = ConfigDirectory(dir);
        var aid = (accountId ?? "").Trim();
        return aid.Length == 0 ? Path.Combine(root, "usage_history.jsonl") : Path.Combine(root, $"usage_history.{Token.SafeAccountId(aid)}.jsonl");
    }
}

public sealed class ConfigLockException : IOException
{
    public ConfigLockException() : base("无法获取配置文件锁，请稍后重试") { }
}

public static class ConfigStore
{
    const int LockWaitMs = 8000;

    public static AppConfig Load(string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        Directory.CreateDirectory(dir);
        return WithLock(dir, () => LoadUnlocked(dir), write: false);
    }

    public static void Save(AppConfig cfg, string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        Directory.CreateDirectory(dir);
        WithLock(dir, () => { SaveUnlocked(cfg, dir); return 0; }, write: true);
    }

    /// <summary>
    /// Reload from disk, apply <paramref name="mutate"/>, and save under the same lock
    /// so a long-running refresh cannot clobber settings saved in the meantime.
    /// </summary>
    public static AppConfig Update(Action<AppConfig> mutate, string? directory = null)
    {
        var dir = AppPaths.ConfigDirectory(directory);
        Directory.CreateDirectory(dir);
        return WithLock(dir, () =>
        {
            var cfg = LoadUnlocked(dir);
            if (cfg.LoadError && cfg.Accounts.Count == 0) return cfg;
            mutate(cfg);
            SaveUnlocked(cfg, dir);
            return cfg;
        }, write: true);
    }

    static AppConfig LoadUnlocked(string dir)
    {
        var path = AppPaths.ConfigPath(dir);
        if (!File.Exists(path))
        {
            var fresh = new AppConfig();
            SaveUnlocked(fresh, dir);
            return fresh;
        }
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            return Normalize(doc.RootElement);
        }
        catch
        {
            TryQuarantine(path);
            return new AppConfig { LoadError = true };
        }
    }

    static void SaveUnlocked(AppConfig cfg, string dir)
    {
        if (cfg.LoadError && cfg.Accounts.Count == 0) return;
        cfg.LoadError = false;
        var path = AppPaths.ConfigPath(dir);
        var json = JsonSerializer.Serialize(ToDict(cfg), new JsonSerializerOptions { WriteIndented = true });
        AtomicWrite(path, json);
    }

    static T WithLock<T>(string dir, Func<T> body, bool write)
    {
        Directory.CreateDirectory(dir);
        var lockPath = Path.Combine(dir, "config.lock");
        var until = DateTime.UtcNow.AddMilliseconds(LockWaitMs);
        while (true)
        {
            try
            {
                using var fs = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
                return body();
            }
            catch (IOException) when (DateTime.UtcNow < until)
            {
                Thread.Sleep(25);
            }
            catch (IOException)
            {
                if (write) throw new ConfigLockException();
                return body();
            }
        }
    }

    static void AtomicWrite(string path, string contents)
    {
        var tmp = path + ".tmp";
        var bytes = System.Text.Encoding.UTF8.GetBytes(contents);
        using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
        {
            fs.Write(bytes, 0, bytes.Length);
            fs.Flush(true);
        }
        if (File.Exists(path))
        {
            try { File.Replace(tmp, path, null); }
            catch
            {
                File.Copy(tmp, path, true);
                try { File.Delete(tmp); } catch { }
            }
        }
        else
        {
            File.Move(tmp, path, true);
        }
        RestrictToOwner(path);
    }

    static void RestrictToOwner(string path)
    {
        if (!OperatingSystem.IsWindows()) return;
        try
        {
            var user = WindowsIdentity.GetCurrent().User;
            if (user is null) return;
            var security = new FileSecurity();
            security.SetAccessRuleProtection(true, false);
            security.AddAccessRule(new FileSystemAccessRule(user, FileSystemRights.FullControl, AccessControlType.Allow));
            new FileInfo(path).SetAccessControl(security);
        }
        catch
        {
            // ACL is best-effort; a saved config is still better than failing the write.
        }
    }

    static void TryQuarantine(string path)
    {
        try { File.Copy(path, path + ".corrupt", true); } catch { }
    }

    public static AppConfig Normalize(JsonElement raw)
    {
        var cfg = new AppConfig();
        if (raw.TryGetProperty("session_token", out var st))
        {
            var stored = st.GetString() ?? "";
            if (TokenProtector.TryUnprotect(stored, out var plain))
                cfg.SessionToken = plain;
            else
            {
                cfg.SessionToken = "";
                cfg.DecryptError = true;
                cfg.StoredSessionToken = stored;
            }
        }
        if (raw.TryGetProperty("active_account_id", out var aid)) cfg.ActiveAccountId = aid.GetString() ?? "";
        if (raw.TryGetProperty("refresh_interval_minutes", out var ri) && ri.TryGetInt32(out var riv)) cfg.RefreshIntervalMinutes = Math.Max(1, riv);
        if (raw.TryGetProperty("low_quota_threshold", out var lq) && lq.TryGetInt32(out var lqv)) cfg.LowQuotaThreshold = Math.Clamp(lqv, 1, 100);
        cfg.NotifyEnabled = Bool(raw, "notify_enabled", true);
        cfg.NotifyExhaustionRisk = Bool(raw, "notify_exhaustion_risk", true);
        cfg.AutostartEnabled = Bool(raw, "autostart_enabled", true);
        cfg.LowQuotaNotified = Bool(raw, "low_quota_notified", false);
        cfg.AuthErrorNotified = Bool(raw, "auth_error_notified", false);
        cfg.ExhaustionNotified = Bool(raw, "exhaustion_notified", false);
        if (!string.IsNullOrWhiteSpace(cfg.SessionToken))
        {
            try { cfg.SessionToken = Token.Normalize(cfg.SessionToken); } catch { }
        }
        var mode = Str(raw, "tray_display_mode", "ring").Trim().ToLowerInvariant();
        cfg.TrayDisplayMode = mode is "ring" or "number" or "dot" ? mode : "ring";
        if (!raw.TryGetProperty("alert_thresholds", out _) && raw.TryGetProperty("low_quota_threshold", out _))
            cfg.AlertThresholds = [cfg.LowQuotaThreshold];
        else
            cfg.AlertThresholds = ParseThresholds(raw.TryGetProperty("alert_thresholds", out var at) ? at : default);
        cfg.AlertNotifiedLevels = ParseIntList(raw.TryGetProperty("alert_notified_levels", out var an) ? an : default);
        cfg.Accounts = ParseAccounts(raw);
        if (cfg.Accounts.Any(a => a.TokenDecryptFailed)) cfg.DecryptError = true;
        return NormalizeAccounts(cfg, raw);
    }

    public static List<int> ParseThresholds(object? value)
    {
        var nums = new List<int>();
        if (value is string s)
        {
            foreach (var p in s.Replace("，", ",").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                if (double.TryParse(p, out var d)) nums.Add((int)d);
        }
        else if (value is JsonElement el)
        {
            if (el.ValueKind == JsonValueKind.String) return ParseThresholds(el.GetString());
            if (el.ValueKind == JsonValueKind.Array)
                foreach (var x in el.EnumerateArray())
                    if (x.TryGetInt32(out var n)) nums.Add(n);
                    else if (x.TryGetDouble(out var d)) nums.Add((int)d);
        }
        else nums.AddRange([50, 20, 5]);
        var cleaned = nums.Where(n => n is >= 1 and <= 100).Distinct().OrderByDescending(x => x).ToList();
        return cleaned.Count == 0 ? [50, 20, 5] : cleaned;
    }

    static AppConfig NormalizeAccounts(AppConfig cfg, JsonElement raw)
    {
        var seen = new HashSet<string>();
        cfg.Accounts = cfg.Accounts.Where(a => seen.Add(a.Id)).ToList();
        var token = cfg.SessionToken;
        try { token = Token.Normalize(token); } catch { token = token.Trim(); }
        var activeId = cfg.ActiveAccountId.Trim();
        if (token.Length > 0)
        {
            var active = cfg.Accounts.FirstOrDefault(a => a.Id == activeId);
            if (active is null || active.Token != token)
                cfg.UpsertAccount(token, activate: true);
        }
        if (cfg.Accounts.Count > 0)
        {
            var ids = cfg.Accounts.Select(a => a.Id).ToHashSet();
            if (!ids.Contains(cfg.ActiveAccountId)) cfg.ActiveAccountId = cfg.Accounts[0].Id;
        }
        else cfg.ActiveAccountId = "";
        cfg.SyncLegacyFields();
        return cfg;
    }

    static List<Account> ParseAccounts(JsonElement raw)
    {
        if (!raw.TryGetProperty("accounts", out var arr) || arr.ValueKind != JsonValueKind.Array) return [];
        var list = new List<Account>();
        foreach (var item in arr.EnumerateArray())
        {
            var acc = Sanitize(item);
            if (acc is not null) list.Add(acc);
        }
        return list;
    }

    static Account? Sanitize(JsonElement raw)
    {
        var stored = Str(raw, "token");
        var decryptFailed = !TokenProtector.TryUnprotect(stored, out var tokenRaw);
        string token;
        try { token = decryptFailed ? "" : Token.Normalize(tokenRaw); } catch { token = tokenRaw.Trim(); }
        var id = Str(raw, "id").Trim();
        if (id.Length == 0 && token.Length > 0) id = Token.AccountId(token);
        if (id.Length == 0) return null;
        if (token.Length == 0 && !decryptFailed) return null;
        var acc = new Account { Id = id, Token = token };
        if (decryptFailed)
        {
            acc.TokenDecryptFailed = true;
            acc.StoredToken = stored;
            acc.LastError = TokenProtector.DecryptFailedMessage;
        }
        acc.Label = Str(raw, "label").Trim();
        var membership = Str(raw, "membership_type");
        if (membership.Length == 0) membership = Str(raw, "membershipType");
        acc.MembershipType = membership.Trim();
        if (!decryptFailed) acc.LastError = Str(raw, "last_error");
        acc.UpdatedAt = Str(raw, "updated_at");
        if (raw.TryGetProperty("last_remaining", out var lr) && lr.ValueKind is JsonValueKind.Number)
            acc.LastRemaining = Numbers.Round2(lr.GetDouble());
        acc.AlertNotifiedLevels = ParseIntList(raw.TryGetProperty("alert_notified_levels", out var an) ? an : default);
        acc.AuthErrorNotified = Bool(raw, "auth_error_notified", false);
        acc.ExhaustionNotified = Bool(raw, "exhaustion_notified", false);
        acc.LowQuotaNotified = Bool(raw, "low_quota_notified", false);
        return acc;
    }

    static List<int> ParseIntList(JsonElement el)
    {
        if (el.ValueKind != JsonValueKind.Array) return [];
        return el.EnumerateArray().Select(x => x.TryGetInt32(out var n) ? n : (int?)null).Where(n => n is >= 1 and <= 100).Select(n => n!.Value).Distinct().OrderBy(x => x).ToList();
    }

    static bool Bool(JsonElement raw, string key, bool fallback) =>
        raw.TryGetProperty(key, out var v) ? v.ValueKind switch { JsonValueKind.True => true, JsonValueKind.False => false, _ => fallback } : fallback;

    static string Str(JsonElement raw, string key, string fallback = "") =>
        raw.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? fallback : fallback;

    static object ToDict(AppConfig cfg) => new
    {
        session_token = TokenProtector.DiskToken(cfg.SessionToken, cfg.StoredSessionToken, cfg.DecryptError && string.IsNullOrEmpty(cfg.SessionToken)),
        accounts = cfg.Accounts.Select(a => new Dictionary<string, object?>
        {
            ["id"] = a.Id,
            ["label"] = a.Label,
            ["token"] = TokenProtector.DiskToken(a.Token, a.StoredToken, a.TokenDecryptFailed),
            ["membership_type"] = a.MembershipType,
            ["last_remaining"] = a.LastRemaining,
            ["last_error"] = a.LastError,
            ["updated_at"] = a.UpdatedAt,
            ["alert_notified_levels"] = a.AlertNotifiedLevels,
            ["auth_error_notified"] = a.AuthErrorNotified,
            ["exhaustion_notified"] = a.ExhaustionNotified,
            ["low_quota_notified"] = a.LowQuotaNotified,
        }).ToList(),
        active_account_id = cfg.ActiveAccountId,
        refresh_interval_minutes = cfg.RefreshIntervalMinutes,
        low_quota_threshold = cfg.LowQuotaThreshold,
        alert_thresholds = cfg.AlertThresholds,
        notify_enabled = cfg.NotifyEnabled,
        notify_exhaustion_risk = cfg.NotifyExhaustionRisk,
        autostart_enabled = cfg.AutostartEnabled,
        tray_display_mode = cfg.TrayDisplayMode,
        low_quota_notified = cfg.LowQuotaNotified,
        auth_error_notified = cfg.AuthErrorNotified,
        alert_notified_levels = cfg.AlertNotifiedLevels,
        exhaustion_notified = cfg.ExhaustionNotified,
    };
}
