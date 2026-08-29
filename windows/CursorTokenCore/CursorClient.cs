using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace CursorTokenCore;

public sealed class CursorClient
{
    readonly HttpClient _http;
    public CursorClient(HttpClient? http = null)
    {
        // Default HttpClientHandler stores Set-Cookie in a shared jar, which mixes
        // sessions when one client refreshes multiple accounts.
        _http = http ?? new HttpClient(new HttpClientHandler { UseCookies = false })
        {
            Timeout = TimeSpan.FromSeconds(90),
        };
    }

    public async Task<UsageSnapshot> FetchUsageSummary(string sessionToken, double timeout = 30, CancellationToken ct = default)
    {
        var token = Token.Normalize(sessionToken);
        if (token.Length == 0) throw new CursorApiException("未配置 Session Token", 401);
        CursorApiException? last = null;
        UsageSnapshot? snap = null;
        foreach (var endpoint in UsageParser.UsageEndpoints)
        {
            try
            {
                var payload = await RequestJson("GET", endpoint, token, null, timeout, ct);
                snap = UsageParser.ParseUsageSummary(payload);
                break;
            }
            catch (CursorApiException err)
            {
                last = err;
                if (err.StatusCode is not (404 or 405)) throw;
            }
        }
        if (snap is null) throw last ?? new CursorApiException("接口返回格式异常");
        try { await AttachAggregated(snap, token, timeout, ct); } catch { }
        return snap;
    }

    async Task AttachAggregated(UsageSnapshot snap, string token, double timeout, CancellationToken ct)
    {
        var startMs = UsageParser.IsoToMs(snap.BillingCycleStart);
        if (startMs is null) return;
        var endMs = UsageParser.IsoToMs(snap.BillingCycleEnd) ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        if (endMs > nowMs) endMs = nowMs;
        if (endMs < startMs) endMs = startMs.Value;
        var body = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["teamId"] = UsageParser.TeamId(snap.Raw),
            ["startDate"] = startMs.Value,
            ["endDate"] = endMs,
        });
        var payload = await RequestJson("POST", UsageParser.AggregatedEndpoint, token, body, timeout, ct);
        var parsed = UsageParser.ParseAggregatedUsage(payload, snap.AutoPercentUsed, snap.ApiPercentUsed);
        snap.ModelUsages = parsed.models;
        snap.TotalTokens = parsed.total;
    }

    public async Task<(List<UsageEvent> events, int totalCount, bool truncated)> FetchUsageEvents(
        string sessionToken,
        long startMs,
        long endMs,
        int? teamId,
        int? userId,
        long? stopAtMs,
        int maxPages = UsageParser.UsageEventsMaxPages,
        int pageSize = UsageParser.UsageEventsPageSize,
        double timeout = 30,
        CancellationToken ct = default)
    {
        var token = Token.Normalize(sessionToken);
        if (token.Length == 0) throw new CursorApiException("未配置 Session Token", 401);
        var all = new List<UsageEvent>();
        var total = 0;
        var truncated = false;
        var pages = Math.Max(1, maxPages);
        var size = Math.Clamp(pageSize, 1, 200);
        for (var page = 1; page <= pages; page++)
        {
            var fields = new Dictionary<string, object?>
            {
                ["startDate"] = startMs,
                ["endDate"] = endMs,
                ["page"] = page,
                ["pageSize"] = size,
            };
            if (teamId is > 0) fields["teamId"] = teamId.Value;
            if (userId is > 0) fields["userId"] = userId.Value;
            var body = JsonSerializer.Serialize(fields);
            var payload = await RequestJson("POST", UsageParser.FilteredEndpoint, token, body, timeout, ct);
            var parsed = UsageEvents.ParsePage(payload);
            if (page == 1) total = parsed.totalCount;
            if (parsed.events.Count == 0) break;
            all.AddRange(parsed.events);
            var oldest = parsed.events.Min(e => e.TimestampMs);
            if (stopAtMs is { } watermark && oldest <= watermark) break;
            if (parsed.events.Count < size) break;
            if (total > 0 && all.Count >= total) break;
            if (page == pages && (parsed.events.Count == size) && (total == 0 || all.Count < total))
                truncated = true;
        }
        return (UsageEvents.Merge(all, []), total, truncated);
    }

    async Task<JsonBag> RequestJson(string method, string endpoint, string token, string? body, double timeout, CancellationToken ct)
    {
        Exception? last = null;
        for (var attempt = 0; attempt < 3; attempt++)
        {
            using var req = new HttpRequestMessage(new HttpMethod(method), UsageParser.CursorBase + endpoint);
            req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            req.Headers.TryAddWithoutValidation("Cookie", $"{Token.CookieName}={token}");
            req.Headers.TryAddWithoutValidation("Origin", "https://cursor.com");
            req.Headers.TryAddWithoutValidation("Referer", "https://cursor.com/dashboard");
            req.Headers.TryAddWithoutValidation("User-Agent", "Mozilla/5.0 CursorTokenTray/1.0");
            if (body is not null) req.Content = new StringContent(body, Encoding.UTF8, "application/json");
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(timeout));
            HttpResponseMessage resp;
            try { resp = await _http.SendAsync(req, cts.Token); }
            catch (Exception ex)
            {
                last = new CursorApiException("网络错误: " + ex.Message);
                if (attempt == 2) throw last;
                await Task.Delay(250 << attempt, ct);
                continue;
            }
            using (resp)
            {
            var status = (int)resp.StatusCode;
            var text = await resp.Content.ReadAsStringAsync(ct);
            if (status is 401 or 403) throw new CursorApiException(CursorApiException.AuthMessage, status);
            if (status is 404 or 405) throw new CursorApiException($"HTTP {status}", status);
            if (status == 429 || status >= 500)
            {
                last = new CursorApiException($"HTTP {status}", status);
                if (attempt == 2) throw last;
                await Task.Delay(250 << attempt, ct);
                continue;
            }
            if (status >= 400)
            {
                var safe = new string(text.Take(200).Select(ch => ch <= 127 ? ch : '?').ToArray());
                throw new CursorApiException(string.IsNullOrEmpty(safe) ? $"HTTP {status}" : $"HTTP {status}: {safe}", status);
            }
            if (string.IsNullOrEmpty(text)) return JsonBag.Null;
            try { return JsonBag.Parse(text); }
            catch { throw new CursorApiException("接口返回非 JSON"); }
            }
        }
        throw last ?? new CursorApiException("网络错误");
    }
}

