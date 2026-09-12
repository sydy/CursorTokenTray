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
}

public sealed class SyncSnapshot
{
    public int Version { get; set; } = 1;
    public string UpdatedAt { get; set; } = "";
    public string DeviceId { get; set; } = "";
    public string ActiveAccountId { get; set; } = "";
    public List<SyncAccount> Accounts { get; set; } = [];
    public List<DeletedAccount> Deleted { get; set; } = [];
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
    };

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
        };
    }

    public static string SnapshotIdentity(SyncSnapshot snap)
    {
        var accounts = snap.Accounts.OrderBy(a => a.Id, StringComparer.Ordinal)
            .Select(a => $"{a.Id}\n{a.Label}\n{a.Token}\n{a.MembershipType}\n{a.AccountKind}\n{a.TempStartAt}\n{a.TempValidDays}\n{a.TempValidHours}\n{a.ActualCny}\n{a.Channel}\n{a.SyncUpdatedAt}");
        var deleted = snap.Deleted.OrderBy(d => d.Id, StringComparer.Ordinal)
            .Select(d => $"{d.Id}\n{d.DeletedAt}");
        return $"{snap.ActiveAccountId}\n{string.Join("|", accounts)}\n{string.Join("|", deleted)}";
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
            var cmp = CompareIso(acc.SyncUpdatedAt, prev.SyncUpdatedAt);
            if (cmp > 0) chosen[acc.Id] = acc;
            else if (cmp == 0 && prev.Token.Length == 0 && acc.Token.Length > 0) chosen[acc.Id] = acc;
        }

        foreach (var id in tombstones.Keys.ToList())
            if (chosen.ContainsKey(id)) tombstones.Remove(id);

        var active = CompareIso(remote.UpdatedAt, local.UpdatedAt) > 0 ? remote.ActiveAccountId : local.ActiveAccountId;
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
        };
    }

    public static bool ApplySnapshotToConfig(AppConfig cfg, SyncSnapshot snap)
    {
        string Before() => string.Join("|", cfg.Accounts.Select(a =>
            $"{a.Id}\n{a.Token}\n{a.Label}\n{a.MembershipType}\n{a.AccountKind}\n{a.TempStartAt}\n{a.TempValidDays}\n{a.TempValidHours}\n{a.ActualCny}\n{a.Channel}\n{a.SyncUpdatedAt}"));
        var before = Before();
        var existing = cfg.Accounts.ToDictionary(a => a.Id, StringComparer.Ordinal);
        var merged = new List<Account>();
        foreach (var row in snap.Accounts)
        {
            var ident = SnapshotAccount(row);
            if (ident.Id.Length == 0 || ident.Token.Length == 0) continue;
            if (!existing.TryGetValue(ident.Id, out var old))
            {
                merged.Add(new Account
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
                });
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
            merged.Add(old);
        }
        cfg.Accounts = merged;
        cfg.DeletedAccounts = SanitizeDeleted(snap.Deleted);
        var ids = merged.Select(a => a.Id).ToHashSet(StringComparer.Ordinal);
        if (ids.Contains(snap.ActiveAccountId)) cfg.ActiveAccountId = snap.ActiveAccountId;
        else cfg.ActiveAccountId = merged.Count > 0 ? merged[0].Id : "";
        cfg.SyncLegacyFields();
        return before != Before();
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
            return $"{{\"id\":{Q(a.Id)},\"label\":{Q(a.Label)},\"membership_type\":{Q(a.MembershipType)},\"sync_updated_at\":{Q(a.SyncUpdatedAt)},\"token\":{Q(a.Token)}{extra}}}";
        }));
        var deleted = string.Join(",", snap.Deleted.Select(d =>
            $"{{\"deleted_at\":{Q(d.DeletedAt)},\"id\":{Q(d.Id)}}}")
        );
        return $"{{\"accounts\":[{accounts}],\"active_account_id\":{Q(snap.ActiveAccountId)},\"deleted\":[{deleted}],\"device_id\":{Q(snap.DeviceId)},\"updated_at\":{Q(snap.UpdatedAt)},\"version\":{snap.Version}}}";
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
            ["format"] = Format,
            ["kdf"] = Kdf,
            ["iterations"] = iterations,
            ["salt"] = Convert.ToBase64String(saltB),
            ["nonce"] = Convert.ToBase64String(nonceB),
            ["ciphertext"] = Convert.ToBase64String(blob),
        };
    }

    public static SyncSnapshot DecryptEnvelope(JsonElement envelope, string passphrase)
    {
        if (Str(envelope, "format") != Format) throw new CursorApiException("不是 CursorTokenTray 账号同步文件");
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
        return snap;
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
        if (!cfg.SyncEnabled) return "未启用多端同步";
        if (string.IsNullOrWhiteSpace(cfg.SyncPath)) return "请选择同步文件夹";
        if (string.IsNullOrWhiteSpace(cfg.SyncSecret)) return "请设置同步口令";
        return "";
    }

    public static SyncStatus Reconcile(AppConfig cfg, DateTimeOffset? now = null, bool write = true)
    {
        var status = new SyncStatus();
        var reason = SyncReady(cfg);
        if (reason.Length > 0)
        {
            status.Message = reason;
            cfg.SyncLastError = reason;
            return status;
        }
        var path = ResolveSyncPath(cfg.SyncPath);
        status.Path = path;
        EnsureDeviceId(cfg);
        var stamp = NowIso(now);
        var local = SnapshotFromConfig(cfg);
        local.DeviceId = cfg.SyncDeviceId;
        try
        {
            var envelope = ReadEnvelope(path);
            var remote = envelope is { } env
                ? DecryptEnvelope(env, cfg.SyncSecret)
                : new SyncSnapshot();
            var merged = MergeSnapshots(local, remote);
            var changed = ApplySnapshotToConfig(cfg, merged);
            if (write && SnapshotIdentity(merged) != SnapshotIdentity(remote))
            {
                merged.UpdatedAt = stamp;
                merged.DeviceId = cfg.SyncDeviceId;
                WriteEnvelope(path, EncryptEnvelope(merged, cfg.SyncSecret));
                status.Pushed = true;
            }
            cfg.SyncLastAt = stamp;
            cfg.SyncLastError = "";
            status.Ok = true;
            status.Changed = changed;
            status.Message = changed && status.Pushed ? "已合并并对齐同步文件"
                : changed ? "已从同步文件导入账号"
                : status.Pushed ? "已写入同步文件"
                : "账号已与同步文件一致";
            return status;
        }
        catch (Exception ex)
        {
            var message = string.IsNullOrWhiteSpace(ex.Message) ? "同步失败" : ex.Message;
            cfg.SyncLastError = message;
            status.Message = message;
            return status;
        }
    }

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
