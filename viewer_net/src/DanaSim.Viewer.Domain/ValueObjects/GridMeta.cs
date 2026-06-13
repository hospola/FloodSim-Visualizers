namespace DanaSim.Viewer.Domain.ValueObjects;

/// <summary>
/// Immutable grid dimensions and spatial metadata, sent to the renderer on Init_EOF.
/// TerrainHeights is a flat array of length Rows*Cols (null until InitAgent_Layer is processed).
/// Palette is the color_palette received via InitAgent_Layer, if the simulator sent one;
/// null means the broadcaster should fall back to a color_palette.json file or defaults
/// (see ISimulationBroadcaster implementations).
/// </summary>
public sealed record GridMeta(
    int Rows,
    int Cols,
    float CellSizeM,
    float[]? TerrainHeights,
    ColorPalette? Palette);
