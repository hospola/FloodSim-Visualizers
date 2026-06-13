using DanaSim.Viewer.Domain.Enums;
using DanaSim.Viewer.Domain.ValueObjects;

namespace DanaSim.Viewer.Domain.Entities;

/// <summary>
/// Aggregate root that owns the full simulation grid state.
/// Mirrors python/visualizer/data_model.py SimulationGrid.
/// </summary>
public sealed class SimulationGrid
{
    private FloodState[] _states;
    private float[] _waterDepths;

    public int Rows { get; private set; }
    public int Cols { get; private set; }
    public float[]? TerrainHeights { get; private set; }
    public bool HasNewData { get; private set; }

    public SimulationGrid()
    {
        Rows = 0;
        Cols = 0;
        _states = [];
        _waterDepths = [];
    }

    public void Resize(int rows, int cols)
    {
        if (rows <= 0 || cols <= 0)
            throw new ArgumentException($"Invalid grid size: {rows}x{cols}");

        Rows = rows;
        Cols = cols;
        _states = new FloodState[rows * cols];
        _waterDepths = new float[rows * cols];
        TerrainHeights = null;
        HasNewData = false;
    }

    public void SetTerrainHeights(float[] heights)
    {
        if (heights.Length != Rows * Cols)
            throw new ArgumentException(
                $"Terrain height array length {heights.Length} does not match grid size {Rows * Cols}");
        TerrainHeights = heights;
    }

    public void ApplyBulkChanges(IReadOnlyList<CellChange> changes)
    {
        bool applied = false;
        foreach (var change in changes)
        {
            if ((uint)change.Index >= (uint)_states.Length)
                continue;

            _states[change.Index] = change.State;
            _waterDepths[change.Index] = change.WaterDepthM;
            applied = true;
        }

        if (applied)
            HasNewData = true;
    }

    public FrameData BuildFrameData(string simulationTime)
    {
        var statesCopy = (FloodState[])_states.Clone();
        var depthsCopy = (float[])_waterDepths.Clone();
        return new FrameData(statesCopy, depthsCopy, simulationTime);
    }

    public void ConsumeData() => HasNewData = false;

    public FloodState GetState(int index) => _states[index];
    public float GetWaterDepth(int index) => _waterDepths[index];
    public int TotalCells => Rows * Cols;
}
