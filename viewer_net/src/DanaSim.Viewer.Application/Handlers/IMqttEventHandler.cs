using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;

namespace DanaSim.Viewer.Application.Handlers;

public interface IMqttEventHandler
{
    Task HandleAsync(
        JsonElement payload,
        SimulationContext context,
        SimulationStateMachine stateMachine,
        IControlPublisher control,
        ISimulationBroadcaster broadcaster,
        CancellationToken ct = default);
}
