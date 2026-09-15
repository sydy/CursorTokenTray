namespace CursorTokenCore;

public static class UiLayout
{
    public const int DesignDpi = 96;
    public const float MinUiScale = 1f;
    public const float MaxUiScale = 3f;

    /// <summary>
    /// Place a popup above-left of <paramref name="anchorX"/>/<paramref name="anchorY"/>,
    /// flipping below the anchor when the work area does not have room above, and clamping
    /// to the work area. Coordinates are screen pixels.
    /// </summary>
    public static (int X, int Y) FitPopup(
        int workLeft, int workTop, int workRight, int workBottom,
        int width, int height, int anchorX, int anchorY,
        int gap = 12, int margin = 8)
    {
        var x = anchorX - width;
        var y = anchorY - height - gap;
        if (x < workLeft + margin) x = workLeft + margin;
        if (x + width > workRight - margin) x = workRight - width - margin;
        if (y < workTop + margin) y = Math.Min(anchorY + gap, workBottom - height - margin);
        if (y + height > workBottom - margin) y = workBottom - height - margin;
        if (x < workLeft) x = workLeft;
        if (y < workTop) y = workTop;
        return (x, y);
    }

    /// <summary>
    /// Size a dialog to measured content, never smaller than <paramref name="minWidth"/>/
    /// <paramref name="minHeight"/> unless the working area cannot fit that minimum.
    /// Values are in the same pixel space the caller measured after layout (already DPI-scaled).
    /// </summary>
    public static (int Width, int Height) FitDialog(
        int preferredWidth, int preferredHeight,
        int minWidth, int minHeight,
        int workWidth, int workHeight,
        int padding = 24, int workMargin = 48)
    {
        return (
            ClampDialogAxis(preferredWidth, minWidth, workWidth, padding, workMargin),
            ClampDialogAxis(preferredHeight, minHeight, workHeight, padding, workMargin));
    }

    static int ClampDialogAxis(int preferred, int min, int work, int padding, int margin)
    {
        var want = Math.Max(min, preferred + padding);
        var max = Math.Max(1, work - margin);
        return Math.Min(want, max);
    }

    /// <summary>
    /// Convert Win32 device DPI to a UI scale factor. Values outside 96–288 are treated as 96
    /// (same clamp as the old Python helper) so a garbage reading cannot shrink or explode layout.
    /// </summary>
    public static float DpiScale(int deviceDpi)
    {
        if (deviceDpi < DesignDpi || deviceDpi > DesignDpi * (int)MaxUiScale)
            return MinUiScale;
        return ClampUiScale(deviceDpi / (float)DesignDpi);
    }

    public static float ClampUiScale(float scale)
    {
        if (float.IsNaN(scale) || float.IsInfinity(scale) || scale < MinUiScale)
            return MinUiScale;
        return Math.Min(MaxUiScale, scale);
    }

    /// <summary>
    /// 96-DPI design pixels → screen pixels. Never smaller than the design size.
    /// </summary>
    public static int ScalePx(int designPx, int deviceDpi)
    {
        var n = (int)Math.Round(designPx * DpiScale(deviceDpi), MidpointRounding.AwayFromZero);
        return Math.Max(designPx, n);
    }

    /// <summary>
    /// Default window size from 96-DPI design values, grown for the current DPI and
    /// clamped to the working area. Unlike <see cref="FitDialog"/>, this does not add
    /// extra padding — the design size is already the intended client/outer size.
    /// </summary>
    public static (int Width, int Height) FitWindow(
        int designWidth, int designHeight,
        int minDesignWidth, int minDesignHeight,
        int deviceDpi,
        int workWidth, int workHeight,
        int workMargin = 48)
    {
        var maxW = Math.Max(1, workWidth - workMargin);
        var maxH = Math.Max(1, workHeight - workMargin);
        var minW = Math.Min(maxW, ScalePx(minDesignWidth, deviceDpi));
        var minH = Math.Min(maxH, ScalePx(minDesignHeight, deviceDpi));
        return (
            Math.Min(maxW, Math.Max(minW, ScalePx(designWidth, deviceDpi))),
            Math.Min(maxH, Math.Max(minH, ScalePx(designHeight, deviceDpi))));
    }
}

/// <summary>
/// Settings dialog metrics shared with the macOS <c>SettingsRootView</c> (design pixels at 96 DPI).
/// Windows uses 托盘 instead of 菜单栏.
/// </summary>
public static class SettingsLayout
{
    public const int DesignWidth = 540;
    public const int DesignHeight = 680;
    public const int MinWidth = 480;
    public const int MinHeight = 420;

