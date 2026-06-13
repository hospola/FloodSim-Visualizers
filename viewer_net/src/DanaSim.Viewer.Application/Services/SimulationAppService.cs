using System.Text.Json;
using DanaSim.Viewer.Application.Handlers;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.StateMachine;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace DanaSim.Viewer.Application.Services;

public sealed class SimulationAppServiceOptions
{
    public int FrameTimeoutMs { get; set; } = 30_000;
}

/// <summary>
/// Orchestrates all MQTT event handling. Implements the inbound port ISimulationEventHandler.
/// Mirrors python/visualizer/simulation_app.py SimulationApp.
/// </summary>
public sealed class SimulationAppService : ISimulationEventHandler
{
    private readonly SimulationContext _context = new();
    private readonly SimulationStateMachine _stateMachine = new();
    private readonly IControlPublisher _control;
    private readonly ISimulationBroadcaster _broadcaster;
    private readonly int _frameTimeoutMs;
    private readonly ILogger<SimulationAppService> _logger;

    private readonly Dictionary<string, IMqttEventHandler> _handlers;

    public SimulationAppService(
        SystemPingHandler ping,
        InitMapConfigHandler initMapConfig,
        InitAgentLayerHandler initAgentLayer,
        InitAgentEofHandler initAgentEof,
        FrameStartHandler frameStart,
        EyeSetStateLayerHandler eyeSetState,
        FrameEndHandler frameEnd,
        InitEofHandler initEof,
        EyeFrameSyncHandler eyeFrameSync,
        SimEndHandler simEnd,
        IControlPublisher control,
        ISimulationBroadcaster broadcaster,
        IOptions<SimulationAppServiceOptions> options,
        ILogger<SimulationAppService> logger)
    {
        _control = control;
        _broadcaster = broadcaster;
        _frameTimeoutMs = options.Value.FrameTimeoutMs;
        _logger = logger;

        _handlers = new Dictionary<string, IMqttEventHandler>(StringComparer.Ordinal)
        {
            ["System_Ping"]         = ping,
            ["InitMap_Config"]      = initMapConfig,
            ["InitAgent_Layer"]     = initAgentLayer,
            ["InitAgent_EOF"]       = initAgentEof,
            ["FrameStart"]          = frameStart,
            ["EYE_SetState_Layer"]  = eyeSetState,
            ["FrameEnd"]            = frameEnd,
            ["Init_EOF"]            = initEof,
            ["EYE_Frame_Sync"]      = eyeFrameSync,
            ["Sim_End"]             = simEnd,
        };
    }

    public async Task HandleEventAsync(string rawJson, CancellationToken ct = default)
    {
        CheckFrameTimeout();

        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(rawJson);
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Malformed MQTT payload — discarding");
            return;
        }

        using (doc)
        {
            if (!doc.RootElement.TryGetProperty("process", out var processProp))
            {
                _logger.LogWarning("MQTT payload missing 'process' field — discarding");
                return;
            }

            var process = processProp.GetString() ?? string.Empty;

            if (!_handlers.TryGetValue(process, out var handler))
            {
                _logger.LogDebug("Unknown event '{Process}' — discarding", process);
                return;
            }

            try
            {
                await handler.HandleAsync(
                    doc.RootElement, _context, _stateMachine, _control, _broadcaster, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error handling event '{Process}'", process);
            }
        }
    }

    /// <summary>
    /// Discards pending changes if FrameEnd is not received within the timeout.
    /// Mirrors SimulationApp.on_idle() in the Python visualizer.
    /// </summary>
    private void CheckFrameTimeout()
    {
        if (_stateMachine.Current != SimulationPhase.Running)
            return;

        if (_context.FrameStartTick is not { } startTick)
            return;

        if (Environment.TickCount64 - startTick < _frameTimeoutMs)
            return;

        _logger.LogWarning(
            "Frame timeout ({Ms}ms): FrameEnd not received. Discarding {Count} pending changes.",
            _frameTimeoutMs, _context.PendingChanges.Count);

        _context.PendingChanges.Clear();
        _context.FrameStartTick = null;
        _context.ChunksPerBatch = 0;
        _context.ChunksSinceAck = 0;
    }
}
