using DanaSim.Viewer.Domain.Enums;
using FluentAssertions;

namespace DanaSim.Viewer.Domain.Tests;

public class FloodStateTests
{
    [Theory]
    [InlineData(FloodState.Dry, 0)]
    [InlineData(FloodState.Risk1, 1)]
    [InlineData(FloodState.Risk2, 2)]
    [InlineData(FloodState.Risk3, 3)]
    [InlineData(FloodState.Risk4, 4)]
    [InlineData(FloodState.Risk5, 5)]
    public void FloodState_NumericValues_MatchProtocol(FloodState state, int expected)
    {
        ((int)state).Should().Be(expected);
    }

    [Fact]
    public void FloodState_CanCastFromProtocolByte()
    {
        var state = (FloodState)3;
        state.Should().Be(FloodState.Risk3);
    }
}
