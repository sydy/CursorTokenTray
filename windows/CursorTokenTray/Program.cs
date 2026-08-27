using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using CursorTokenCore;

namespace CursorTokenTray;

static class Program
{
    [STAThread]
    static void Main()
    {
        using var mutex = new Mutex(true, @"Local\CursorTokenTray_SingleInstance_v2", out var created);
        if (!created)
        {
            MessageBox.Show("Cursor Token 剩余进度已经在托盘运行。", "已在后台运行", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new TrayContext());
    }
}

sealed class TrayContext : ApplicationContext
{
    readonly NotifyIcon _icon;
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
        _icon = new NotifyIcon
        {
            Visible = true,
            Text = "Cursor Token 剩余进度",
            Icon = IconRenderer.Make(null, false, _config.TrayDisplayMode),
            ContextMenuStrip = BuildMenu(),
        };
        _icon.MouseUp += (_, e) =>
        {
            if (e.Button == MouseButtons.Left) ShowFlyout();
        };
        if (string.IsNullOrEmpty(_config.SessionToken))
            BeginInvoke(() => OpenSettings(true, false));
        _ = LoopAsync(_cts.Token);
    }

    void BeginInvoke(Action a)
    {
        if (_icon.ContextMenuStrip?.IsHandleCreated == true)
            _icon.ContextMenuStrip.BeginInvoke(a);
        else
            a();
    }

