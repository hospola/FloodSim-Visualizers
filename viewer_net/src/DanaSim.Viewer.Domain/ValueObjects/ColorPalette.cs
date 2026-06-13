namespace DanaSim.Viewer.Domain.ValueObjects;

/// <summary>
/// A single flood-risk level: numeric value, label and color (hex + RGBA).
/// Mirrors python/visualizer/palette.py PaletteEntry.
/// </summary>
public sealed record ColorPaletteEntry(int Value, string Label, string Hex, byte[] Rgba);

/// <summary>
/// Centralized flood-risk color palette, resolved once per run from (in order
/// of preference) the InitAgent_Layer MQTT message, a color_palette.json file,
/// or hardcoded defaults. Every consumer (web player config, future renderers)
/// derives its representation from this single object.
/// Mirrors python/visualizer/palette.py Palette.
/// </summary>
public sealed class ColorPalette
{
    public IReadOnlyList<ColorPaletteEntry> Entries { get; }

    public ColorPalette(IEnumerable<ColorPaletteEntry> entries)
    {
        Entries = entries.OrderBy(e => e.Value).ToArray();
    }

    /// <summary>"r g b" floating-point strings (0.0-1.0), for the web player config.</summary>
    public string[] ColorStrings() =>
        Entries.Select(e => $"{e.Rgba[0] / 255.0:F2} {e.Rgba[1] / 255.0:F2} {e.Rgba[2] / 255.0:F2}").ToArray();

    public string[] Labels() => Entries.Select(e => e.Label).ToArray();

    public static ColorPalette Default { get; } = new([
        new(0, "Seco",                "#9E8050", [158, 128,  80, 255]),
        new(1, "Muy somero",          "#99E6FF", [153, 230, 255, 255]),
        new(2, "Profundidad baja",    "#3399E6", [ 51, 153, 230, 255]),
        new(3, "Profundidad media",   "#1A66CC", [ 26, 102, 204, 255]),
        new(4, "Profundidad alta",    "#0D33B3", [ 13,  51, 179, 255]),
        new(5, "Profundidad extrema", "#1A1A99", [ 26,  26, 153, 255]),
    ]);
}
