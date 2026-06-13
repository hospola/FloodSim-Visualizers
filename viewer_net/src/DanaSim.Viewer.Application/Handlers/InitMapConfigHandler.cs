using System.Text.Json;
using DanaSim.Viewer.Application.Dtos;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class InitMapConfigHandler(ILogger<InitMapConfigHandler> logger) : IMqttEventHandler
{
    public Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        var dto = payload.Deserialize<InitMapConfigDto>()
            ?? throw new InvalidOperationException("Failed to deserialize InitMap_Config");

        context.Config.Apply(
            dto.Map.SizeX, dto.Map.SizeY, dto.Map.CellResolutionM,
            dto.Metadata.SimStartTime, dto.Metadata.TimeStepS,
            dto.Georeference.Lat, dto.Georeference.Lon);

        context.Grid.Resize(dto.Map.SizeY, dto.Map.SizeX);

        if (stateMachine.Current == SimulationPhase.Handshake)
            stateMachine.Transition(SimulationPhase.Initialising);

        logger.LogInformation(
            "InitMap_Config applied — grid {Cols}x{Rows}, cell {Res}m",
            dto.Map.SizeX, dto.Map.SizeY, dto.Map.CellResolutionM);

        return Task.CompletedTask;
    }
}
