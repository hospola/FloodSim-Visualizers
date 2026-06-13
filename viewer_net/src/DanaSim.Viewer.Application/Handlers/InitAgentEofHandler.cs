using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class InitAgentEofHandler(ILogger<InitAgentEofHandler> logger) : IMqttEventHandler
{
    public Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        logger.LogInformation("InitAgent_EOF — all layers received, waiting for initial state chunks");
        return Task.CompletedTask;
    }
}
