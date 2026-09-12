using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CursorTokenCore;

public static class CloudSyncApi
{
    public const string BaseUrl = "https://sync.harker.cn";
}

public static class CloudSync
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };
    static readonly JsonSerializerOptions JsonOpt = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static void ApplySession(AppConfig cfg, string email, string password, string access, string refresh)
    {
        cfg.CloudEmail = (email ?? "").Trim().ToLowerInvariant();
        cfg.CloudAccessToken = access ?? "";
        cfg.CloudRefreshToken = refresh ?? "";
        cfg.SyncSecret = password ?? "";
        cfg.SyncEnabled = cfg.CloudLoggedIn;
        cfg.SyncLastError = "";
        cfg.SyncSecretDecryptFailed = false;
    }

    public static void ClearSession(AppConfig cfg, bool keepEmail = true)
    {
        if (!keepEmail) cfg.CloudEmail = "";
        cfg.CloudAccessToken = "";
        cfg.CloudRefreshToken = "";
        cfg.SyncSecret = "";
        cfg.CloudRevision = 0;
        cfg.SyncEnabled = false;
    }

    public static SyncStatus Reconcile(AppConfig cfg, DateTimeOffset? now = null, bool write = true) =>
        ReconcileAsync(cfg, now, write).GetAwaiter().GetResult();

    public static async Task<(string Email, string Access, string Refresh)> RegisterAsync(string email, string password, CancellationToken ct = default)
    {
        var payload = await SendAsync("POST", "/v1/auth/register", null, new { email, password }, ct);
        return ReadAuth(payload);
    }

    public static async Task<(string Email, string Access, string Refresh)> LoginAsync(string email, string password, CancellationToken ct = default)
    {
        var payload = await SendAsync("POST", "/v1/auth/login", null, new { email, password }, ct);
        return ReadAuth(payload);
    }

    public static async Task LogoutAsync(AppConfig cfg, CancellationToken ct = default)
    {
        var refresh = cfg.CloudRefreshToken;
        if (!string.IsNullOrWhiteSpace(refresh))
        {
            try { await SendAsync("POST", "/v1/auth/logout", null, new { refresh_token = refresh }, ct); }
            catch { }
        }
        ClearSession(cfg);
    }

    public static async Task<SyncStatus> ReconcileAsync(AppConfig cfg, DateTimeOffset? now = null, bool write = true, CancellationToken ct = default)
    {
        var status = new SyncStatus { Path = CloudSyncApi.BaseUrl };
        var reason = AccountSync.SyncReady(cfg);
        if (reason.Length > 0)
        {
            status.Message = reason;
            cfg.SyncLastError = reason;
            return status;
        }
        AccountSync.EnsureDeviceId(cfg);
        var stamp = AccountSync.NowIso(now);
        var passphrase = cfg.SyncSecret;
        var local = AccountSync.SnapshotFromConfig(cfg);
        local.DeviceId = cfg.SyncDeviceId;
        try
        {
            using var got = await AuthedAsync(cfg, HttpMethod.Get, "/v1/sync", null, ct);
            var revision = got.RootElement.TryGetProperty("revision", out var rev) && rev.TryGetInt32(out var n) ? n : 0;
            var remote = ParseRemote(got.RootElement, passphrase);
            var merged = AccountSync.MergeSnapshots(local, remote);
            var changed = AccountSync.ApplySnapshotToConfig(cfg, merged);
            if (write && AccountSync.SnapshotIdentity(merged) != AccountSync.SnapshotIdentity(remote))
            {
                merged.UpdatedAt = stamp;
                merged.DeviceId = cfg.SyncDeviceId;
                var envelope = AccountSync.EncryptEnvelope(merged, passphrase);
                using var put = await AuthedAsync(cfg, HttpMethod.Put, "/v1/sync", new { revision, envelope }, ct);
                if (put.RootElement.TryGetProperty("revision", out var next) && next.TryGetInt32(out var nextRev))
                    cfg.CloudRevision = nextRev;
                else
                    cfg.CloudRevision = revision + 1;
                status.Pushed = true;
            }
            else cfg.CloudRevision = revision;
            cfg.SyncLastAt = stamp;
            cfg.SyncLastError = "";
            status.Ok = true;
            status.Changed = changed;
            status.Message = changed && status.Pushed ? "已合并并对齐云端"
                : changed ? "已从云端导入账号和设置"
                : status.Pushed ? "已上传到云端"
                : "账号和设置已与云端一致";
            return status;
        }
        catch (CursorApiException ex) when (ex.StatusCode == 401)
        {
            ClearSession(cfg);
            status.Message = "登录已过期，请重新登录";
            cfg.SyncLastError = status.Message;
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

    static SyncSnapshot ParseRemote(JsonElement root, string passphrase)
    {
        if (!root.TryGetProperty("envelope", out var env) || env.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
            return new SyncSnapshot();
        return AccountSync.DecryptEnvelope(env, passphrase);
    }

    static (string Email, string Access, string Refresh) ReadAuth(JsonDocument payload)
    {
        var root = payload.RootElement;
        var access = root.TryGetProperty("access_token", out var a) ? a.GetString() ?? "" : "";
        var refresh = root.TryGetProperty("refresh_token", out var r) ? r.GetString() ?? "" : "";
        var email = root.TryGetProperty("email", out var e) ? e.GetString() ?? "" : "";
        if (access.Length == 0) throw new CursorApiException("登录失败");
        return (email, access, refresh);
    }

    static async Task<JsonDocument> AuthedAsync(AppConfig cfg, HttpMethod method, string path, object? body, CancellationToken ct)
    {
        try
        {
            return await SendAsync(method.Method, path, cfg.CloudAccessToken, body, ct);
        }
        catch (CursorApiException ex) when (ex.StatusCode == 401)
        {
            if (!await RefreshAsync(cfg, ct)) throw;
            return await SendAsync(method.Method, path, cfg.CloudAccessToken, body, ct);
        }
    }

    static async Task<bool> RefreshAsync(AppConfig cfg, CancellationToken ct)
    {
        var refresh = (cfg.CloudRefreshToken ?? "").Trim();
        if (refresh.Length == 0) return false;
        try
        {
            using var doc = await SendAsync("POST", "/v1/auth/refresh", null, new { refresh_token = refresh }, ct);
            var root = doc.RootElement;
            cfg.CloudAccessToken = root.TryGetProperty("access_token", out var a) ? a.GetString() ?? "" : "";
            if (root.TryGetProperty("refresh_token", out var r))
                cfg.CloudRefreshToken = r.GetString() ?? cfg.CloudRefreshToken ?? "";
            return cfg.CloudAccessToken.Length > 0;
        }
        catch
        {
            ClearSession(cfg);
            return false;
        }
    }

    static async Task<JsonDocument> SendAsync(string method, string path, string? access, object? body, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(new HttpMethod(method), CloudSyncApi.BaseUrl.TrimEnd('/') + path);
        req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (!string.IsNullOrWhiteSpace(access))
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", access);
        if (body is not null)
            req.Content = new StringContent(JsonSerializer.Serialize(body, JsonOpt), Encoding.UTF8, "application/json");
        HttpResponseMessage res;
        try
        {
            res = await Http.SendAsync(req, ct);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new CursorApiException("无法连接同步服务器");
        }
        catch (HttpRequestException)
        {
            throw new CursorApiException("无法连接同步服务器");
        }
        using (res)
        {
        var text = await res.Content.ReadAsStringAsync(ct);
        JsonDocument doc;
        try { doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text); }
        catch { doc = JsonDocument.Parse("{}"); }
        if ((int)res.StatusCode >= 400)
        {
            var detail = doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String
                ? d.GetString()
                : null;
            throw new CursorApiException(string.IsNullOrWhiteSpace(detail) ? "同步失败" : detail!, (int)res.StatusCode);
        }
        return doc;
        }
    }
}
