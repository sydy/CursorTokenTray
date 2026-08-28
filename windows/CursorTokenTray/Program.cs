using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using CursorTokenCore;

namespace CursorTokenTray;

static class Program
{
    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, e) => CrashLog.Write(e.Exception);
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            if (e.ExceptionObject is Exception ex) CrashLog.Write(ex);
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            CrashLog.Write(e.Exception);
            e.SetObserved();
        };

        using var mutex = new Mutex(true, @"Local\CursorTokenTray_SingleInstance_v2", out var created);
        if (!created)
        {
            MessageBox.Show("Cursor Token 剩余进度已经在托盘运行。", "已在后台运行", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        Application.Run(new TrayContext());
    }
}

sealed class HiddenSyncForm : Form
{
    public HiddenSyncForm()
    {
        ShowInTaskbar = false;
        FormBorderStyle = FormBorderStyle.FixedToolWindow;
        StartPosition = FormStartPosition.Manual;
        Location = new Point(-32000, -32000);
        Size = new Size(1, 1);
        Opacity = 0;
        ShowIcon = false;
        Text = "";
    }

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            const int WsExToolwindow = 0x00000080;
            const int WsExNoActivate = 0x08000000;
            var cp = base.CreateParams;
            cp.ExStyle |= WsExToolwindow | WsExNoActivate;
            return cp;
        }
    }

    protected override void SetVisibleCore(bool value)
    {
        if (!IsHandleCreated) CreateHandle();
        base.SetVisibleCore(false);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (e.CloseReason == CloseReason.UserClosing)
        {
            e.Cancel = true;
            return;
        }
        base.OnFormClosing(e);
    }
}

sealed class TrayContext : ApplicationContext
{
    readonly HiddenSyncForm _sync;
    readonly NotifyIcon _icon;
    readonly ContextMenuStrip _menu;
    readonly ToolStripMenuItem _dashboardItem;
    readonly ToolStripMenuItem _switcher;
    readonly CursorClient _client = new();
    AppConfig _config;
    UsageSnapshot? _usage;
    string? _error;
    string? _updated;
    SettingsForm? _settings;
    FlyoutForm? _flyout;
    CancellationTokenSource _cts = new();
    bool _refreshNow;

    public TrayContext()
    {
        _config = ConfigStore.Load();
        Autostart.Apply(_config.AutostartEnabled);
        _sync = new HiddenSyncForm();
        _ = _sync.Handle;
        _menu = new ContextMenuStrip();
        _dashboardItem = new ToolStripMenuItem();
        _switcher = new ToolStripMenuItem("切换账号");
        BuildMenu();
        _icon = new NotifyIcon
        {
            Visible = true,
            Text = "Cursor Token 剩余进度",
            Icon = IconRenderer.Make(null, false, _config.TrayDisplayMode),
            ContextMenuStrip = _menu,
        };
        _icon.MouseUp += (_, e) =>
        {
            if (e.Button == MouseButtons.Left) ShowFlyout(Cursor.Position);
        };
        _sync.BeginInvoke(() =>
        {
            if (string.IsNullOrEmpty(_config.SessionToken))
                OpenSettings(true, false);
            _ = LoopAsync(_cts.Token);
        });
    }

    void OnUi(Action action)
    {
        if (_sync.IsDisposed) return;
        if (_sync.InvokeRequired)
        {
            try { _sync.BeginInvoke(action); } catch (ObjectDisposedException) { }
            return;
        }
        action();
    }

    void BuildMenu()
    {
        _menu.Items.Clear();
        _menu.Items.Add("显示状态", null, (_, _) => ShowFlyout(Cursor.Position));
        _menu.Items.Add("立即刷新", null, (_, _) => { _refreshNow = true; });
        _dashboardItem.Text = UsageParser.DashboardMenuLabel(_usage);
        _dashboardItem.Click -= DashboardClick;
        _dashboardItem.Click += DashboardClick;
        _menu.Items.Add(_dashboardItem);
        _menu.Items.Add(_switcher);
        _menu.Items.Add("导入 Token…", null, (_, _) => OpenSettings(true, true));
        _menu.Items.Add("设置…", null, (_, _) => OpenSettings(false, false));
        _menu.Items.Add(new ToolStripSeparator());
        _menu.Items.Add("退出", null, (_, _) => Exit());
        _menu.Opening -= MenuOpening;
        _menu.Opening += MenuOpening;
        RefreshAccountMenu();
    }

