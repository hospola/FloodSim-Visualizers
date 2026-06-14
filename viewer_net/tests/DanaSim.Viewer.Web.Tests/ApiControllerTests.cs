using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Infrastructure.Config;
using DanaSim.Viewer.Infrastructure.FileOutput;
using DanaSim.Viewer.Web.Controllers;
using DanaSim.Viewer.Web.Logging;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using Moq;

namespace DanaSim.Viewer.Web.Tests;

// UserConfigService caches AppPaths.UserConfigFile in a `static readonly` field at
// type-initialization time, so AppPaths must be configured exactly once, before the
// first UserConfigService is constructed anywhere in this test assembly, and the
// resulting directory must stay alive for the whole run.
public class ApiControllerTests
{
    private static readonly string _tempDir;

    static ApiControllerTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), "danasim-api-tests-" + Guid.NewGuid());
        Directory.CreateDirectory(_tempDir);
        AppPaths.Configure(_tempDir);
    }

    private static ApiController CreateController(
        Mock<ISimulationController>? simController = null,
        SimulationStatusService? status = null,
        FileOutputOptions? fileOutputOptions = null,
        string contentRoot = "")
    {
        var env = new Mock<IWebHostEnvironment>();
        env.SetupGet(e => e.ContentRootPath).Returns(contentRoot);

        return new ApiController(
            new InMemoryLogSink(),
            status ?? new SimulationStatusService(),
            new UserConfigService(),
            (simController ?? new Mock<ISimulationController>()).Object,
            Options.Create(fileOutputOptions ?? new FileOutputOptions()),
            env.Object);
    }

    // ── GetStatus ────────────────────────────────────────────────────────────

    [Fact]
    public void GetStatus_ReturnsCurrentStatus()
    {
        var status = new SimulationStatusService();
        status.SetConnection("Connected");
        var controller = CreateController(status: status);

        var result = controller.GetStatus() as OkObjectResult;

        result.Should().NotBeNull();
        var value = result!.Value as SimulationStatus;
        value!.ConnectionStatus.Should().Be("Connected");
    }

    // ── GetConfig ────────────────────────────────────────────────────────────

    [Fact]
    public void GetConfig_WhenNoConfigSaved_ReturnsDefaults()
    {
        var configFile = AppPaths.UserConfigFile;
        if (File.Exists(configFile))
            File.Delete(configFile);

        var controller = CreateController();

        var result = controller.GetConfig() as OkObjectResult;

        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("\"MqttHost\":\"localhost\"");
        json.Should().Contain("\"MqttPort\":1883");
    }

    [Fact]
    public void GetConfig_WhenConfigSaved_ReturnsSavedValues()
    {
        var configService = new UserConfigService();
        configService.Save(new UserConfig { MqttHost = "broker.local", MqttPort = 1884, Scenario = "demo", OutputDir = "out" });

        var env = new Mock<IWebHostEnvironment>();
        var controller = new ApiController(
            new InMemoryLogSink(),
            new SimulationStatusService(),
            configService,
            Mock.Of<ISimulationController>(),
            Options.Create(new FileOutputOptions()),
            env.Object);

        var result = controller.GetConfig() as OkObjectResult;

        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("\"MqttHost\":\"broker.local\"");
        json.Should().Contain("\"Scenario\":\"demo\"");
    }

    // ── PostConfig ───────────────────────────────────────────────────────────

    [Fact]
    public async Task PostConfig_WithValidConfig_SavesAndReconfigures()
    {
        var simController = new Mock<ISimulationController>();
        simController.Setup(s => s.ReconfigureAsync("broker", 1884, "demo", It.IsAny<CancellationToken>()))
                      .Returns(Task.CompletedTask);
        var controller = CreateController(simController);

        var cfg = new UserConfig { MqttHost = "broker", MqttPort = 1884, Scenario = "demo", OutputDir = "out" };
        var result = await controller.PostConfig(cfg, CancellationToken.None);

        result.Should().BeOfType<OkResult>();
        simController.Verify(s => s.ReconfigureAsync("broker", 1884, "demo", It.IsAny<CancellationToken>()), Times.Once);

        new UserConfigService().Load()!.MqttHost.Should().Be("broker");
    }

    [Fact]
    public async Task PostConfig_WithMissingHost_ReturnsBadRequestWithError()
    {
        var controller = CreateController();

        var cfg = new UserConfig { MqttHost = "", MqttPort = 1884, Scenario = "demo", OutputDir = "out" };
        var result = await controller.PostConfig(cfg, CancellationToken.None) as BadRequestObjectResult;

        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("mqttHost");
    }

    [Theory]
    [InlineData(0)]
    [InlineData(65536)]
    public async Task PostConfig_WithOutOfRangePort_ReturnsBadRequest(int port)
    {
        var controller = CreateController();

        var cfg = new UserConfig { MqttHost = "broker", MqttPort = port, Scenario = "demo", OutputDir = "out" };
        var result = await controller.PostConfig(cfg, CancellationToken.None) as BadRequestObjectResult;

        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("mqttPort");
    }

    [Fact]
    public async Task PostConfig_WithMissingScenario_ReturnsBadRequest()
    {
        var controller = CreateController();

        var cfg = new UserConfig { MqttHost = "broker", MqttPort = 1884, Scenario = "", OutputDir = "out" };
        var result = await controller.PostConfig(cfg, CancellationToken.None) as BadRequestObjectResult;

        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("scenario");
    }

    [Fact]
    public async Task PostConfig_WithMissingOutputDir_ReturnsBadRequest()
    {
        var controller = CreateController();

        var cfg = new UserConfig { MqttHost = "broker", MqttPort = 1884, Scenario = "demo", OutputDir = "" };
        var result = await controller.PostConfig(cfg, CancellationToken.None) as BadRequestObjectResult;

        result.Should().NotBeNull();
        var json = System.Text.Json.JsonSerializer.Serialize(result!.Value);
        json.Should().Contain("outputDir");
    }

    [Fact]
    public async Task PostConfig_WithBlankTerrainBasePath_IsAccepted()
    {
        var simController = new Mock<ISimulationController>();
        var controller = CreateController(simController);

        var cfg = new UserConfig { MqttHost = "broker", MqttPort = 1884, Scenario = "demo", TerrainBasePath = "", OutputDir = "out" };
        var result = await controller.PostConfig(cfg, CancellationToken.None);

        result.Should().BeOfType<OkResult>();
    }

    // ── Connect / Disconnect ─────────────────────────────────────────────────

    [Fact]
    public void Connect_TriggersConnectAsync_AndReturnsAccepted()
    {
        var simController = new Mock<ISimulationController>();
        simController.Setup(s => s.ConnectAsync(It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        var controller = CreateController(simController);

        var result = controller.Connect();

        result.Should().BeOfType<AcceptedResult>();
        simController.Verify(s => s.ConnectAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Disconnect_AwaitsDisconnectAsync_AndReturnsOk()
    {
        var simController = new Mock<ISimulationController>();
        simController.Setup(s => s.DisconnectAsync(It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        var controller = CreateController(simController);

        var result = await controller.Disconnect(CancellationToken.None);

        result.Should().BeOfType<OkResult>();
        simController.Verify(s => s.DisconnectAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    // ── GetLogs ──────────────────────────────────────────────────────────────

    [Fact]
    public void GetLogs_ReturnsEntriesFromLogSink()
    {
        var env = new Mock<IWebHostEnvironment>();
        var logSink = new InMemoryLogSink();
        var controller = new ApiController(
            logSink,
            new SimulationStatusService(),
            new UserConfigService(),
            Mock.Of<ISimulationController>(),
            Options.Create(new FileOutputOptions()),
            env.Object);

        var result = controller.GetLogs() as OkObjectResult;

        result.Should().NotBeNull();
    }

    // ── GetRuns ──────────────────────────────────────────────────────────────

    [Fact]
    public void GetRuns_WhenOutputDirDoesNotExist_ReturnsEmptyArray()
    {
        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = Path.Combine(_tempDir, "missing") },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;

        result.Should().NotBeNull();
        ((object[])result!.Value!).Should().BeEmpty();
    }

    [Fact]
    public void GetRuns_WithRelativeOutputDir_ResolvesAgainstContentRoot()
    {
        var outputDir = Path.Combine(_tempDir, "outputs");
        Directory.CreateDirectory(outputDir);

        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = "outputs" },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;

        result.Should().NotBeNull();
        ((object[])result!.Value!).Should().BeEmpty();
    }

    [Fact]
    public void GetRuns_WithRunDirectory_ReturnsRunInfoFromManifest()
    {
        var outputDir = Path.Combine(_tempDir, "outputs");
        var runDir = Path.Combine(outputDir, "run1");
        var floodDir = Path.Combine(runDir, "flood");
        Directory.CreateDirectory(floodDir);
        File.WriteAllText(Path.Combine(runDir, "player.html"), "<html></html>");
        File.WriteAllText(Path.Combine(floodDir, "manifest.json"), """{"frames": ["a.png", "b.png"], "live": true}""");

        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = outputDir },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;

        result.Should().NotBeNull();
        var runs = (object[])result!.Value!;
        runs.Should().ContainSingle();

        var json = System.Text.Json.JsonSerializer.Serialize(runs[0]);
        json.Should().Contain("\"name\":\"run1\"");
        json.Should().Contain("\"playerUrl\":\"/sim-outputs/run1/player.html\"");
        json.Should().Contain("\"frameCount\":2");
        json.Should().Contain("\"live\":true");
    }

    [Fact]
    public void GetRuns_IgnoresDirectoriesWithoutPlayerHtml()
    {
        var outputDir = Path.Combine(_tempDir, "outputs");
        var runDir = Path.Combine(outputDir, "not-a-run");
        Directory.CreateDirectory(runDir);

        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = outputDir },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;

        ((object[])result!.Value!).Should().BeEmpty();
    }

    [Fact]
    public void GetRuns_WithMissingManifest_ReturnsNullFrameCountAndLiveFalse()
    {
        var outputDir = Path.Combine(_tempDir, "outputs");
        var runDir = Path.Combine(outputDir, "run1");
        Directory.CreateDirectory(runDir);
        File.WriteAllText(Path.Combine(runDir, "player.html"), "<html></html>");

        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = outputDir },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;
        var runs = (object[])result!.Value!;

        var json = System.Text.Json.JsonSerializer.Serialize(runs[0]);
        json.Should().Contain("\"frameCount\":null");
        json.Should().Contain("\"live\":false");
    }

    [Fact]
    public void GetRuns_WithInvalidManifestJson_ReturnsNullFrameCountAndLiveFalse()
    {
        var outputDir = Path.Combine(_tempDir, "outputs");
        var runDir = Path.Combine(outputDir, "run1");
        var floodDir = Path.Combine(runDir, "flood");
        Directory.CreateDirectory(floodDir);
        File.WriteAllText(Path.Combine(runDir, "player.html"), "<html></html>");
        File.WriteAllText(Path.Combine(floodDir, "manifest.json"), "not valid json");

        var controller = CreateController(
            fileOutputOptions: new FileOutputOptions { OutputDir = outputDir },
            contentRoot: _tempDir);

        var result = controller.GetRuns() as OkObjectResult;
        var runs = (object[])result!.Value!;

        var json = System.Text.Json.JsonSerializer.Serialize(runs[0]);
        json.Should().Contain("\"frameCount\":null");
        json.Should().Contain("\"live\":false");
    }
}
