using System.Drawing.Drawing2D;
using CursorTokenCore;

namespace CursorTokenTray;

static class UsageChartPalette
{
    public static readonly Color[] Colors =
    [
        Color.FromArgb(0, 120, 212),
        Color.FromArgb(0, 168, 150),
        Color.FromArgb(232, 160, 32),
        Color.FromArgb(136, 87, 184),
        Color.FromArgb(216, 80, 91),
        Color.FromArgb(90, 148, 74),
        Color.FromArgb(70, 130, 180),
        Color.FromArgb(180, 110, 70),
    ];

    public static Color ForModel(IReadOnlyList<string> models, string name)
    {
        var i = 0;
        for (; i < models.Count; i++)
            if (string.Equals(models[i], name, StringComparison.Ordinal)) break;
        if (i >= models.Count) i = 0;
        return Colors[i % Colors.Length];
    }
}

sealed class UsageChartPanel : TableLayoutPanel
{
    public const int DesignPlotH = 168;
    const int DesignHeaderH = 28;
    const int DesignLegendH = 28;

    readonly Label _caption = new() { AutoSize = true, ForeColor = Color.DimGray, Text = "按日 Token（UTC）", Anchor = AnchorStyles.Left };
    readonly Button _dayBtn = MakeToggle("按日");
    readonly Button _hourBtn = MakeToggle("按小时");
    readonly FlowLayoutPanel _legend = new()
    {
        AutoSize = true,
        WrapContents = true,
        Dock = DockStyle.Fill,
        Margin = new Padding(0, 2, 0, 4),
    };
    readonly UsageChartBox _plot = new() { Dock = DockStyle.Fill };
    readonly HashSet<string> _hidden = new(StringComparer.Ordinal);
    List<UsageEvent> _events = [];
    bool _hourly;

    public UsageChartPanel()
    {
        ColumnCount = 1;
        RowCount = 3;
        Dock = DockStyle.Fill;
        Margin = new Padding(0);
        RowStyles.Add(new RowStyle(SizeType.AutoSize));
        RowStyles.Add(new RowStyle(SizeType.AutoSize));
        RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var header = new TableLayoutPanel
        {
            ColumnCount = 2,
            RowCount = 1,
            Dock = DockStyle.Fill,
            AutoSize = true,
            Margin = new Padding(0),
        };
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        header.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        var toggles = new FlowLayoutPanel
        {
            AutoSize = true,
            WrapContents = false,
            Margin = new Padding(0),
            Anchor = AnchorStyles.Right,
        };
        toggles.Controls.Add(_dayBtn);
        toggles.Controls.Add(_hourBtn);
        header.Controls.Add(_caption, 0, 0);
        header.Controls.Add(toggles, 1, 0);

        Controls.Add(header, 0, 0);
        Controls.Add(_legend, 0, 1);
        Controls.Add(_plot, 0, 2);

        _dayBtn.Click += (_, _) => SetHourly(false);
        _hourBtn.Click += (_, _) => SetHourly(true);
        StyleToggles();
    }

    public static int DesignHeight => DesignHeaderH + DesignLegendH + DesignPlotH + 8;

    public void Bind(IReadOnlyList<UsageEvent> events)
    {
        _events = events as List<UsageEvent> ?? events.ToList();
        var models = UsageEvents.BuildChart(_events, false).Models;
        _hidden.RemoveWhere(n => !models.Contains(n));
        Rebuild();
    }

    public void ApplyDpi(int dpi)
    {
        _dayBtn.Padding = new Padding(UiLayout.ScalePx(10, dpi), UiLayout.ScalePx(2, dpi), UiLayout.ScalePx(10, dpi), UiLayout.ScalePx(2, dpi));
        _hourBtn.Padding = new Padding(UiLayout.ScalePx(10, dpi), UiLayout.ScalePx(2, dpi), UiLayout.ScalePx(10, dpi), UiLayout.ScalePx(2, dpi));
        foreach (Control chip in _legend.Controls)
            chip.Font = Font;
    }

