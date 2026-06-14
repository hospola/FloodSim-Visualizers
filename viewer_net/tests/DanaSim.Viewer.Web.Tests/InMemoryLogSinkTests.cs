using DanaSim.Viewer.Web.Logging;
using FluentAssertions;
using Serilog.Events;
using Serilog.Parsing;

namespace DanaSim.Viewer.Web.Tests;

public class InMemoryLogSinkTests
{
    private static LogEvent CreateEvent(
        LogEventLevel level = LogEventLevel.Information,
        string message = "hello",
        string? sourceContext = null,
        Exception? exception = null)
    {
        var properties = new List<LogEventProperty>();
        if (sourceContext is not null)
            properties.Add(new LogEventProperty("SourceContext", new ScalarValue(sourceContext)));

        return new LogEvent(
            DateTimeOffset.UtcNow,
            level,
            exception,
            new MessageTemplate(message, [new TextToken(message)]),
            properties);
    }

    [Fact]
    public void Emit_AddsEntry_RetrievableViaSince()
    {
        var sink = new InMemoryLogSink();

        sink.Emit(CreateEvent(message: "first"));

        var (lastIndex, entries) = sink.Since(0);

        lastIndex.Should().Be(1);
        entries.Should().ContainSingle();
        entries[0].Message.Should().Be("first");
    }

    [Fact]
    public void Since_WithAfterIndexEqualToTotal_ReturnsNoEntries()
    {
        var sink = new InMemoryLogSink();
        sink.Emit(CreateEvent());

        var (lastIndex, entries) = sink.Since(1);

        lastIndex.Should().Be(1);
        entries.Should().BeEmpty();
    }

    [Fact]
    public void Since_ReturnsOnlyEntriesAfterGivenIndex()
    {
        var sink = new InMemoryLogSink();
        sink.Emit(CreateEvent(message: "one"));
        sink.Emit(CreateEvent(message: "two"));
        sink.Emit(CreateEvent(message: "three"));

        var (lastIndex, entries) = sink.Since(1);

        lastIndex.Should().Be(3);
        entries.Should().HaveCount(2);
        entries[0].Message.Should().Be("two");
        entries[1].Message.Should().Be("three");
    }

    [Fact]
    public void Emit_BeyondCapacity_DropsOldestEntries()
    {
        var sink = new InMemoryLogSink();

        for (var i = 0; i < 510; i++)
            sink.Emit(CreateEvent(message: $"msg-{i}"));

        sink.Count.Should().Be(500);

        var (lastIndex, _) = sink.Since(0);
        lastIndex.Should().Be(510);

        var (_, entries) = sink.Since(509);
        entries.Should().ContainSingle();
        entries[0].Message.Should().Be("msg-509");
    }

    [Theory]
    [InlineData(LogEventLevel.Verbose, "VRB")]
    [InlineData(LogEventLevel.Debug, "DBG")]
    [InlineData(LogEventLevel.Information, "INF")]
    [InlineData(LogEventLevel.Warning, "WRN")]
    [InlineData(LogEventLevel.Error, "ERR")]
    [InlineData(LogEventLevel.Fatal, "FTL")]
    public void Emit_MapsLevel_ToShortCode(LogEventLevel level, string expected)
    {
        var sink = new InMemoryLogSink();

        sink.Emit(CreateEvent(level: level));

        var (_, entries) = sink.Since(0);
        entries[0].Level.Should().Be(expected);
    }

    [Fact]
    public void Emit_WithSourceContext_UsesLastSegmentAsSource()
    {
        var sink = new InMemoryLogSink();

        sink.Emit(CreateEvent(sourceContext: "DanaSim.Viewer.Web.Controllers.ApiController"));

        var (_, entries) = sink.Since(0);
        entries[0].Source.Should().Be("ApiController");
    }

    [Fact]
    public void Emit_WithoutSourceContext_UsesEmptySource()
    {
        var sink = new InMemoryLogSink();

        sink.Emit(CreateEvent());

        var (_, entries) = sink.Since(0);
        entries[0].Source.Should().Be("");
    }

    [Fact]
    public void Emit_WithException_CapturesExceptionMessage()
    {
        var sink = new InMemoryLogSink();

        sink.Emit(CreateEvent(exception: new InvalidOperationException("boom")));

        var (_, entries) = sink.Since(0);
        entries[0].Exception.Should().Be("boom");
    }
}
