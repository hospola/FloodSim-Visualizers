namespace DanaSim.Viewer.Infrastructure.FileOutput;

public sealed class FileOutputOptions
{
    /// <summary>Root directory where per-scenario output folders are created.</summary>
    public string OutputDir { get; set; } = "outputs/x3d_heightmap";
}
