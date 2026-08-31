using CursorTokenCore;

namespace CursorTokenTray;

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
    bool _loading;

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
        var cookie = ActionButton("仅导入 Cookie");
        _root.Controls.Add(Flow(cur, add, ff, cookie));
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
            if (_loading) return;
            if (_accounts.SelectedItem is AccountItem item) { _cfg.SetActiveAccount(item.Id); NotifySaved(); }
        };
        rename.Click += (_, _) => RenameActive();
        del.Click += (_, _) =>
        {
            if (_cfg.ActiveAccount is null) return;
            if (MessageBox.Show($"确定删除「{_cfg.ActiveAccount.DisplayLabel}」？", "删除账号", MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            _cfg.RemoveAccount(_cfg.ActiveAccount.Id);
            LoadFrom(_cfg); NotifySaved();
        };
        add.Click += (_, _) => AddToken();
        cur.Click += async (_, _) => await DoImport("cursor-app");
        cookie.Click += async (_, _) => await DoImport(null);
        ff.Click += async (_, _) =>
        {
            try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("https://cursor.com/dashboard") { UseShellExecute = true }); } catch { }
            await DoImport("firefox", waitForLogin: true);
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
        LoadFrom(_cfg); NotifySaved();
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
        _loading = true;
        try
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
        finally { _loading = false; }
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

    async Task DoImport(string? prefer, bool waitForLogin = false)
    {
        if (_importing) return;
        _importing = true;
        _status.Text = waitForLogin ? "请在浏览器登录，正在等待 Cookie…" : "正在导入…";
        try
        {
            if (waitForLogin)
            {
                var deadline = DateTime.UtcNow.AddSeconds(180);
                while (DateTime.UtcNow < deadline && !IsDisposed)
                {
                    var result = await _import(prefer);
                    if (result.Ok)
                    {
                        ApplyImport(result);
                        return;
                    }
                    await Task.Delay(2000);
                }
                if (!IsDisposed) _status.Text = "等待登录超时，请手动粘贴 Token。";
                return;
            }
            var once = await _import(prefer);
            _status.Text = once.Message;
            if (!once.Ok) return;
            ApplyImport(once);
        }
        finally { _importing = false; }
    }

    void ApplyImport(ImportResult result)
    {
        _status.Text = result.Message;
        _cfg.UpsertAccount(result.Token, membershipType: result.MembershipType, remaining: result.RemainingPercent, activate: true);
        _token.Text = "";
        Persist(false);
    }

    void CopyRuntimeFromDisk()
    {
        try
        {
            var live = ConfigStore.Load();
            foreach (var acc in _cfg.Accounts)
            {
                var src = live.Accounts.FirstOrDefault(a => a.Id == acc.Id);
                if (src is null) continue;
                acc.AlertNotifiedLevels = [.. src.AlertNotifiedLevels];
                acc.AuthErrorNotified = src.AuthErrorNotified;
                acc.ExhaustionNotified = src.ExhaustionNotified;
                acc.LowQuotaNotified = src.LowQuotaNotified;
                acc.LastRemaining = src.LastRemaining;
                acc.LastError = src.LastError;
                acc.UpdatedAt = src.UpdatedAt;
                if (string.IsNullOrEmpty(acc.MembershipType)) acc.MembershipType = src.MembershipType;
            }
            _cfg.LowQuotaNotified = live.LowQuotaNotified;
            _cfg.AuthErrorNotified = live.AuthErrorNotified;
            _cfg.AlertNotifiedLevels = [.. live.AlertNotifiedLevels];
            _cfg.ExhaustionNotified = live.ExhaustionNotified;
        }
        catch { }
    }

    void NotifySaved()
    {
        CopyRuntimeFromDisk();
        _onSaved(_cfg);
    }

    void Persist(bool _)
    {
        CopyRuntimeFromDisk();
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
