using DanaSim.Viewer.Infrastructure.Config;
using FluentAssertions;

namespace DanaSim.Viewer.Infrastructure.Tests;

// UserConfigService caches AppPaths.UserConfigFile in a `static readonly` field at
// type-initialization time, so AppPaths must be configured exactly once, before the
// first UserConfigService is constructed anywhere in this test assembly, and the
// resulting directory must stay alive for the whole run.
[Collection("AppPaths")]
public class UserConfigServiceTests
{
    private static readonly string _tempDir;

    static UserConfigServiceTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), "danasim-userconfig-tests-" + Guid.NewGuid());
        Directory.CreateDirectory(_tempDir);
        AppPaths.Configure(_tempDir);
    }

    private static void DeleteConfigFile()
    {
        if (File.Exists(AppPaths.UserConfigFile))
            File.Delete(AppPaths.UserConfigFile);
    }

    [Fact]
    public void Load_WhenFileDoesNotExist_ReturnsNull()
    {
        DeleteConfigFile();

        new UserConfigService().Load().Should().BeNull();
    }

    [Fact]
    public void SaveAndLoad_RoundTripsConfig()
    {
        var service = new UserConfigService();
        var cfg = new UserConfig
        {
            MqttHost = "broker.example",
            MqttPort = 1885,
            Scenario = "demo",
            TerrainBasePath = "/data/terrain",
            OutputDir = "/data/out",
        };

        service.Save(cfg);
        var loaded = service.Load();

        loaded.Should().NotBeNull();
        loaded!.MqttHost.Should().Be("broker.example");
        loaded.MqttPort.Should().Be(1885);
        loaded.Scenario.Should().Be("demo");
        loaded.TerrainBasePath.Should().Be("/data/terrain");
        loaded.OutputDir.Should().Be("/data/out");
    }

    [Fact]
    public void Load_WithCorruptJson_ReturnsNull()
    {
        var service = new UserConfigService();
        AppPaths.EnsureBaseExists();
        File.WriteAllText(AppPaths.UserConfigFile, "not json");

        service.Load().Should().BeNull();
    }

    [Fact]
    public void IsConfigured_WhenNoFileExists_ReturnsFalse()
    {
        DeleteConfigFile();

        new UserConfigService().IsConfigured().Should().BeFalse();
    }

    [Fact]
    public void IsConfigured_WithCompleteConfig_ReturnsTrue()
    {
        var service = new UserConfigService();
        service.Save(new UserConfig
        {
            MqttHost = "broker",
            MqttPort = 1883,
            Scenario = "demo",
            OutputDir = "out",
        });

        service.IsConfigured().Should().BeTrue();
    }

    [Theory]
    [InlineData("", 1883, "demo", "out")]
    [InlineData("broker", 0, "demo", "out")]
    [InlineData("broker", 70000, "demo", "out")]
    [InlineData("broker", 1883, "", "out")]
    [InlineData("broker", 1883, "demo", "")]
    public void IsConfigured_WithIncompleteConfig_ReturnsFalse(
        string host, int port, string scenario, string outputDir)
    {
        var service = new UserConfigService();
        service.Save(new UserConfig
        {
            MqttHost = host,
            MqttPort = port,
            Scenario = scenario,
            OutputDir = outputDir,
        });

        service.IsConfigured().Should().BeFalse();
    }
}
