using System.Text.Json.Serialization;

namespace DanaSim.Viewer.Application.Dtos;

public sealed class InitAgentLayerDto
{
    [JsonPropertyName("id")] public string Id { get; set; } = string.Empty;
    [JsonPropertyName("data_path")] public string DataPath { get; set; } = string.Empty;
    [JsonPropertyName("data_filename")] public string DataFilename { get; set; } = string.Empty;
    [JsonPropertyName("color_palette")] public List<ColorPaletteEntryDto>? ColorPalette { get; set; }
}

public sealed class ColorPaletteEntryDto
{
    [JsonPropertyName("value")] public int Value { get; set; }
    [JsonPropertyName("label")] public string Label { get; set; } = string.Empty;
    [JsonPropertyName("hex")] public string Hex { get; set; } = string.Empty;
    // The simulator sends `rgba` as a JSON array of integers (e.g. [158,128,80,255]),
    // not a Base64 string — System.Text.Json's default byte[] converter only accepts
    // the latter, so this must be int[] and converted to byte[] when consumed.
    [JsonPropertyName("rgba")] public int[] Rgba { get; set; } = [];
}
