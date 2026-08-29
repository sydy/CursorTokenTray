using System.Globalization;
using CursorTokenCore;

namespace CursorTokenTray;

sealed class ReportForm : Form
{
    public readonly record struct ReportState(string Token, string AccountId, UsageSnapshot? Usage, bool IsTeam);

    const int DesignWidth = 1040;
    const int DesignHeight = 880;
    const int DesignMinWidth = 900;
    const int DesignMinHeight = 640;
    const int DesignChartRow = 250;
    const int DesignModelRow = 180;
    const int DesignHeaderH = 28;
    const int DesignRowH = 24;

    readonly CursorClient _client;
    readonly Func<ReportState> _state;
    readonly ComboBox _scope = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    readonly ComboBox _kind = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    readonly ComboBox _model = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    readonly ComboBox _cloud = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    readonly Label _status = new() { AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(8, 8, 0, 0) };
    readonly Label _kpi = new() { AutoSize = true, Margin = new Padding(0, 8, 0, 8) };
    readonly UsageChartPanel _chart = new();
    readonly DataGridView _models = MakeGrid();
    readonly DataGridView _grid = MakeGrid();
    readonly Button _syncBtn = new() { Text = "同步", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    readonly Button _exportBtn = new() { Text = "导出 CSV", AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
    readonly Label _scopeLabel = new() { Text = "范围", AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 8, 6, 0) };
    readonly TableLayoutPanel _root = new()
    {
        Dock = DockStyle.Fill,
        ColumnCount = 1,
        RowCount = 6,
        Padding = new Padding(16),
    };
    static readonly int[] ModelMinWidths = [160, 72, 72, 56, 48];
    static readonly int[] DetailMinWidths = [110, 100, 56, 140, 64, 72, 48];
    List<UsageEvent> _all = [];
    bool _syncing;
    bool _teamScope;
    bool _ready;

    public ReportForm(CursorClient client, Func<ReportState> state)
    {
        _client = client;
        _state = state;
        SuspendLayout();
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        Text = "用量报表";
        var icon = AppWindow.CreateIcon();
        if (icon is not null) Icon = icon;
        MinimumSize = new Size(DesignMinWidth, DesignMinHeight);
        StartPosition = FormStartPosition.CenterScreen;
        Width = DesignWidth;
        Height = DesignHeight;

        _scope.Items.AddRange(["仅自己", "全员"]);
        _scope.SelectedIndex = 0;
        _kind.Items.AddRange(["全部类型", "套餐内", "免费", "按需"]);
        _kind.SelectedIndex = 0;
        _cloud.Items.AddRange(["全部来源", "本机", "云端 Agent"]);
        _cloud.SelectedIndex = 0;
        _model.Items.Add("全部模型");
        _model.SelectedIndex = 0;

        _models.Columns.Add(new DataGridViewTextBoxColumn { Name = "model", HeaderText = "模型", FillWeight = 40 });
        _models.Columns.Add(new DataGridViewTextBoxColumn { Name = "tokens", HeaderText = "Token", FillWeight = 18 });
        _models.Columns.Add(new DataGridViewTextBoxColumn { Name = "cost", HeaderText = "费用", FillWeight = 16 });
        _models.Columns.Add(new DataGridViewTextBoxColumn { Name = "count", HeaderText = "次数", FillWeight = 14 });
        _models.Columns.Add(new DataGridViewTextBoxColumn { Name = "cloud", HeaderText = "云端", FillWeight = 12 });

        _grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "date", HeaderText = "日期 (北京时间)", FillWeight = 18 });
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

