using CursorTokenCore;

namespace CursorTokenTray;

sealed class FlyoutForm : Form
{
    readonly Label _hero = new() { AutoSize = true, Font = new Font("Segoe UI", 22, FontStyle.Bold), ForeColor = Color.White };
    readonly Label _plan = new() { AutoSize = true, ForeColor = Color.Silver };
    readonly Label _body = new() { AutoSize = false, ForeColor = Color.Gainsboro, Width = 360 };
    readonly SparklineBox _spark = new() { Width = 360, Height = 36 };
    readonly Action _refresh, _web, _settings, _copy;

    public FlyoutForm(Action _, Action refresh, Action web, Action settings, Action copy)
    {
        _refresh = refresh; _web = web; _settings = settings; _copy = copy;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        ShowInTaskbar = false;
        TopMost = true;
        Width = 420;
        Height = 320;
        BackColor = Color.FromArgb(32, 32, 32);
        var copyBtn = Link("复制", _copy);
        var refBtn = Link("刷新", _refresh);
        var webBtn = Link("账单", _web);
        var setBtn = Link("设置", _settings);
        Controls.Add(_hero);
        Controls.Add(_plan);
        Controls.Add(_body);
        Controls.Add(_spark);
        Controls.Add(copyBtn);
        Controls.Add(refBtn);
        Controls.Add(webBtn);
        Controls.Add(setBtn);
        _hero.Location = new Point(16, 16);
        _plan.Location = new Point(16, 56);
        _body.Location = new Point(16, 88);
        _body.Height = 140;
        _spark.Location = new Point(16, 230);
        copyBtn.Location = new Point(16, 276);
        refBtn.Location = new Point(70, 276);
        webBtn.Location = new Point(280, 276);
        setBtn.Location = new Point(340, 276);
        Deactivate += (_, _) => Hide();
        KeyPreview = true;
        KeyDown += (_, e) => { if (e.KeyCode == Keys.Escape) Hide(); };
    }

    static LinkLabel Link(string t, Action a)
    {
        var l = new LinkLabel { Text = t, AutoSize = true, LinkColor = Color.DeepSkyBlue, ActiveLinkColor = Color.White };
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
            if (c is LinkLabel l && (l.Text == "账单" || l.Text == "用量"))
                l.Text = UsageParser.DashboardButtonLabel(usage);
        if (history is not null) _spark.Values = history;
    }

    public void PopupNear(Point anchor)
    {
        var screen = Screen.FromPoint(anchor).WorkingArea;
        var x = anchor.X - Width;
        var y = anchor.Y - Height - 12;
        if (x < screen.Left + 8) x = screen.Left + 8;
        if (x + Width > screen.Right - 8) x = screen.Right - Width - 8;
        if (y < screen.Top + 8) y = Math.Min(anchor.Y + 12, screen.Bottom - Height - 8);
        if (y + Height > screen.Bottom - 8) y = screen.Bottom - Height - 8;
        Location = new Point(Math.Max(screen.Left, x), Math.Max(screen.Top, y));
        Show();
        Activate();
    }

    public void PopupNearTray() => PopupNear(Cursor.Position);
}

