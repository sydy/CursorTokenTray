using System.Text.Encodings.Web;
using System.Text.Json;

namespace CursorTokenCore;

public sealed record CursorInstall(string Name, string StateDb, string? LaunchPath);

public sealed record CursorAuthApplyResult(
    bool Ok,
    string Message,
    string? BackupPath = null,
    int KeysWritten = 0,
    string? InstallName = null,
    bool Relaunched = false);

/// <summary>
/// Surgical read/write of Cursor's <c>state.vscdb</c> auth keys.
/// Browser <c>web</c> cookies cannot sign the desktop app in; only a <c>session</c> JWT can.
/// </summary>
public static class CursorAuth
{
    public const string BackupSuffix = ".tray-backup";
    public const string WebTokenMessage =
        "浏览器 Cookie（JWT type=web）不能登录 Cursor 应用，写回去会把客户端登出。"
        + "请先在 Cursor 里登录该账号，再点「从 Cursor 导入」，之后才能写回切换。";
    public const string NotJwtMessage = "当前 Token 不是 Cursor 会话，无法写入客户端。请先从 Cursor 应用导入。";
    public const string ConfirmCloseMessage =
        "会先关闭 Cursor，再把当前账号写入客户端。请先保存未提交的改动。未保存的文件不会被强制结束。";

    public static readonly string[] OwnedKeys =
    [
        "cursorAuth/accessToken",
        "cursorAuth/refreshToken",
        "cursorAuth/cachedEmail",
        "cursorAuth/cachedSignUpType",
        "cursorAuth/cachedScopedProfile",
        "cursorAuth/stripeMembershipType",
        "cursorAuth/stripeSubscriptionStatus",
        "glass.lastSignedInAuthId",
    ];

    public static readonly string[] OptionalUpdateKeys = ["cursorAuth/cachedAccessToken"];

    public static bool CanWrite(string token) => Token.CanWriteToCursor(token);

    public static (Dictionary<string, string>? Values, string Error) BuildValues(
        string token,
        string? email = null,
        string? membershipType = null,
        string? displayName = null)
    {
        var jwt = Token.ExtractJwt(token);
        if (!Token.LooksLikeJwt(jwt))
            return (null, NotJwtMessage);
        if (Token.JwtType(jwt) == "web")
            return (null, WebTokenMessage);

        var values = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["cursorAuth/accessToken"] = jwt,
            ["cursorAuth/refreshToken"] = jwt,
            ["cursorAuth/cachedSignUpType"] = "Auth_0",
        };

        var sub = Token.JwtSubject(jwt).Trim();
        if (sub.Length == 0)
        {
            var uid = Token.AccountId(token);
            if (uid.Length > 0 && !uid.StartsWith("tok_", StringComparison.Ordinal))
                sub = "auth0|" + uid;
        }
        if (sub.Length > 0) values["glass.lastSignedInAuthId"] = sub;

        var mail = FirstNonEmpty(Token.JwtClaim(jwt, "email"), email);
        if (LooksLikeEmail(mail)) values["cursorAuth/cachedEmail"] = mail.Trim();

