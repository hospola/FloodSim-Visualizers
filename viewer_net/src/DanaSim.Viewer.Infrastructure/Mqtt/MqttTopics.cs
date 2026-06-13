namespace DanaSim.Viewer.Infrastructure.Mqtt;

public static class MqttTopics
{
    private const string Base = "FloodSim/{0}";

    public static string Events(string scenario)        => $"{Base}/events".Replace("{0}", scenario);
    public static string PingIn(string scenario)        => $"{Base}/system/handshake/ping".Replace("{0}", scenario);
    public static string PongOut(string scenario)       => $"{Base}/system/handshake/pong".Replace("{0}", scenario);
    public static string ControlEvents(string scenario) => $"{Base}/control/events".Replace("{0}", scenario);
}