    public const string AccountTab = "账户";
    public const string NotifyTab = "通知";
    public const string TrayTab = "托盘";
    public const string SyncTab = "同步";

    public static readonly string[] TabTitles = [AccountTab, NotifyTab, TrayTab, SyncTab];
}

/// <summary>
/// Usage-report chart metrics shared with the macOS <c>UsageChartView</c> (design pixels at 96 DPI).
/// </summary>
public static class UsageChartLayout
{
    public const int DesignPlotH = 168;
    public const int DesignHeaderH = 28;
    public const int DesignLegendLineH = 26;
    public const int DesignLegendGap = 8;
    public const int DesignToggleW = 150;
    public const int DesignToggleH = 24;
    public const int DesignToggleRadius = 6;
    public const int ChipPadX = 8;
    public const int ChipDot = 8;
    public const int ChipGap = 6;
    public const int ChipPadRight = 8;
    public const int ChipPadY = 4;
    public const int ChipMinH = 22;

    public static int PlotHeight(int dpi) => UiLayout.ScalePx(DesignPlotH, dpi);
    public static int HeaderHeight(int dpi) => UiLayout.ScalePx(DesignHeaderH, dpi);
    public static int ToggleWidth(int dpi) => UiLayout.ScalePx(DesignToggleW, dpi);
    public static int ToggleHeight(int dpi) => UiLayout.ScalePx(DesignToggleH, dpi);
    public static int ToggleRadius(int dpi) => UiLayout.ScalePx(DesignToggleRadius, dpi);
    public static (int Width, int Height) ToggleSize(int dpi) => (ToggleWidth(dpi), ToggleHeight(dpi));

    public static (int PadX, int Dot, int Gap, int PadRight, int PadY) ChipMetrics(int dpi) => (
        UiLayout.ScalePx(ChipPadX, dpi),
        UiLayout.ScalePx(ChipDot, dpi),
        UiLayout.ScalePx(ChipGap, dpi),
        UiLayout.ScalePx(ChipPadRight, dpi),
        UiLayout.ScalePx(ChipPadY, dpi));

    /// <summary>
    /// Preferred legend-chip size. <paramref name="textWidth"/> is the already-measured
    /// label width (GDI <c>NoPadding</c>), so the chip cannot paint wider than its layout slot.
    /// </summary>
    public static (int Width, int Height) ChipSize(int textWidth, int fontHeight, int dpi)
    {
        var (padX, dot, gap, padRight, padY) = ChipMetrics(dpi);
        var h = Math.Max(UiLayout.ScalePx(ChipMinH, dpi), Math.Max(0, fontHeight) + padY * 2);
        var w = padX + dot + gap + Math.Max(0, textWidth) + padRight;
        return (w, h);
    }

    public readonly record struct ChipFrame(int X, int Y, int Width, int Height);

    /// <summary>
    /// Pack chips left-to-right at their own width and wrap when the next chip
    /// does not fit. Unlike equal-width grid columns, a long label keeps its size.
    /// </summary>
    public static (int Width, int Height, ChipFrame[] Frames) WrapChips(
        IReadOnlyList<(int Width, int Height)> sizes,
        int containerWidth,
        int hSpacing = DesignLegendGap,
        int vSpacing = 6)
    {
        var limit = containerWidth > 0 ? containerWidth : int.MaxValue;
        var frames = new ChipFrame[sizes.Count];
        var x = 0;
        var y = 0;
        var rowH = 0;
        var maxX = 0;
        for (var i = 0; i < sizes.Count; i++)
        {
            var w = Math.Max(0, sizes[i].Width);
            var h = Math.Max(0, sizes[i].Height);
            if (x > 0 && x + w > limit)
            {
                maxX = Math.Max(maxX, x - hSpacing);
                x = 0;
                y += rowH + vSpacing;
                rowH = 0;
            }
            frames[i] = new ChipFrame(x, y, w, h);
            x += w + hSpacing;
            rowH = Math.Max(rowH, h);
        }
        maxX = Math.Max(maxX, Math.Max(0, x - hSpacing));
        return (maxX, y + rowH, frames);
    }

    public static int LegendHeight(int legendLines, int dpi)
    {
        if (legendLines <= 0) return 0;
        return UiLayout.ScalePx(DesignLegendGap, dpi)
            + legendLines * UiLayout.ScalePx(DesignLegendLineH, dpi);
    }