        var name = FirstNonEmpty(displayName, mail);
        if (!string.IsNullOrWhiteSpace(name))
            values["cursorAuth/cachedScopedProfile"] = JsonSerializer.Serialize(
                new Dictionary<string, string> { ["displayName"] = name.Trim() },
                new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });

        var (plan, status) = StripePlan(membershipType);
        if (plan.Length > 0)
        {
            values["cursorAuth/stripeMembershipType"] = plan;
            values["cursorAuth/stripeSubscriptionStatus"] = status;
        }
        return (values, "");
    }

    public static (string Membership, string Status) StripePlan(string? membershipType)
    {
        var raw = (membershipType ?? "").Trim();
        if (raw.Length == 0 || raw == "未知") return ("", "");
        var lower = raw.ToLowerInvariant();
        var key = lower switch
        {
            "pro" or "pro+" or "pro_plus" => lower == "pro+" ? "pro_plus" : lower,
            "ultra" => "ultra",
            "free" or "hobby" or "unpaid" => "free",
            "enterprise" or "enterprise_trial" => lower,
            "team" or "teams" => "team",
            "business" => "business",
            _ => "",
        };
        if (key.Length == 0)
        {
            if (raw.Equals("Pro", StringComparison.OrdinalIgnoreCase)) key = "pro";
            else if (raw.Equals("Pro+", StringComparison.OrdinalIgnoreCase)) key = "pro_plus";
            else if (raw.Equals("Ultra", StringComparison.OrdinalIgnoreCase)) key = "ultra";
            else if (raw.Equals("Free", StringComparison.OrdinalIgnoreCase) || raw.Equals("Hobby", StringComparison.OrdinalIgnoreCase)) key = "free";
            else if (raw.Equals("Enterprise", StringComparison.OrdinalIgnoreCase)) key = "enterprise";
            else if (raw.Equals("Team", StringComparison.OrdinalIgnoreCase)) key = "team";
            else if (raw.Equals("Business", StringComparison.OrdinalIgnoreCase)) key = "business";
            else key = lower;
        }
        var unpaid = key is "free" or "hobby" or "unpaid";
        return (unpaid ? "free" : key, unpaid ? "unpaid" : "active");
    }

    public static Dictionary<string, string> ReadValues(string dbPath, IEnumerable<string>? keys = null)
    {
        var found = new Dictionary<string, string>(StringComparer.Ordinal);
        if (!File.Exists(dbPath)) return found;
        var want = (keys ?? OwnedKeys.Concat(OptionalUpdateKeys)).ToHashSet(StringComparer.Ordinal);
        try
        {
            using var conn = Open(dbPath, readOnly: true);
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT key, value FROM ItemTable";
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                var key = r.IsDBNull(0) ? "" : r.GetString(0);
                if (!want.Contains(key)) continue;
                var value = r.IsDBNull(1) ? "" : r.GetValue(1)?.ToString() ?? "";
                if (key.Length > 0) found[key] = value;
            }
        }
        catch { }
        return found;
    }

    public static CursorAuthApplyResult WriteValues(string dbPath, IReadOnlyDictionary<string, string> values, bool backup = true)
    {
        if (string.IsNullOrWhiteSpace(dbPath) || !File.Exists(dbPath))
            return new CursorAuthApplyResult(false, "未找到 Cursor 状态库，请先至少启动并登录过一次 Cursor。");
        if (values.Count == 0)
            return new CursorAuthApplyResult(false, "没有可写入的登录态。");

        string? backupPath = null;
        if (backup)
        {
            try { backupPath = Backup(dbPath); }
            catch (Exception ex)
            {
                return new CursorAuthApplyResult(false, "备份 Cursor 状态库失败，已中止写入：" + ex.Message);
            }
        }

        try
        {
            using var conn = Open(dbPath, readOnly: false);
            using var tx = conn.BeginTransaction();
            var existing = new HashSet<string>(StringComparer.Ordinal);
            using (var list = conn.CreateCommand())
            {
                list.Transaction = tx;
                list.CommandText = "SELECT key FROM ItemTable";
                using var r = list.ExecuteReader();
                while (r.Read())
                {
                    var key = r.IsDBNull(0) ? "" : r.GetString(0);
                    if (key.Length > 0) existing.Add(key);
                }
            }

            var written = 0;
            using var cmd = conn.CreateCommand();
            cmd.Transaction = tx;
            cmd.CommandText = "INSERT OR REPLACE INTO ItemTable(key, value) VALUES ($k, $v)";
            var pk = cmd.Parameters.Add("$k", Microsoft.Data.Sqlite.SqliteType.Text);
            var pv = cmd.Parameters.Add("$v", Microsoft.Data.Sqlite.SqliteType.Text);
            foreach (var key in OwnedKeys)
            {
                if (!values.TryGetValue(key, out var value) || string.IsNullOrEmpty(value)) continue;
                pk.Value = key;
                pv.Value = value;
                cmd.ExecuteNonQuery();
                written++;
            }
            foreach (var key in OptionalUpdateKeys)
            {
                if (!existing.Contains(key)) continue;
                if (!values.TryGetValue("cursorAuth/accessToken", out var jwt) || jwt.Length == 0) continue;
                pk.Value = key;
                pv.Value = jwt;
                cmd.ExecuteNonQuery();
                written++;
            }
            tx.Commit();
            return new CursorAuthApplyResult(true, $"已写入 Cursor（{written} 项）", backupPath, written);
        }
        catch (Exception ex)
        {
            return new CursorAuthApplyResult(false, "写入 Cursor 状态库失败：" + ex.Message, backupPath);
        }
    }

    public static string Backup(string dbPath)
    {
        var dest = dbPath + BackupSuffix;
        File.Copy(dbPath, dest, true);
        foreach (var suffix in new[] { "-wal", "-shm" })
        {
            var side = dbPath + suffix;
            if (File.Exists(side))
            {
                try { File.Copy(side, dest + suffix, true); } catch { }
            }
        }
        return dest;
    }

    public static IEnumerable<CursorInstall> FindInstalls(string? appData = null, string? localAppData = null, string? home = null)
    {
        var roaming = appData
            ?? Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (string.IsNullOrEmpty(roaming) && !string.IsNullOrEmpty(home))
            roaming = Path.Combine(home, "AppData", "Roaming");
        var local = localAppData
            ?? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrEmpty(local) && !string.IsNullOrEmpty(home))
            local = Path.Combine(home, "AppData", "Local");

        foreach (var (name, folder) in new[]
        {
            ("Cursor", "Cursor"),
            ("Cursor Nightly", "Cursor Nightly"),
            ("Cursor Insiders", "Cursor - Insiders"),
        })
        {
            var db = Path.Combine(roaming, folder, "User", "globalStorage", "state.vscdb");
            if (!File.Exists(db)) continue;
            yield return new CursorInstall(name, db, FindLaunchPath(name, local));
        }
    }

    public static CursorInstall? ResolveTarget(IEnumerable<CursorInstall>? installs = null)
    {
        var list = (installs ?? FindInstalls()).ToList();
        if (list.Count == 0) return null;
        foreach (var inst in list)
        {
            if (IsRunning(inst)) return inst;
        }
        return list[0];
    }

    public static bool IsRunning(CursorInstall install)
    {
        try
        {
            foreach (var proc in System.Diagnostics.Process.GetProcesses())
            {
                try
                {
                    if (!IsCursorProcess(proc, install)) continue;
                    if (!proc.HasExited) return true;
                }
                catch { }
            }
        }
        catch { }
        return false;
    }

    public static bool RequestClose(CursorInstall install)
    {
        var any = false;
        try
        {
            foreach (var proc in System.Diagnostics.Process.GetProcesses())
            {
                try
                {
                    if (!IsCursorProcess(proc, install)) continue;
                    if (proc.HasExited) continue;
                    any = true;
                    try { proc.CloseMainWindow(); } catch { }
                }
                catch { }
            }
        }
        catch { }
        return any;
    }

    public static bool WaitUntilGone(CursorInstall install, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (!IsRunning(install)) return true;
            Thread.Sleep(250);
        }
        return !IsRunning(install);
    }

    public static bool Launch(CursorInstall install)
    {
        var path = install.LaunchPath;
        if (string.IsNullOrEmpty(path) || !File.Exists(path))
            path = FindLaunchPath(install.Name, Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
        if (string.IsNullOrEmpty(path) || !File.Exists(path)) return false;
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path) { UseShellExecute = true });
            return true;
        }
        catch { return false; }
    }

    public static CursorAuthApplyResult Apply(
        string token,
        string? email = null,
        string? membershipType = null,
        string? displayName = null,
        bool closeIfRunning = true,
        bool relaunch = true,
        TimeSpan? wait = null,
        IEnumerable<CursorInstall>? installs = null,
        Func<CursorInstall, bool>? isRunning = null,
        Func<CursorInstall, bool>? requestClose = null,
        Func<CursorInstall, bool>? waitGone = null,
        Func<CursorInstall, bool>? launch = null,
        Func<string, IReadOnlyDictionary<string, string>, bool, CursorAuthApplyResult>? write = null)
    {
        var built = BuildValues(token, email, membershipType, displayName);
        if (built.Values is null) return new CursorAuthApplyResult(false, built.Error);

        var target = ResolveTarget(installs);
        if (target is null)
            return new CursorAuthApplyResult(false, "未找到 Cursor 状态库，请先至少启动并登录过一次 Cursor。");

        var runningFn = isRunning ?? IsRunning;
        var closeFn = requestClose ?? RequestClose;
        var goneFn = waitGone ?? (inst => WaitUntilGone(inst, wait ?? TimeSpan.FromSeconds(10)));
        var launchFn = launch ?? Launch;
        var writeFn = write ?? WriteValues;

        if (runningFn(target))
        {
            if (!closeIfRunning)
                return new CursorAuthApplyResult(false, "Cursor 正在运行。请先关闭后再写入，以免冲掉未保存的文件。", InstallName: target.Name);
            closeFn(target);
            if (!goneFn(target))
                return new CursorAuthApplyResult(false,
                    "Cursor 没有退出（可能有未保存的改动）。请先手动关闭后再试，不会强制结束。",
                    InstallName: target.Name);
        }

        var written = writeFn(target.StateDb, built.Values, true);
        if (!written.Ok) return written with { InstallName = target.Name };

        var started = false;
        if (relaunch) started = launchFn(target);
        var msg = written.Message + " · " + target.Name;
        if (relaunch)
            msg += started ? "，已重新打开。" : "。请手动打开 Cursor。";
        else
            msg += "。请重新打开 Cursor 后生效。";
        return written with { Message = msg, InstallName = target.Name, Relaunched = started };
    }

    static Microsoft.Data.Sqlite.SqliteConnection Open(string dbPath, bool readOnly)
    {
        var conn = new Microsoft.Data.Sqlite.SqliteConnection(new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = readOnly
                ? Microsoft.Data.Sqlite.SqliteOpenMode.ReadOnly
                : Microsoft.Data.Sqlite.SqliteOpenMode.ReadWrite,
        }.ToString());
        conn.Open();
        using var pragma = conn.CreateCommand();
        pragma.CommandText = "PRAGMA busy_timeout = 5000";
        pragma.ExecuteNonQuery();
        return conn;
    }

    static bool IsCursorProcess(System.Diagnostics.Process proc, CursorInstall install)
    {
        var name = proc.ProcessName;
        if (!name.Contains("Cursor", StringComparison.OrdinalIgnoreCase)) return false;
        string? file = null;
        try { file = proc.MainModule?.FileName; } catch { }
        if (string.IsNullOrEmpty(file))
        {
            // If we cannot see the path, only match the default Cursor install by process name.
            return install.Name == "Cursor" && name.Equals("Cursor", StringComparison.OrdinalIgnoreCase);
        }
        var hay = file.Replace('/', Path.DirectorySeparatorChar);
        if (install.Name.Contains("Nightly", StringComparison.OrdinalIgnoreCase))
            return hay.Contains("Cursor Nightly", StringComparison.OrdinalIgnoreCase);
        if (install.Name.Contains("Insiders", StringComparison.OrdinalIgnoreCase))
            return hay.Contains("Cursor - Insiders", StringComparison.OrdinalIgnoreCase)
                || hay.Contains("Cursor Insiders", StringComparison.OrdinalIgnoreCase);
        return hay.Contains($"{Path.DirectorySeparatorChar}Cursor{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase)
            || hay.EndsWith($"{Path.DirectorySeparatorChar}Cursor.exe", StringComparison.OrdinalIgnoreCase);
    }

    static string? FindLaunchPath(string name, string localAppData)
    {
        if (string.IsNullOrEmpty(localAppData)) return null;
        var folders = name.Contains("Nightly", StringComparison.OrdinalIgnoreCase)
            ? new[] { "cursor nightly", "Cursor Nightly" }
            : name.Contains("Insiders", StringComparison.OrdinalIgnoreCase)
                ? new[] { "cursor insiders", "Cursor Insiders", "cursor-insiders" }
                : new[] { "cursor", "Cursor" };
        foreach (var folder in folders)
        {
            var candidate = Path.Combine(localAppData, "Programs", folder, "Cursor.exe");
            if (File.Exists(candidate)) return candidate;
        }
        return null;
    }

    static string FirstNonEmpty(params string?[] values)
    {
        foreach (var v in values)
        {
            if (!string.IsNullOrWhiteSpace(v)) return v!;
        }
        return "";
    }

    public static bool LooksLikeEmail(string? value)
    {
        var text = (value ?? "").Trim();
        var at = text.IndexOf('@');
        return at > 0 && at < text.Length - 1 && !text.Contains(' ');
    }
}
