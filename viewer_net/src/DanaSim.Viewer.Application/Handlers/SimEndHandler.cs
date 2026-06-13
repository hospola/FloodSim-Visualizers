using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class SimEndHandler(
    SimulationStatusService statusService,
    ILogger<SimEndHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        context.IsRunning = false;
        stateMachine.Transition(SimulationPhase.Ended);

        await broadcaster.BroadcastSimulationEndedAsync(ct);
        statusService.SetPhase("Ended");

        var totalTime = payload.TryGetProperty("sim_time_total", out var t) ? t.GetDouble() : 0;
        logger.LogInformation("Sim_End — total simulation time: {Total}s", totalTime);
    }
}
