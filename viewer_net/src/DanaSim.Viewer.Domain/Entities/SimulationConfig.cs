namespace DanaSim.Viewer.Domain.Entities;

public sealed class SimulationConfig
{
    public int SizeX { get; private set; }
    public int SizeY { get; private set; }
    public float CellResolutionM { get; private set; }
    public string SimStartTime { get; private set; } = string.Empty;
    public float TimeStepS { get; private set; }
    public double GeoLat { get; private set; }
    public double GeoLon { get; private set; }
    public bool IsConfigured { get; private set; }

    public void Apply(
        int sizeX, int sizeY, float cellResolutionM,
        string simStartTime, float timeStepS,
        double geoLat, double geoLon)
    {
        if (sizeX <= 0 || sizeY <= 0)
            throw new ArgumentException($"Invalid grid dimensions: {sizeX}x{sizeY}");

        SizeX = sizeX;
        SizeY = sizeY;
        CellResolutionM = cellResolutionM;
        SimStartTime = simStartTime;
        TimeStepS = timeStepS;
        GeoLat = geoLat;
        GeoLon = geoLon;
        IsConfigured = true;
    }
}