    void SetHourly(bool hourly)
    {
        if (_hourly == hourly) return;
        _hourly = hourly;
        StyleToggles();
        Rebuild();
    }

    void StyleToggles()
    {
        StyleToggle(_dayBtn, !_hourly);
        StyleToggle(_hourBtn, _hourly);
    }

    static void StyleToggle(Button btn, bool on)
    {
        btn.BackColor = on ? Color.FromArgb(0, 120, 212) : Color.White;
        btn.ForeColor = on ? Color.White : Color.FromArgb(32, 32, 32);
        btn.FlatAppearance.BorderColor = on ? Color.FromArgb(0, 120, 212) : Color.FromArgb(180, 180, 180);
    }

    static Button MakeToggle(string text) => new()
    {
        Text = text,
        AutoSize = true,
        FlatStyle = FlatStyle.Flat,
        Margin = new Padding(0, 0, 4, 0),
        Cursor = Cursors.Hand,
    };

    void Rebuild()
    {
        var series = UsageEvents.BuildChart(_events, _hourly, _hidden);
        _caption.Text = series.Caption;
        _plot.Series = series;
        RebuildLegend();
    }

    void RebuildLegend()
    {
        var series = _plot.Series;
        _legend.SuspendLayout();
        _legend.Controls.Clear();
        if (series.Models.Count == 0)
        {
            _legend.ResumeLayout();
            return;
        }
        foreach (var name in series.Models)
        {
            var chip = new LegendChip(name, UsageChartPalette.ForModel(series.Models, name), !_hidden.Contains(name));
            chip.Toggled += (_, _) =>
            {
                if (_hidden.Contains(name)) _hidden.Remove(name);
                else _hidden.Add(name);
                Rebuild();
            };
            _legend.Controls.Add(chip);
        }
        _legend.ResumeLayout();
    }
}

sealed class LegendChip : Control
{
    public event EventHandler? Toggled;
    readonly string _model;
    readonly Color _swatch;
    bool _on;

    public LegendChip(string model, Color swatch, bool on)
    {
        _model = model;
        _swatch = swatch;
        _on = on;
        Text = UsageEvents.ChartModelLabel(model);
        Cursor = Cursors.Hand;
        Margin = new Padding(0, 0, 8, 4);
        Size = GetPreferredSize(Size.Empty);
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
    }

    protected override void OnFontChanged(EventArgs e)
    {
        base.OnFontChanged(e);
        Size = GetPreferredSize(Size.Empty);
    }

    public override Size GetPreferredSize(Size proposedSize)
    {
        var text = TextRenderer.MeasureText(Text, Font);
        var pad = Math.Max(22, (int)Math.Round(Font.Height * 1.6));
        return new Size(text.Width + pad, Math.Max(22, Font.Height + 8));
    }

    protected override void OnClick(EventArgs e)
    {
        _on = !_on;
        Invalidate();
        Toggled?.Invoke(this, EventArgs.Empty);
        base.OnClick(e);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        var fill = _on ? Blend(_swatch, Color.White, 0.82f) : Color.White;
        var border = _on ? _swatch : Color.FromArgb(180, 180, 180);
        var r = Height / 2f;
        using var path = Rounded(ClientRectangle, r);
        using var br = new SolidBrush(fill);
        using var pen = new Pen(border);
        g.FillPath(br, path);
        g.DrawPath(pen, path);
        var d = Math.Max(8, Height / 3);
        var cy = (Height - d) / 2;
        using var sw = new SolidBrush(_on ? _swatch : Color.FromArgb(180, 180, 180));
        g.FillEllipse(sw, 6, cy, d, d);
        var fc = _on ? Color.FromArgb(32, 32, 32) : Color.DimGray;
        TextRenderer.DrawText(g, Text, Font, new Point(6 + d + 4, (Height - Font.Height) / 2), fc, TextFormatFlags.NoPadding);
    }

