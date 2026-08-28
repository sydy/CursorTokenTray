namespace CursorTokenCore;

public static class UiLayout
{
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
}