    public static int PanelHeight(int legendLines, int dpi) =>
        HeaderHeight(dpi) + LegendHeight(legendLines, dpi) + PlotHeight(dpi);
}

/// <summary>
/// Flyout metrics shared with the macOS <c>FlyoutLayout</c> (design pixels at 96 DPI).
/// </summary>
public static class FlyoutLayout
{
    public const int Width = 500;
    public const int Height = 280;
    public const int CornerRadius = 16;
    public const int Padding = 16;
    public const int ColumnGap = 16;
    public const int LeftWidth = 176;
    public const int RingSize = 148;
    public const int RingLine = 10;
    public const int CardRadius = 10;
    public const int CardPadding = 10;
    public const int CardGap = 8;
    public const int BarHeight = 5;
    public const int ToolButtonHeight = 24;
    public const int ToolButtonGap = 6;
    public const int ToolButtonPadX = 8;
    public const int ToolButtonPadY = 5;
    public const int ToolButtonIcon = 14;
    public const int ToolButtonIconGap = 4;

    /// <summary>
    /// Ellipse diameter for GDI <c>CreateRoundRectRgn</c>. A GraphicsPath region
    /// rasterizes each corner with a 1px square ear.
    /// </summary>
    public static int RoundRegionDiameter(int radius) => Math.Max(2, radius * 2);

    /// <summary>
    /// Exclusive right/bottom for <c>CreateRoundRectRgn</c>. The extra pixel is
    /// GDI's convention and keeps the far edge from being clipped.
    /// </summary>
    public static (int Right, int Bottom) RoundRegionExtent(int width, int height)
        => (Math.Max(0, width) + 1, Math.Max(0, height) + 1);

    /// <summary>
    /// Center-line of a rounded stroke drawn inside the window, like SwiftUI
    /// <c>strokeBorder</c>. A centered stroke is clipped by the window region
    /// and flattens the corner curve.
    /// </summary>
    public static (float X, float Y, float Width, float Height, float Radius) InnerStroke(
        float width, float height, float radius, float penWidth)
    {
        var inset = Math.Max(0.5f, penWidth / 2f);
        return (
            inset,
            inset,
            Math.Max(0f, width - inset * 2f),
            Math.Max(0f, height - inset * 2f),
            Math.Max(1f, radius - inset));
    }

    public readonly record struct ToolButtonFrame(float X, float Y, float Width, float Height);

    /// <summary>
    /// Preferred capsule size. <paramref name="textWidth"/> is the already-measured
    /// label width (GDI typographic / no extra padding), so the button grows with the text.
    /// </summary>
    public static (float Width, float Height) ToolButtonSize(
        float textWidth, float textHeight, bool hasIcon, float scale)
    {
        var s = Math.Max(0f, scale);
        var padX = ToolButtonPadX * s;
        var padY = ToolButtonPadY * s;
        var icon = hasIcon ? ToolButtonIcon * s : 0f;
        var iconGap = hasIcon ? ToolButtonIconGap * s : 0f;
        var textW = Math.Max(0f, textWidth);
        var textH = Math.Max(0f, textHeight);
        var w = padX + icon + iconGap + textW + padX;
        var h = Math.Max(ToolButtonHeight * s, Math.Max(icon, textH) + padY * 2);
        return (w, h);
    }

    /// <summary>
    /// Pack toolbar buttons left-to-right. Each chip keeps at least its content width
    /// and leftover space is shared so the row fills the bar. If the preferred sizes
    /// overflow, widths shrink together instead of clipping a single glyph to “…”.
    /// </summary>
    public static (float Width, float Height, ToolButtonFrame[] Frames) ArrangeToolButtons(
        IReadOnlyList<(float Width, float Height)> sizes,
        float containerWidth,
        float gap)
    {
        var n = sizes.Count;
        var frames = new ToolButtonFrame[n];
        if (n == 0) return (0, 0, frames);

        var minW = new float[n];
        var height = 0f;
        var minSum = 0f;
        for (var i = 0; i < n; i++)
        {
            minW[i] = Math.Max(0f, sizes[i].Width);
            height = Math.Max(height, Math.Max(0f, sizes[i].Height));
            minSum += minW[i];
        }

        var gaps = Math.Max(0f, gap) * Math.Max(0, n - 1);
        var inner = Math.Max(0f, containerWidth - gaps);
        var widths = new float[n];
        if (minSum > inner && minSum > 0)
        {
            var shrink = inner / minSum;
            for (var i = 0; i < n; i++) widths[i] = minW[i] * shrink;
        }
        else
        {
            var extra = n > 0 ? (inner - minSum) / n : 0f;
            for (var i = 0; i < n; i++) widths[i] = minW[i] + extra;
        }

        var x = 0f;
        for (var i = 0; i < n; i++)
        {
            frames[i] = new ToolButtonFrame(x, 0, widths[i], height);
            x += widths[i] + (i < n - 1 ? Math.Max(0f, gap) : 0f);
        }
        return (x, height, frames);
    }
}

