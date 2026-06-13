namespace DanaSim.Viewer.Application.Services;

public sealed record SimulationStatus
{
    public string  ConnectionStatus { get; init; } = "Disconnected";
    public string  Phase            { get; init; } = "Idle";
    public int     FrameCount       { get; init; }
    public string  SimulationTime   { get; init; } = "";
    public string  Scenario         { get; init; } = "";
    public string? ActivePlayerUrl  { get; init; }
    public string? LastError        { get; init; }
}

public sealed class SimulationStatusService
{
    // volatile + immutable record: reads never block and always get a consistent snapshot
    private volatile SimulationStatus _current = new();

    public SimulationStatus Get() => _current;

    public void SetConnection(string status, string? error = null) =>
        _current = _current with { ConnectionStatus = status, LastError = error };

    public void SetPhase(string phase) =>
        _current = _current with { Phase = phase };

    /// <summary>
    /// Clears per-run state (frame count, time, player URL, errors).
    /// Optionally updates the scenario name. Connection status is preserved.
    /// </summary>
    public void Reset(string? scenario = null) =>
        _current = _current with
        {
            Phase           = "Idle",
            Scenario        = scenario ?? _current.Scenario,
            FrameCount      = 0,
            SimulationTime  = "",
            ActivePlayerUrl = null,
            LastError       = null,
        };

    public void RecordFrame(string simTime, string playerUrl) =>
        _current = _current with
        {
            FrameCount      = _current.FrameCount + 1,
            SimulationTime  = simTime,
            ActivePlayerUrl = playerUrl,
        };
}
