using System.Runtime.InteropServices;
using CursorTokenCore;

namespace CursorTokenTray;

sealed class FlyoutForm : Form
{
    readonly Label _hero = new() { AutoSize = true, Font = new Font("Segoe UI", 22, FontStyle.Bold), ForeColor = Color.White };
    readonly Label _plan = new() { AutoSize = true, ForeColor = Color.Silver };
    readonly Label _body = new() { AutoSize = true, ForeColor = Color.Gainsboro, MaximumSize = new Size(388, 0) };
    readonly SparklineBox _spark = new() { Width = 388, Height = 36 };
    readonly Action _dismissBalloon, _refresh, _web, _settings, _copy, _report;
    readonly System.Windows.Forms.Timer _activateTimer = new() { Interval = 220 };
    readonly System.Windows.Forms.Timer _holdTimer = new() { Interval = 180 };
    readonly System.Windows.Forms.Timer _hideTimer = new() { Interval = 160 };
    bool _holdOpen;

    protected override bool ShowWithoutActivation => true;

    public FlyoutForm(Action dismissBalloon, Action refresh, Action web, Action settings, Action copy, Action report)
    {
        _dismissBalloon = dismissBalloon;
        _refresh = refresh;
        _web = web;
        _settings = settings;
        _copy = copy;
        _report = report;
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        ShowInTaskbar = false;
        TopMost = true;
        MinimumSize = new Size(360, 220);
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        BackColor = Color.FromArgb(32, 32, 32);
        KeyPreview = true;

        var copyBtn = Link("复制", _copy);
        var refBtn = Link("刷新", _refresh);
        var reportBtn = Link("报表", _report);
        var webBtn = Link("账单", _web);
        var setBtn = Link("设置", _settings);

        var leftBtns = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = false,
            FlowDirection = FlowDirection.LeftToRight,
            BackColor = Color.Transparent,
            Margin = new Padding(0),
        };
        leftBtns.Controls.Add(copyBtn);
        leftBtns.Controls.Add(refBtn);
        leftBtns.Controls.Add(reportBtn);
        var rightBtns = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = false,
            FlowDirection = FlowDirection.RightToLeft,
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            Margin = new Padding(0),
        };
        rightBtns.Controls.Add(setBtn);
        rightBtns.Controls.Add(webBtn);
        var bar = new TableLayoutPanel
        {
            AutoSize = true,
            ColumnCount = 2,
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 8, 0, 0),
        };
        bar.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        bar.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        bar.Controls.Add(leftBtns, 0, 0);
        bar.Controls.Add(rightBtns, 1, 0);

        var root = new TableLayoutPanel
        {
            AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink,
            ColumnCount = 1,
            Dock = DockStyle.Fill,
            Padding = new Padding(16),
        };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.Controls.Add(_hero);
        root.Controls.Add(_plan);
        root.Controls.Add(_body);
        root.Controls.Add(_spark);
        root.Controls.Add(bar);
        Controls.Add(root);

        _activateTimer.Tick += (_, _) =>
        {
            _activateTimer.Stop();
            if (IsDisposed || !Visible) { _holdOpen = false; return; }
            Activate();
            if (IsHandleCreated) SetForegroundWindow(Handle);
            _holdTimer.Stop();
            _holdTimer.Start();
        };
        _holdTimer.Tick += (_, _) => { _holdOpen = false; _holdTimer.Stop(); };
        _hideTimer.Tick += (_, _) =>
        {
            _hideTimer.Stop();
            if (!_holdOpen && !ContainsFocus) Hide();
        };
        Deactivate += (_, _) =>
        {
            if (_holdOpen) return;
            _hideTimer.Stop();
            _hideTimer.Start();
        };
        KeyDown += (_, e) =>
        {
            if (e.KeyCode != Keys.Escape) return;
            _holdOpen = false;
            _activateTimer.Stop();
            _holdTimer.Stop();
            _hideTimer.Stop();
            Hide();
        };
    }

    static LinkLabel Link(string t, Action a)
    {
        var l = new LinkLabel
        {
            Text = t,
            AutoSize = true,
            LinkColor = Color.DeepSkyBlue,
            ActiveLinkColor = Color.White,
            Margin = new Padding(0, 0, 12, 0),
        };
        l.LinkClicked += (_, _) => a();
        return l;
    }

    public void Render(UsageSnapshot? usage, string? error, string? updated, AppConfig cfg, List<double>? history = null)
    {
        if (usage is not null)
        {
            _hero.Text = $"{usage.RemainingPercent:0.0}%";
            _hero.ForeColor = usage.RemainingPercent > 50 ? Color.FromArgb(46, 204, 113)
                : usage.RemainingPercent >= 20 ? Color.FromArgb(241, 196, 15)
                : Color.FromArgb(231, 76, 60);
            _plan.Text = StatusText.FormatPlanCaption(usage.MembershipType, cfg.ActiveAccount?.DisplayLabel);
        }
        else
        {
            _hero.Text = error is { Length: > 0 } ? "—" : "…";
            _hero.ForeColor = Color.Silver;
            _plan.Text = error ?? "等待刷新…";
        }
        var rows = StatusText.BuildStatusLines(usage, error, updated, cfg.ActiveAccount?.DisplayLabel);
        _body.Text = string.Join("\n", rows.Select(r => $"{r.Item1}  {r.Item2}"));
        foreach (Control c in Controls)
            UpdateDashboardLinks(c, usage);
        if (history is not null) _spark.Values = history;
    }

    static void UpdateDashboardLinks(Control parent, UsageSnapshot? usage)
    {
        if (parent is LinkLabel l && (l.Text == "账单" || l.Text == "用量"))
            l.Text = UsageParser.DashboardButtonLabel(usage);
        foreach (Control child in parent.Controls)
            UpdateDashboardLinks(child, usage);
    }

    public void PopupNear(Point anchor)
    {
        try { _dismissBalloon(); } catch { }
        _hideTimer.Stop();
        _holdOpen = true;
        _holdTimer.Stop();
        _activateTimer.Stop();
        PerformLayout();
        var screen = Screen.FromPoint(anchor).WorkingArea;
        var (x, y) = UiLayout.FitPopup(screen.Left, screen.Top, screen.Right, screen.Bottom, Width, Height, anchor.X, anchor.Y);
        Location = new Point(x, y);
        if (!Visible) Show();
        else BringToFront();
        _activateTimer.Start();
    }

    public void PopupNearTray() => PopupNear(Cursor.Position);

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _activateTimer.Dispose();
            _holdTimer.Dispose();
            _hideTimer.Dispose();
        }
        base.Dispose(disposing);
    }

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);
}