    static Color Blend(Color a, Color b, float t) =>
        Color.FromArgb(
            (int)(a.R + (b.R - a.R) * t),
            (int)(a.G + (b.G - a.G) * t),
            (int)(a.B + (b.B - a.B) * t));

    static GraphicsPath Rounded(Rectangle rect, float radius)
    {
        var path = new GraphicsPath();
        var d = radius * 2;
        var r = new RectangleF(rect.X + 0.5f, rect.Y + 0.5f, Math.Max(1, rect.Width - 1f), Math.Max(1, rect.Height - 1f));
        path.AddArc(r.X, r.Y, d, d, 180, 90);
        path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }
}

sealed class UsageChartBox : Control
{
    UsageChartSeries _series = new();
    int _hover = -1;
    RectangleF _plot;

    public UsageChartSeries Series
    {
        get => _series;
        set
        {
            _series = value ?? new UsageChartSeries();
            _hover = -1;
            Invalidate();
        }
    }

    public UsageChartBox()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        BackColor = Color.White;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var next = HitBucket(e.Location);
        if (next == _hover) return;
        _hover = next;
        Invalidate();
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        if (_hover < 0) return;
        _hover = -1;
        Invalidate();
    }

    int HitBucket(Point pt)
    {
        if (_series.Buckets.Count == 0 || !_plot.Contains(pt)) return -1;
        var slot = _plot.Width / _series.Buckets.Count;
        if (slot <= 0) return -1;
        var i = (int)((pt.X - _plot.X) / slot);
        if (i < 0 || i >= _series.Buckets.Count) return -1;
        return i;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.Clear(Color.White);
        using var border = new Pen(Color.FromArgb(210, 210, 210));
        g.DrawRectangle(border, 0, 0, Width - 1, Height - 1);

        var axisFont = Font;
        var buckets = _series.Buckets;
        var maxTokens = buckets.Count == 0 ? 0L : Math.Max(1, buckets.Max(b => b.Tokens));
        var ticks = YTicks(maxTokens);
        var yMax = ticks[^1];
        var yLabels = ticks.Select(t => t == 0 ? "0" : UsageParser.FormatTokenCount(t)).ToList();
        var labelW = yLabels.Max(s => TextRenderer.MeasureText(g, s, axisFont).Width);
        var padL = labelW + 10;
        var padB = axisFont.Height + 8;
        var padT = 8;
        var padR = 8;
        _plot = new RectangleF(padL, padT, Math.Max(8, Width - padL - padR), Math.Max(8, Height - padT - padB));
        using var grid = new Pen(Color.FromArgb(230, 230, 230));
        using var dim = new SolidBrush(Color.DimGray);
        for (var i = 0; i < ticks.Count; i++)
        {
            var y = _plot.Bottom - (ticks[i] / (float)yMax) * _plot.Height;
            g.DrawLine(grid, _plot.Left, y, _plot.Right, y);
            var lab = yLabels[i];
            var sz = TextRenderer.MeasureText(g, lab, axisFont);
            TextRenderer.DrawText(g, lab, axisFont, new Point((int)(_plot.Left - sz.Width - 4), (int)y - sz.Height / 2), Color.DimGray, TextFormatFlags.NoPadding);
        }

        if (buckets.Count == 0)
        {
            TextRenderer.DrawText(g, "暂无数据", axisFont, Rectangle.Round(_plot), Color.Silver, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            return;
        }

        var n = buckets.Count;
        var slot = _plot.Width / n;
        var maxBar = Math.Min(slot * 0.58f, UiLayout.ScalePx(72, DeviceDpi));
        var barW = Math.Max(2f, maxBar);
        for (var i = 0; i < n; i++)
        {
            var bucket = buckets[i];
            var cx = _plot.Left + slot * (i + 0.5f);
            var x0 = cx - barW / 2;
            var yb = _plot.Bottom;
            foreach (var slice in bucket.Slices)
            {
                var h = yMax <= 0 ? 0 : (slice.Tokens / (float)yMax) * _plot.Height;
                if (h < 0.5f) continue;
                using var br = new SolidBrush(UsageChartPalette.ForModel(_series.Models, slice.Model));
                g.FillRectangle(br, x0, yb - h, barW, h);
                yb -= h;
            }
            if (i == _hover)
            {
                using var hi = new Pen(Color.FromArgb(60, 0, 0, 0), 1);
                g.DrawRectangle(hi, x0, yb, barW, _plot.Bottom - yb);
            }
        }

        var step = Math.Max(1, (int)Math.Ceiling(n * TextRenderer.MeasureText(g, "00-00", axisFont).Width / Math.Max(1, _plot.Width)));
        for (var i = 0; i < n; i += step)
        {
            var lab = buckets[i].Label;
            var cx = (int)(_plot.Left + slot * (i + 0.5f));
            var sz = TextRenderer.MeasureText(g, lab, axisFont);
            TextRenderer.DrawText(g, lab, axisFont, new Point(cx - sz.Width / 2, (int)_plot.Bottom + 2), Color.DimGray, TextFormatFlags.NoPadding);
        }

        if (_hover >= 0 && _hover < n)
            DrawTooltip(g, axisFont, buckets[_hover], _plot.Left + slot * (_hover + 0.5f));
    }

    void DrawTooltip(Graphics g, Font font, ChartBucket bucket, float barX)
    {
        var lines = new List<string> { bucket.Key + "  UTC", "合计 " + UsageParser.FormatTokenCount(bucket.Tokens) };
        foreach (var slice in bucket.Slices)
            lines.Add($"{UsageEvents.ChartModelLabel(slice.Model)}  {UsageParser.FormatTokenCount(slice.Tokens)}");
        if (bucket.Cents > 0)
            lines.Add("费用 " + UsageParser.FormatUsdCents(bucket.Cents));
        var pad = 8;
        var lineH = font.Height + 2;
        var tw = lines.Max(s => TextRenderer.MeasureText(g, s, font).Width) + pad * 2;
        var th = lineH * lines.Count + pad;
        var x = (int)Math.Min(Width - tw - 4, Math.Max(4, barX + 10));
        var y = 8;
        using var bg = new SolidBrush(Color.FromArgb(230, 40, 40, 40));
        using var path = new GraphicsPath();
        var rr = new Rectangle(x, y, tw, th);
        const int rad = 6;
        path.AddArc(rr.X, rr.Y, rad * 2, rad * 2, 180, 90);
        path.AddArc(rr.Right - rad * 2, rr.Y, rad * 2, rad * 2, 270, 90);
        path.AddArc(rr.Right - rad * 2, rr.Bottom - rad * 2, rad * 2, rad * 2, 0, 90);
        path.AddArc(rr.X, rr.Bottom - rad * 2, rad * 2, rad * 2, 90, 90);
        path.CloseFigure();
        g.FillPath(bg, path);
        var yy = y + pad / 2 + 2;
        foreach (var line in lines)
        {
            TextRenderer.DrawText(g, line, font, new Point(x + pad, yy), Color.White, TextFormatFlags.NoPadding);
            yy += lineH;
        }
    }

    static List<long> YTicks(long max)
    {
        if (max <= 0) return [0, 1];
        var exp = Math.Floor(Math.Log10(max));
        var f = max / Math.Pow(10, exp);
        double nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
        var top = nice * Math.Pow(10, exp);
        if (top < max) top *= 1.2;
        var step = top / 4;
        var ticks = new List<long>();
        for (var i = 0; i <= 4; i++)
            ticks.Add((long)Math.Round(step * i));
        if (ticks[^1] < max) ticks[^1] = max;
        return ticks;
    }
}
