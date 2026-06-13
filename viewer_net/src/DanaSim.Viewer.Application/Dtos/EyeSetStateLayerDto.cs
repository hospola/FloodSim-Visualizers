using System.Text.Json;
using System.Text.Json.Serialization;

namespace DanaSim.Viewer.Application.Dtos;

public sealed class EyeSetStateLayerDto
{
    [JsonPropertyName("id")]      public string Id      { get; set; } = string.Empty;
    [JsonPropertyName("changes")] public ChangesSection Changes { get; set; } = new();

    public sealed class ChangesSection
    {
        [JsonPropertyName("cells")]
        public Dictionary<string, CellStateDto> Cells { get; set; } = new();
    }

    public sealed class CellStateDto
    {
        [JsonPropertyName("state")]
        [JsonConverter(typeof(FloodStateValueConverter))]
        public int State { get; set; }

        [JsonPropertyName("height")] public float Height { get; set; }
    }

    /// <summary>
    /// Accepts state as an integer (real simulator) or a string name (test publisher / legacy).
    /// </summary>
    private sealed class FloodStateValueConverter : JsonConverter<int>
    {
        private static readonly Dictionary<string, int> StringMap = new(StringComparer.OrdinalIgnoreCase)
        {
            ["DRY"]          = 0,
            ["VERY_SHALLOW"] = 1, ["RISK1"] = 1,
            ["LOW_DEPTH"]    = 2, ["RISK2"] = 2,
            ["MEDIUM_DEPTH"] = 3, ["RISK3"] = 3,
            ["HIGH_DEPTH"]   = 4, ["RISK4"] = 4,
            ["FLOODED"]      = 5, ["RISK5"] = 5,
            ["OBSTACLE"]     = 6,
        };

        public override int Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType == JsonTokenType.Number)
                return reader.GetInt32();

            if (reader.TokenType == JsonTokenType.String)
            {
                var s = reader.GetString() ?? "";
                return StringMap.TryGetValue(s, out var v) ? v : 0;
            }

            return 0;
        }

        public override void Write(Utf8JsonWriter writer, int value, JsonSerializerOptions options)
            => writer.WriteNumberValue(value);
    }
}