sealed class SettingsForm : Form
{
    readonly TableLayoutPanel _root = new()
    {
        AutoSize = true,
        AutoSizeMode = AutoSizeMode.GrowAndShrink,
        ColumnCount = 1,
        Dock = DockStyle.Top,
        Padding = new Padding(16),
    };
    readonly TextBox _token = new() { Multiline = true, Height = 64, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
    readonly TextBox _interval = new() { Width = 80 };
    readonly TextBox _thresholds = new() { Width = 180 };
    readonly CheckBox _notify = new() { Text = "启用用量通知", AutoSize = true, Margin = new Padding(0, 6, 0, 4) };
    readonly CheckBox _exhaust = new() { Text = "启用耗尽风险通知", AutoSize = true, Margin = new Padding(0, 4, 0, 4) };
    readonly ComboBox _mode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 200 };
    readonly CheckBox _auto = new() { Text = "开机自启", AutoSize = true, Margin = new Padding(0, 6, 0, 8) };
    readonly ComboBox _accounts = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
    readonly Label _addCaption = Caption("添加账号（粘贴 Token，请勿分享；已保存的不会显示）");
    readonly Label _status = new() { AutoSize = true, Margin = new Padding(0, 4, 0, 4) };
    readonly Label _hint = new()
    {
        Text = "Windows 可从 Cursor 应用或 Firefox 导入；Chrome / Edge 因系统加密无法读取。",
        AutoSize = true,
        ForeColor = Color.DimGray,
        Margin = new Padding(0, 4, 0, 8),
    };
    AppConfig _cfg;
    readonly Action<AppConfig> _onSaved;
    readonly Func<string?, Task<ImportResult>> _import;

    bool _importing;

