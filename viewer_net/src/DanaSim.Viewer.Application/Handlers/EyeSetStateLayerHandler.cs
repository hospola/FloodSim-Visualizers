using System.Text.Json;
using DanaSim.Viewer.Application.Dtos;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Domain.ValueObjects;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class EyeSetStateLayerHandler(ILogger<EyeSetStateLayerHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        var dto = payload.Deserialize<EyeSetStateLayerDto>()
            ?? throw new InvalidOperationException("Failed to deserialize EYE_SetState_Layer");

        foreach (var (key, cell) in dto.Changes.Cells)
        {
            if (!int.TryParse(key, out var index))
                continue;

            context.PendingChanges.Add(new CellChange(index, (FloodState)cell.State, cell.Height));
        }

        logger.LogDebug("EYE_SetState_Layer — {Count} cell changes accumulated", dto.Changes.Cells.Count);

        await MaybePublishAckAsync(context, control, ct);
    }

    private static async Task MaybePublishAckAsync(
        SimulationContext context, IControlPublisher control, CancellationToken ct)
    {
        if (context.ChunksPerBatch <= 0)
            return;

        context.ChunksSinceAck++;
        if (context.ChunksSinceAck >= context.ChunksPerBatch)
        {
            await control.PublishChunkAckAsync(ct);
            context.ChunksSinceAck = 0;
        }
    }
}
