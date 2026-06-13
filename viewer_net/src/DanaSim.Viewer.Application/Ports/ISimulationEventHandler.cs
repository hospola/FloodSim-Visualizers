namespace DanaSim.Viewer.Application.Ports;

/// <summary>
/// Inbound port: entry point for raw MQTT event JSON received by the MQTT adapter.
/// </summary>
public interface ISimulationEventHandler
{
    Task HandleEventAsync(string rawJson, CancellationToken ct = default);
}
