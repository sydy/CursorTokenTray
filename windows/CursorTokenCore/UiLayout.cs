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
