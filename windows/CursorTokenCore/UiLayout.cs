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
    public const int Height = 300;
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
    public const int SparkHeight = 36;
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

public static class SparklineGeometry
{
    public static (double Min, double Max) Range(IReadOnlyList<double> values)
    {
        if (values.Count == 0) return (0, 100);
        var minV = values.Min();
        var maxV = values.Max();
        if (maxV - minV < 1)
        {
            minV -= 0.5;
            maxV += 0.5;
        }
        var pad = (maxV - minV) * 0.08;
        return (minV - pad, maxV + pad);
    }

    public static (float X, float Y)[] Points(IReadOnlyList<double> values, float width, float height)
    {
        var (minV, maxV) = Range(values);
        var span = maxV - minV;
        if (span <= 0) span = 1;
        var n = Math.Max(values.Count - 1, 1);
        var pts = new (float X, float Y)[values.Count];
        for (var i = 0; i < values.Count; i++)
        {
            pts[i] = (
                width * i / n,
                height * (1 - (float)((values[i] - minV) / span)));
        }
        return pts;
    }
}
