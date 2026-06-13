using DanaSim.Viewer.Domain.Enums;

namespace DanaSim.Viewer.Domain.ValueObjects;

/// <summary>
/// Snapshot of the grid state for a single render frame.
/// Both arrays are flat with length Rows*Cols.
/// </summary>
public sealed record FrameData(
    FloodState[] PaletteGrid,
    float[] WaterDepths,
    string SimulationTime);