public sealed record CookieCandidate(string Browser, string Profile, string TokenValue, long LastUpdate);
public sealed record ImportResult(bool Ok, string Token = "", string Browser = "", string Profile = "", double? RemainingPercent = null, string MembershipType = "", string Message = "");

public static class SessionImporter
{
    public static string[] DefaultPreferBrowsers() => ["cursor-app", "firefox", "firefox-dev", "edge", "chrome"];
    public static string[]? OnlyBrowsers(string? prefer) =>
        prefer is "firefox" or "firefox-dev" or "firefox-nightly" or "librewolf" or "waterfox" or "zen"
            ? ["firefox", "firefox-dev", "firefox-nightly", "librewolf", "waterfox", "zen"]
            : prefer == "cursor-app" ? ["cursor-app"] : null;

    public static IEnumerable<string> CursorStateDbPaths()
    {
        var appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        yield return Path.Combine(appdata, "Cursor", "User", "globalStorage", "state.vscdb");
        yield return Path.Combine(appdata, "Cursor Nightly", "User", "globalStorage", "state.vscdb");
    }

    public static async Task<ImportResult> ImportAndValidate(CursorClient client, string[]? prefer = null, string[]? only = null, HashSet<string>? skipTokens = null, CancellationToken ct = default)
    {
        prefer ??= DefaultPreferBrowsers();
        var candidates = FindCandidates(only).ToList();
        if (candidates.Count == 0)
            return new ImportResult(false, Message: "未找到可用 Cookie。Windows 可从 Cursor 应用或 Firefox 导入；Chrome / Edge 因系统加密无法读取，请改用 Firefox 或手动粘贴 WorkosCursorSessionToken。");
        var order = prefer.Select((b, i) => (b, i)).ToDictionary(x => x.b, x => x.i);
        candidates = candidates.OrderByDescending(c => c.LastUpdate).ThenBy(c => order.GetValueOrDefault(c.Browser, 99)).ToList();
        var skip = skipTokens ?? [];
        var lastErr = "找到 Cookie，但校验均失败";
        var lastSource = candidates[0].Browser;
        var tried = 0;
        foreach (var c in candidates)
        {
            var variants = Token.Variants(c.TokenValue);
            if (variants.Count == 0) variants = [c.TokenValue];
            if (variants.All(skip.Contains)) continue;
            foreach (var variant in variants)
            {
                if (skip.Contains(variant)) continue;
                tried++;
                try
                {
                    var snap = await client.FetchUsageSummary(variant, 12, ct);
                    return new ImportResult(true, variant, c.Browser, c.Profile, snap.RemainingPercent, snap.MembershipType,
                        $"已从 {c.Browser} ({c.Profile}) 导入并校验成功：剩余 {snap.RemainingPercent:0.0}% · {snap.MembershipType}");
                }
                catch (CursorApiException err)
                {
                    lastErr = err.Message;
                    lastSource = c.Browser;
                    if (err.IsAuthError) skip.Add(variant);
                    else break;
                }
                catch (Exception ex)
                {
                    lastErr = "校验失败: " + ex.Message;
                    lastSource = c.Browser;
                    break;
                }
            }
        }
        if (tried == 0 && skip.Count > 0)
            return new ImportResult(false, Message: $"已读到 {lastSource} 的 Cookie，但接口拒绝了这条登录态。请完整复制 WorkosCursorSessionToken 后粘贴。");
        return new ImportResult(false, Message: $"已读到 {lastSource} 的 Cookie，但校验失败：{lastErr}\n请完整复制 WorkosCursorSessionToken 后粘贴。");
    }