    public SettingsForm(AppConfig cfg, Action<AppConfig> onSaved, Func<string?, Task<ImportResult>> import, bool startImport)
    {
        _cfg = cfg; _onSaved = onSaved; _import = import;
        SuspendLayout();
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScroll = true;
        Text = "Cursor Token 设置";
        var icon = AppWindow.CreateIcon();
        if (icon is not null) Icon = icon;
        ClientSize = new Size(540, 640);
        MinimumSize = new Size(480, 360);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        _root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        _root.Controls.Add(Caption("当前账号"));
        _root.Controls.Add(_accounts);
        var rename = ActionButton("重命名");
        var del = ActionButton("删除");
        _root.Controls.Add(Flow(rename, del));
        _root.Controls.Add(_addCaption);
        _root.Controls.Add(_token);
        var cur = ActionButton("从 Cursor 导入");
        var add = ActionButton("添加此 Token");
        var ff = ActionButton("Firefox 登录");
        _root.Controls.Add(Flow(cur, add, ff));
        _root.Controls.Add(_status);
        _root.Controls.Add(_hint);
        _root.Controls.Add(FieldRow("刷新间隔（分钟）", _interval));
        _root.Controls.Add(FieldRow("告警阈值", _thresholds));
        _root.Controls.Add(_notify);
        _root.Controls.Add(_exhaust);
        _mode.Items.AddRange(["圆环百分比", "纯数字", "仅色点"]);
        _root.Controls.Add(FieldRow("托盘图标", _mode));
        _root.Controls.Add(_auto);
        var cancel = ActionButton("取消");
        var apply = ActionButton("应用");
        var save = ActionButton("保存");
        var actions = Flow(save, apply, cancel);
        actions.FlowDirection = FlowDirection.RightToLeft;
        actions.Dock = DockStyle.Fill;
        _root.Controls.Add(actions);
        Controls.Add(_root);
        LoadFrom(_cfg);
        _accounts.SelectedIndexChanged += (_, _) =>
        {
            if (_accounts.SelectedItem is AccountItem item) { _cfg.SetActiveAccount(item.Id); _onSaved(_cfg); }
        };
        rename.Click += (_, _) => RenameActive();
        del.Click += (_, _) =>
        {
            if (_cfg.ActiveAccount is null) return;
            if (MessageBox.Show($"确定删除「{_cfg.ActiveAccount.DisplayLabel}」？", "删除账号", MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            _cfg.RemoveAccount(_cfg.ActiveAccount.Id);
            LoadFrom(_cfg); _onSaved(_cfg);
        };
        add.Click += (_, _) => AddToken();
        cur.Click += async (_, _) => await DoImport("cursor-app");
        ff.Click += async (_, _) =>
        {
            try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("https://cursor.com/dashboard") { UseShellExecute = true }); } catch { }
            await DoImport("firefox");
        };
        cancel.Click += (_, _) => Close();
        apply.Click += (_, _) => Persist(false);
        save.Click += (_, _) => { Persist(true); Close(); };
        ResumeLayout(false);
        if (startImport) BeginInvoke(async () => await DoImport("cursor-app"));
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        FitToContent();
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        BeginInvoke(FitToContent);
    }

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        WrapText();
    }

    void FitToContent()
    {
        WrapText();
        _root.PerformLayout();
        var pref = _root.PreferredSize;
        var work = Screen.FromControl(this).WorkingArea;
        var (w, h) = UiLayout.FitDialog(pref.Width, pref.Height, 520, 420, work.Width, work.Height);
        ClientSize = new Size(w, h);
        WrapText();
    }

    void WrapText()
    {
        var inner = Math.Max(200, ClientSize.Width - _root.Padding.Horizontal - 8);
        foreach (var label in new[] { _addCaption, _status, _hint })
            label.MaximumSize = new Size(inner, 0);
    }

    void RenameActive()
    {
        if (_cfg.ActiveAccount is null) return;
        using var prompt = new Form
        {
            Text = "重命名",
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterParent,
            AutoScaleMode = AutoScaleMode.Dpi,
            AutoScaleDimensions = new SizeF(96F, 96F),
            AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink,
            MinimizeBox = false,
            MaximizeBox = false,
            Padding = new Padding(16),
        };
        var field = new TextBox { Text = _cfg.ActiveAccount.Label, Width = 320, MinimumSize = new Size(260, 0) };
        var ok = ActionButton("确定");
        ok.DialogResult = DialogResult.OK;
        var cancelR = ActionButton("取消");
        cancelR.DialogResult = DialogResult.Cancel;
        var box = new TableLayoutPanel
        {
            AutoSize = true,
            ColumnCount = 1,
            Dock = DockStyle.Fill,
        };
        box.Controls.Add(field);
        box.Controls.Add(Flow(ok, cancelR));
        prompt.Controls.Add(box);
        prompt.AcceptButton = ok;
        prompt.CancelButton = cancelR;
        if (prompt.ShowDialog(this) != DialogResult.OK) return;
        _cfg.RenameAccount(_cfg.ActiveAccount.Id, field.Text);
        LoadFrom(_cfg); _onSaved(_cfg);
    }

    static Label Caption(string text) => new()
    {
        Text = text,
        AutoSize = true,
        Margin = new Padding(0, 8, 0, 4),
    };

    static Button ActionButton(string text) => new()
    {
        Text = text,
        AutoSize = true,
        AutoSizeMode = AutoSizeMode.GrowAndShrink,
        Margin = new Padding(0, 0, 8, 4),
    };

    static FlowLayoutPanel Flow(params Control[] items)
    {
        var p = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = true,
            FlowDirection = FlowDirection.LeftToRight,
            Margin = new Padding(0, 4, 0, 4),
        };
        foreach (var c in items) p.Controls.Add(c);
        return p;
    }

    static TableLayoutPanel FieldRow(string label, Control field)
    {
        var row = new TableLayoutPanel
        {
            AutoSize = true,
            ColumnCount = 2,
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 6, 0, 6),
        };
        row.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        row.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        row.Controls.Add(new Label
        {
            Text = label,
            AutoSize = true,
            Anchor = AnchorStyles.Left,
            Margin = new Padding(0, 6, 12, 0),
        }, 0, 0);
        field.Anchor = AnchorStyles.Left;
        field.Margin = new Padding(0, 2, 0, 2);
        row.Controls.Add(field, 1, 0);
        return row;
    }

    public void FocusToken() { _token.Focus(); _token.SelectAll(); }

    public void StartImport() => BeginInvoke(async () => await DoImport("cursor-app"));

    void LoadFrom(AppConfig cfg)
    {
        _cfg = cfg;
        _accounts.Items.Clear();
        foreach (var a in cfg.Accounts)
            _accounts.Items.Add(new AccountItem(a.Id, a.Caption(a.Id == cfg.ActiveAccountId)));
        var idx = cfg.Accounts.FindIndex(a => a.Id == cfg.ActiveAccountId);
        if (idx >= 0) _accounts.SelectedIndex = idx;
        _token.Text = "";
        _token.PlaceholderText = "粘贴新 Token 以添加或更换账号（已保存的不会显示）";
        _interval.Text = cfg.RefreshIntervalMinutes.ToString();
        _thresholds.Text = string.Join(",", cfg.AlertThresholds);
        _notify.Checked = cfg.NotifyEnabled;
        _exhaust.Checked = cfg.NotifyExhaustionRisk;
        _mode.SelectedIndex = cfg.TrayDisplayMode switch { "number" => 1, "dot" => 2, _ => 0 };
        _auto.Checked = cfg.AutostartEnabled;
    }

    void AddToken()
    {
        try
        {
            _cfg.UpsertAccount(_token.Text, activate: true);
            Persist(false);
            _status.Text = "已添加";
        }
        catch (Exception ex) { _status.Text = ex.Message; }
    }

    async Task DoImport(string? prefer)
    {
        if (_importing) return;
        _importing = true;
        _status.Text = "正在导入…";
        try
        {
            var result = await _import(prefer);
            _status.Text = result.Message;
            if (!result.Ok) return;
            _cfg.UpsertAccount(result.Token, membershipType: result.MembershipType, remaining: result.RemainingPercent, activate: true);
            _token.Text = "";
            Persist(false);
        }
        finally { _importing = false; }
    }

    void Persist(bool _)
    {
        if (int.TryParse(_interval.Text, out var n) && n >= 1) _cfg.RefreshIntervalMinutes = n;
        _cfg.AlertThresholds = ConfigStore.ParseThresholds(_thresholds.Text);
        _cfg.NotifyEnabled = _notify.Checked;
        _cfg.NotifyExhaustionRisk = _exhaust.Checked;
        _cfg.TrayDisplayMode = _mode.SelectedIndex switch { 1 => "number", 2 => "dot", _ => "ring" };
        _cfg.AutostartEnabled = _auto.Checked;
        if (!string.IsNullOrWhiteSpace(_token.Text))
            try { _cfg.UpsertAccount(_token.Text, activate: true); } catch { }
        _onSaved(_cfg);
        LoadFrom(_cfg);
    }

    sealed record AccountItem(string Id, string Caption)
    {
        public override string ToString() => Caption;
    }
}

sealed class SparklineBox : Control
{
    List<double> _values = [];
    public List<double>? Values
    {
        get => _values;
        set
        {
            _values = value is { Count: >= 2 } ? value : [];
            Visible = _values.Count >= 2;
            Invalidate();
        }
    }

    public SparklineBox()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
        Visible = false;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        if (_values.Count < 2) return;
        var g = e.Graphics;
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        var minV = Math.Min(_values.Min(), 0);
        var maxV = Math.Max(_values.Max(), minV + 1);
        var pts = new PointF[_values.Count];
        for (var i = 0; i < _values.Count; i++)
        {
            var x = Width * i / (float)Math.Max(_values.Count - 1, 1);
            var y = Height * (1 - (float)((_values[i] - minV) / (maxV - minV)));
            pts[i] = new PointF(x, y);
        }
        var penW = Math.Max(1.5f, 1.5f * UiLayout.DpiScale(DeviceDpi));
        using var pen = new Pen(Color.DeepSkyBlue, penW);
        g.DrawLines(pen, pts);
    }
}
