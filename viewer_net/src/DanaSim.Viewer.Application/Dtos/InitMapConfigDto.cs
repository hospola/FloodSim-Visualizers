using System.Text.Json.Serialization;

namespace DanaSim.Viewer.Application.Dtos;

public sealed class InitMapConfigDto
{
    [JsonPropertyName("map")]
    public MapSection Map { get; set; } = new();

    [JsonPropertyName("metadata")]
    public MetadataSection Metadata { get; set; } = new();

    [JsonPropertyName("georeference")]
    public GeoreferenceSection Georeference { get; set; } = new();

    public sealed class MapSection
    {
        [JsonPropertyName("size_x")] public int SizeX { get; set; }
        [JsonPropertyName("size_y")] public int SizeY { get; set; }
        [JsonPropertyName("cell_resolution_m")] public float CellResolutionM { get; set; }
    }

    public sealed class MetadataSection
    {
        [JsonPropertyName("sim_start_time")] public string SimStartTime { get; set; } = string.Empty;
        [JsonPropertyName("time_step_s")] public float TimeStepS { get; set; }
    }

    public sealed class GeoreferenceSection
    {
        [JsonPropertyName("lat")] public double Lat { get; set; }
        [JsonPropertyName("lon")] public double Lon { get; set; }
    }
}
