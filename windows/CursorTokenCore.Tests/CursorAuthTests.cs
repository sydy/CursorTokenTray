using System.Text;
using System.Text.Json;
using CursorTokenCore;
using Microsoft.Data.Sqlite;
using Xunit;

namespace CursorTokenCore.Tests;

public class CursorAuthTests
{
    static string Jwt(object payload)
    {
        var header = B64Url("{\"alg\":\"none\"}");
        var body = B64Url(JsonSerializer.Serialize(payload));
        return $"{header}.{body}.sig";
    }

    static string B64Url(string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        return Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    }

    static string SessionToken(string user = "user_01SESS") =>
        Jwt(new Dictionary<string, string> { ["sub"] = "auth0|" + user, ["type"] = "session" });

    static string WebToken(string user = "user_01WEB") =>
        Jwt(new Dictionary<string, string>
        {
            ["sub"] = "auth0|" + user,
            ["type"] = "web",
            ["workosSessionId"] = "wos_x",
        });

    [Fact]
    public void JwtTypeDistinguishesSessionAndWeb()
    {
        var session = SessionToken();
        var web = WebToken();
        Assert.Equal("session", Token.JwtType(session));
        Assert.Equal("web", Token.JwtType(web));
        Assert.True(Token.CanWriteToCursor(session));
        Assert.False(Token.CanWriteToCursor(web));
        Assert.True(Token.CanWriteToCursor(userIdPrefix(session)));
        Assert.False(Token.CanWriteToCursor("not-a-jwt-token-value"));
    }

    static string userIdPrefix(string jwt) => "user_01SESS%3A%3A" + jwt;

    [Fact]
    public void BuildValuesRefusesWebAndWritesSessionKeys()
    {
        var web = CursorAuth.BuildValues(WebToken());
        Assert.Null(web.Values);
        Assert.Contains("浏览器 Cookie", web.Error);

        var jwt = SessionToken();
        var built = CursorAuth.BuildValues(
            "user_01SESS::" + jwt,
            email: "work@example.com",
            membershipType: "Pro",
            displayName: "工作号");
        Assert.True(string.IsNullOrEmpty(built.Error));
        var values = built.Values;
        Assert.NotNull(values);
        Assert.Equal(jwt, values!["cursorAuth/accessToken"]);
        Assert.Equal(jwt, values["cursorAuth/refreshToken"]);
        Assert.Equal("auth0|user_01SESS", values["glass.lastSignedInAuthId"]);
        Assert.Equal("work@example.com", values["cursorAuth/cachedEmail"]);
        Assert.Equal("Auth_0", values["cursorAuth/cachedSignUpType"]);
        Assert.Equal("pro", values["cursorAuth/stripeMembershipType"]);
        Assert.Equal("active", values["cursorAuth/stripeSubscriptionStatus"]);
        Assert.Contains("工作号", values["cursorAuth/cachedScopedProfile"]);
    }

    [Theory]
    [InlineData("Free", "free", "unpaid")]
    [InlineData("Hobby", "free", "unpaid")]
    [InlineData("Pro+", "pro_plus", "active")]
    [InlineData("Ultra", "ultra", "active")]
    [InlineData("Enterprise", "enterprise", "active")]
    public void StripePlanMapsLabels(string input, string membership, string status)
    {
        var got = CursorAuth.StripePlan(input);
        Assert.Equal(membership, got.Membership);
        Assert.Equal(status, got.Status);
    }

    [Fact]
    public void WriteIsSurgicalAndBacksUp()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_auth_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var db = Path.Combine(dir, "state.vscdb");
            SeedDb(db, new Dictionary<string, string>
            {
                ["cursorAuth/accessToken"] = "old-token",
                ["cursorAuth/cachedEmail"] = "old@example.com",
                ["cursorAuth/onboardingDate"] = "2024-01-01T00:00:00.000Z",
                ["cursorAuth/cachedAccessToken"] = "old-cached",
                ["mcpOAuth.secret.demo"] = "keep-secret",
                ["theme"] = "dark",
            }, kv: ("chat-1", "transcript"));

            var jwt = SessionToken();
            var built = CursorAuth.BuildValues(jwt, email: "new@example.com", membershipType: "free", displayName: "新号");
            Assert.NotNull(built.Values);
            Assert.True(string.IsNullOrEmpty(built.Error));
            var result = CursorAuth.WriteValues(db, built.Values!, backup: true);
            Assert.True(result.Ok, result.Message);
            Assert.True(File.Exists(result.BackupPath));
            Assert.Equal("old-token", CursorAuth.ReadValues(result.BackupPath!)["cursorAuth/accessToken"]);

