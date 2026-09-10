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
    readonly CheckBox _syncEnable = new() { Text = "启用账号多端同步", AutoSize = true, Margin = new Padding(0, 8, 0, 4) };
    readonly TextBox _syncPath = new() { Dock = DockStyle.Fill };
    readonly TextBox _syncSecret = new() { Width = 220, UseSystemPasswordChar = true };
    readonly Label _syncStatus = new() { AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(0, 4, 0, 4) };
    readonly Label _syncHint = new()
    {
        Text = "把同步文件夹放到 iCloud / OneDrive / 坚果云 等，两端填写相同口令。文件用口令加密，请勿分享口令。",
        AutoSize = true,
        ForeColor = Color.DimGray,
        Margin = new Padding(0, 4, 0, 8),
    };
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
        ClientSize = new Size(540, 760);
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
        _root.Controls.Add(Caption("多端同步"));
        _root.Controls.Add(_syncEnable);
        var browse = ActionButton("浏览…");
        _root.Controls.Add(FieldRow("同步文件夹", PathRow(_syncPath, browse)));
        _root.Controls.Add(FieldRow("同步口令", _syncSecret));
        var syncNow = ActionButton("立即同步");
        var syncExport = ActionButton("导出…");
        var syncImport = ActionButton("导入…");
        _root.Controls.Add(Flow(syncNow, syncExport, syncImport));
        _root.Controls.Add(_syncStatus);
        _root.Controls.Add(_syncHint);
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
        browse.Click += (_, _) => PickFolder();
        syncNow.Click += (_, _) => DoSync();
        syncExport.Click += (_, _) => DoExport();
        syncImport.Click += (_, _) => DoImportFile();
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
        foreach (var label in new[] { _addCaption, _status, _hint, _syncStatus, _syncHint })
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
        field.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        field.Margin = new Padding(0, 2, 0, 2);
        row.Controls.Add(field, 1, 0);
        return row;
    }

    static TableLayoutPanel PathRow(TextBox path, Button browse)
    {
        var row = new TableLayoutPanel
        {
            AutoSize = true,
            ColumnCount = 2,
            Dock = DockStyle.Fill,
            Margin = new Padding(0),
        };
        row.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        row.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        path.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        row.Controls.Add(path, 0, 0);
        browse.Margin = new Padding(8, 0, 0, 0);
        row.Controls.Add(browse, 1, 0);
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
            _syncEnable.Checked = cfg.SyncEnabled;
            _syncPath.Text = cfg.SyncPath;
            _syncSecret.Text = "";
            _syncSecret.PlaceholderText = string.IsNullOrEmpty(cfg.SyncSecret) ? "两端必须相同，用于加密同步文件" : "已保存，留空则不修改";
            _syncStatus.Text = SyncStatusText(cfg);
        }
        finally { _loading = false; }
    }

    static string SyncStatusText(AppConfig cfg)
    {
        if (!string.IsNullOrWhiteSpace(cfg.SyncLastError)) return cfg.SyncLastError;
        if (!string.IsNullOrWhiteSpace(cfg.SyncLastAt)) return "上次同步 " + cfg.SyncLastAt;
        return cfg.SyncEnabled ? "尚未同步" : "";
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
        ReadSyncFields();
        if (!string.IsNullOrWhiteSpace(_token.Text))
            try { _cfg.UpsertAccount(_token.Text, activate: true); } catch { }
        _onSaved(_cfg);
        LoadFrom(_cfg);
    }

    void ReadSyncFields()
    {
        _cfg.SyncEnabled = _syncEnable.Checked;
        _cfg.SyncPath = _syncPath.Text.Trim();
        if (!string.IsNullOrWhiteSpace(_syncSecret.Text))
            _cfg.SyncSecret = _syncSecret.Text.Trim();
    }

    void PickFolder()
    {
        using var dlg = new FolderBrowserDialog
        {
            Description = "选择同步文件夹（建议放到 iCloud / OneDrive / 坚果云）",
            UseDescriptionForTitle = true,
        };
        if (!string.IsNullOrWhiteSpace(_syncPath.Text) && Directory.Exists(_syncPath.Text))
            dlg.SelectedPath = _syncPath.Text;
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        _syncPath.Text = dlg.SelectedPath;
    }

    void DoSync()
    {
        ReadSyncFields();
        var status = AccountSync.Reconcile(_cfg);
        _syncStatus.Text = status.Message;
        _status.Text = status.Ok ? status.Message : status.Message;
        NotifySaved();
        LoadFrom(_cfg);
    }

    void DoExport()
    {
        ReadSyncFields();
        using var dlg = new SaveFileDialog
        {
            Filter = "同步文件|*.sync|JSON|*.json",
            FileName = AccountSync.Filename,
            Title = "导出加密账号包",
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            var dest = AccountSync.ExportToFile(_cfg, dlg.FileName);
            _syncStatus.Text = "已导出到 " + dest;
        }
        catch (Exception ex) { _syncStatus.Text = ex.Message; }
    }

    void DoImportFile()
    {
        ReadSyncFields();
        using var dlg = new OpenFileDialog
        {
            Filter = "同步文件|*.sync;*.json|所有文件|*.*",
            Title = "导入加密账号包",
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            AccountSync.ImportFromFile(_cfg, dlg.FileName);
            _syncStatus.Text = "已从文件合并账号";
            NotifySaved();
            LoadFrom(_cfg);
        }
        catch (Exception ex) { _syncStatus.Text = ex.Message; }
    }

    sealed record AccountItem(string Id, string Caption)
    {
        public override string ToString() => Caption;
    }
}
