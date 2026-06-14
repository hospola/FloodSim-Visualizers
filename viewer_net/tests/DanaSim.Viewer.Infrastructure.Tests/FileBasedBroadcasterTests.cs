using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.ValueObjects;
using DanaSim.Viewer.Infrastructure.FileOutput;
using DanaSim.Viewer.Infrastructure.Mqtt;
using DanaSim.Viewer.Infrastructure.SignalR;
using DanaSim.Viewer.Infrastructure.Terrain;
using FluentAssertions;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class FileBasedBroadcasterTests : IDisposable
{
    private readonly string _tempDir;
    private readonly Mock<IClientProxy> _groupProxy = new();
    private readonly Mock<IHubContext<SimulationHub>> _hub = new();

    public FileBasedBroadcasterTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), "danasim-broadcaster-tests-" + Guid.NewGuid());
        Directory.CreateDirectory(_tempDir);

        _groupProxy.Setup(p => p.SendCoreAsync(It.IsAny<string>(), It.IsAny<object?[]>(), It.IsAny<CancellationToken>()))
                   .Returns(Task.CompletedTask);
        var clients = new Mock<IHubClients>();
        clients.Setup(c => c.Group(It.IsAny<string>())).Returns(_groupProxy.Object);
        _hub.SetupGet(h => h.Clients).Returns(clients.Object);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    private FileBasedBroadcaster CreateBroadcaster(
        SimulationStatusService? status = null,
        string scenario = "demo",
        string terrainBasePath = "")
    {
        return new FileBasedBroadcaster(
            Options.Create(new FileOutputOptions { OutputDir = _tempDir }),
            Options.Create(new MqttOptions { Scenario = scenario }),
            Options.Create(new TerrainOptions { BasePath = terrainBasePath }),
            status ?? new SimulationStatusService(),
            _hub.Object,
            NullLogger<FileBasedBroadcaster>.Instance);
    }

    private static GridMeta CreateMeta(int rows = 2, int cols = 2, ColorPalette? palette = null) =>
        new(rows, cols, 1.0f, [10f, 20f, 30f, 40f], palette);

    private static FrameData CreateFrame(int rows = 2, int cols = 2) =>
        new(
            Enumerable.Repeat(FloodState.Risk1, rows * cols).ToArray(),
            Enumerable.Repeat(0.5f, rows * cols).ToArray(),
            "00:00:01");

    // ── BroadcastInitialStateAsync ───────────────────────────────────────────

    [Fact]
    public async Task BroadcastInitialStateAsync_CreatesScenarioAndFloodDirectories()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        Directory.Exists(Path.Combine(_tempDir, "demo")).Should().BeTrue();
        Directory.Exists(Path.Combine(_tempDir, "demo", "flood")).Should().BeTrue();
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WritesPlayerHtmlAndManifest()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var playerHtmlPath = Path.Combine(_tempDir, "demo", "player.html");
        var manifestPath = Path.Combine(_tempDir, "demo", "flood", "manifest.json");

        File.Exists(playerHtmlPath).Should().BeTrue();
        File.Exists(manifestPath).Should().BeTrue();

        var manifest = await File.ReadAllTextAsync(manifestPath);
        manifest.Should().Contain("\"frames\": []");
        manifest.Should().Contain("\"live\": true");

        var html = await File.ReadAllTextAsync(playerHtmlPath);
        html.Should().Contain("window.__CONFIG__");
        html.Should().Contain("\"scenario\":\"demo\"");
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_UpdatesStatusService()
    {
        var status = new SimulationStatusService();
        status.SetConnection("Connected");
        var broadcaster = CreateBroadcaster(status: status, scenario: "demo");

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var snapshot = status.Get();
        snapshot.Phase.Should().Be("Running");
        snapshot.Scenario.Should().Be("demo");
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithMessagePalette_UsesItOverFileAndDefaults()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        var meta = CreateMeta(palette: ColorPalette.Default);

        await broadcaster.BroadcastInitialStateAsync(meta, CreateFrame(), CancellationToken.None);

        var html = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "player.html"));
        html.Should().Contain(ColorPalette.Default.ColorStrings()[0]);
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithoutPaletteFile_UsesHardcodedDefaults()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var html = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "player.html"));
        html.Should().Contain("0.62 0.50 0.25"); // first DefaultStateColors entry
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithX3dStateColorsInPaletteFile_UsesThem()
    {
        var terrainDir = Path.Combine(_tempDir, "terrain");
        Directory.CreateDirectory(terrainDir);
        await File.WriteAllTextAsync(Path.Combine(terrainDir, "color_palette.json"), """
            {
                "x3d": {
                    "state_colors": [
                        [0.1, 0.2, 0.3],
                        [0.4, 0.5, 0.6]
                    ]
                }
            }
            """);

        var broadcaster = CreateBroadcaster(scenario: "demo", terrainBasePath: terrainDir);

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var html = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "player.html"));
        html.Should().Contain("0.10 0.20 0.30");
        html.Should().Contain("0.40 0.50 0.60");
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithFloodRiskLayerInPaletteFile_UsesThem()
    {
        var terrainDir = Path.Combine(_tempDir, "terrain");
        Directory.CreateDirectory(terrainDir);
        await File.WriteAllTextAsync(Path.Combine(terrainDir, "color_palette.json"), """
            {
                "layers": {
                    "flood_risk": [
                        { "value": 1, "label": "Medium", "rgba": [26, 102, 204, 255] },
                        { "value": 0, "label": "Dry", "rgba": [158, 128, 80, 255] }
                    ]
                }
            }
            """);

        var broadcaster = CreateBroadcaster(scenario: "demo", terrainBasePath: terrainDir);

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var html = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "player.html"));
        // Sorted by value: Dry (0) comes before Medium (1)
        html.Should().Contain("0.62 0.50 0.31"); // 158/255, 128/255, 80/255
        html.Should().Contain("0.10 0.40 0.80"); // 26/255, 102/255, 204/255
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithInvalidPaletteFile_FallsBackToDefaults()
    {
        var terrainDir = Path.Combine(_tempDir, "terrain");
        Directory.CreateDirectory(terrainDir);
        await File.WriteAllTextAsync(Path.Combine(terrainDir, "color_palette.json"), "not json");

        var broadcaster = CreateBroadcaster(scenario: "demo", terrainBasePath: terrainDir);

        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        var html = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "player.html"));
        html.Should().Contain("0.62 0.50 0.25");
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithFlatTerrain_NormalizesToDefaultRange()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        var meta = new GridMeta(2, 2, 1.0f, [5f, 5f, 5f, 5f], null);

        await broadcaster.BroadcastInitialStateAsync(meta, CreateFrame(), CancellationToken.None);

        File.Exists(Path.Combine(_tempDir, "demo", "player.html")).Should().BeTrue();
    }

    [Fact]
    public async Task BroadcastInitialStateAsync_WithNullTerrainHeights_UsesAllNodataGrid()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        var meta = new GridMeta(2, 2, 1.0f, null, null);

        await broadcaster.BroadcastInitialStateAsync(meta, CreateFrame(), CancellationToken.None);

        File.Exists(Path.Combine(_tempDir, "demo", "player.html")).Should().BeTrue();
    }

    // ── BroadcastFrameUpdateAsync ────────────────────────────────────────────

    [Fact]
    public async Task BroadcastFrameUpdateAsync_BeforeInitialState_IsNoOp()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");

        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 0, CancellationToken.None);

        Directory.Exists(Path.Combine(_tempDir, "demo")).Should().BeFalse();
        _groupProxy.Verify(p => p.SendCoreAsync(It.IsAny<string>(), It.IsAny<object?[]>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task BroadcastFrameUpdateAsync_WritesFloodPngAndUpdatesManifest()
    {
        var status = new SimulationStatusService();
        var broadcaster = CreateBroadcaster(status: status, scenario: "demo");
        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 0, CancellationToken.None);

        var pngPath = Path.Combine(_tempDir, "demo", "flood", "step_00000.png");
        File.Exists(pngPath).Should().BeTrue();

        var manifest = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "flood", "manifest.json"));
        manifest.Should().Contain("step_00000");
        manifest.Should().Contain("\"live\": true");

        status.Get().FrameCount.Should().Be(1);
        status.Get().SimulationTime.Should().Be("00:00:01");
        status.Get().ActivePlayerUrl.Should().Be("/sim-outputs/demo/player.html");
    }

    [Fact]
    public async Task BroadcastFrameUpdateAsync_NotifiesHubGroup()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 0, CancellationToken.None);

        _groupProxy.Verify(p => p.SendCoreAsync(
            "FrameReady",
            It.Is<object?[]>(args => (string)args[0]! == "step_00000"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task BroadcastFrameUpdateAsync_MultipleFrames_AccumulatesManifestEntries()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);

        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 0, CancellationToken.None);
        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 1, CancellationToken.None);

        var manifest = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "flood", "manifest.json"));
        manifest.Should().Contain("step_00000");
        manifest.Should().Contain("step_00001");
    }

    // ── BroadcastSimulationEndedAsync ────────────────────────────────────────

    [Fact]
    public async Task BroadcastSimulationEndedAsync_WritesFinalManifestAndNotifiesHub()
    {
        var broadcaster = CreateBroadcaster(scenario: "demo");
        await broadcaster.BroadcastInitialStateAsync(CreateMeta(), CreateFrame(), CancellationToken.None);
        await broadcaster.BroadcastFrameUpdateAsync(CreateFrame(), 0, CancellationToken.None);

        await broadcaster.BroadcastSimulationEndedAsync(CancellationToken.None);

        var manifest = await File.ReadAllTextAsync(Path.Combine(_tempDir, "demo", "flood", "manifest.json"));
        manifest.Should().Contain("\"live\": false");
        manifest.Should().Contain("step_00000");

        _groupProxy.Verify(p => p.SendCoreAsync(
            "SimulationEnded",
            It.IsAny<object?[]>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }
}
