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
        Text = "账号一行，First-party / API / Grok Bot 各占一行。日均持有 = 折合月费÷30。",
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
        MinimumSize = new Size(900, 480);
        StartPosition = FormStartPosition.CenterScreen;
        Width = 1020;
        Height = 640;
        _grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;

        foreach (var (name, header, fill, align) in Columns())
        {
            _grid.Columns.Add(new DataGridViewTextBoxColumn
            {
                Name = name,
                HeaderText = header,
                FillWeight = fill,
                DefaultCellStyle = { Alignment = align },
            });
        }

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

    static (string Name, string Header, float Fill, DataGridViewContentAlignment Align)[] Columns() =>
    [
        ("name", "账号 / 分类", 22, DataGridViewContentAlignment.MiddleLeft),
        ("window", "窗口", 14, DataGridViewContentAlignment.MiddleLeft),
        ("holding", "日均持有", 11, DataGridViewContentAlignment.MiddleRight),
        ("paid", "实付", 11, DataGridViewContentAlignment.MiddleRight),
        ("requests", "请求", 9, DataGridViewContentAlignment.MiddleRight),
        ("tokens", "Token", 11, DataGridViewContentAlignment.MiddleRight),
        ("perM", "¥/百万", 11, DataGridViewContentAlignment.MiddleRight),
        ("perR", "¥/次", 11, DataGridViewContentAlignment.MiddleRight),
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
        var units = _report.Rows.Where(r => r.CnyPerMillion is not null).Select(r => r.CnyPerMillion!.Value).ToList();
        var hasBest = units.Count > 0;
        var best = hasBest ? units.Min() : 0;
        var accounts = _state().Accounts;
        foreach (var group in _report.Groups)
        {
            StyleRow(_grid.Rows[_grid.Rows.Add(Line(group.ChannelLabel, "", "", "", "", "", "", ""))], RowKind.Header);
            foreach (var row in group.Rows)
            {
                var name = AccountName(accounts, row);
                var memb = UsageParser.FormatMembershipType(row.MembershipType);
                if (!string.IsNullOrEmpty(memb) && !memb.Equals(name, StringComparison.OrdinalIgnoreCase))
                    name += "  " + memb;
                var accIdx = _grid.Rows.Add(Line(
                    name,
                    $"{row.WindowLabel} {FormatDays(row.WindowDays)}天",
                    UsageEvents.FormatCny(row.DailyHoldingCny),
                    UsageEvents.FormatCny(row.TotalCny),
                    FormatCount(row.EventCount),
                    UsageParser.FormatTokenCount(row.TotalTokens),
                    Unit(row.CnyPerMillion),
                    Unit(row.CnyPerRequest)));
                StyleRow(_grid.Rows[accIdx], RowKind.Account);
                if (hasBest && row.CnyPerMillion is { } perM && Math.Abs(perM - best) < 1e-9)
                    _grid.Rows[accIdx].Cells["perM"].Style.ForeColor = Color.SeaGreen;
                AddCategory("First-party", row.FirstParty);
                AddCategory("API", row.Api);
                AddCategory("Grok Bot", row.GrokBot);
            }
            var sumIdx = _grid.Rows.Add(Line(
                group.ChannelLabel + "合计",
                "",
                UsageEvents.FormatCny(group.DailyHoldingCny),
                UsageEvents.FormatCny(group.TotalCny),
                FormatCount(group.EventCount),
                UsageParser.FormatTokenCount(group.TotalTokens),
                Unit(group.CnyPerMillion),
                Unit(group.CnyPerRequest)));
            StyleRow(_grid.Rows[sumIdx], RowKind.Total);
        }
        _grid.ResumeLayout();
        _exportBtn.Enabled = _report.Rows.Count > 0;
    }

    void AddCategory(string name, AccountCompareCategory cat)
    {
        var tokens = cat.Tokens == 0 && cat.Count == 0 ? "—" : UsageParser.FormatTokenCount(cat.Tokens);
        var idx = _grid.Rows.Add(Line(name, "", "", UsageEvents.FormatCny(cat.Cny), FormatCount(cat.Count), tokens, Unit(cat.CnyPerMillion), Unit(cat.CnyPerRequest)));
        StyleRow(_grid.Rows[idx], RowKind.Category);
    }

    enum RowKind { Header, Account, Category, Total }

    void StyleRow(DataGridViewRow row, RowKind kind)
    {
        switch (kind)
        {
            case RowKind.Header:
                row.DefaultCellStyle.Font = new Font(_grid.Font, FontStyle.Bold);
                row.DefaultCellStyle.BackColor = Color.FromArgb(245, 245, 245);
                break;
            case RowKind.Account:
                row.DefaultCellStyle.Font = new Font(_grid.Font, FontStyle.Bold);
                break;
            case RowKind.Category:
                row.DefaultCellStyle.ForeColor = Color.DimGray;
                row.Cells["name"].Style.Padding = new Padding(18, 0, 0, 0);
                break;
            case RowKind.Total:
                row.DefaultCellStyle.Font = new Font(_grid.Font, FontStyle.Bold);
                row.DefaultCellStyle.BackColor = Color.FromArgb(248, 248, 248);
                break;
        }
    }

    static object[] Line(string name, string window, string holding, string paid, string requests, string tokens, string perM, string perR) =>
        [name, window, holding, paid, requests, tokens, perM, perR];

    static string AccountName(IReadOnlyList<Account> accounts, AccountCompareRow row)
    {
        var acc = accounts.FirstOrDefault(a => a.Id == row.AccountId);
        var custom = (acc?.Label ?? "").Trim();
        if (custom.Length > 0) return custom;
        custom = (row.Label ?? "").Trim();
        if (custom.Length > 0 && custom != row.AccountId) return custom;
        return CompactAccountId(row.AccountId);
    }

    static string CompactAccountId(string raw)
    {
        var aid = (raw ?? "").Trim();
        if (aid.StartsWith("user_", StringComparison.Ordinal) && aid.Length > 18)
        {
            var body = aid[5..];
            if (body.StartsWith("01", StringComparison.Ordinal)) body = body[2..];
            return body[..5] + "…" + body[^2..];
        }
        if (aid.Length > 14) return aid[..12] + "…";
        return aid.Length == 0 ? "未命名账号" : aid;
    }

    static string Unit(double? amount) => UsageEvents.FormatCnyUnit(amount, "");

    static string FormatCount(int value) => value.ToString("N0", CultureInfo.InvariantCulture);

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