sealed class SettingsForm : Form
{
    readonly TextBox _token = new() { Multiline = true, Height = 56, Width = 460, ScrollBars = ScrollBars.Vertical };
    readonly TextBox _interval = new() { Width = 72 };
    readonly TextBox _thresholds = new() { Width = 160 };
    readonly CheckBox _notify = new() { Text = "启用用量通知", AutoSize = true };
    readonly CheckBox _exhaust = new() { Text = "启用耗尽风险通知", AutoSize = true };
    readonly ComboBox _mode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 180 };
    readonly CheckBox _auto = new() { Text = "开机自启", AutoSize = true };
    readonly ComboBox _accounts = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 460 };
    readonly Label _status = new() { AutoSize = false, Width = 460, Height = 40 };
    AppConfig _cfg;
    readonly Action<AppConfig> _onSaved;
    readonly Func<string?, Task<ImportResult>> _import;

    bool _importing;

    public SettingsForm(AppConfig cfg, Action<AppConfig> onSaved, Func<string?, Task<ImportResult>> import, bool startImport)
    {
        _cfg = cfg; _onSaved = onSaved; _import = import;
        Text = "Cursor Token 设置";
        Width = 520; Height = 600;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        var y = 16;
        Controls.Add(new Label { Text = "当前账号", Left = 20, Top = y, AutoSize = true });
        y += 22; _accounts.Left = 20; _accounts.Top = y; Controls.Add(_accounts);
        y += 36;
        var rename = new Button { Text = "重命名", Left = 20, Top = y, Width = 80 };
        var del = new Button { Text = "删除", Left = 110, Top = y, Width = 80 };
        Controls.Add(rename); Controls.Add(del);
        y += 40;
        Controls.Add(new Label { Text = "添加账号（粘贴 Token，请勿分享）", Left = 20, Top = y, AutoSize = true });
        y += 22; _token.Left = 20; _token.Top = y; Controls.Add(_token);
        y += 66;
        var cur = new Button { Text = "从 Cursor 导入", Left = 20, Top = y, Width = 140 };
        var add = new Button { Text = "添加此 Token", Left = 170, Top = y, Width = 120 };
        var ff = new Button { Text = "Firefox 登录", Left = 300, Top = y, Width = 110 };
        Controls.Add(cur); Controls.Add(add); Controls.Add(ff);
        y += 40; _status.Left = 20; _status.Top = y; Controls.Add(_status);
        y += 36;
        Controls.Add(new Label
        {
            Text = "Windows 可从 Cursor 应用或 Firefox 导入；Chrome / Edge 因系统加密无法读取。",
            Left = 20,
            Top = y,
            Width = 460,
            Height = 32,
            ForeColor = Color.DimGray,
        });
        y += 36;
        Controls.Add(new Label { Text = "刷新间隔（分钟）", Left = 20, Top = y, AutoSize = true });
        _interval.Left = 200; _interval.Top = y - 4; Controls.Add(_interval);
        y += 32;
        Controls.Add(new Label { Text = "告警阈值", Left = 20, Top = y, AutoSize = true });
        _thresholds.Left = 200; _thresholds.Top = y - 4; Controls.Add(_thresholds);
        y += 32; _notify.Left = 20; _notify.Top = y; Controls.Add(_notify);
        y += 28; _exhaust.Left = 20; _exhaust.Top = y; Controls.Add(_exhaust);
        y += 32;
        Controls.Add(new Label { Text = "托盘图标", Left = 20, Top = y, AutoSize = true });
        _mode.Items.AddRange(["圆环百分比", "纯数字", "仅色点"]);
        _mode.Left = 200; _mode.Top = y - 4; Controls.Add(_mode);
        y += 36; _auto.Left = 20; _auto.Top = y; Controls.Add(_auto);
        y += 40;
        var cancel = new Button { Text = "取消", Left = 220, Top = y, Width = 80 };
        var apply = new Button { Text = "应用", Left = 310, Top = y, Width = 80 };
        var save = new Button { Text = "保存", Left = 400, Top = y, Width = 80 };
        Controls.Add(cancel); Controls.Add(apply); Controls.Add(save);
        LoadFrom(_cfg);
        _accounts.SelectedIndexChanged += (_, _) =>
        {
            if (_accounts.SelectedItem is AccountItem item) { _cfg.SetActiveAccount(item.Id); _onSaved(_cfg); }
        };
        rename.Click += (_, _) =>
        {
            if (_cfg.ActiveAccount is null) return;
            using var prompt = new Form
            {
                Text = "重命名",
                Width = 360,
                Height = 140,
                FormBorderStyle = FormBorderStyle.FixedDialog,
                StartPosition = FormStartPosition.CenterParent,
            };
            var field = new TextBox { Left = 16, Top = 16, Width = 310, Text = _cfg.ActiveAccount.Label };
            var ok = new Button { Text = "确定", Left = 160, Top = 56, Width = 80, DialogResult = DialogResult.OK };
            var cancelR = new Button { Text = "取消", Left = 246, Top = 56, Width = 80, DialogResult = DialogResult.Cancel };
            prompt.Controls.AddRange([field, ok, cancelR]);
            prompt.AcceptButton = ok;
            if (prompt.ShowDialog(this) != DialogResult.OK) return;
            _cfg.RenameAccount(_cfg.ActiveAccount.Id, field.Text);
            LoadFrom(_cfg); _onSaved(_cfg);
        };
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
        if (startImport) BeginInvoke(async () => await DoImport("cursor-app"));
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
        _token.Text = cfg.SessionToken;
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
            _token.Text = result.Token;
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
        using var pen = new Pen(Color.DeepSkyBlue, 1.5f);
        g.DrawLines(pen, pts);
    }
}