    public static IEnumerable<CookieCandidate> FindCandidates(string[]? only = null)
    {
        var allow = only?.ToHashSet();
        if (allow is null || allow.Contains("cursor-app"))
        {
            foreach (var path in CursorStateDbPaths())
            {
                var jwt = ReadCursorAccessToken(path);
                if (jwt is null) continue;
                string? token;
                try { token = Token.Normalize(jwt); } catch { continue; }
                if (token.Length < 20) continue;
                var mtime = File.Exists(path) ? new DateTimeOffset(File.GetLastWriteTimeUtc(path)).ToUnixTimeMilliseconds() * 1000 : 0;
                yield return new CookieCandidate("cursor-app", Path.GetFileName(Path.GetDirectoryName(Path.GetDirectoryName(Path.GetDirectoryName(path))) ?? "Cursor"), token, mtime);
            }
        }
        if (allow is null || allow.Any(x => x.StartsWith("firefox")))
        {
            foreach (var c in FindFirefox()) yield return c;
        }
    }

    public static string? ReadCursorAccessToken(string dbPath)
    {
        if (!File.Exists(dbPath)) return null;
        try
        {
            using var conn = new Microsoft.Data.Sqlite.SqliteConnection(new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = dbPath,
                Mode = Microsoft.Data.Sqlite.SqliteOpenMode.ReadOnly,
            }.ToString());
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT value FROM ItemTable WHERE key = $k LIMIT 1";
            foreach (var key in new[] { "cursorAuth/accessToken", "cursorAuth/cachedAccessToken" })
            {
                cmd.Parameters.Clear();
                cmd.Parameters.AddWithValue("$k", key);
                var v = cmd.ExecuteScalar()?.ToString();
                if (!string.IsNullOrWhiteSpace(v)) return v.Trim();
            }
        }
        catch { }
        return null;
    }

        static List<CookieCandidate> FindFirefox()
    {
        var found = new List<CookieCandidate>();
        var appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var roots = new (string name, string path)[]
        {
            ("firefox", Path.Combine(appdata, "Mozilla", "Firefox")),
            ("firefox-dev", Path.Combine(appdata, "Mozilla", "Firefox Developer Edition")),
            ("firefox-nightly", Path.Combine(appdata, "Mozilla", "Firefox Nightly")),
            ("librewolf", Path.Combine(appdata, "librewolf")),
            ("waterfox", Path.Combine(appdata, "Waterfox")),
            ("zen", Path.Combine(appdata, "zen")),
        };
        foreach (var (name, support) in roots)
        {
            if (!Directory.Exists(support)) continue;
            var profilesDir = Path.Combine(support, "Profiles");
            if (!Directory.Exists(profilesDir)) continue;
            foreach (var profile in Directory.GetDirectories(profilesDir))
            {
                var db = Path.Combine(profile, "cookies.sqlite");
                if (!File.Exists(db)) continue;
                foreach (var (_, value, last) in ReadFirefoxCookies(db))
                {
                    try
                    {
                        var token = Token.Normalize(value);
                        if (token.Length >= 20)
                            found.Add(new CookieCandidate(name, Path.GetFileName(profile), token, last < 10_000_000_000_000 ? last * 1000 : last));
                    }
                    catch { }
                }
            }
        }
        return found;
    }

    public static List<(string host, string value, long last)> ReadFirefoxCookies(string dbPath)
    {
        var rows = new List<(string, string, long)>();
        var tmpDir = Path.Combine(Path.GetTempPath(), "ctt_ff_" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(tmpDir);
            var tmp = Path.Combine(tmpDir, "cookies.sqlite");
            File.Copy(dbPath, tmp, true);
            foreach (var suffix in new[] { "-wal", "-shm" })
            {
                var side = dbPath + suffix;
                if (File.Exists(side))
                {
                    try { File.Copy(side, tmp + suffix, true); } catch { }
                }
            }
            using var conn = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={tmp};Mode=ReadOnly");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT host, value, lastAccessed FROM moz_cookies WHERE name = $n";
            cmd.Parameters.AddWithValue("$n", Token.CookieName);
            using var r = cmd.ExecuteReader();
            while (r.Read())
                rows.Add((r.GetString(0), r.GetString(1), r.IsDBNull(2) ? 0 : r.GetInt64(2)));
        }
        catch { }
        finally
        {
            try { if (Directory.Exists(tmpDir)) Directory.Delete(tmpDir, true); } catch { }
        }
        return rows;
    }
}
