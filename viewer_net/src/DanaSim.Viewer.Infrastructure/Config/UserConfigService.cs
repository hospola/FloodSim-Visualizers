using System.Text.Json;

namespace DanaSim.Viewer.Infrastructure.Config;

public sealed class UserConfigService
{
    private static readonly string ConfigPath = AppPaths.UserConfigFile;

    private static readonly JsonSerializerOptions JsonOpts =
        new() { WriteIndented = true };

    public UserConfig? Load()
    {
        if (!File.Exists(ConfigPath))
            return null;

        try
        {
            return JsonSerializer.Deserialize<UserConfig>(
                File.ReadAllText(ConfigPath));
        }
        catch
        {
            return null;
        }
    }

    public void Save(UserConfig cfg)
    {
        AppPaths.EnsureBaseExists();
        var tmp = ConfigPath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(cfg, JsonOpts));
        File.Move(tmp, ConfigPath, overwrite: true);
    }

    public bool IsConfigured()
    {
        var cfg = Load();
        return cfg is not null
            && !string.IsNullOrWhiteSpace(cfg.MqttHost)
            && cfg.MqttPort is >= 1 and <= 65535
            && !string.IsNullOrWhiteSpace(cfg.Scenario)
            // TerrainBasePath may be left blank — see ApiController.PostConfig.
            && !string.IsNullOrWhiteSpace(cfg.OutputDir);
    }
}
