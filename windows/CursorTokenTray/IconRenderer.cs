using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using CursorTokenCore;

namespace CursorTokenTray;

static class IconRenderer
{
    const int SmCxsmicon = 49;

    public static int PixelSize()
    {
        var sm = 16;
        try { sm = SystemInformation.SmallIconSize.Width; }
        catch
        {
            try { sm = GetSystemMetrics(SmCxsmicon); } catch { }
        }
        if (sm < 16) sm = 16;
        if (sm > 64) sm = 64;
        // 2× so Shell's downscale stays sharp; square so the glyph maps onto the tray slot.
        return Math.Clamp(sm * 2, 32, 64);
    }

    public static Icon Make(double? remaining, bool error, string mode, int size = 0)
    {
        if (size <= 0) size = PixelSize();
        using var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.CompositingQuality = CompositingQuality.HighQuality;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.Clear(Color.Transparent);
            Draw(g, size, remaining, error, (mode ?? "ring").Trim().ToLowerInvariant());
        }
        var hicon = bmp.GetHicon();
        try
        {
            using var icon = Icon.FromHandle(hicon);
            return (Icon)icon.Clone();
        }
        finally
        {
            DestroyIcon(hicon);
        }
    }

    static void Draw(Graphics g, int size, double? remaining, bool error, string mode)
    {
        var color = error ? Color.FromArgb(231, 76, 60)
            : remaining is null ? Color.FromArgb(148, 163, 184)
            : remaining > 50 ? Color.FromArgb(46, 204, 113)
            : remaining >= 20 ? Color.FromArgb(241, 196, 15)
            : Color.FromArgb(231, 76, 60);
        var label = PercentLabel(remaining, error);

        if (mode == "dot")
        {
            DrawDot(g, size, color);
            return;
        }
        if (mode == "number")
        {
            DrawDisc(g, size, 0.02f);
            var max = size * (label.Length >= 3 ? 0.42f : label.Length == 2 ? 0.58f : 0.72f);
            DrawCentered(g, label, size / 2f, size / 2f, max, color);
            return;
        }

        // Ring: stroke sits just inside the bitmap so the badge fills the tray slot.
        var pad = TrayIconLayout.RingPad(size);
        var stroke = TrayIconLayout.RingStroke(size);
        var inset = TrayIconLayout.RingInset(size);
        var box = new RectangleF(inset, inset, size - inset * 2, size - inset * 2);
        DrawDisc(g, size, pad / size);

        using (var track = new Pen(Color.FromArgb(72, 76, 84), stroke))
            g.DrawEllipse(track, box);

        if (error)
        {
            using var pen = new Pen(color, stroke);
            g.DrawEllipse(pen, box);
        }
        else if (remaining is { } pct)
        {
            var clamped = Math.Clamp(pct, 0, 100);
            if (clamped >= 99.95)
            {
                using var pen = new Pen(color, stroke);
                g.DrawEllipse(pen, box);
            }
            else if (clamped > 0.05)
            {
                using var pen = new Pen(color, stroke) { StartCap = LineCap.Round, EndCap = LineCap.Round };
                g.DrawArc(pen, box, -90, (float)(-clamped / 100 * 360));
            }
        }

        var inner = Math.Max(4f, size / 2f - pad - stroke);
        var fontMax = inner * (label.Length >= 3 ? 1.05f : label.Length == 2 ? 1.28f : 1.45f);
        DrawCentered(g, label, size / 2f, size / 2f, fontMax, color);
    }

    static void DrawDot(Graphics g, int size, Color color)
    {
        // ~92% of the slot; only enough inset to keep AA from clipping.
        var pad = TrayIconLayout.DotPad(size);
        var d = TrayIconLayout.DotDiameter(size);
        using var brush = new SolidBrush(color);
        g.FillEllipse(brush, pad, pad, d, d);
        var ir = d * 0.28f;
        using var gloss = new SolidBrush(Color.FromArgb(40, 255, 255, 255));
        g.FillEllipse(gloss, size / 2f - ir, size / 2f - ir, ir * 2, ir * 2);
    }

    static void DrawDisc(Graphics g, int size, float padFrac)
    {
        var pad = Math.Max(1f, size * padFrac);
        var d = size - pad * 2;
        using var disc = new SolidBrush(Color.FromArgb(230, 16, 18, 22));
        g.FillEllipse(disc, pad, pad, d, d);
    }

    static string PercentLabel(double? remaining, bool error)
    {
        if (error) return "!";
        if (remaining is null) return "–";
        var pct = Math.Clamp(remaining.Value, 0, 100);
        return pct >= 99.5 ? "100" : ((int)Math.Round(pct)).ToString();
    }

    static void DrawCentered(Graphics g, string text, float cx, float cy, float maxPx, Color color)
    {
        if (string.IsNullOrEmpty(text) || maxPx < 4) return;
        using var font = new Font("Segoe UI Semibold", maxPx, FontStyle.Bold, GraphicsUnit.Pixel);
        using var path = new GraphicsPath();
        path.AddString(text, font.FontFamily, (int)FontStyle.Bold, maxPx, PointF.Empty, StringFormat.GenericTypographic);
        var b = path.GetBounds();
        if (b.Width <= 0 || b.Height <= 0) return;
        var scale = Math.Min(1f, Math.Min(maxPx / b.Height, maxPx * 1.55f / b.Width));
        using var m = new Matrix();
        m.Translate(cx, cy);
        m.Scale(scale, scale);
        m.Translate(-(b.X + b.Width / 2f), -(b.Y + b.Height / 2f));
        path.Transform(m);
        using var brush = new SolidBrush(color);
        g.FillPath(brush, path);
    }

    [DllImport("user32.dll")]
    static extern int GetSystemMetrics(int nIndex);

    [DllImport("user32.dll", SetLastError = true)]
    static extern bool DestroyIcon(IntPtr hIcon);
}
