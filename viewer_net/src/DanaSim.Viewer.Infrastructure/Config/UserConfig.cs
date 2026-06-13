namespace DanaSim.Viewer.Infrastructure.Config;

public sealed class UserConfig
{
    public string MqttHost        { get; set; } = "localhost";
    public int    MqttPort        { get; set; } = 1883;
    public string Scenario        { get; set; } = "";
    public string TerrainBasePath { get; set; } = "";
    public string OutputDir       { get; set; } = "";
}
