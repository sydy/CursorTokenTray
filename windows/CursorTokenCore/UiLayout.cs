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
}