    void DashboardClick(object? sender, EventArgs e) => OpenDashboard();

    void MenuOpening(object? sender, EventArgs e)
    {
        if (_sync.IsHandleCreated) SetForegroundWindow(_sync.Handle);
    }

    void RefreshAccountMenu()
    {
        if (_switcher.DropDown.Visible) return;
        _switcher.DropDownItems.Clear();
        if (_config.Accounts.Count == 0)
            _switcher.DropDownItems.Add(new ToolStripMenuItem("暂无账号") { Enabled = false });
        else
        {
            foreach (var acc in _config.Accounts)
            {
                var title = acc.DisplayLabel;
                if (acc.LastRemaining is { } r) title += $"  {r:0}%";
                var item = new ToolStripMenuItem(title) { Checked = acc.Id == _config.ActiveAccountId, Tag = acc.Id };
                item.Click += (_, _) =>
                {
                    if (item.Tag is string id) { _config.SetActiveAccount(id); ApplyConfig(_config, true); }
                };
                _switcher.DropDownItems.Add(item);
            }
        }
    }

    async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try { await RefreshAll(); }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { CrashLog.Write(ex); }
            var minutes = Math.Max(1, _config.RefreshIntervalMinutes);
            var until = DateTime.UtcNow.AddSeconds(Math.Max(60, minutes * 60));
            while (DateTime.UtcNow < until && !ct.IsCancellationRequested)
            {
                if (_refreshNow) { _refreshNow = false; break; }
                await Task.Delay(250, ct).ContinueWith(_ => { }, CancellationToken.None);
            }
        }
    }

    sealed record RefreshOutcome(string Id, UsageSnapshot? Snap, string? Error, bool AuthError, string Stamp);

    async Task RefreshAll()
    {
        var targets = _config.Accounts.Select(a => (a.Id, a.Token, a.TokenDecryptFailed)).ToList();
        if (targets.Count == 0)
        {
            _usage = null;
            _error = "未配置 Token，请打开设置粘贴";
            _updated = null;
            UpdateUi();
            return;
        }
        var activeId = _config.ActiveAccountId;
        var outcomes = new List<RefreshOutcome>();
        foreach (var acc in targets.OrderBy(a => a.Id == activeId ? 0 : 1))
        {
            var stamp = DateTime.Now.ToString("HH:mm:ss");
            if (acc.TokenDecryptFailed || string.IsNullOrWhiteSpace(acc.Token))
            {
                outcomes.Add(new RefreshOutcome(acc.Id, null, TokenProtector.DecryptFailedMessage, false, stamp));
                continue;
            }
            try
            {
                var snap = await _client.FetchUsageSummary(acc.Token, 20);
                outcomes.Add(new RefreshOutcome(acc.Id, snap, null, false, stamp));
                UsageHistory.Append(snap.RemainingPercent, snap.AutoPercentUsed, snap.ApiPercentUsed, accountId: acc.Id);
            }
            catch (CursorApiException err)
            {
                outcomes.Add(new RefreshOutcome(acc.Id, null, err.Message, err.IsAuthError, stamp));
            }
            catch (Exception ex)
            {
                outcomes.Add(new RefreshOutcome(acc.Id, null, "刷新失败: " + ex.Message, false, stamp));
            }
        }

        var notices = new List<(string Title, string Body, bool Warn)>();
        AppConfig cfg;
        try
        {
            cfg = ConfigStore.Update(live =>
            {
                foreach (var o in outcomes)
                {
                    var acc = live.Accounts.FirstOrDefault(a => a.Id == o.Id);
                    if (acc is null) continue;
                    if (o.Snap is { } snap)
                    {
                        live.ApplySnapshot(o.Id, snap.MembershipType, snap.RemainingPercent, "", o.Stamp);
                        acc.AuthErrorNotified = false;
                        foreach (var n in AlertLogic.Evaluate(live, acc, snap))
                            notices.Add((n.Title, n.Body, false));
                    }
                    else if (o.Error is not null)
                    {
                        live.ApplySnapshot(o.Id, error: o.Error, updatedAt: o.Stamp);
                        if (o.AuthError && !acc.AuthErrorNotified)
                        {
                            acc.AuthErrorNotified = true;
                            if (live.NotifyEnabled)
                            {
                                var body = string.IsNullOrEmpty(acc.DisplayLabel) ? o.Error : $"账号「{acc.DisplayLabel}」：{o.Error}";
                                notices.Add(("Token 需要更新", body, true));
                            }
                        }
                    }
                }
                live.SyncLegacyFields();
            });
        }
        catch (Exception)
        {
            cfg = _config;
        }

        _config = cfg;
        var active = outcomes.FirstOrDefault(o => o.Id == cfg.ActiveAccountId);
        if (active?.Snap is { } activeSnap) { _usage = activeSnap; _error = null; _updated = active.Stamp; }
        else if (active?.Error is not null) { _usage = null; _error = active.Error; _updated = active.Stamp; }
        else if (cfg.Accounts.Count == 0) { _usage = null; _error = "未配置 Token，请打开设置粘贴"; _updated = null; }
        UpdateUi();
        OnUi(() =>
        {
            foreach (var n in notices)
                _icon.ShowBalloonTip(n.Warn ? 5000 : 4000, n.Title, n.Body, n.Warn ? ToolTipIcon.Warning : ToolTipIcon.Info);
        });
    }

    void UpdateUi()
    {
        OnUi(() =>
        {
            try { UpdateUiCore(); }
            catch (Exception ex) { CrashLog.Write(ex); }
        });
    }

    void UpdateUiCore()
    {
        var remaining = _error is not null && !_error.StartsWith("未配置") ? (double?)null : _usage?.RemainingPercent;
        var error = _error is not null && !_error.StartsWith("未配置");
        var old = _icon.Icon;
        _icon.Icon = IconRenderer.Make(remaining, error, _config.TrayDisplayMode);
        old?.Dispose();
        var label = _config.ActiveAccount?.DisplayLabel ?? "";
        var tip = error ? (_error ?? "异常")
            : remaining is { } r ? (string.IsNullOrEmpty(label) ? $"{r:0}%" : $"{label} · {r:0}%")
            : "Cursor Token 剩余进度";
        if (tip.Length > 63) tip = tip[..63];
        _icon.Text = tip;
        _dashboardItem.Text = UsageParser.DashboardMenuLabel(_usage);
        if (!_menu.Visible) RefreshAccountMenu();
        _flyout?.Render(_usage, _error, _updated, _config);
    }

    void ShowFlyout(Point? anchor = null)
    {
        OnUi(() =>
        {
            try
            {
                if (_flyout is { IsDisposed: true }) _flyout = null;
                _flyout ??= new FlyoutForm(
                    () =>
                    {
                        try { _icon.ShowBalloonTip(1, " ", " ", ToolTipIcon.None); } catch { }
                    },
                    () => { _refreshNow = true; },
                    OpenDashboard,
                    () => OpenSettings(true, true),
                    () =>
                    {
                        var text = StatusText.FormatSummary(_usage, _error, _updated, _config.ActiveAccount?.DisplayLabel);
                        Clipboard.SetText(text);
                    });
                var hist = UsageHistory.LoadRecent(7, _config.ActiveAccount?.Id).Select(p => p.Remaining).ToList();
                _flyout.Render(_usage, _error, _updated, _config, hist);
                _flyout.PopupNear(anchor ?? Cursor.Position);
            }
            catch (Exception ex) { CrashLog.Write(ex); }
        });
    }

    void OpenDashboard()
    {
        var url = UsageParser.DashboardUrl(_usage);
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true }); } catch { }
    }

    public void OpenSettings(bool focusToken, bool startImport)
    {
        OnUi(() =>
        {
            try
            {
                if (_settings is { IsDisposed: false })
                {
                    _settings.Show();
                    _settings.Activate();
                    if (focusToken) _settings.FocusToken();
                    if (startImport) _settings.StartImport();
                    return;
                }
                _settings = new SettingsForm(_config, cfg => ApplyConfig(cfg, true), async prefer =>
                {
                    return await SessionImporter.ImportAndValidate(_client, SessionImporter.DefaultPreferBrowsers(), SessionImporter.OnlyBrowsers(prefer), _config.ExistingTokenVariants());
                }, startImport);
                _settings.Show();
                if (focusToken) _settings.FocusToken();
            }
            catch (Exception ex) { CrashLog.Write(ex); }
        });
    }

    public void ApplyConfig(AppConfig cfg, bool refresh)
    {
        var prevAuto = _config.AutostartEnabled;
        _config = cfg;
        try { ConfigStore.Save(cfg); }
        catch (Exception)
        {
            OnUi(() => _icon.ShowBalloonTip(4000, "保存失败", "无法写入配置（文件忙碌或加密失败），请稍后再试。", ToolTipIcon.Warning));
        }
        if (prevAuto != cfg.AutostartEnabled) Autostart.Apply(cfg.AutostartEnabled);
        if (refresh) _refreshNow = true;
        UpdateUi();
    }

    void Exit()
    {
        _cts.Cancel();
        _icon.Visible = false;
        _icon.Dispose();
        _menu.Dispose();
        _flyout?.Dispose();
        _settings?.Dispose();
        _sync.Dispose();
        Application.Exit();
    }

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);
}

