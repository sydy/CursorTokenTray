using System.Text.Json;
using CursorTokenCore;
using Xunit;

namespace CursorTokenCore.Tests;

public class FixtureTests
{
    static string FixturePath(string name)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 12 && dir is not null; i++)
        {
            var candidate = Path.Combine(dir.FullName, "fixtures", name);
            if (File.Exists(candidate)) return candidate;
            candidate = Path.Combine(dir.FullName, name);
            if (File.Exists(Path.Combine(dir.FullName, "fixtures", name))) return Path.Combine(dir.FullName, "fixtures", name);
            dir = dir.Parent;
        }
        // walk from this source file via env
        var cwd = Directory.GetCurrentDirectory();
        dir = new DirectoryInfo(cwd);
        for (var i = 0; i < 12 && dir is not null; i++)
        {
            var candidate = Path.Combine(dir.FullName, "fixtures", name);
            if (File.Exists(candidate)) return candidate;
            dir = dir.Parent;
        }
        throw new FileNotFoundException(name);
    }

    static JsonElement Load(string name)
    {
        var json = File.ReadAllText(FixturePath(name));
        return JsonDocument.Parse(json).RootElement.Clone();
    }

    [Fact]
    public void UsageSummaryCases()
    {
        foreach (var cse in Load("usage_summary_cases.json").EnumerateArray())
        {
            var name = cse.GetProperty("name").GetString();
            var payload = JsonBag.Parse(cse.GetProperty("payload").GetRawText());
            var snap = UsageParser.ParseUsageSummary(payload);
            var exp = cse.GetProperty("expected");
            Assert.Equal(exp.GetProperty("used_percent").GetDouble(), snap.UsedPercent, 3);
            Assert.Equal(exp.GetProperty("remaining_percent").GetDouble(), snap.RemainingPercent, 3);
            Assert.Equal(Opt(exp, "auto_percent_used"), snap.AutoPercentUsed);
            Assert.Equal(Opt(exp, "api_percent_used"), snap.ApiPercentUsed);
            Assert.Equal(exp.GetProperty("membership_type").GetString(), snap.MembershipType);
            Assert.Equal(exp.GetProperty("billing_mode").GetString(), snap.BillingMode);
            Assert.Equal(Opt(exp, "used_cents"), snap.UsedCents);
            Assert.Equal(Opt(exp, "limit_cents"), snap.LimitCents);
            Assert.Equal(Opt(exp, "pooled_used_cents"), snap.PooledUsedCents);
            Assert.Equal(Opt(exp, "pooled_limit_cents"), snap.PooledLimitCents);
            Assert.Equal(exp.GetProperty("is_unlimited").GetBoolean(), snap.IsUnlimited);
            Assert.Equal(exp.GetProperty("is_team_account").GetBoolean(), snap.IsTeamAccount);
            Assert.Equal(exp.GetProperty("shows_amount").GetBoolean(), snap.ShowsAmount);
            Assert.Equal(exp.GetProperty("dashboard_url").GetString(), UsageParser.DashboardUrl(snap));
            Assert.Equal(exp.GetProperty("dashboard_button_label").GetString(), UsageParser.DashboardButtonLabel(snap));
            Assert.Equal(exp.GetProperty("dashboard_menu_label").GetString(), UsageParser.DashboardMenuLabel(snap));
            Assert.Equal(exp.GetProperty("dashboard_link_label").GetString(), UsageParser.DashboardLinkLabel(snap));
            _ = name;
        }
    }

    [Fact]
    public void TokenCases()
    {
        var root = Load("token_cases.json");
        foreach (var row in root.GetProperty("account_ids").EnumerateArray())
            Assert.Equal(row.GetProperty("id").GetString(), Token.AccountId(row.GetProperty("token").GetString()!));
        var variants = root.GetProperty("variants_jwt");
            Assert.Equal(
                variants.GetProperty("variants").EnumerateArray().Select(x => x.GetString()!).ToList(),
                Token.Variants(variants.GetProperty("input").GetString()!));
        foreach (var row in root.GetProperty("normalize").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), Token.Normalize(row.GetProperty("input").GetString()!));
        foreach (var row in root.GetProperty("normalize_errors").EnumerateArray())
        {
            var ex = Assert.Throws<CursorApiException>(() => Token.Normalize(row.GetProperty("input").GetString()!));
            Assert.Contains(row.GetProperty("message_contains").GetString()!, ex.Message);
        }
    }

    [Fact]
    public void FormatCases()
    {
        var root = Load("format_cases.json");
        foreach (var row in root.GetProperty("membership").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), UsageParser.FormatMembershipType(row.GetProperty("input").GetString()));
        foreach (var row in root.GetProperty("usd").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), UsageParser.FormatUsdCents(row.GetProperty("cents").GetDouble()));
        foreach (var row in root.GetProperty("spend_range").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), UsageParser.FormatSpendRange(row.GetProperty("used").GetDouble(), row.GetProperty("limit").GetDouble()));
        foreach (var row in root.GetProperty("token_count").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), UsageParser.FormatTokenCount(row.GetProperty("n").GetDouble()));
        foreach (var row in root.GetProperty("plan_caption").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), StatusText.FormatPlanCaption(row.GetProperty("membership").GetString(), NullStr(row, "label")));
        foreach (var row in root.GetProperty("status_pill").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), StatusText.StatusPillText(Opt(row, "remaining"), row.GetProperty("error").GetBoolean()));

        var enterprise = Load("usage_summary_cases.json").EnumerateArray()
            .First(x => x.GetProperty("name").GetString() == "enterprise_overall");
        var snap = UsageParser.ParseUsageSummary(JsonBag.Parse(enterprise.GetProperty("payload").GetRawText()));
        var lines = StatusText.BuildStatusLines(snap, null, "12:00").ToDictionary(x => x.Item1, x => x.Item2);
        Assert.Contains("$73.84 / $100", lines["剩余"]);
        Assert.Equal("$73.84 / $100", lines["金额"]);
        Assert.Contains("$", lines["团队额度"]);
        Assert.Equal("Enterprise", lines["计划"]);
    }

    [Fact]
    public void AggregatedUsage()
    {
        var cse = Load("aggregated_usage_cases.json")[0];
        var parsed = UsageParser.ParseAggregatedUsage(
            JsonBag.Parse(cse.GetProperty("payload").GetRawText()),
            cse.GetProperty("auto_percent").GetDouble(),
            cse.GetProperty("api_percent").GetDouble());
        Assert.Equal(cse.GetProperty("total").GetInt32(), parsed.total);
        var models = cse.GetProperty("models").EnumerateArray().ToList();
        Assert.Equal(models.Count, parsed.models.Count);
        for (var i = 0; i < models.Count; i++)
        {
            Assert.Equal(models[i].GetProperty("name").GetString(), parsed.models[i].Name);
            Assert.Equal(models[i].GetProperty("tokens").GetInt32(), parsed.models[i].Tokens);
            Assert.Equal(Opt(models[i], "usage_percent"), parsed.models[i].UsagePercent);
        }
    }

    [Fact]
    public void ConfigAndHistory()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            UsageHistory.Append(80, ts: 1_700_000_000, accountId: "user_01A", directory: dir);
            UsageHistory.Append(20, ts: 1_700_000_100, accountId: "user_01B", directory: dir);
            Assert.Equal([80], UsageHistory.LoadRecent(10_000, "user_01A", dir).Select(p => p.Remaining));
            Assert.Equal([20], UsageHistory.LoadRecent(10_000, "user_01B", dir).Select(p => p.Remaining));

            var legacyDir = Path.Combine(dir, "legacy");
            Directory.CreateDirectory(legacyDir);
            File.WriteAllText(Path.Combine(legacyDir, "usage_history.jsonl"), "{\"ts\":1700000000,\"remaining\":55,\"auto\":null,\"api\":null}\n");
            UsageHistory.AdoptLegacy("user_01LEG", legacyDir);
            Assert.True(File.Exists(Path.Combine(legacyDir, "usage_history.user_01LEG.jsonl")));
            Assert.False(File.Exists(Path.Combine(legacyDir, "usage_history.jsonl")));

            var skipDir = Path.Combine(dir, "skip");
            Directory.CreateDirectory(skipDir);
            File.WriteAllText(Path.Combine(skipDir, "usage_history.jsonl"), "{\"ts\":1700000000,\"remaining\":40,\"auto\":null,\"api\":null}\n");
            File.WriteAllText(Path.Combine(skipDir, "usage_history.user_01A.jsonl"), "{\"ts\":1700000100,\"remaining\":10,\"auto\":null,\"api\":null}\n");
            UsageHistory.AdoptLegacy("user_01LEG", skipDir);
            Assert.True(File.Exists(Path.Combine(skipDir, "usage_history.jsonl")));
            Assert.False(File.Exists(Path.Combine(skipDir, "usage_history.user_01LEG.jsonl")));

            var header = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("{\"alg\":\"none\"}"))
                .TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var payload = Convert.ToBase64String(System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(new { sub = "github|user_01SAVE" }))
                .TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var token = $"user_01SAVE%3A%3A{header}.{payload}.sig";
            var cfg = new AppConfig();
            cfg.UpsertAccount(token, label: "工作", activate: true);
            ConfigStore.Save(cfg, dir);
            var loaded = ConfigStore.Load(dir);
            Assert.Single(loaded.Accounts);
            Assert.Equal("工作", loaded.Accounts[0].Label);
            Assert.Equal("user_01SAVE", loaded.ActiveAccountId);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    static double? Opt(JsonElement el, string key)
    {
        if (!el.TryGetProperty(key, out var v) || v.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined) return null;
        return v.GetDouble();
    }

    static string? NullStr(JsonElement el, string key)
    {
        if (!el.TryGetProperty(key, out var v) || v.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined) return null;
        return v.GetString();
    }
}
