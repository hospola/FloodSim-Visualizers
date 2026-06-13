using DanaSim.Viewer.Domain.Enums;

namespace DanaSim.Viewer.Application.StateMachine;

public sealed class SimulationStateMachine
{
    private static readonly Dictionary<SimulationPhase, SimulationPhase[]> ValidTransitions = new()
    {
        [SimulationPhase.Disconnected] = [SimulationPhase.Handshake],
        [SimulationPhase.Handshake]    = [SimulationPhase.Initialising],
        [SimulationPhase.Initialising] = [SimulationPhase.Running],
        [SimulationPhase.Running]      = [SimulationPhase.Ended],
        [SimulationPhase.Ended]        = [],
    };

    public SimulationPhase Current { get; private set; } = SimulationPhase.Disconnected;

    public void Transition(SimulationPhase next)
    {
        if (!ValidTransitions[Current].Contains(next))
            throw new InvalidOperationException(
                $"Invalid phase transition: {Current} → {next}");

        Current = next;
    }

    public bool IsAtLeast(SimulationPhase phase) =>
        Current >= phase;
}
