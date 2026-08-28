using System.Globalization;
using CursorTokenCore;

namespace CursorTokenTray;

sealed class ReportForm : Form
{
    public readonly record struct ReportState(string Token, string AccountId, UsageSnapshot? Usage, bool IsTeam);

    readonly CursorClient _client;
    readonly Func<ReportState> _state;
    readonly ComboBox _scope = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 110 };
    readonly ComboBox _kind = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 110 };
    readonly ComboBox _model = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 240 };
    readonly ComboBox _cloud = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 110 };
    readonly Label _status = new() { AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(8, 8, 0, 0) };
    readonly Label _kpi = new() { AutoSize = true, MaximumSize = new Size(980, 0), Margin = new Padding(0, 8, 0, 8) };
    readonly SparklineBox _spark = new() { Height = 52, Dock = DockStyle.Fill };
    readonly Label _sparkCaption = new() { AutoSize = true, ForeColor = Color.DimGray, Text = "按日 Token" };
    readonly ListView _models = new()
    {
        View = View.Details,
        FullRowSelect = true,
        HeaderStyle = ColumnHeaderStyle.Nonclickable,
        Height = 140,
        Dock = DockStyle.Fill,
    };
    readonly DataGridView _grid = new()
    {
        Dock = DockStyle.Fill,
        ReadOnly = true,
        AllowUserToAddRows = false,
        AllowUserToDeleteRows = false,
        AllowUserToResizeRows = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
        RowHeadersVisible = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect,
        MultiSelect = false,
        BackgroundColor = Color.White,
    };
    readonly Button _syncBtn = new() { Text = "同步", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    readonly Button _exportBtn = new() { Text = "导出 CSV", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    readonly Label _scopeLabel = new() { Text = "范围", AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 8, 6, 0) };
    List<UsageEvent> _all = [];
    bool _syncing;
    bool _teamScope;
    bool _ready;

    public ReportForm(CursorClient client, Func<ReportState> state)
    {
        _client = client;
        _state = state;
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        Text = "用量报表";
        MinimumSize = new Size(820, 560);
        StartPosition = FormStartPosition.CenterScreen;
        Width = 980;
        Height = 720;

        _scope.Items.AddRange(["仅自己", "全员"]);
        _scope.SelectedIndex = 0;
        _kind.Items.AddRange(["全部类型", "套餐内", "免费", "按需"]);
        _kind.SelectedIndex = 0;
        _cloud.Items.AddRange(["全部来源", "本机", "云端 Agent"]);
        _cloud.SelectedIndex = 0;
        _model.Items.Add("全部模型");
        _model.SelectedIndex = 0;

        _models.Columns.Add("模型", 280);
        _models.Columns.Add("Token", 90);
        _models.Columns.Add("费用", 90);
        _models.Columns.Add("次数", 70);
        _models.Columns.Add("云端", 70);

        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "date", HeaderText = "日期 (UTC)", FillWeight = 18 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "user", HeaderText = "用户", FillWeight = 18 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "kind", HeaderText = "类型", FillWeight = 10 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "model", HeaderText = "模型", FillWeight = 22 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "tokens", HeaderText = "Token", FillWeight = 10 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "cost", HeaderText = "费用", FillWeight = 14 });
        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "cloud", HeaderText = "云端", FillWeight = 8 });

        var filters = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = true,
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 4, 0, 4),
        };
        filters.Controls.Add(_scopeLabel);
        filters.Controls.Add(_scope);
        filters.Controls.Add(Tag("类型", _kind));
        filters.Controls.Add(Tag("模型", _model));
        filters.Controls.Add(Tag("来源", _cloud));
        filters.Controls.Add(_syncBtn);
        filters.Controls.Add(_exportBtn);
        filters.Controls.Add(_status);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 6,
            Padding = new Padding(16),
        };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 160));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.Controls.Add(filters, 0, 0);
        root.Controls.Add(_kpi, 0, 1);
        var sparkWrap = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        sparkWrap.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        sparkWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        sparkWrap.Controls.Add(_sparkCaption, 0, 0);
        sparkWrap.Controls.Add(_spark, 0, 1);
        root.Controls.Add(sparkWrap, 0, 2);
        var modelWrap = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        modelWrap.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        modelWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        modelWrap.Controls.Add(new Label { Text = "按模型", AutoSize = true, Margin = new Padding(0, 8, 0, 4) }, 0, 0);
        modelWrap.Controls.Add(_models, 0, 1);
        root.Controls.Add(modelWrap, 0, 3);
        root.Controls.Add(new Label { Text = "明细", AutoSize = true, Margin = new Padding(0, 8, 0, 4) }, 0, 4);
        root.Controls.Add(_grid, 0, 5);
        Controls.Add(root);

        _scope.SelectedIndexChanged += (_, _) =>
        {
            if (!_ready) return;
            _teamScope = _scope.SelectedIndex == 1;
            _ = SyncAsync(false);
        };
        _kind.SelectedIndexChanged += (_, _) => { if (_ready) Render(); };
        _model.SelectedIndexChanged += (_, _) => { if (_ready) Render(); };
        _cloud.SelectedIndexChanged += (_, _) => { if (_ready) Render(); };
        _syncBtn.Click += (_, _) => _ = SyncAsync(true);
        _exportBtn.Click += (_, _) => ExportCsv();
        Shown += (_, _) => _ = SyncAsync(false);
    }

    public void RequestSync() => _ = SyncAsync(false);

    static Control Tag(string label, Control field)
    {
        var row = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = false,
            Margin = new Padding(12, 0, 0, 0),
        };
        row.Controls.Add(new Label { Text = label, AutoSize = true, Margin = new Padding(0, 8, 6, 0) });
        row.Controls.Add(field);
        return row;
    }

    void UpdateScopeVisible(bool isTeam)
    {
        _scope.Visible = isTeam;
        _scopeLabel.Visible = isTeam;
        if (!isTeam)
        {
            _teamScope = false;
            if (_scope.SelectedIndex != 0) _scope.SelectedIndex = 0;
        }
    }

    async Task SyncAsync(bool forceFull)
    {
        if (_syncing) return;
        _syncing = true;
        _ready = true;
        _syncBtn.Enabled = false;
        var st = _state();
        UpdateScopeVisible(st.IsTeam);
        if (string.IsNullOrWhiteSpace(st.Token))
        {
            _status.Text = "未配置 Token，请先在设置里导入账号";
            _syncing = false;
            _syncBtn.Enabled = true;
            return;
        }
        if (!forceFull)
        {
            _all = UsageEvents.Load(st.AccountId, _teamScope);
            FillModels();
            Render();
        }
        _status.Text = "正在同步本周期明细…";
        try
        {
            var result = await UsageEvents.SyncAsync(_client, st.Token, st.AccountId, st.Usage, _teamScope);
            _all = result.Events;
            FillModels();
            Render();
            var extra = result.Truncated ? $"（服务端约 {result.TotalAvailable} 条，已截到最近 {result.Events.Count} 条）" : "";
            _status.Text = $"已同步 {_all.Count} 条{extra}  ·  {DateTime.Now:HH:mm:ss}";
        }
        catch (CursorApiException ex)
        {
            FillModels();
            Render();
            _status.Text = "同步失败：" + ex.Message;
        }
        catch (Exception ex)
        {
            FillModels();
            Render();
            _status.Text = "同步失败：" + ex.Message;
        }
        finally
        {
            _syncing = false;
            _syncBtn.Enabled = true;
        }
    }

    UsageReportFilter CurrentFilter()
    {
        var kind = _kind.SelectedIndex switch { 1 => UsageEvents.KindIncluded, 2 => UsageEvents.KindFree, 3 => UsageEvents.KindOnDemand, _ => "" };
        var model = _model.SelectedIndex > 0 ? _model.SelectedItem?.ToString() ?? "" : "";
        bool? cloud = _cloud.SelectedIndex switch { 1 => false, 2 => true, _ => null };
        return new UsageReportFilter { Kind = kind, Model = model, Headless = cloud };
    }

    void FillModels()
    {
        var selected = _model.SelectedItem?.ToString();
        var names = _all.Select(e => e.Model).Where(n => n.Length > 0).Distinct(StringComparer.Ordinal).OrderBy(n => n).ToList();
        _model.BeginUpdate();
        _model.Items.Clear();
        _model.Items.Add("全部模型");
        foreach (var name in names) _model.Items.Add(name);
        var idx = selected is null or "全部模型" ? 0 : _model.Items.IndexOf(selected);
        _model.SelectedIndex = idx >= 0 ? idx : 0;
        _model.EndUpdate();
    }

    void Render()
    {
        var report = UsageEvents.BuildReport(_all, CurrentFilter());
        var mix = $"套餐内 {report.IncludedCount} · 免费 {report.FreeCount} · 按需 {report.OnDemandCount}";
        if (report.HeadlessCount > 0) mix += $" · 云端 {report.HeadlessCount}";
        var cost = report.HasCost ? $"    费用 {UsageParser.FormatUsdCents(report.TotalCents)}" : "";
        _kpi.Text = $"请求 {report.EventCount}    Token {UsageParser.FormatTokenCount(report.TotalTokens)}    {mix}{cost}";
        _sparkCaption.Text = report.Daily.Count == 0
            ? "按日 Token"
            : $"按日 Token（{report.Daily.First().Date} 至 {report.Daily.Last().Date}）";
        _spark.Values = report.Daily.Count >= 2 ? report.Daily.Select(d => (double)d.Tokens).ToList() : [];

        _models.BeginUpdate();
        _models.Items.Clear();
        foreach (var row in report.Models)
        {
            var item = new ListViewItem(row.Name);
            item.SubItems.Add(UsageParser.FormatTokenCount(row.Tokens));
            item.SubItems.Add(row.Cents > 0 ? UsageParser.FormatUsdCents(row.Cents) : "—");
            item.SubItems.Add(row.Count.ToString(CultureInfo.InvariantCulture));
            item.SubItems.Add(row.HeadlessCount > 0 ? row.HeadlessCount.ToString(CultureInfo.InvariantCulture) : "—");
            _models.Items.Add(item);
        }
        _models.EndUpdate();

        _grid.Rows.Clear();
        _grid.SuspendLayout();
        foreach (var ev in report.Events)
        {
            _grid.Rows.Add(
                UsageEvents.FormatTime(ev.TimestampMs),
                ev.UserEmail,
                UsageEvents.KindLabel(ev.Kind),
                ev.Model,
                UsageParser.FormatTokenCount(ev.Tokens),
                UsageEvents.FormatCost(ev),
                ev.IsHeadless ? "是" : "否");
        }
        _grid.ResumeLayout();
        _exportBtn.Enabled = report.Events.Count > 0;
    }

    void ExportCsv()
    {
        var report = UsageEvents.BuildReport(_all, CurrentFilter());
        if (report.Events.Count == 0) return;
        using var dlg = new SaveFileDialog
        {
            Filter = "CSV 文件 (*.csv)|*.csv",
            FileName = $"cursor-usage-{DateTime.UtcNow:yyyyMMdd}.csv",
            OverwritePrompt = true,
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            File.WriteAllText(dlg.FileName, UsageEvents.ToCsv(report.Events));
            _status.Text = "已导出 " + dlg.FileName;
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "导出失败：" + ex.Message, "用量报表", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