            var got = ReadAll(db);
            Assert.Equal(jwt, got["cursorAuth/accessToken"]);
            Assert.Equal(jwt, got["cursorAuth/refreshToken"]);
            Assert.Equal(jwt, got["cursorAuth/cachedAccessToken"]);
            Assert.Equal("new@example.com", got["cursorAuth/cachedEmail"]);
            Assert.Equal("2024-01-01T00:00:00.000Z", got["cursorAuth/onboardingDate"]);
            Assert.Equal("keep-secret", got["mcpOAuth.secret.demo"]);
            Assert.Equal("dark", got["theme"]);
            Assert.Equal("transcript", ReadKv(db, "chat-1"));
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void ApplyRefusesWhenStillRunningAndWritesWhenClosed()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_auth2_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var db = Path.Combine(dir, "state.vscdb");
            SeedDb(db, new Dictionary<string, string> { ["cursorAuth/accessToken"] = "old" });
            var install = new CursorInstall("Cursor", db, null);
            var jwt = SessionToken();
            var stillRunning = CursorAuth.Apply(
                jwt,
                closeIfRunning: true,
                relaunch: true,
                installs: [install],
                isRunning: _ => true,
                requestClose: _ => true,
                waitGone: _ => false,
                launch: _ => throw new Exception("must not launch"),
                write: (_, _, _) => throw new Exception("must not write"));
            Assert.False(stillRunning.Ok);
            Assert.Contains("没有退出", stillRunning.Message);
            Assert.Equal("old", CursorAuth.ReadValues(db)["cursorAuth/accessToken"]);

            var ok = CursorAuth.Apply(
                jwt,
                email: "a@b.c",
                membershipType: "Pro",
                displayName: "A",
                closeIfRunning: true,
                relaunch: true,
                installs: [install],
                isRunning: _ => false,
                requestClose: _ => throw new Exception("must not close"),
                waitGone: _ => true,
                launch: _ => true);
            Assert.True(ok.Ok, ok.Message);
            Assert.True(ok.Relaunched);
            Assert.Equal(jwt, CursorAuth.ReadValues(db)["cursorAuth/accessToken"]);
            Assert.Contains("已重新打开", ok.Message);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void FindInstallsUsesInjectedRoots()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_auth3_" + Guid.NewGuid().ToString("N"));
        var dbDir = Path.Combine(dir, "Cursor", "User", "globalStorage");
        Directory.CreateDirectory(dbDir);
        var db = Path.Combine(dbDir, "state.vscdb");
        File.WriteAllText(db, "x");
        try
        {
            var found = CursorAuth.FindInstalls(appData: dir, localAppData: dir).ToList();
            Assert.Single(found);
            Assert.Equal("Cursor", found[0].Name);
            Assert.Equal(db, found[0].StateDb);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    static void SeedDb(string path, Dictionary<string, string> items, (string key, string value)? kv = null)
    {
        using var conn = new SqliteConnection($"Data Source={path}");
        conn.Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
            CREATE TABLE cursorDiskKV (key TEXT, value BLOB);
            """;
        cmd.ExecuteNonQuery();
        foreach (var (k, v) in items)
        {
            cmd.CommandText = "INSERT INTO ItemTable(key, value) VALUES ($k, $v)";
            cmd.Parameters.Clear();
            cmd.Parameters.AddWithValue("$k", k);
            cmd.Parameters.AddWithValue("$v", v);
            cmd.ExecuteNonQuery();
        }
        if (kv is { } row)
        {
            cmd.CommandText = "INSERT INTO cursorDiskKV(key, value) VALUES ($k, $v)";
            cmd.Parameters.Clear();
            cmd.Parameters.AddWithValue("$k", row.key);
            cmd.Parameters.AddWithValue("$v", row.value);
            cmd.ExecuteNonQuery();
        }
    }

    static Dictionary<string, string> ReadAll(string path)
    {
        var found = new Dictionary<string, string>();
        using var conn = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Mode = SqliteOpenMode.ReadOnly }.ToString());
        conn.Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT key, value FROM ItemTable";
        using var r = cmd.ExecuteReader();
        while (r.Read()) found[r.GetString(0)] = r.GetValue(1)?.ToString() ?? "";
        return found;
    }

    static string ReadKv(string path, string key)
    {
        using var conn = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Mode = SqliteOpenMode.ReadOnly }.ToString());
        conn.Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT value FROM cursorDiskKV WHERE key = $k";
        cmd.Parameters.AddWithValue("$k", key);
        return cmd.ExecuteScalar()?.ToString() ?? "";
    }
}