    ContextMenuStrip BuildMenu()
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add("显示状态", null, (_, _) => ShowFlyout());
        menu.Items.Add("立即刷新", null, (_, _) => { _refreshNow = true; });
        menu.Items.Add(UsageParser.DashboardMenuLabel(_usage), null, (_, _) => OpenDashboard());
        var switcher = new ToolStripMenuItem("切换账号");
        if (_config.Accounts.Count == 0)
            switcher.DropDownItems.Add(new ToolStripMenuItem("暂无账号") { Enabled = false });
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
                switcher.DropDownItems.Add(item);
            }
        }
        menu.Items.Add(switcher);
        menu.Items.Add("导入 Token…", null, (_, _) => OpenSettings(true, true));
        menu.Items.Add("设置…", null, (_, _) => OpenSettings(false, false));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => Exit());
        return menu;
    }

    async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await RefreshAll();
            var minutes = Math.Max(1, _config.RefreshIntervalMinutes);
            var until = DateTime.UtcNow.AddSeconds(Math.Max(60, minutes * 60));
            while (DateTime.UtcNow < until && !ct.IsCancellationRequested)
            {
                if (_refreshNow) { _refreshNow = false; break; }
                await Task.Delay(250, ct).ContinueWith(_ => { }, CancellationToken.None);
            }
        }
    }

    async Task RefreshAll()
    {
        var cfg = _config;
        if (cfg.Accounts.Count == 0)
        {
            _usage = null;
            _error = "未配置 Token，请打开设置粘贴";
            _updated = null;
            UpdateUi();
            return;
        }
        var activeId = cfg.ActiveAccountId;
        foreach (var acc in cfg.Accounts.OrderBy(a => a.Id == activeId ? 0 : 1).ToList())
        {
            if (string.IsNullOrWhiteSpace(acc.Token)) continue;
            var stamp = DateTime.Now.ToString("HH:mm:ss");
            var isActive = acc.Id == activeId;
            try
            {
                var snap = await _client.FetchUsageSummary(acc.Token, 20);
                cfg.ApplySnapshot(acc.Id, snap.MembershipType, snap.RemainingPercent, "", stamp);
                var live = cfg.Accounts.First(a => a.Id == acc.Id);
                live.AuthErrorNotified = false;
                foreach (var n in AlertLogic.Evaluate(cfg, live, snap))
                    _icon.ShowBalloonTip(4000, n.Title, n.Body, ToolTipIcon.Info);
                UsageHistory.Append(snap.RemainingPercent, snap.AutoPercentUsed, snap.ApiPercentUsed, accountId: acc.Id);
                if (isActive) { _usage = snap; _error = null; _updated = stamp; }
            }
            catch (CursorApiException err)
            {
                cfg.ApplySnapshot(acc.Id, error: err.Message, updatedAt: stamp);
                var live = cfg.Accounts.FirstOrDefault(a => a.Id == acc.Id);
                if (err.IsAuthError && live is not null && !live.AuthErrorNotified)
                {
                    if (cfg.NotifyEnabled)
                        _icon.ShowBalloonTip(5000, "Token 需要更新", string.IsNullOrEmpty(live.DisplayLabel) ? err.Message : $"账号「{live.DisplayLabel}」：{err.Message}", ToolTipIcon.Warning);
                    live.AuthErrorNotified = true;
                }
                if (isActive) { _usage = null; _error = err.Message; _updated = stamp; }
            }
            catch (Exception ex)
            {
                var msg = "刷新失败: " + ex.Message;
                cfg.ApplySnapshot(acc.Id, error: msg, updatedAt: stamp);
                if (isActive) { _usage = null; _error = msg; _updated = stamp; }
            }
        }
        cfg.SyncLegacyFields();
        _config = cfg;
        ConfigStore.Save(cfg);
        UpdateUi();
    }

    void UpdateUi()
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
        if (_icon.ContextMenuStrip is not { Visible: true })
        {
            var oldMenu = _icon.ContextMenuStrip;
            _icon.ContextMenuStrip = BuildMenu();
            oldMenu?.Dispose();
        }
        _flyout?.Render(_usage, _error, _updated, _config);
    }

    void ShowFlyout()
    {
        _flyout ??= new FlyoutForm(
            () => _icon.ShowBalloonTip(1, "", "", ToolTipIcon.None),
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
        _flyout.PopupNearTray();
    }

    void OpenDashboard()
    {
        var url = UsageParser.DashboardUrl(_usage);
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true }); } catch { }
    }

    public void OpenSettings(bool focusToken, bool startImport)
    {
        if (_settings is { IsDisposed: false })
        {
            _settings.Show();
            _settings.Activate();
            return;
        }
        _settings = new SettingsForm(_config, cfg => ApplyConfig(cfg, true), async prefer =>
        {
            return await SessionImporter.ImportAndValidate(_client, SessionImporter.DefaultPreferBrowsers(), SessionImporter.OnlyBrowsers(prefer), _config.ExistingTokenVariants());
        }, startImport);
        _settings.Show();
        if (focusToken) _settings.FocusToken();
    }

    public void ApplyConfig(AppConfig cfg, bool refresh)
    {
        var prevAuto = _config.AutostartEnabled;
        _config = cfg;
        ConfigStore.Save(cfg);
        if (prevAuto != cfg.AutostartEnabled) Autostart.Apply(cfg.AutostartEnabled);
        if (refresh) _refreshNow = true;
        UpdateUi();
    }

    void Exit()
    {
        _cts.Cancel();
        _icon.Visible = false;
        _icon.Dispose();
        Application.Exit();
    }
}

static class Autostart
{
    public static void Apply(bool enabled)
    {
        var startup = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "CursorTokenTray.lnk");
        if (!enabled)
        {
            try { File.Delete(startup); } catch { }
            return;
        }
        var exe = Environment.ProcessPath ?? Application.ExecutablePath;
        try
        {
            var t = Type.GetTypeFromProgID("WScript.Shell");
            if (t is null) return;
            var shell = Activator.CreateInstance(t);
            if (shell is null) return;
            var shortcut = t.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, [startup]);
            if (shortcut is null) return;
            var st = shortcut.GetType();
            st.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, shortcut, [exe]);
            st.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, shortcut, [Path.GetDirectoryName(exe) ?? ""]);
            st.InvokeMember("WindowStyle", System.Reflection.BindingFlags.SetProperty, null, shortcut, [7]);
            st.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, shortcut, ["Cursor Token 剩余进度托盘"]);
            st.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
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
