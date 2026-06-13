using System.Text.Json.Serialization;

namespace DanaSim.Viewer.Application.Dtos;

public sealed class FrameStartDto
{
    [JsonPropertyName("total_chunks")] public int TotalChunks { get; set; }
    [JsonPropertyName("chunks_per_batch")] public int ChunksPerBatch { get; set; }
}
