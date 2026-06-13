using Serilog.Core;
using Serilog.Events;

namespace DanaSim.Viewer.Web.Logging;

public sealed record LogEntry(
    string Timestamp,
    string Level,
    string Source,
    string Message,
    string? Exception);

public sealed class InMemoryLogSink : ILogEventSink
{
    private const int Capacity = 500;
    private readonly object _lock = new();
    private readonly List<LogEntry> _entries = new(Capacity + 1);
    private int _totalEmitted;

    public void Emit(LogEvent logEvent)
    {
        var entry = new LogEntry(
            Timestamp: logEvent.Timestamp.ToString("HH:mm:ss"),
            Level:     MapLevel(logEvent.Level),
            Source:    GetSource(logEvent),
            Message:   logEvent.RenderMessage(),
            Exception: logEvent.Exception?.Message);

        lock (_lock)
        {
            _entries.Add(entry);
            if (_entries.Count > Capacity)
                _entries.RemoveAt(0);
            _totalEmitted++;
        }
    }

    /// <summary>
    /// Returns entries added after <paramref name="afterIndex"/> together with
    /// the new lastIndex the caller should pass on the next poll.
    /// </summary>
    public (int lastIndex, IReadOnlyList<LogEntry> entries) Since(int afterIndex)
    {
        lock (_lock)
        {
            int total = _totalEmitted;
            if (afterIndex >= total)
                return (total, Array.Empty<LogEntry>());

            // oldest entry in the buffer sits at absolute index (total - count)
            int bufferStart  = total - _entries.Count;
            int fromOffset   = Math.Max(0, afterIndex - bufferStart);
            return (total, _entries.Skip(fromOffset).ToArray());
        }
    }

    public int Count { get { lock (_lock) return _entries.Count; } }

    private static string MapLevel(LogEventLevel level) => level switch
    {
        LogEventLevel.Verbose     => "VRB",
        LogEventLevel.Debug       => "DBG",
        LogEventLevel.Information => "INF",
        LogEventLevel.Warning     => "WRN",
        LogEventLevel.Error       => "ERR",
        LogEventLevel.Fatal       => "FTL",
        _                         => "INF",
    };

    private static string GetSource(LogEvent logEvent)
    {
        if (logEvent.Properties.TryGetValue("SourceContext", out var prop)
            && prop is ScalarValue { Value: string ctx })
        {
            var dot = ctx.LastIndexOf('.');
            return dot >= 0 ? ctx[(dot + 1)..] : ctx;
        }
        return "";
    }
}
