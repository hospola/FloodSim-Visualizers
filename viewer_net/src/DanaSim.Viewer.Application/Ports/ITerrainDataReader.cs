namespace DanaSim.Viewer.Application.Ports;

/// <summary>
/// Outbound port: reads terrain height data from a local IDRISI file.
/// Implemented in the Infrastructure layer.
/// </summary>
public interface ITerrainDataReader
{
    /// <summary>
    /// Returns a flat float array of height values (length = rows * cols),
    /// or null if the file cannot be read.
    /// </summary>
    Task<float[]?> ReadHeightsAsync(string dataPath, string dataFilename, CancellationToken ct = default);
}
