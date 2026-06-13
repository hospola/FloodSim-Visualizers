using System.Text.Json;
using DanaSim.Viewer.Application.Dtos;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class FrameStartHandler(ILogger<FrameStartHandler> logger) : IMqttEventHandler
{
    public Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        var dto = payload.Deserialize<FrameStartDto>()
            ?? throw new InvalidOperationException("Failed to deserialize FrameStart");

        context.PendingChanges.Clear();
        context.ChunksPerBatch = dto.ChunksPerBatch;
        context.ChunksSinceAck = 0;
        context.FrameStartTick = Environment.TickCount64;

        logger.LogInformation(
            "FrameStart — total_chunks={Total}, chunks_per_batch={Batch}",
            dto.TotalChunks, dto.ChunksPerBatch);

        return Task.CompletedTask;
    }
}
