namespace DanaSim.Viewer.Domain.Ports;

/// <summary>
/// Outbound port: publishes control messages back to the simulator via MQTT.
/// Implemented by MqttControlPublisher in the Infrastructure layer.
/// </summary>
public interface IControlPublisher
{
    Task PublishChunkAckAsync(CancellationToken ct = default);
    Task PublishPongAsync(CancellationToken ct = default);
}
