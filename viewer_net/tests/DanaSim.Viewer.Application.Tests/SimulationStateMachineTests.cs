using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using FluentAssertions;

namespace DanaSim.Viewer.Application.Tests;

public class SimulationStateMachineTests
{
    [Fact]
    public void InitialPhase_IsDisconnected()
    {
        new SimulationStateMachine().Current.Should().Be(SimulationPhase.Disconnected);
    }

    [Fact]
    public void ValidFullSequence_TransitionsCorrectly()
    {
        var sm = new SimulationStateMachine();
        sm.Transition(SimulationPhase.Handshake);
        sm.Transition(SimulationPhase.Initialising);
        sm.Transition(SimulationPhase.Running);
        sm.Transition(SimulationPhase.Ended);
        sm.Current.Should().Be(SimulationPhase.Ended);
    }

    [Theory]
    [InlineData(SimulationPhase.Disconnected, SimulationPhase.Running)]
    [InlineData(SimulationPhase.Disconnected, SimulationPhase.Ended)]
    [InlineData(SimulationPhase.Handshake, SimulationPhase.Running)]
    [InlineData(SimulationPhase.Running, SimulationPhase.Disconnected)]
    public void InvalidTransition_Throws(SimulationPhase from, SimulationPhase to)
    {
        var sm = new SimulationStateMachine();
        // Advance to 'from' state
        if (from == SimulationPhase.Handshake)
            sm.Transition(SimulationPhase.Handshake);
        else if (from == SimulationPhase.Running)
        {
            sm.Transition(SimulationPhase.Handshake);
            sm.Transition(SimulationPhase.Initialising);
            sm.Transition(SimulationPhase.Running);
        }

        var act = () => sm.Transition(to);
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void IsAtLeast_ReturnsTrueForCurrentAndLaterPhases()
    {
        var sm = new SimulationStateMachine();
        sm.Transition(SimulationPhase.Handshake);
        sm.Transition(SimulationPhase.Initialising);

        sm.IsAtLeast(SimulationPhase.Disconnected).Should().BeTrue();
        sm.IsAtLeast(SimulationPhase.Initialising).Should().BeTrue();
        sm.IsAtLeast(SimulationPhase.Running).Should().BeFalse();
    }
}
