using System.Text.Json;
using DanaSim.Viewer.Application.Dtos;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Domain.ValueObjects;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class InitAgentLayerHandler(
    ITerrainDataReader terrainReader,
    ILogger<InitAgentLayerHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        var dto = payload.Deserialize<InitAgentLayerDto>()
            ?? throw new InvalidOperationException("Failed to deserialize InitAgent_Layer");

        if (dto.ColorPalette is { Count: > 0 } paletteEntries)
        {
            context.ColorPalette = new ColorPalette(paletteEntries.Select(e =>
                new ColorPaletteEntry(e.Value, e.Label, e.Hex, e.Rgba.Select(c => (byte)c).ToArray())));
            logger.LogInformation(
                "Color palette received from InitAgent_Layer '{Id}' ({Count} levels)",
                dto.Id, context.ColorPalette.Entries.Count);
        }

        var heights = await terrainReader.ReadHeightsAsync(dto.DataPath, dto.DataFilename, ct);
        if (heights is null)
        {
            logger.LogWarning("Terrain data not found for layer '{Id}' at {Path}/{File}",
                dto.Id, dto.DataPath, dto.DataFilename);
            return;
        }

        context.Grid.SetTerrainHeights(heights);
        logger.LogInformation("InitAgent_Layer '{Id}' loaded — {Count} height values", dto.Id, heights.Length);
    }
}
