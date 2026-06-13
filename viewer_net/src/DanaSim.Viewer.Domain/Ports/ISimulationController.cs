namespace DanaSim.Viewer.Domain.Ports;

/// <summary>
/// User-facing control surface for the MQTT connection.
/// Distinct from IHostedService so connect/disconnect can be triggered at runtime
/// without conflicting with the host lifecycle Start/Stop.
/// </summary>
public interface ISimulationController
{
    bool IsConnected { get; }

    /// <summary>Idempotent: returns immediately if already connected.</summary>
    Task ConnectAsync(CancellationToken ct = default);

    /// <summary>Graceful disconnect; leaves the processing loop alive.</summary>
    Task DisconnectAsync(CancellationToken ct = default);

    /// <summary>Disconnect → apply new broker settings → reconnect.</summary>
    Task ReconfigureAsync(string host, int port, string scenario, CancellationToken ct = default);
}