public static class RemainingTone
{
    public static (int R, int G, int B) Rgb(double? remaining, bool error, bool unlimited = false)
    {
        if (error) return (142, 142, 147);
        if (unlimited) return (48, 209, 88);
        if (remaining is null) return (142, 142, 147);
        if (remaining < 20) return (231, 76, 60);
        if (remaining < 50) return (241, 196, 15);
        return (46, 204, 113);
    }
}

public static class SparklineCopy
{
    public const string Title = "近 7 日剩余额度";
    public const string EmptyHint = "刷新几次后显示近日消耗";
    public const string Flat = "几乎没消耗";
    public const string AxisStart = "7天前";
    public const string AxisEnd = "现在";
    public const string Reset = "重置";
    public const string Minus = "\u2212";
    public const int WindowDays = 7;
    public const double FlatBurnEpsilon = 0.05;
    public const double ResetJump = 15;
}

public readonly record struct SparkMappedPoint(float X, float Y, double Ts, double Remaining, int Index);

public sealed record SparkPlot(SparkMappedPoint[] Points, SparkMappedPoint? Reset, double T0, double T1);

public static class SparklineGeometry
{
    public static (double Min, double Max) Range(IReadOnlyList<double> values) => (0, 100);

    public static (float X, float Y)[] Points(IReadOnlyList<double> values, float width, float height)
    {
        var n = Math.Max(values.Count - 1, 1);
        var pts = new (float X, float Y)[values.Count];
        for (var i = 0; i < values.Count; i++)
        {
            var rem = Math.Clamp(values[i], 0, 100);
            pts[i] = (width * i / n, YAt(rem, height));
        }
        return pts;
    }

    public static float YAt(double remaining, float height) =>
        height * (1f - (float)(Math.Clamp(remaining, 0, 100) / 100.0));

    public static SparkPlot Layout(
        IReadOnlyList<HistoryPoint> points,
        float width,
        float height,
        double nowTs,
        double? cycleStartTs = null,
        int windowDays = SparklineCopy.WindowDays)
    {
        var windowStart = nowTs - Math.Max(1, windowDays) * 86400.0;
        var minTs = points.Count == 0 ? windowStart : points[0].Ts;
        var maxTs = points.Count == 0 ? nowTs : points[0].Ts;
        for (var i = 1; i < points.Count; i++)
        {
            if (points[i].Ts < minTs) minTs = points[i].Ts;
            if (points[i].Ts > maxTs) maxTs = points[i].Ts;
        }

        // Fit the axis to the sample span so a day of history is not
        // crushed into the right edge of an empty 7-day window.
        var t0 = Math.Max(windowStart, minTs);
        var t1 = Math.Max(nowTs, maxTs);
        var span = t1 - t0;
        if (span <= 0) span = 1;

        var mapped = new SparkMappedPoint[points.Count];
        for (var i = 0; i < points.Count; i++)
        {
            var p = points[i];
            var xFrac = (p.Ts - t0) / span;
            if (double.IsNaN(xFrac) || double.IsInfinity(xFrac)) xFrac = 0;
            mapped[i] = new SparkMappedPoint(
                (float)(width * Math.Clamp(xFrac, 0, 1)),
                YAt(p.Remaining, height),
                p.Ts,
                p.Remaining,
                i);
        }

        if (mapped.Length >= 2 && maxTs - minTs < 1)
        {
            var n = Math.Max(mapped.Length - 1, 1);
            for (var i = 0; i < mapped.Length; i++)
            {
                var p = mapped[i];
                mapped[i] = p with { X = width * i / n };
            }
        }

        return new SparkPlot(mapped, FindReset(mapped, width, height, t0, t1, cycleStartTs), t0, t1);
    }

    public static float RibbonOffset(float height) => Math.Max(8f, height * 0.22f);

