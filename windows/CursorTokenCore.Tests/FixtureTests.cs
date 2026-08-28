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
    public void UsageEventsCases()
    {
        var root = Load("usage_events_cases.json");
        foreach (var row in root.GetProperty("kind").EnumerateArray())
        {
            Assert.Equal(
                row.GetProperty("output").GetString(),
                UsageEvents.ClassifyKind(
                    row.GetProperty("kind").GetString(),
                    row.GetProperty("usage_based_costs").GetString(),
                    row.GetProperty("is_chargeable").GetBoolean()));
        }
        Assert.Equal(root.GetProperty("labels").GetProperty("included").GetString(), UsageEvents.KindLabel("included"));
        Assert.Equal(root.GetProperty("labels").GetProperty("free").GetString(), UsageEvents.KindLabel("free"));
        Assert.Equal(root.GetProperty("labels").GetProperty("on_demand").GetString(), UsageEvents.KindLabel("on_demand"));
        foreach (var cse in root.GetProperty("parse").EnumerateArray())
        {
            var parsed = UsageEvents.ParsePage(JsonBag.Parse(cse.GetProperty("payload").GetRawText()));
            Assert.Equal(cse.GetProperty("total_count").GetInt32(), parsed.totalCount);
            var expected = cse.GetProperty("events").EnumerateArray().ToList();
            Assert.Equal(expected.Count, parsed.events.Count);
            for (var i = 0; i < expected.Count; i++)
            {
                AssertEvent(expected[i], parsed.events[i]);
            }
        }
        foreach (var cse in root.GetProperty("report").EnumerateArray())
        {
            var events = cse.GetProperty("events").EnumerateArray()
                .Select(row => UsageEvents.FromDict(JsonBag.Parse(row.GetRawText()))!)
                .ToList();
            var filtEl = cse.GetProperty("filter");
            var report = UsageEvents.BuildReport(events, new UsageReportFilter
            {
                Kind = filtEl.GetProperty("kind").GetString() ?? "",
                Model = filtEl.GetProperty("model").GetString() ?? "",
                Headless = NullBool(filtEl, "headless"),
                OwningUser = NullStr(filtEl, "owning_user") ?? "",
            });
            var exp = cse.GetProperty("expected");
            Assert.Equal(exp.GetProperty("event_count").GetInt32(), report.EventCount);
            Assert.Equal(exp.GetProperty("total_tokens").GetInt64(), report.TotalTokens);
            Assert.Equal(exp.GetProperty("total_cents").GetDouble(), report.TotalCents, 3);
            Assert.Equal(exp.GetProperty("has_cost").GetBoolean(), report.HasCost);
            Assert.Equal(exp.GetProperty("included_count").GetInt32(), report.IncludedCount);
            Assert.Equal(exp.GetProperty("free_count").GetInt32(), report.FreeCount);
            Assert.Equal(exp.GetProperty("on_demand_count").GetInt32(), report.OnDemandCount);
            Assert.Equal(exp.GetProperty("headless_count").GetInt32(), report.HeadlessCount);
            var daily = exp.GetProperty("daily").EnumerateArray().ToList();
            Assert.Equal(daily.Count, report.Daily.Count);
            for (var i = 0; i < daily.Count; i++)
            {
                Assert.Equal(daily[i].GetProperty("date").GetString(), report.Daily[i].Date);
                Assert.Equal(daily[i].GetProperty("tokens").GetInt64(), report.Daily[i].Tokens);
                Assert.Equal(daily[i].GetProperty("cents").GetDouble(), report.Daily[i].Cents, 3);
                Assert.Equal(daily[i].GetProperty("count").GetInt32(), report.Daily[i].Count);
            }
            var modelsExp = exp.GetProperty("models").EnumerateArray().ToList();
            Assert.Equal(modelsExp.Count, report.Models.Count);
            for (var i = 0; i < modelsExp.Count; i++)
            {
                Assert.Equal(modelsExp[i].GetProperty("name").GetString(), report.Models[i].Name);
                Assert.Equal(modelsExp[i].GetProperty("tokens").GetInt64(), report.Models[i].Tokens);
                Assert.Equal(modelsExp[i].GetProperty("cents").GetDouble(), report.Models[i].Cents, 3);
                Assert.Equal(modelsExp[i].GetProperty("count").GetInt32(), report.Models[i].Count);
                Assert.Equal(modelsExp[i].GetProperty("headless_count").GetInt32(), report.Models[i].HeadlessCount);
            }
        }
        foreach (var row in root.GetProperty("cost_format").EnumerateArray())
        {
            var ev = new UsageEvent
            {
                Kind = row.GetProperty("kind").GetString() ?? "",
                ChargedCents = Opt(row, "charged_cents"),
                TotalCents = Opt(row, "total_cents"),
            };
            Assert.Equal(row.GetProperty("output").GetString(), UsageEvents.FormatCost(ev));
        }
        var csv = UsageEvents.ToCsv(UsageEvents.ParsePage(JsonBag.Parse(root.GetProperty("parse")[0].GetProperty("payload").GetRawText())).events);
        Assert.StartsWith("\ufeff", csv);
        Assert.StartsWith(root.GetProperty("csv_header").GetString(), csv.TrimStart('\ufeff'));
        Assert.Equal(UsageEvents.CsvHeader, root.GetProperty("csv_header").GetString());
    }

    [Fact]
    public void UsageChartCases()
    {
        var root = Load("usage_chart_cases.json");
        Assert.Equal(UsageEvents.HourlyChartWindowHours, root.GetProperty("hourly_window_hours").GetInt32());
        foreach (var row in root.GetProperty("model_labels").EnumerateArray())
            Assert.Equal(row.GetProperty("output").GetString(), UsageEvents.ChartModelLabel(row.GetProperty("input").GetString()));
        foreach (var cse in root.GetProperty("cases").EnumerateArray())
        {
            var events = cse.GetProperty("events").EnumerateArray()
                .Select(row => UsageEvents.FromDict(JsonBag.Parse(row.GetRawText()))!)
                .ToList();
            var hidden = cse.GetProperty("hidden_models").EnumerateArray().Select(x => x.GetString()!).ToList();
            var series = UsageEvents.BuildChart(events, cse.GetProperty("hourly").GetBoolean(), hidden);
            var exp = cse.GetProperty("expected");
            Assert.Equal(exp.GetProperty("hourly").GetBoolean(), series.Hourly);
            Assert.Equal(exp.GetProperty("caption").GetString(), series.Caption);
            Assert.Equal(exp.GetProperty("models").EnumerateArray().Select(x => x.GetString()!).ToList(), series.Models);
            if (exp.TryGetProperty("buckets", out var buckets))
            {
                AssertBuckets(buckets, series.Buckets);
                continue;
            }
            Assert.Equal(exp.GetProperty("bucket_count").GetInt32(), series.Buckets.Count);
            Assert.Equal(exp.GetProperty("first_key").GetString(), series.Buckets[0].Key);
            Assert.Equal(exp.GetProperty("last_key").GetString(), series.Buckets[^1].Key);
            var nonzero = series.Buckets.Where(b => b.Tokens != 0 || b.Cents != 0 || b.Count != 0).ToList();
            AssertBuckets(exp.GetProperty("nonzero"), nonzero);
        }
    }

    [Fact]
    public void UsageEventsStoreMergeAndRoundtrip()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_ev_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var a = new UsageEvent { Id = "a", TimestampMs = 200, Tokens = 1, Kind = "included" };
            var b = new UsageEvent { Id = "b", TimestampMs = 100, Tokens = 2, Kind = "free" };
            var b2 = new UsageEvent { Id = "b", TimestampMs = 150, Tokens = 9, Kind = "free" };
            var merged = UsageEvents.Merge([a, b], [b2]);
            Assert.Equal(["a", "b"], merged.Select(e => e.Id).ToList());
            Assert.Equal(9, merged.First(e => e.Id == "b").Tokens);
            UsageEvents.Save(merged, "user_01EV", false, dir);
            var loaded = UsageEvents.Load("user_01EV", false, dir);
            Assert.Equal(["a", "b"], loaded.Select(e => e.Id).ToList());
            Assert.Equal(9, loaded.First(e => e.Id == "b").Tokens);
            Assert.Empty(UsageEvents.Load("user_01EV", true, dir));
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    static void AssertEvent(JsonElement exp, UsageEvent got)
    {
        Assert.Equal(exp.GetProperty("id").GetString(), got.Id);
        Assert.Equal(exp.GetProperty("timestamp_ms").GetInt64(), got.TimestampMs);
        Assert.Equal(exp.GetProperty("model").GetString(), got.Model);
        Assert.Equal(exp.GetProperty("kind").GetString(), got.Kind);
        Assert.Equal(exp.GetProperty("user_email").GetString(), got.UserEmail);
        Assert.Equal(exp.GetProperty("owning_user").GetString(), got.OwningUser);
        Assert.Equal(exp.GetProperty("tokens").GetInt32(), got.Tokens);
        Assert.Equal(Opt(exp, "charged_cents"), got.ChargedCents);
        Assert.Equal(Opt(exp, "total_cents"), got.TotalCents);
        Assert.Equal(exp.GetProperty("is_headless").GetBoolean(), got.IsHeadless);
    }

    static void AssertBuckets(JsonElement expected, List<ChartBucket> got)
    {
        var rows = expected.EnumerateArray().ToList();
        Assert.Equal(rows.Count, got.Count);
        for (var i = 0; i < rows.Count; i++)
        {
            Assert.Equal(rows[i].GetProperty("key").GetString(), got[i].Key);
            Assert.Equal(rows[i].GetProperty("label").GetString(), got[i].Label);
            Assert.Equal(rows[i].GetProperty("tokens").GetInt64(), got[i].Tokens);
            Assert.Equal(rows[i].GetProperty("cents").GetDouble(), got[i].Cents, 3);
            Assert.Equal(rows[i].GetProperty("count").GetInt32(), got[i].Count);
            var slices = rows[i].GetProperty("slices").EnumerateArray().ToList();
            Assert.Equal(slices.Count, got[i].Slices.Count);
            for (var j = 0; j < slices.Count; j++)
            {
                Assert.Equal(slices[j].GetProperty("model").GetString(), got[i].Slices[j].Model);
                Assert.Equal(slices[j].GetProperty("tokens").GetInt64(), got[i].Slices[j].Tokens);
                Assert.Equal(slices[j].GetProperty("cents").GetDouble(), got[i].Slices[j].Cents, 3);
                Assert.Equal(slices[j].GetProperty("count").GetInt32(), got[i].Slices[j].Count);
            }
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

    [Fact]
    public void AlertMarksAllNewlyCrossedLevels()
    {
        var cfg = new AppConfig { NotifyEnabled = true, AlertThresholds = [50, 20, 5] };
        var acc = new Account { Label = "工作" };
        var snap = new UsageSnapshot { RemainingPercent = 4 };
        var notices = AlertLogic.Evaluate(cfg, acc, snap);
        Assert.Single(notices);
        Assert.Contains("5%", notices[0].Body);
        Assert.Equal([5, 20, 50], acc.AlertNotifiedLevels);
        Assert.Empty(AlertLogic.Evaluate(cfg, acc, snap));
    }

    [Fact]
    public void CorruptConfigIsNotOverwritten()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var path = AppPaths.ConfigPath(dir);
            File.WriteAllText(path, "{not-json");
            var loaded = ConfigStore.Load(dir);
            Assert.True(loaded.LoadError);
            Assert.Empty(loaded.Accounts);
            Assert.Equal("{not-json", File.ReadAllText(path));
            Assert.True(File.Exists(path + ".corrupt"));
            ConfigStore.Save(loaded, dir);
            Assert.Equal("{not-json", File.ReadAllText(path));
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void HistoryPruneDropsOldPoints()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var old = DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 100 * 86400;
            UsageHistory.Append(10, ts: old, accountId: "user_p", directory: dir);
            UsageHistory.Append(20, accountId: "user_p", directory: dir);
            var recent = UsageHistory.LoadRecent(200, "user_p", dir);
            Assert.DoesNotContain(recent, p => Math.Abs(p.Remaining - 10) < 0.01);
            Assert.Contains(recent, p => Math.Abs(p.Remaining - 20) < 0.01);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void TokenProtectorRoundtrip()
    {
        const string token = "user_01PROT%3A%3Aaaa.bbb.ccc";
        Assert.Equal(token, TokenProtector.Unprotect(TokenProtector.Protect(token)));
        Assert.Equal("plain", TokenProtector.Unprotect("plain"));
        Assert.Equal("", TokenProtector.Protect(""));
        var blob = TokenProtector.Prefix + Convert.ToBase64String(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 });
        Assert.False(TokenProtector.TryUnprotect(blob, out var plain));
        Assert.Equal("", plain);
        Assert.Equal("", TokenProtector.Unprotect(blob));
        Assert.DoesNotContain(TokenProtector.Prefix, TokenProtector.Unprotect(blob));
    }

    [Fact]
    public void EncryptedBlobIsNotUsedAsTokenAndIsPreserved()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var blob = TokenProtector.Prefix + Convert.ToBase64String("not-a-real-dpapi-payload"u8.ToArray());
            var json = $$"""
                {
                  "session_token": "{{blob}}",
                  "accounts": [{ "id": "user_01X", "token": "{{blob}}", "label": "坏" }],
                  "active_account_id": "user_01X",
                  "refresh_interval_minutes": 10
                }
                """;
            File.WriteAllText(AppPaths.ConfigPath(dir), json);
            var loaded = ConfigStore.Load(dir);
            Assert.True(loaded.DecryptError);
            Assert.Single(loaded.Accounts);
            Assert.True(loaded.Accounts[0].TokenDecryptFailed);
            Assert.Equal("", loaded.Accounts[0].Token);
            Assert.Equal("坏", loaded.Accounts[0].Label);
            Assert.Equal(TokenProtector.DecryptFailedMessage, loaded.Accounts[0].LastError);
            ConfigStore.Save(loaded, dir);
            Assert.Contains(blob, File.ReadAllText(AppPaths.ConfigPath(dir)));
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void UpdateMergesOntoLatestDiskConfig()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var header = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("{\"alg\":\"none\"}"))
                .TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var payload = Convert.ToBase64String(System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(new { sub = "github|user_01SAVE" }))
                .TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var token = $"user_01SAVE%3A%3A{header}.{payload}.sig";
            var cfg = new AppConfig { RefreshIntervalMinutes = 10 };
            cfg.UpsertAccount(token, label: "工作", activate: true);
            ConfigStore.Save(cfg, dir);

            var settings = ConfigStore.Load(dir);
            settings.RefreshIntervalMinutes = 15;
            ConfigStore.Save(settings, dir);

            var merged = ConfigStore.Update(live =>
            {
                Assert.Equal(15, live.RefreshIntervalMinutes);
                live.ApplySnapshot(live.ActiveAccountId, remaining: 42);
            }, dir);
            Assert.Equal(15, merged.RefreshIntervalMinutes);
            Assert.Equal(42, merged.ActiveAccount!.LastRemaining);
            var reloaded = ConfigStore.Load(dir);
            Assert.Equal(15, reloaded.RefreshIntervalMinutes);
            Assert.Equal(42, reloaded.ActiveAccount!.LastRemaining);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public async Task HttpRetriesServerErrors()
    {
        var handler = new SeqHandler([500, 500, 200]);
        var client = new CursorClient(new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan });
        var snap = await client.FetchUsageSummary("user_01HTTP%3A%3Aaaa.bbb.ccc", 5);
        Assert.Equal(3, handler.Calls);
        Assert.Equal(0, snap.UsedPercent);
    }

    [Fact]
    public void FitPopupSitsAboveLeftOfTrayAnchor()
    {
        var (x, y) = UiLayout.FitPopup(0, 0, 1920, 1040, 420, 320, 1900, 1040);
        Assert.Equal(1480, x);
        Assert.Equal(708, y);
    }

    [Fact]
    public void FitPopupFlipsBelowWhenTaskbarIsOnTop()
    {
        var (x, y) = UiLayout.FitPopup(0, 40, 1920, 1080, 420, 320, 1900, 40);
        Assert.Equal(1480, x);
        Assert.Equal(52, y);
    }

    [Fact]
    public void FitPopupClampsToLeftAndBottomEdges()
    {
        var (x, y) = UiLayout.FitPopup(0, 0, 800, 600, 420, 320, 10, 620);
        Assert.Equal(8, x);
        Assert.Equal(272, y);
    }

    [Fact]
    public void FitDialogUsesMinimumWhenContentIsSmaller()
    {
        var (w, h) = UiLayout.FitDialog(400, 300, 520, 420, 1920, 1080);
        Assert.Equal(520, w);
        Assert.Equal(420, h);
    }

    [Fact]
    public void FitDialogGrowsForHighDpiPreferredSize()
    {
        var (w, h) = UiLayout.FitDialog(780, 900, 520, 420, 1920, 1080);
        Assert.Equal(804, w);
        Assert.Equal(924, h);
    }

    [Fact]
    public void FitDialogClampsToWorkingArea()
    {
        var (w, h) = UiLayout.FitDialog(900, 1200, 520, 420, 800, 600);
        Assert.Equal(752, w);
        Assert.Equal(552, h);
    }

    [Fact]
    public void ScalePxKeepsDesignPixelsAt96Dpi()
    {
        Assert.Equal(90, UiLayout.ScalePx(90, 96));
        Assert.Equal(1040, UiLayout.ScalePx(1040, 96));
        Assert.Equal(1f, UiLayout.DpiScale(96));
    }

    [Fact]
    public void ScalePxGrowsForCommonWindowsFactors()
    {
        Assert.Equal(113, UiLayout.ScalePx(90, 120));
        Assert.Equal(135, UiLayout.ScalePx(90, 144));
        Assert.Equal(180, UiLayout.ScalePx(90, 192));
        Assert.Equal(1560, UiLayout.ScalePx(1040, 144));
    }

    [Fact]
    public void ScalePxNeverShrinksAndClampsGarbageDpi()
    {
        Assert.Equal(90, UiLayout.ScalePx(90, 0));
        Assert.Equal(90, UiLayout.ScalePx(90, 48));
        Assert.Equal(90, UiLayout.ScalePx(90, 11520));
        Assert.Equal(1f, UiLayout.DpiScale(0));
        Assert.Equal(1f, UiLayout.ClampUiScale(float.NaN));
        Assert.Equal(3f, UiLayout.ClampUiScale(120f));
    }

    [Fact]
    public void FitWindowGrowsForHighDpiAndClampsToWorkArea()
    {
        var at100 = UiLayout.FitWindow(1040, 760, 900, 600, 96, 1920, 1080);
        Assert.Equal((1040, 760), at100);

        var at150 = UiLayout.FitWindow(1040, 760, 900, 600, 144, 1920, 1080);
        Assert.Equal(1560, at150.Width);
        Assert.Equal(1032, at150.Height);

        var tiny = UiLayout.FitWindow(1040, 760, 900, 600, 144, 800, 600);
        Assert.Equal(752, tiny.Width);
        Assert.Equal(552, tiny.Height);
    }

    [Fact]
    public void CrashLogWritesExceptionAndIgnoresNull()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ctt-crash-" + Guid.NewGuid().ToString("N"));
        try
        {
            CrashLog.Write(null, dir);
            Assert.False(File.Exists(CrashLog.PathFor(dir)));
            CrashLog.Write(new InvalidOperationException("boom-ui"), dir);
            var text = File.ReadAllText(CrashLog.PathFor(dir));
            Assert.Contains("boom-ui", text);
            Assert.Contains("InvalidOperationException", text);
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    sealed class SeqHandler(int[] statuses) : HttpMessageHandler
    {
        public int Calls;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var code = statuses[Math.Min(Calls, statuses.Length - 1)];
            Calls++;
            return Task.FromResult(new HttpResponseMessage((System.Net.HttpStatusCode)code)
            {
                Content = new StringContent("{}", System.Text.Encoding.UTF8, "application/json"),
            });
        }
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

    static bool? NullBool(JsonElement el, string key)
    {
        if (!el.TryGetProperty(key, out var v) || v.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined) return null;
        return v.GetBoolean();
    }
}
