using DanaSim.Viewer.Domain.ValueObjects;

namespace DanaSim.Viewer.Domain.Ports;

/// <summary>
/// Outbound port: delivers simulation state to the viewer (file output or real-time stream).
/// </summary>
public interface ISimulationBroadcaster
{
    Task BroadcastInitialStateAsync(GridMeta meta, FrameData frame, CancellationToken ct = default);
    Task BroadcastFrameUpdateAsync(FrameData frame, int stepIndex, CancellationToken ct = default);
    Task BroadcastSimulationEndedAsync(CancellationToken ct = default);
}
