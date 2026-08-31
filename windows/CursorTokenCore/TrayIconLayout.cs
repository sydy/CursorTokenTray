namespace CursorTokenCore;

/// <summary>
/// Tray-icon geometry. Insets stay tiny so the badge fills the notification-area slot.
/// </summary>
public static class TrayIconLayout
{
    public static float RingPad(int size) => Math.Max(1f, size * 0.015f);

    public static float RingStroke(int size) => Math.Max(2.4f, size * 0.18f);

    public static float RingInset(int size) => RingPad(size) + RingStroke(size) / 2f;

    public static float RingOuterSpan(int size) => size - 2f * RingPad(size);

    public static float DotPad(int size) => Math.Max(1f, size * 0.04f);

    public static float DotDiameter(int size) => size - 2f * DotPad(size);
}
