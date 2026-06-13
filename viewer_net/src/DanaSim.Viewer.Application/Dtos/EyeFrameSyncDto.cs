using System.Text.Json.Serialization;

namespace DanaSim.Viewer.Application.Dtos;

public sealed class EyeFrameSyncDto
{
    [JsonPropertyName("simulation_time")] public string SimulationTime { get; set; } = string.Empty;
}
