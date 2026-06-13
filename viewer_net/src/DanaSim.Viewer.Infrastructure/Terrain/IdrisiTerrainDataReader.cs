using System.Diagnostics;
using DanaSim.Viewer.Application.Ports;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace DanaSim.Viewer.Infrastructure.Terrain;

public sealed class TerrainOptions
{
    /// <summary>
    /// Base directory where terrain data files are stored on the server.
    /// Leave empty to use the "data" folder bundled next to the executable
    /// (see IdrisiTerrainDataReader) — e.g. the installer's "full" variant.
    /// </summary>
    public string BasePath { get; set; } = "";
}

/// <summary>
/// Reads terrain height data from IDRISI ASCII raster files (.doc + .img).
/// Mirrors python/visualizer/idrisi_io.py IdrisiIO.read().
///
/// File format:
///   {BasePath}/{dataPath}/{dataFilename}.doc  — key:value metadata (rows, columns, data type)
///   {BasePath}/{dataPath}/{dataFilename}.img  — space-separated float32 values, row by row
/// </summary>
public sealed class IdrisiTerrainDataReader(
    IOptions<TerrainOptions> options,
    ILogger<IdrisiTerrainDataReader> logger) : ITerrainDataReader
{
    /// <summary>
    /// An empty configured BasePath resolves to "{app directory}/data" rather than
    /// the process's current working directory — the working directory varies by
    /// launch method (run.sh/run.bat vs. IIS) and isn't reliably the install folder,
    /// whereas AppContext.BaseDirectory always points at the published binaries.
    /// </summary>
    private readonly string _basePath = string.IsNullOrWhiteSpace(options.Value.BasePath)
        ? Path.Combine(AppContext.BaseDirectory, "data")
        : options.Value.BasePath;

    public async Task<float[]?> ReadHeightsAsync(
        string dataPath, string dataFilename, CancellationToken ct = default)
    {
        var folder = Path.Combine(_basePath, dataPath);
        var docPath = Path.Combine(folder, $"{dataFilename}.doc");
        var imgPath = Path.Combine(folder, $"{dataFilename}.img");

        if (!File.Exists(docPath))
        {
            logger.LogWarning("IDRISI metadata not found: {Path}", docPath);
            return null;
        }

        if (!File.Exists(imgPath))
        {
            logger.LogWarning("IDRISI data not found: {Path}", imgPath);
            return null;
        }

        try
        {
            var total = Stopwatch.StartNew();

            var docSw = Stopwatch.StartNew();
            var (rows, cols) = await ReadDocMetadataAsync(docPath, ct);
            docSw.Stop();

            var imgSw = Stopwatch.StartNew();
            var heights = await ReadImgDataAsync(imgPath, rows * cols, ct);
            imgSw.Stop();

            total.Stop();
            logger.LogInformation(
                "[PERF] Loaded terrain '{File}' — {Rows}x{Cols} ({Total} cells) in {TotalMs}ms (doc={DocMs}ms, img={ImgMs}ms)",
                dataFilename, rows, cols, heights.Length,
                total.ElapsedMilliseconds, docSw.ElapsedMilliseconds, imgSw.ElapsedMilliseconds);

            return heights;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to read IDRISI terrain file '{File}'", dataFilename);
            return null;
        }
    }

    private static async Task<(int rows, int cols)> ReadDocMetadataAsync(
        string docPath, CancellationToken ct)
    {
        var metadata = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        await foreach (var line in File.ReadLinesAsync(docPath, ct))
        {
            var idx = line.IndexOf(':');
            if (idx < 0) continue;
            metadata[line[..idx].Trim()] = line[(idx + 1)..].Trim();
        }

        var rows = int.Parse(metadata["rows"]);
        var cols = int.Parse(metadata["columns"]);
        return (rows, cols);
    }

    private static async Task<float[]> ReadImgDataAsync(
        string imgPath, int expectedCount, CancellationToken ct)
    {
        var result = new List<float>(expectedCount);

        await foreach (var line in File.ReadLinesAsync(imgPath, ct))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;

            foreach (var token in line.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            {
                if (float.TryParse(token,
                    System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture,
                    out var val))
                {
                    result.Add(val);
                }
            }
        }

        return [.. result];
    }
}
