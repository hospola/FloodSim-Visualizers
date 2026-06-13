using System.Diagnostics;
using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class FrameEndHandler(ILogger<FrameEndHandler> logger) : IMqttEventHandler
{
    public Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        var count = context.PendingChanges.Count;

        var applySw = Stopwatch.StartNew();
        context.Grid.ApplyBulkChanges(context.PendingChanges);
        applySw.Stop();

        var cloneSw = Stopwatch.StartNew();
        context.LastFrameChanges = [.. context.PendingChanges];
        cloneSw.Stop();

        context.PendingChanges.Clear();
        context.FrameStartTick = null;

        logger.LogInformation(
            "[PERF] FrameEnd — {Count} changes applied in {ApplyMs}ms (clone={CloneMs}ms)",
            count, applySw.ElapsedMilliseconds, cloneSw.ElapsedMilliseconds);
        return Task.CompletedTask;
    }
}
