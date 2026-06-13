using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Domain.ValueObjects;
using Microsoft.Extensions.Logging;

namespace DanaSim.Viewer.Application.Handlers;

public sealed class InitEofHandler(ILogger<InitEofHandler> logger) : IMqttEventHandler
{
    public async Task HandleAsync(
        JsonElement payload, SimulationContext context, SimulationStateMachine stateMachine,
        IControlPublisher control, ISimulationBroadcaster broadcaster, CancellationToken ct)
    {
        stateMachine.Transition(SimulationPhase.Running);

        var meta = new GridMeta(
            context.Grid.Rows,
            context.Grid.Cols,
            context.Config.CellResolutionM,
            context.Grid.TerrainHeights,
            context.ColorPalette);

        var frame = context.Grid.BuildFrameData(context.Config.SimStartTime);
        context.Grid.ConsumeData();
        context.StepIndex++;

        await broadcaster.BroadcastInitialStateAsync(meta, frame, ct);

        logger.LogInformation(
            "Init_EOF — initial state broadcast to browser ({Rows}x{Cols})",
            context.Grid.Rows, context.Grid.Cols);
    }
}
