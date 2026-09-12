using System.Globalization;
using CursorTokenCore;

namespace CursorTokenTray;

sealed class CompareForm : Form
{
    public readonly record struct CompareState(
        IReadOnlyList<Account> Accounts,
        double MonthlyPlanUsd,
        double UsdCnyRate,
        Action<string, string?, string?, string?> PersistCycle);

    readonly CursorClient _client;
    readonly Func<CompareState> _state;
    readonly Label _status = new() { AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(8, 8, 0, 0) };
    readonly Label _hint = new()
    {
        Text = "窗口按各账号自己的最新周期或有效期。日均持有 = 折合月费÷30。窗口实付把月费按窗口天数折算后再摊到套餐内请求；按需仍按费用×汇率。表内同时给出 First-party / API / Grok Bot 的次数、Token 与单位成本。",
        AutoSize = true,
        ForeColor = Color.DimGray,
        Margin = new Padding(0, 4, 0, 8),
    };
    readonly DataGridView _grid = new()
    {
        Dock = DockStyle.Fill,
        ReadOnly = true,
        AllowUserToAddRows = false,
        AllowUserToDeleteRows = false,
        AllowUserToResizeRows = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.None,
        ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing,
        RowHeadersVisible = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect,
        MultiSelect = false,
        BackgroundColor = Color.White,
        BorderStyle = BorderStyle.FixedSingle,
        ScrollBars = ScrollBars.Both,
    };
    readonly Button _syncBtn = new() { Text = "同步", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    readonly Button _exportBtn = new() { Text = "导出 CSV", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    AccountCompareReport _report = new();
    bool _syncing;

    public CompareForm(CursorClient client, Func<CompareState> state)
    {
        _client = client;
        _state = state;
        SuspendLayout();
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        Text = "账号对比";
        var icon = AppWindow.CreateIcon();
        if (icon is not null) Icon = icon;
        MinimumSize = new Size(1040, 520);
        StartPosition = FormStartPosition.CenterScreen;
        Width = 1180;
        Height = 640;

        foreach (var (name, header, width) in Columns())
            _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = name, HeaderText = header, Width = width });

        var toolbar = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = true,
            Dock = DockStyle.Top,
            Padding = new Padding(0, 0, 0, 4),
        };
        toolbar.Controls.Add(_syncBtn);
        toolbar.Controls.Add(_exportBtn);
        toolbar.Controls.Add(_status);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            Padding = new Padding(16),
        };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.Controls.Add(toolbar, 0, 0);
        root.Controls.Add(_hint, 0, 1);
        root.Controls.Add(_grid, 0, 2);
        Controls.Add(root);

        _syncBtn.Click += async (_, _) => await SyncAsync();
        _exportBtn.Click += (_, _) => ExportCsv();
        Load += (_, _) =>
        {
            LoadCache();
            _hint.MaximumSize = new Size(Math.Max(400, ClientSize.Width - 40), 0);
        };
        ResumeLayout();
    }

    static (string Name, string Header, int Width)[] Columns() =>
    [
        ("name", "账号", 110),
        ("channel", "渠道", 72),
        ("membership", "套餐", 80),
        ("window", "窗口", 72),
        ("days", "天数", 56),
        ("holding", "日均持有", 88),
        ("paid", "窗口实付", 88),
        ("requests", "请求", 56),
        ("tokens", "Token", 80),
        ("perM", "¥/百万", 80),
        ("perR", "¥/次", 72),
        ("fpN", "FP次数", 64),
        ("fpT", "FP Token", 80),
        ("fpC", "FP实付", 72),
        ("fpM", "FP ¥/百万", 80),
        ("fpR", "FP ¥/次", 72),
        ("apiN", "API次数", 68),
        ("apiT", "API Token", 80),
        ("apiC", "API实付", 72),
        ("apiM", "API ¥/百万", 80),
        ("apiR", "API ¥/次", 72),
        ("gbN", "Grok次数", 72),
        ("gbT", "Grok Token", 80),
        ("gbC", "Grok实付", 72),
        ("gbM", "Grok ¥/百万", 88),
        ("gbR", "Grok ¥/次", 72),
    ];

    void LoadCache()
    {
        _report = BuildReport();
        Render();
        if (_report.Rows.Count == 0)
        {
            _status.Text = _state().Accounts.Count == 0
                ? "还没有账号。请先在设置里导入。"
                : "本地还没有明细。点「同步」按各账号最新周期拉取。";
        }
        else
        {
            _status.Text = "已加载本地明细。点「同步」按各账号最新周期拉取。";
        }
    }

    AccountCompareReport BuildReport()
    {
        var state = _state();
        var items = state.Accounts.Select(acc =>
            UsageEvents.CompareInputFromAccount(
                acc,
                UsageEvents.Load(acc.Id, false),
                state.MonthlyPlanUsd,
                state.UsdCnyRate));
        return UsageEvents.BuildAccountCompareReport(items);
    }

    async Task SyncAsync()
    {
        if (_syncing) return;
        var accounts = _state().Accounts.ToList();
        if (accounts.Count == 0)
        {
            _status.Text = "还没有账号。请先在设置里导入。";
            return;
        }
        _syncing = true;
        _syncBtn.Enabled = false;
        _status.Text = "正在同步各账号最新周期…";
        var ok = 0;
        var fail = 0;
        try
        {
            foreach (var acc in accounts)
            {
                if (string.IsNullOrWhiteSpace(acc.Token))
                {
                    fail++;
                    continue;
                }
                try
                {
                    var snap = await _client.FetchUsageSummary(acc.Token, 20);
                    AccountValidity.ApplyEndOverride(snap, acc);
                    _state().PersistCycle(acc.Id, snap.MembershipType, snap.BillingCycleStart, snap.BillingCycleEnd);
                    await UsageEvents.SyncAsync(_client, acc.Token, acc.Id, snap, false);
                    ok++;
                }
                catch (Exception ex)
                {
                    fail++;
                    CrashLog.Write(ex);
                }
            }
            _report = BuildReport();
            Render();
            var stamp = DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("HH:mm:ss", CultureInfo.InvariantCulture);
            _status.Text = fail == 0
                ? $"已同步 {ok} 个账号  ·  {stamp}"
                : $"已同步 {ok} 个账号，{fail} 个失败  ·  {stamp}";
        }
        finally
        {
            _syncing = false;
            _syncBtn.Enabled = true;
        }
    }

    void Render()
    {
        _grid.Rows.Clear();
        _grid.SuspendLayout();
        foreach (var group in _report.Groups)
        {
            foreach (var row in group.Rows)
                _grid.Rows.Add(Cells(row.Label, row.ChannelLabel, UsageParser.FormatMembershipType(row.MembershipType), row.WindowLabel, FormatDays(row.WindowDays), false, row.DailyHoldingCny, row.TotalCny, row.EventCount, row.TotalTokens, row.CnyPerMillion, row.CnyPerRequest, row.FirstParty, row.Api, row.GrokBot));
            var idx = _grid.Rows.Add(Cells(group.ChannelLabel + "合计", group.ChannelLabel, "", "", "", true, group.DailyHoldingCny, group.TotalCny, group.EventCount, group.TotalTokens, group.CnyPerMillion, group.CnyPerRequest, group.FirstParty, group.Api, group.GrokBot));
            _grid.Rows[idx].DefaultCellStyle.Font = new Font(_grid.Font, FontStyle.Bold);
        }
        _grid.ResumeLayout();
        _exportBtn.Enabled = _report.Rows.Count > 0;
    }

    static object[] Cells(
        string name, string channel, string membership, string window, string days, bool group,
        double dailyHolding, double totalCny, int requests, long tokens,
        double? perMillion, double? perRequest,
        AccountCompareCategory firstParty, AccountCompareCategory api, AccountCompareCategory grok)
    {
        _ = group;
        return
        [
            name, channel, membership, window, days,
            UsageEvents.FormatCny(dailyHolding),
            UsageEvents.FormatCny(totalCny),
            requests.ToString(CultureInfo.InvariantCulture),
            UsageParser.FormatTokenCount(tokens),
            UsageEvents.FormatCnyUnit(perMillion, "/百万"),
            UsageEvents.FormatCnyUnit(perRequest, "/次"),
            firstParty.Count.ToString(CultureInfo.InvariantCulture),
            UsageParser.FormatTokenCount(firstParty.Tokens),
            UsageEvents.FormatCny(firstParty.Cny),
            UsageEvents.FormatCnyUnit(firstParty.CnyPerMillion, "/百万"),
            UsageEvents.FormatCnyUnit(firstParty.CnyPerRequest, "/次"),
            api.Count.ToString(CultureInfo.InvariantCulture),
            UsageParser.FormatTokenCount(api.Tokens),
            UsageEvents.FormatCny(api.Cny),
            UsageEvents.FormatCnyUnit(api.CnyPerMillion, "/百万"),
            UsageEvents.FormatCnyUnit(api.CnyPerRequest, "/次"),
            grok.Count.ToString(CultureInfo.InvariantCulture),
            UsageParser.FormatTokenCount(grok.Tokens),
            UsageEvents.FormatCny(grok.Cny),
            UsageEvents.FormatCnyUnit(grok.CnyPerMillion, "/百万"),
            UsageEvents.FormatCnyUnit(grok.CnyPerRequest, "/次"),
        ];
    }

    static string FormatDays(double days) =>
        Math.Abs(days - Math.Round(days)) < 0.05
            ? Math.Round(days).ToString("0", CultureInfo.InvariantCulture)
            : days.ToString("0.00", CultureInfo.InvariantCulture);

    void ExportCsv()
    {
        if (_report.Rows.Count == 0) return;
        using var dlg = new SaveFileDialog
        {
            Filter = "CSV 文件 (*.csv)|*.csv",
            FileName = $"cursor-account-compare-{DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)):yyyyMMdd}.csv",
            OverwritePrompt = true,
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            File.WriteAllText(dlg.FileName, UsageEvents.AccountCompareToCsv(_report));
            _status.Text = "已导出 " + dlg.FileName;
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "导出失败：" + ex.Message, "账号对比", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
