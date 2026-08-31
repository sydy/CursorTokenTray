using CursorTokenCore;
using Xunit;

namespace CursorTokenCore.Tests;

public class TrayIconLayoutTests
{
    [Theory]
    [InlineData(32)]
    [InlineData(48)]
    [InlineData(64)]
    public void RingFillsTheCanvas(int size)
    {
        var fill = TrayIconLayout.RingOuterSpan(size) / size;
        Assert.True(fill >= 0.93f, $"ring outer span {fill:0.###} of {size}px");
        Assert.True(TrayIconLayout.RingPad(size) <= size * 0.04f);
        Assert.True(TrayIconLayout.RingStroke(size) >= size * 0.15f);
    }

    [Theory]
    [InlineData(32)]
    [InlineData(48)]
    [InlineData(64)]
    public void DotFillsTheCanvas(int size)
    {
        var fill = TrayIconLayout.DotDiameter(size) / size;
        Assert.True(fill >= 0.90f, $"dot diameter {fill:0.###} of {size}px");
    }
}
