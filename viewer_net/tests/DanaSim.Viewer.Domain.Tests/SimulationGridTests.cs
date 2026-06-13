using DanaSim.Viewer.Domain.Entities;
using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.ValueObjects;
using FluentAssertions;

namespace DanaSim.Viewer.Domain.Tests;

public class SimulationGridTests
{
    [Fact]
    public void Resize_SetsRowsAndCols()
    {
        var grid = new SimulationGrid();
        grid.Resize(800, 1200);
        grid.Rows.Should().Be(800);
        grid.Cols.Should().Be(1200);
        grid.TotalCells.Should().Be(960_000);
    }

    [Theory]
    [InlineData(0, 100)]
    [InlineData(100, 0)]
    [InlineData(-1, 100)]
    public void Resize_InvalidDimensions_Throws(int rows, int cols)
    {
        var grid = new SimulationGrid();
        var act = () => grid.Resize(rows, cols);
        act.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void ApplyBulkChanges_UpdatesStateAndDepth()
    {
        var grid = new SimulationGrid();
        grid.Resize(10, 10);

        var changes = new List<CellChange>
        {
            new(5,  FloodState.Risk3, 1.2f),
            new(99, FloodState.Risk5, 3.0f),
        };

        grid.ApplyBulkChanges(changes);

        grid.GetState(5).Should().Be(FloodState.Risk3);
        grid.GetWaterDepth(5).Should().BeApproximately(1.2f, 0.001f);
        grid.GetState(99).Should().Be(FloodState.Risk5);
        grid.HasNewData.Should().BeTrue();
    }

    [Fact]
    public void ApplyBulkChanges_OutOfBoundsIndex_IsIgnored()
    {
        var grid = new SimulationGrid();
        grid.Resize(5, 5);

        var changes = new List<CellChange> { new(999, FloodState.Risk1, 0.5f) };
        var act = () => grid.ApplyBulkChanges(changes);

        act.Should().NotThrow();
        grid.HasNewData.Should().BeFalse();
    }

    [Fact]
    public void BuildFrameData_ReturnsIsolatedCopies()
    {
        var grid = new SimulationGrid();
        grid.Resize(2, 2);
        grid.ApplyBulkChanges([new(0, FloodState.Risk2, 0.8f)]);

        var frame = grid.BuildFrameData("2024-10-29T10:00:00");

        // Mutating the grid after snapshot must not affect the frame
        grid.ApplyBulkChanges([new(0, FloodState.Risk5, 5.0f)]);

        frame.PaletteGrid[0].Should().Be(FloodState.Risk2);
        frame.WaterDepths[0].Should().BeApproximately(0.8f, 0.001f);
        frame.SimulationTime.Should().Be("2024-10-29T10:00:00");
    }

    [Fact]
    public void ConsumeData_ClearsHasNewData()
    {
        var grid = new SimulationGrid();
        grid.Resize(2, 2);
        grid.ApplyBulkChanges([new(0, FloodState.Risk1, 0.1f)]);
        grid.HasNewData.Should().BeTrue();

        grid.ConsumeData();
        grid.HasNewData.Should().BeFalse();
    }

    [Fact]
    public void SetTerrainHeights_WrongLength_Throws()
    {
        var grid = new SimulationGrid();
        grid.Resize(4, 4);
        var act = () => grid.SetTerrainHeights(new float[5]);
        act.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void SetTerrainHeights_CorrectLength_Stores()
    {
        var grid = new SimulationGrid();
        grid.Resize(2, 3);
        var heights = new float[] { 1, 2, 3, 4, 5, 6 };
        grid.SetTerrainHeights(heights);
        grid.TerrainHeights.Should().BeEquivalentTo(heights);
    }
}
