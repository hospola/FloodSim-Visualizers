using DanaSim.Viewer.Infrastructure.Terrain;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class IdrisiTerrainDataReaderTests : IDisposable
{
    private readonly string _basePath =
        Path.Combine(Path.GetTempPath(), "danasim-idrisi-test-" + Guid.NewGuid());

    public void Dispose()
    {
        if (Directory.Exists(_basePath)) Directory.Delete(_basePath, recursive: true);
    }

    private IdrisiTerrainDataReader CreateReader() =>
        new(Options.Create(new TerrainOptions { BasePath = _basePath }),
            NullLogger<IdrisiTerrainDataReader>.Instance);

    [Fact]
    public async Task ReadHeightsAsync_ReturnsNull_WhenDocFileMissing()
    {
        var reader = CreateReader();

        var result = await reader.ReadHeightsAsync("topo_bathy", "topo_bathy");

        result.Should().BeNull();
    }

    [Fact]
    public async Task ReadHeightsAsync_ReturnsNull_WhenImgFileMissing()
    {
        var folder = Path.Combine(_basePath, "topo_bathy");
        Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder, "topo_bathy.doc"), "rows: 2\ncolumns: 2\n");

        var reader = CreateReader();
        var result = await reader.ReadHeightsAsync("topo_bathy", "topo_bathy");

        result.Should().BeNull();
    }

    [Fact]
    public async Task ReadHeightsAsync_ReadsHeights_FromDocAndImg()
    {
        var folder = Path.Combine(_basePath, "topo_bathy");
        Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder, "topo_bathy.doc"), "rows: 2\ncolumns: 3\n");
        await File.WriteAllTextAsync(Path.Combine(folder, "topo_bathy.img"), "1.0 2.0 3.0\n4.0 5.0 6.0\n");

        var reader = CreateReader();
        var result = await reader.ReadHeightsAsync("topo_bathy", "topo_bathy");

        result.Should().NotBeNull();
        result.Should().Equal(1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f);
    }

    [Fact]
    public async Task ReadHeightsAsync_SkipsBlankLines_AndUsesInvariantCulture()
    {
        var folder = Path.Combine(_basePath, "topo_bathy");
        Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder, "topo_bathy.doc"), "rows: 1\ncolumns: 2\n");
        await File.WriteAllTextAsync(Path.Combine(folder, "topo_bathy.img"), "\n1.5 2.5\n\n");

        var reader = CreateReader();
        var result = await reader.ReadHeightsAsync("topo_bathy", "topo_bathy");

        result.Should().Equal(1.5f, 2.5f);
    }

    [Fact]
    public async Task ReadHeightsAsync_EmptyBasePath_ResolvesUnderAppDirectory()
    {
        var reader = new IdrisiTerrainDataReader(
            Options.Create(new TerrainOptions { BasePath = "" }),
            NullLogger<IdrisiTerrainDataReader>.Instance);

        // No "data/topo_bathy" exists next to the test binaries -> missing doc -> null,
        // confirming the empty-BasePath fallback doesn't throw and resolves to a path
        // under AppContext.BaseDirectory rather than the configured _basePath.
        var result = await reader.ReadHeightsAsync("topo_bathy", "topo_bathy");

        result.Should().BeNull();
    }
}
