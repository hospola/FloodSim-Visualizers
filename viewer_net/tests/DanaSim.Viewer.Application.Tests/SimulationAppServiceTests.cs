using DanaSim.Viewer.Application.Handlers;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Domain.ValueObjects;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace DanaSim.Viewer.Application.Tests;

public class SimulationAppServiceTests
{
    private readonly Mock<IControlPublisher> _control = new();
    private readonly Mock<ISimulationBroadcaster> _broadcaster = new();
    private readonly Mock<ITerrainDataReader> _terrain = new();

    private SimulationAppService BuildService()
    {
        _terrain.Setup(t => t.ReadHeightsAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((float[]?)null);

        return new SimulationAppService(
            new SystemPingHandler(NullLogger<SystemPingHandler>.Instance),
            new InitMapConfigHandler(NullLogger<InitMapConfigHandler>.Instance),
            new InitAgentLayerHandler(_terrain.Object, NullLogger<InitAgentLayerHandler>.Instance),
            new InitAgentEofHandler(NullLogger<InitAgentEofHandler>.Instance),
            new FrameStartHandler(NullLogger<FrameStartHandler>.Instance),
            new EyeSetStateLayerHandler(NullLogger<EyeSetStateLayerHandler>.Instance),
            new FrameEndHandler(NullLogger<FrameEndHandler>.Instance),
            new InitEofHandler(NullLogger<InitEofHandler>.Instance),
            new EyeFrameSyncHandler(NullLogger<EyeFrameSyncHandler>.Instance),
            new SimEndHandler(new SimulationStatusService(), NullLogger<SimEndHandler>.Instance),
            _control.Object,
            _broadcaster.Object,
            Options.Create(new SimulationAppServiceOptions()),
            NullLogger<SimulationAppService>.Instance);
    }

    [Fact]
    public async Task MalformedJson_IsDiscardedWithoutException()
    {
        var service = BuildService();
        var act = () => service.HandleEventAsync("{not valid json}");
        await act.Should().NotThrowAsync();
    }

    [Fact]
    public async Task UnknownProcess_IsDiscardedWithoutException()
    {
        var service = BuildService();
        var act = () => service.HandleEventAsync("""{"process":"Unknown_Event"}""");
        await act.Should().NotThrowAsync();
    }

    [Fact]
    public async Task SystemPing_PublishesPong()
    {
        var service = BuildService();
        await service.HandleEventAsync("""{"process":"System_Ping","source":"test"}""");
        _control.Verify(c => c.PublishPongAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task FullInitSequence_BroadcastsInitialState()
    {
        var service = BuildService();

        await service.HandleEventAsync("""{"process":"System_Ping"}""");
        await service.HandleEventAsync("""
            {"process":"InitMap_Config",
             "map":{"size_x":4,"size_y":4,"cell_resolution_m":50.0},
             "metadata":{"sim_start_time":"2024-10-29T10:00:00","time_step_s":1.0},
             "georeference":{"lat":39.3,"lon":-0.7}}
            """);
        await service.HandleEventAsync("""{"process":"InitAgent_EOF"}""");
        await service.HandleEventAsync("""{"process":"FrameStart","total_chunks":1,"chunks_per_batch":10}""");
        await service.HandleEventAsync("""
            {"process":"EYE_SetState_Layer","id":"topo","changes":{"cells":{"0":{"state":3,"height":0.5}}}}
            """);
        await service.HandleEventAsync("""{"process":"FrameEnd"}""");
        await service.HandleEventAsync("""{"process":"Init_EOF","total_chunks_sent":1}""");

        _broadcaster.Verify(b => b.BroadcastInitialStateAsync(
            It.IsAny<GridMeta>(),
            It.IsAny<FrameData>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InitAgentLayer_ColorPaletteFlowsToInitialBroadcast()
    {
        var service = BuildService();

        await service.HandleEventAsync("""{"process":"System_Ping"}""");
        await service.HandleEventAsync("""
            {"process":"InitMap_Config",
             "map":{"size_x":4,"size_y":4,"cell_resolution_m":50.0},
             "metadata":{"sim_start_time":"2024-10-29T10:00:00","time_step_s":1.0},
             "georeference":{"lat":39.3,"lon":-0.7}}
            """);
        await service.HandleEventAsync("""
            {"process":"InitAgent_Layer",
             "id":"terrain",
             "data_path":"topo_bathy",
             "data_filename":"topo_bathy",
             "color_palette":[
               {"value":0,"label":"Dry","hex":"#9E8050","rgba":[158,128,80,255]},
               {"value":1,"label":"Shallow","hex":"#99E6FF","rgba":[153,230,255,255]}
             ]}
            """);
        await service.HandleEventAsync("""{"process":"InitAgent_EOF"}""");
        await service.HandleEventAsync("""{"process":"FrameStart","total_chunks":0,"chunks_per_batch":10}""");
        await service.HandleEventAsync("""{"process":"FrameEnd"}""");
        await service.HandleEventAsync("""{"process":"Init_EOF","total_chunks_sent":0}""");

        _broadcaster.Verify(b => b.BroadcastInitialStateAsync(
            It.Is<GridMeta>(meta =>
                meta.Palette != null &&
                meta.Palette.Entries.Count == 2 &&
                meta.Palette.Entries[0].Value == 0 &&
                meta.Palette.Entries[0].Label == "Dry" &&
                meta.Palette.Entries[0].Hex == "#9E8050" &&
                meta.Palette.Entries[0].Rgba.SequenceEqual(new byte[] { 158, 128, 80, 255 }) &&
                meta.Palette.Entries[1].Value == 1 &&
                meta.Palette.Entries[1].Label == "Shallow" &&
                meta.Palette.Entries[1].Hex == "#99E6FF" &&
                meta.Palette.Entries[1].Rgba.SequenceEqual(new byte[] { 153, 230, 255, 255 })),
            It.IsAny<FrameData>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Backpressure_ChunkAckPublishedEveryBatch()
    {
        var service = BuildService();

        await service.HandleEventAsync("""{"process":"System_Ping"}""");
        await service.HandleEventAsync("""
            {"process":"InitMap_Config",
             "map":{"size_x":4,"size_y":4,"cell_resolution_m":50.0},
             "metadata":{"sim_start_time":"2024-10-29T10:00:00","time_step_s":1.0},
             "georeference":{"lat":39.3,"lon":-0.7}}
            """);
        // batch size = 2
        await service.HandleEventAsync("""{"process":"FrameStart","total_chunks":4,"chunks_per_batch":2}""");

        await service.HandleEventAsync("""{"process":"EYE_SetState_Layer","id":"x","changes":{"cells":{}}}""");
        _control.Verify(c => c.PublishChunkAckAsync(It.IsAny<CancellationToken>()), Times.Never);

        await service.HandleEventAsync("""{"process":"EYE_SetState_Layer","id":"x","changes":{"cells":{}}}""");
        _control.Verify(c => c.PublishChunkAckAsync(It.IsAny<CancellationToken>()), Times.Once);

        await service.HandleEventAsync("""{"process":"EYE_SetState_Layer","id":"x","changes":{"cells":{}}}""");
        await service.HandleEventAsync("""{"process":"EYE_SetState_Layer","id":"x","changes":{"cells":{}}}""");
        _control.Verify(c => c.PublishChunkAckAsync(It.IsAny<CancellationToken>()), Times.Exactly(2));
    }

    [Fact]
    public async Task SimEnd_BroadcastsEndedAndStopsRunning()
    {
        var service = BuildService();
        await service.HandleEventAsync("""{"process":"System_Ping"}""");
        await service.HandleEventAsync("""
            {"process":"InitMap_Config",
             "map":{"size_x":2,"size_y":2,"cell_resolution_m":50.0},
             "metadata":{"sim_start_time":"2024-10-29T10:00:00","time_step_s":1.0},
             "georeference":{"lat":39.3,"lon":-0.7}}
            """);
        await service.HandleEventAsync("""{"process":"FrameStart","total_chunks":0,"chunks_per_batch":10}""");
        await service.HandleEventAsync("""{"process":"FrameEnd"}""");
        await service.HandleEventAsync("""{"process":"Init_EOF","total_chunks_sent":0}""");
        await service.HandleEventAsync("""{"process":"Sim_End","sim_time_total":3600.0}""");

        _broadcaster.Verify(b => b.BroadcastSimulationEndedAsync(It.IsAny<CancellationToken>()), Times.Once);
    }
}
