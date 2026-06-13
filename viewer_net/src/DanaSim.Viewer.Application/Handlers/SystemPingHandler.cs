using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class SystemPingHandler(ILogger<SystemPingHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        if (stateMachine.Current == SimulationPhase.Disconnected)
            stateMachine.Transition(SimulationPhase.Handshake);

        await control.PublishPongAsync(ct);
        logger.LogInformation("System_Ping received — Pong sent");
    }
}
