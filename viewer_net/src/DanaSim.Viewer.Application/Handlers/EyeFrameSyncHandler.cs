using System.Diagnostics;
using System.Text.Json;
using DanaSim.Viewer.Application.Dtos;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class EyeFrameSyncHandler(ILogger<EyeFrameSyncHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        if (!context.Grid.HasNewData)
            return;

        var dto = payload.Deserialize<EyeFrameSyncDto>() ?? new EyeFrameSyncDto();

        var buildSw = Stopwatch.StartNew();
        var frameData = context.Grid.BuildFrameData(dto.SimulationTime);
        buildSw.Stop();

        context.Grid.ConsumeData();
        context.StepIndex++;

        var broadcastSw = Stopwatch.StartNew();
        await broadcaster.BroadcastFrameUpdateAsync(frameData, context.StepIndex, ct);
        broadcastSw.Stop();

        logger.LogInformation(
            "[PERF] EYE_Frame_Sync — step {Step}, sim_time={Time}, {Changed} changed cells, buildFrame={BuildMs}ms, broadcast={BroadcastMs}ms",
            context.StepIndex, dto.SimulationTime, context.LastFrameChanges.Count,
            buildSw.ElapsedMilliseconds, broadcastSw.ElapsedMilliseconds);
    }
}