        _root.ColumnStyles.Clear();
        _root.RowStyles.Clear();
        _root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        _root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        _root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        _root.RowStyles.Add(new RowStyle(SizeType.Absolute, DesignChartRow));
        _root.RowStyles.Add(new RowStyle(SizeType.Absolute, DesignModelRow));
        _root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        _root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        _root.Controls.Add(filters, 0, 0);
        _root.Controls.Add(_kpi, 0, 1);
        _root.Controls.Add(_chart, 0, 2);
        var modelWrap = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
        modelWrap.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        modelWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        modelWrap.Controls.Add(new Label { Text = "按模型", AutoSize = true, Margin = new Padding(0, 8, 0, 4) }, 0, 0);
        modelWrap.Controls.Add(_models, 0, 1);
        _root.Controls.Add(modelWrap, 0, 3);
        _root.Controls.Add(new Label { Text = "明细", AutoSize = true, Margin = new Padding(0, 8, 0, 4) }, 0, 4);
        _root.Controls.Add(_grid, 0, 5);
        Controls.Add(_root);

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
        ResumeLayout(false);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ApplyDpiLayout(resizeWindow: true);
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        BeginInvoke(() => ApplyDpiLayout(resizeWindow: false));
    }

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        WrapKpi();
    }

    void ApplyDpiLayout(bool resizeWindow)
    {
        var dpi = DeviceDpi;
        _scope.Width = UiLayout.ScalePx(120, dpi);
        _kind.Width = UiLayout.ScalePx(130, dpi);
        _model.Width = UiLayout.ScalePx(280, dpi);
        _cloud.Width = UiLayout.ScalePx(140, dpi);
        _model.DropDownWidth = Math.Max(_model.Width, UiLayout.ScalePx(360, dpi));

        if (_root.RowStyles.Count > 3)
        {
            _root.RowStyles[2].SizeType = SizeType.Absolute;
            _root.RowStyles[2].Height = UiLayout.ScalePx(DesignChartRow, dpi);
            _root.RowStyles[3].SizeType = SizeType.Absolute;
            _root.RowStyles[3].Height = UiLayout.ScalePx(DesignModelRow, dpi);
        }
        _chart.ApplyDpi(dpi);

        var headerH = UiLayout.ScalePx(DesignHeaderH, dpi);
        var rowH = UiLayout.ScalePx(DesignRowH, dpi);
        ApplyGridMetrics(_models, headerH, rowH, ModelMinWidths, dpi);
        ApplyGridMetrics(_grid, headerH, rowH, DetailMinWidths, dpi);

        var work = Screen.FromControl(this).WorkingArea;
        var (w, h) = UiLayout.FitWindow(DesignWidth, DesignHeight, DesignMinWidth, DesignMinHeight, dpi, work.Width, work.Height);
        MinimumSize = new Size(Math.Min(w, UiLayout.ScalePx(DesignMinWidth, dpi)), Math.Min(h, UiLayout.ScalePx(DesignMinHeight, dpi)));
        if (resizeWindow)
            Size = new Size(w, h);
        WrapKpi();
    }

    static void ApplyGridMetrics(DataGridView grid, int headerH, int rowH, int[] minDesignWidths, int dpi)
    {
        grid.ColumnHeadersHeight = headerH;
        grid.RowTemplate.Height = rowH;
        for (var i = 0; i < grid.Columns.Count && i < minDesignWidths.Length; i++)
            grid.Columns[i].MinimumWidth = UiLayout.ScalePx(minDesignWidths[i], dpi);
        foreach (DataGridViewRow row in grid.Rows)
            row.Height = rowH;
    }

    void WrapKpi()
    {
        var inner = Math.Max(200, ClientSize.Width - _root.Padding.Horizontal - 8);
        _kpi.MaximumSize = new Size(inner, 0);
        _status.MaximumSize = new Size(Math.Max(160, inner / 2), 0);
    }

    static DataGridView MakeGrid() => new()
    {
        Dock = DockStyle.Fill,
        ReadOnly = true,
        AllowUserToAddRows = false,
        AllowUserToDeleteRows = false,
        AllowUserToResizeRows = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
        ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing,
        RowHeadersVisible = false,
        SelectionMode = DataGridViewSelectionMode.FullRowSelect,
        MultiSelect = false,
        BackgroundColor = Color.White,
        BorderStyle = BorderStyle.FixedSingle,
    };

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
            var stamp = DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8));
            _status.Text = $"已同步 {_all.Count} 条{extra}  ·  {stamp:HH:mm:ss}";
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
        _chart.Bind(report.Events);

        _models.Rows.Clear();
        _models.SuspendLayout();
        foreach (var row in report.Models)
        {
            _models.Rows.Add(
                row.Name,
                UsageParser.FormatTokenCount(row.Tokens),
                row.Cents > 0 ? UsageParser.FormatUsdCents(row.Cents) : "—",
                row.Count.ToString(CultureInfo.InvariantCulture),
                row.HeadlessCount > 0 ? row.HeadlessCount.ToString(CultureInfo.InvariantCulture) : "—");
        }
        _models.ResumeLayout();

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
        ApplyGridMetrics(_models, UiLayout.ScalePx(DesignHeaderH, DeviceDpi), UiLayout.ScalePx(DesignRowH, DeviceDpi), ModelMinWidths, DeviceDpi);
        ApplyGridMetrics(_grid, UiLayout.ScalePx(DesignHeaderH, DeviceDpi), UiLayout.ScalePx(DesignRowH, DeviceDpi), DetailMinWidths, DeviceDpi);
    }

    void ExportCsv()
    {
        var report = UsageEvents.BuildReport(_all, CurrentFilter());
        if (report.Events.Count == 0) return;
        using var dlg = new SaveFileDialog
        {
            Filter = "CSV 文件 (*.csv)|*.csv",
            FileName = $"cursor-usage-{DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)):yyyyMMdd}.csv",
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
