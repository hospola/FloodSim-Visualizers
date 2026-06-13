namespace DanaSim.Viewer.Infrastructure.Mqtt;

public sealed class MqttOptions
{
    public string Host { get; set; } = "localhost";
    public int Port { get; set; } = 1883;
    public string Scenario { get; set; } = "scenario_29_10_2024";
    public int KeepAliveSeconds { get; set; } = 60;
    public int  ReconnectDelayMs { get; set; } = 2_000;
    /// <summary>
    /// When false the adapter starts the processing loop but does not attempt
    /// to connect until ISimulationController.ConnectAsync is called explicitly.
    /// Defaults to true; set to false on first launch when no UserConfig exists.
    /// </summary>
    public bool AutoConnect      { get; set; } = true;
}
