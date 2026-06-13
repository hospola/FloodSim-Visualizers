using System.Diagnostics;
using System.Text;
using System.Text.Json;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Domain.ValueObjects;
using DanaSim.Viewer.Infrastructure.Mqtt;
using DanaSim.Viewer.Infrastructure.SignalR;
using DanaSim.Viewer.Infrastructure.Terrain;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;

namespace DanaSim.Viewer.Infrastructure.FileOutput;

/// <summary>
/// Output adapter that writes flood PNGs + manifest.json + player.html to disk,
/// mirroring the output of python/visualizer/renderers/x3d/x3d_renderer.py.
/// Player JS/CSS are served from the embedded assembly at /player-assets — nothing
/// is copied per run.
/// </summary>
public sealed class FileBasedBroadcaster(
    IOptions<FileOutputOptions> options,
    IOptions<MqttOptions> mqttOptions,
    IOptions<TerrainOptions> terrainOptions,
    SimulationStatusService statusService,
    IHubContext<SimulationHub> hub,
    ILogger<FileBasedBroadcaster> logger) : ISimulationBroadcaster
{
    private const float Nodata = -9999f;

    private static readonly string[] DefaultStateColors =
    [
        "0.62 0.50 0.25",
        "0.60 0.90 1.00",
        "0.20 0.60 0.90",
        "0.10 0.40 0.80",
        "0.05 0.20 0.70",
        "0.10 0.10 0.60",
    ];

    private static readonly string[] DefaultStateLabels =
    [
        "Seco",
        "Muy somero",
        "Profundidad baja",
        "Profundidad media",
        "Profundidad alta",
        "Profundidad extrema",
    ];

    // Read dynamically so changes saved via the dashboard take effect immediately
    // without requiring a restart.
    private string _outputBaseDir   => options.Value.OutputDir;
    private string _terrainBasePath => terrainOptions.Value.BasePath;
    private string _scenario        => mqttOptions.Value.Scenario;

    private string _scenarioDir = "";
    private string _floodDir    = "";
    private GridMeta? _meta;
    private float _minH;
    private float _maxH;
    private readonly List<string> _frameNames = [];

    // ── ISimulationBroadcaster ────────────────────────────────────────────────

    public async Task BroadcastInitialStateAsync(GridMeta meta, FrameData frame, CancellationToken ct)
    {
        var total = Stopwatch.StartNew();

        _meta = meta;
        _frameNames.Clear();
        _scenarioDir = Path.Combine(_outputBaseDir, _scenario);
        _floodDir    = Path.Combine(_scenarioDir, "flood");
        Directory.CreateDirectory(_scenarioDir);
        Directory.CreateDirectory(_floodDir);

        var encodeSw = Stopwatch.StartNew();
        var (terrainPng, minH, maxH) = EncodeTerrain(meta);
        encodeSw.Stop();
        _minH = minH;
        _maxH = maxH;

        var (stateColors, stateLabels) = ResolvePalette(meta.Palette);

        var htmlSw = Stopwatch.StartNew();
        var playerHtml = GeneratePlayerHtml(meta, minH, maxH,
            Convert.ToBase64String(terrainPng), stateColors, stateLabels, [], _scenario);
        htmlSw.Stop();

        var writeSw = Stopwatch.StartNew();
        await File.WriteAllTextAsync(Path.Combine(_scenarioDir, "player.html"), playerHtml, ct);
        await WriteManifestAsync(live: true, ct);
        writeSw.Stop();

        statusService.Reset(_scenario);
        statusService.SetPhase("Running");

        total.Stop();
        logger.LogInformation(
            "[PERF] BroadcastInitialState: total={TotalMs}ms (terrainEncode={EncodeMs}ms [{PngKb:F1} KB], html={HtmlMs}ms, writes={WriteMs}ms) — heights {MinH:F1}–{MaxH:F1} m, {N} states",
            total.ElapsedMilliseconds, encodeSw.ElapsedMilliseconds, terrainPng.Length / 1024.0,
            htmlSw.ElapsedMilliseconds, writeSw.ElapsedMilliseconds, minH, maxH, stateColors.Length);

        logger.LogInformation(
            "FileBasedBroadcaster: output ready at '{Dir}' (heights {MinH:F1}–{MaxH:F1} m, {N} states)",
            _scenarioDir, minH, maxH, stateColors.Length);
    }

    public async Task BroadcastFrameUpdateAsync(FrameData frame, int stepIndex, CancellationToken ct)
    {
        if (_meta is null) return;

        var total = Stopwatch.StartNew();

        var stepName = $"step_{stepIndex:D5}";

        var encodeSw = Stopwatch.StartNew();
        var floodPng = EncodeFlood(frame.PaletteGrid, _meta.Rows, _meta.Cols);
        encodeSw.Stop();

        var writeSw = Stopwatch.StartNew();
        await File.WriteAllBytesAsync(Path.Combine(_floodDir, $"{stepName}.png"), floodPng, ct);

        _frameNames.Add(stepName);
        await WriteManifestAsync(live: true, ct);
        writeSw.Stop();

        var playerUrl = $"/sim-outputs/{_scenario}/player.html";
        statusService.RecordFrame(frame.SimulationTime, playerUrl);

        var hubSw = Stopwatch.StartNew();
        await hub.Clients.Group(_scenario).SendAsync("FrameReady", stepName, ct);
        hubSw.Stop();

        total.Stop();
        logger.LogInformation(
            "[PERF] BroadcastFrameUpdate {Step}: total={TotalMs}ms (encode={EncodeMs}ms, write={WriteMs}ms, hub={HubMs}ms) — {Kb:F1} KB",
            stepName, total.ElapsedMilliseconds, encodeSw.ElapsedMilliseconds, writeSw.ElapsedMilliseconds,
            hubSw.ElapsedMilliseconds, floodPng.Length / 1024.0);
    }

    public async Task BroadcastSimulationEndedAsync(CancellationToken ct)
    {
        await WriteManifestAsync(live: false, ct);
        await hub.Clients.Group(_scenario).SendAsync("SimulationEnded", ct);
        logger.LogInformation(
            "Simulation ended — {Count} frames written to '{Dir}'", _frameNames.Count, _scenarioDir);
    }

    // ── Palette ───────────────────────────────────────────────────────────────

    /// <summary>
    /// Resolve the palette to broadcast: the InitAgent_Layer message palette takes
    /// precedence (single source of truth across runs), then color_palette.json on
    /// disk, then hardcoded defaults. Mirrors python/visualizer/palette.py resolve_palette.
    /// </summary>
    private (string[] colors, string[] labels) ResolvePalette(ColorPalette? messagePalette)
    {
        if (messagePalette is not null)
        {
            logger.LogDebug("Using color palette from InitAgent_Layer message ({N} states)", messagePalette.Entries.Count);
            return (messagePalette.ColorStrings(), messagePalette.Labels());
        }

        return ReadPaletteFromFile();
    }

    private (string[] colors, string[] labels) ReadPaletteFromFile()
    {
        var palettePath = Path.Combine(_terrainBasePath, "color_palette.json");
        if (!File.Exists(palettePath))
        {
            logger.LogDebug("color_palette.json not found at '{Path}', using defaults", palettePath);
            return (DefaultStateColors, DefaultStateLabels);
        }

        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(palettePath));
            var root = doc.RootElement;

            // Prefer x3d.state_colors (float RGB arrays)
            if (root.TryGetProperty("x3d", out var x3d)
                && x3d.TryGetProperty("state_colors", out var rawColors)
                && rawColors.ValueKind == JsonValueKind.Array)
            {
                var colors = rawColors.EnumerateArray()
                    .Select(c =>
                    {
                        var arr = c.EnumerateArray().ToArray();
                        return $"{arr[0].GetDouble():F2} {arr[1].GetDouble():F2} {arr[2].GetDouble():F2}";
                    })
                    .ToArray();
                var labels = DefaultStateLabels[..Math.Min(colors.Length, DefaultStateLabels.Length)];
                logger.LogDebug("Loaded palette from x3d.state_colors ({N} states)", colors.Length);
                return (colors, labels);
            }

            // Fall back to layers.flood_risk (0-255 RGBA + label, sorted by value)
            if (root.TryGetProperty("layers", out var layers)
                && layers.TryGetProperty("flood_risk", out var floodRisk)
                && floodRisk.ValueKind == JsonValueKind.Array)
            {
                var entries = floodRisk.EnumerateArray()
                    .OrderBy(e => e.GetProperty("value").GetInt32())
                    .ToArray();

                var colors = entries.Select(e =>
                {
                    var rgba = e.GetProperty("rgba").EnumerateArray().ToArray();
                    return $"{rgba[0].GetInt32() / 255.0:F2} {rgba[1].GetInt32() / 255.0:F2} {rgba[2].GetInt32() / 255.0:F2}";
                }).ToArray();

                var labels = entries.Select(e => e.GetProperty("label").GetString() ?? "").ToArray();

                logger.LogDebug("Loaded palette from layers.flood_risk ({N} states)", colors.Length);
                return (colors, labels);
            }
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to parse color_palette.json — using defaults");
        }

        return (DefaultStateColors, DefaultStateLabels);
    }

    // ── PNG encoding ──────────────────────────────────────────────────────────

    private static (byte[] png, float minH, float maxH) EncodeTerrain(GridMeta meta)
    {
        var heights = meta.TerrainHeights ?? new float[meta.Rows * meta.Cols];

        float minH = float.MaxValue, maxH = float.MinValue;
        foreach (var h in heights)
        {
            if (h > Nodata) { minH = MathF.Min(minH, h); maxH = MathF.Max(maxH, h); }
        }
        if (minH >= maxH || minH == float.MaxValue) { minH = 0f; maxH = 1f; }

        using var img = new Image<L8>(meta.Cols, meta.Rows);
        for (int r = 0; r < meta.Rows; r++)
            for (int c = 0; c < meta.Cols; c++)
            {
                var h = heights[r * meta.Cols + c];
                float norm = h > Nodata
                    ? Math.Clamp((h - minH) / (maxH - minH), 0f, 1f)
                    : 0f;
                img[c, r] = new L8((byte)(norm * 255));
            }

        using var ms = new MemoryStream();
        img.SaveAsPng(ms);
        return (ms.ToArray(), minH, maxH);
    }

    private static byte[] EncodeFlood(FloodState[] paletteGrid, int rows, int cols)
    {
        using var img = new Image<L8>(cols, rows);
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++)
                img[c, r] = new L8((byte)paletteGrid[r * cols + c]);

        using var ms = new MemoryStream();
        img.SaveAsPng(ms);
        return ms.ToArray();
    }

    // ── Manifest ──────────────────────────────────────────────────────────────

    private async Task WriteManifestAsync(bool live, CancellationToken ct)
    {
        var obj  = new { frames = _frameNames.ToArray(), live };
        var json = JsonSerializer.Serialize(obj, new JsonSerializerOptions { WriteIndented = true });
        await File.WriteAllTextAsync(Path.Combine(_floodDir, "manifest.json"), json, ct);
    }

    // ── player.html generation ────────────────────────────────────────────────

    private static string GeneratePlayerHtml(
        GridMeta meta, float minH, float maxH,
        string terrainB64, string[] stateColors, string[] stateLabels, string[] frameNames,
        string scenario = "")
    {
        float mapW = meta.Cols * meta.CellSizeM;
        float mapD = meta.Rows * meta.CellSizeM;
        float camH = MathF.Max(maxH * 3.0f, mapD * 0.3f);

        string ovPos  = $"{mapW / 2:F0} {camH:F0} {mapD + mapD * 0.4f:F0}";
        string cenPos = $"{mapW / 2:F0} {camH * 2:F0} {mapD / 2:F0}";
        string latPos = $"{mapW / 2:F0} {camH * 0.35f:F0} {mapD * 2.2f:F0}";

        var configObj = new
        {
            pngCols    = meta.Cols,
            pngRows    = meta.Rows,
            pngRes     = meta.CellSizeM,
            mapW,
            mapD,
            minH,
            maxH,
            stateColors,
            floodFrames = frameNames,
            terrainSrc  = $"data:image/png;base64,{terrainB64}",
            scenario,
        };
        var configJson = JsonSerializer.Serialize(configObj);

        int nFrames   = frameNames.Length;
        int sliderMax = Math.Max(0, nFrames - 1);

        // Generate one checkbox row per non-dry state (index 1 onwards)
        var sidebarRows = new StringBuilder();
        for (int i = 1; i < stateLabels.Length; i++)
        {
            sidebarRows.AppendLine(
                $"""          <label class="layer-row"><input id="layerState{i}" type="checkbox" checked/><span class="swatch" data-state="{i}"></span><span>{stateLabels[i]}</span></label>""");
        }

        return $$"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8"/>
              <title>DanaSim Heightmap Viewer</title>
              <script src="https://cdn.jsdelivr.net/npm/x_ite@12.1.4/dist/x_ite.min.js"></script>
              <script src="/player-assets/js/vendor/signalr.min.js"></script>
              <link rel="stylesheet" href="/player-assets/css/style.css"/>
            </head>
            <body>
              <!-- rows={{meta.Rows}} cols={{meta.Cols}} cell_size={{meta.CellSizeM:F4}}m frames={{nFrames}} -->
              <div id="loading">Decoding heightmap and building 3D terrain&#8230;</div>
              <div id="viewport">
                <x3d-canvas>
                  <x3d>
                    <scene>
                      <background skyColor="0.53 0.81 0.98"></background>
                      <Viewpoint DEF="VP_Overview" position="{{ovPos}}"  orientation="1 0 0 -0.5"    description="Overview"></Viewpoint>
                      <Viewpoint DEF="VP_Cenital"  position="{{cenPos}}" orientation="1 0 0 -1.5708" description="Cenital"></Viewpoint>
                      <Viewpoint DEF="VP_Lateral"  position="{{latPos}}" orientation="0 0 0 1"       description="Lateral"></Viewpoint>
                      <Viewpoint DEF="VP_Zone" position="0 1 1" orientation="1 0 0 -0.5" description="Zona seleccionada"></Viewpoint>
                      <NavigationInfo type='"EXAMINE" "ANY"' speed="500"></NavigationInfo>
                      <Transform DEF="ZScale" scale="1 1 1">
                        <Group id="terrain_container"></Group>
                      </Transform>
                    </scene>
                  </x3d>
                </x3d-canvas>

                <aside id="sidebar" aria-label="Panel de control">
                  <button id="sidebarToggle" type="button" aria-label="Mostrar/ocultar panel">&#9776;</button>
                  <div class="sidebar-content">
                    <h2>Capas</h2>
                    <label class="layer-row"><input id="layerTerrain" type="checkbox" checked/><span>Terreno</span></label>
                    <label class="layer-row"><input id="layerWater"   type="checkbox" checked/><span>Agua</span></label>
                    <fieldset class="state-group">
                      <legend>Profundidad</legend>
            {{sidebarRows}}        </fieldset>
                    <h2>C&#225;mara</h2>
                    <div class="camera-presets">
                      <button class="cam-btn" data-vp="VP_Overview" title="Vista perspectiva (P)">Perspectiva</button>
                      <button class="cam-btn" data-vp="VP_Cenital"  title="Vista cenital (C)">Cenital</button>
                      <button class="cam-btn" data-vp="VP_Lateral"  title="Vista lateral (L)">Lateral</button>
                      <button class="cam-btn" id="camReset"         title="Resetear c&#225;mara (R)">&#8635; Reset</button>
                    </div>
                    <div class="slider-row">
                      <label for="zScale">Exageraci&#243;n Z</label>
                      <input id="zScale" type="range" min="1" max="10" value="1" step="0.5"/>
                      <span id="zScaleVal">1&#215;</span>
                    </div>
                    <p class="shortcuts-hint">
                      Atajos: <kbd>C</kbd> cenital &nbsp;&#183;&nbsp; <kbd>P</kbd> perspectiva
                      &nbsp;&#183;&nbsp; <kbd>L</kbd> lateral &nbsp;&#183;&nbsp; <kbd>R</kbd> reset
                      &nbsp;&#183;&nbsp; <kbd>Space</kbd> play &nbsp;&#183;&nbsp; <kbd>&#8592;</kbd><kbd>&#8594;</kbd> frames
                    </p>
                    <h2>Minimapa</h2>
                    <div class="minimap-wrap">
                      <canvas id="minimapCanvas" title="Arrastra para seleccionar zona"></canvas>
                      <button id="minimapReset" class="cam-btn" style="margin-top:6px;width:100%">&#8635; Vista completa</button>
                    </div>
                    <h2>Leyenda</h2>
                    <div id="legend"></div>
                  </div>
                </aside>
              </div>

              <div id="controls">
                <button id="prevBtn">&#9664;</button>
                <button id="playBtn">&#9654; Play</button>
                <button id="nextBtn">&#9654;&#9654;</button>
                <input id="slider" type="range" min="0" max="{{sliderMax}}" value="0"/>
                <span id="frame-label">Frame 0 / {{sliderMax}}</span>
                <label>Speed <input id="speed" type="range" min="100" max="2000" value="800" step="100"/></label>
                <button id="followBtn" title="Saltar al &#250;ltimo frame al llegar uno nuevo">&#128205; Seguir</button>
                <span id="status">Loading terrain&#8230;</span>
              </div>

              <script>
            window.__CONFIG__ = {{configJson}};
              </script>
              <script type="module" src="/player-assets/js/app.js"></script>
            </body>
            </html>
            """;
    }
}