    public static string FormatAxisDay(double unixSeconds)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds((long)Math.Round(unixSeconds * 1000.0)).ToLocalTime();
        return $"{dt.Month}月{dt.Day}日";
    }

    public static string AxisStartLabel(double t0, double t1) =>
        t1 - t0 >= 6 * 86400.0 ? SparklineCopy.AxisStart : FormatAxisDay(t0);

    public static SparkMappedPoint? FindReset(
        IReadOnlyList<SparkMappedPoint> points,
        float width,
        float height,
        double t0,
        double t1,
        double? cycleStartTs)
    {
        var span = t1 - t0;
        if (span <= 0) span = 1;
        if (cycleStartTs is { } cs && cs >= t0 && cs <= t1)
        {
            var x = (float)(width * (cs - t0) / span);
            return new SparkMappedPoint(x, YAt(0, height), cs, 0, -1);
        }

        var best = -1;
        var bestJump = SparklineCopy.ResetJump;
        for (var i = 1; i < points.Count; i++)
        {
            var jump = points[i].Remaining - points[i - 1].Remaining;
            if (jump >= bestJump)
            {
                bestJump = jump;
                best = i;
            }
        }
        return best >= 0 ? points[best] : null;
    }

    public static int? HitIndex(IReadOnlyList<SparkMappedPoint> points, float x)
    {
        if (points.Count == 0) return null;
        var best = 0;
        var bestDist = Math.Abs(points[0].X - x);
        for (var i = 1; i < points.Count; i++)
        {
            var d = Math.Abs(points[i].X - x);
            if (d < bestDist)
            {
                bestDist = d;
                best = i;
            }
        }
        return best;
    }

    public static string Caption(int pointCount, double? dailyAvg, double? current)
    {
        if (pointCount < 2) return SparklineCopy.EmptyHint;
        if (dailyAvg is { } burn && burn >= SparklineCopy.FlatBurnEpsilon)
        {
            var rate = $"{SparklineCopy.Minus}{burn.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)}%";
            return current is { } cur
                ? $"日均约 {rate} · 当前 {FormatPercent(cur)}"
                : $"日均约 {rate}";
        }
        if (dailyAvg is null && current is { } only)
            return $"当前 {FormatPercent(only)}";
        return SparklineCopy.Flat;
    }

    public static string WindowLabel(double spanSeconds)
    {
        var days = spanSeconds / 86400.0;
        if (days >= 6) return "近 7 日";
        if (days >= 1.5) return $"近 {Math.Max(2, (int)Math.Round(days))} 日";
        return "近 1 日";
    }

    public static string TrendSummary(
        IReadOnlyList<HistoryPoint> points,
        double? dailyAvg,
        double? current,
        double nowTs)
    {
        if (points.Count < 2) return SparklineCopy.EmptyHint;
        var first = points[0];
        var lastPt = points[^1];
        for (var i = 0; i < points.Count; i++)
        {
            if (points[i].Ts < first.Ts) first = points[i];
            if (points[i].Ts > lastPt.Ts) lastPt = points[i];
        }
        var last = current ?? lastPt.Remaining;
        var t1 = Math.Max(nowTs, lastPt.Ts);
        var window = WindowLabel(t1 - first.Ts);
        var used = first.Remaining - last;
        if (used >= SparklineCopy.FlatBurnEpsilon)
            return $"{window}用掉 {FormatPercent(used)}";
        if (used <= -SparklineCopy.FlatBurnEpsilon)
            return $"{window}剩余回升了 {FormatPercent(-used)}";
        return $"{window}{SparklineCopy.Flat}";
    }

    public static string FormatPercent(double remaining)
    {
        var v = Math.Clamp(remaining, 0, 100);
        var rounded = Math.Round(v, 1, MidpointRounding.AwayFromZero);
        if (Math.Abs(rounded - Math.Round(rounded)) < 0.05)
            return $"{Math.Round(rounded).ToString("0", System.Globalization.CultureInfo.InvariantCulture)}%";
        return $"{rounded.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)}%";
    }

    public static string FormatLocalStamp(double unixSeconds)
    {
        var dt = DateTimeOffset.FromUnixTimeMilliseconds((long)Math.Round(unixSeconds * 1000.0)).ToLocalTime();
        return $"{dt.Month}月{dt.Day}日 {dt.Hour:00}:{dt.Minute:00}";
    }

    public static string FormatHover(double ts, double remaining, double? previous = null)
    {
        var text = $"{FormatLocalStamp(ts)} · 剩余 {remaining.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)}%";
        if (previous is { } prev)
        {
            var delta = remaining - prev;
            if (Math.Abs(delta) >= 0.05)
            {
                var sign = delta > 0 ? "+" : SparklineCopy.Minus;
                text += $"（{sign}{Math.Abs(delta).ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)}%）";
            }
        }
        return text;
    }
}