static class Autostart
{
    const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    const string ValueName = "CursorTokenTray";
    static string StartupDir => Environment.GetFolderPath(Environment.SpecialFolder.Startup);

    public static void Apply(bool enabled)
    {
        foreach (var path in new[]
        {
            Path.Combine(StartupDir, "CursorTokenTray.lnk"),
            Path.Combine(StartupDir, "CursorTokenTray.vbs"),
            Path.Combine(StartupDir, "CursorTokenTray.cmd"),
        })
            try { File.Delete(path); } catch { }

        try
        {
            using var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(RunKey);
            if (key is null) return;
            if (!enabled)
            {
                try { key.DeleteValue(ValueName, false); } catch { }
                return;
            }
            var exe = Environment.ProcessPath ?? Application.ExecutablePath;
            key.SetValue(ValueName, "\"" + exe.Replace("\"", "") + "\"");
        }
        catch { }
    }
}

static class IconRenderer
{
    public static Icon Make(double? remaining, bool error, string mode, int size = 32)
    {
        var bmp = new Bitmap(size, size);
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.Clear(Color.Transparent);
        var color = error ? Color.FromArgb(231, 76, 60)
            : remaining is null ? Color.FromArgb(180, 180, 180)
            : remaining > 50 ? Color.FromArgb(46, 204, 113)
            : remaining >= 20 ? Color.FromArgb(241, 196, 15)
            : Color.FromArgb(231, 76, 60);
        using var brush = new SolidBrush(color);
        if (mode == "dot")
        {
            g.FillEllipse(brush, size * 0.3f, size * 0.3f, size * 0.4f, size * 0.4f);
        }
        else if (mode == "number")
        {
            var label = error ? "!" : remaining is null ? "-" : remaining.Value.ToString("0");
            using var font = new Font("Segoe UI Semibold", size * 0.42f, FontStyle.Bold, GraphicsUnit.Pixel);
            var sz = g.MeasureString(label, font);
            using var textBrush = new SolidBrush(color);
            g.DrawString(label, font, textBrush, (size - sz.Width) / 2, (size - sz.Height) / 2);
        }
        else
        {
            using var track = new Pen(Color.FromArgb(72, 76, 84), size * 0.12f);
            g.DrawEllipse(track, size * 0.12f, size * 0.12f, size * 0.76f, size * 0.76f);
            if (!error && remaining is > 0)
            {
                using var pen = new Pen(color, size * 0.12f) { StartCap = LineCap.Round, EndCap = LineCap.Round };
                g.DrawArc(pen, size * 0.12f, size * 0.12f, size * 0.76f, size * 0.76f, -90, (float)(-remaining.Value / 100 * 360));
            }
            else if (error)
            {
                using var pen = new Pen(color, size * 0.12f);
                g.DrawEllipse(pen, size * 0.12f, size * 0.12f, size * 0.76f, size * 0.76f);
            }
            var label = error ? "!" : remaining is null ? "-" : remaining.Value.ToString("0");
            using var font = new Font("Segoe UI Semibold", size * 0.32f, FontStyle.Bold, GraphicsUnit.Pixel);
            var sz = g.MeasureString(label, font);
            g.DrawString(label, font, Brushes.White, (size - sz.Width) / 2, (size - sz.Height) / 2);
        }
        var hicon = bmp.GetHicon();
        var icon = Icon.FromHandle(hicon);
        var clone = (Icon)icon.Clone();
        DestroyIcon(hicon);
        bmp.Dispose();
        return clone;
    }

    [DllImport("user32.dll", SetLastError = true)]
    static extern bool DestroyIcon(IntPtr hIcon);
}
