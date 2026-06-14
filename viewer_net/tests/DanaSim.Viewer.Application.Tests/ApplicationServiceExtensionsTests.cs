using DanaSim.Viewer.Application.Extensions;
using DanaSim.Viewer.Application.Handlers;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Ports;
using FluentAssertions;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace DanaSim.Viewer.Application.Tests;

public class ApplicationServiceExtensionsTests
{
    private static ServiceProvider BuildProvider()
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton(Mock.Of<IControlPublisher>());
        services.AddSingleton(Mock.Of<ISimulationBroadcaster>());
        services.AddSingleton(Mock.Of<ITerrainDataReader>());
        services.AddApplication();

        return services.BuildServiceProvider();
    }

    [Fact]
    public void AddApplication_RegistersSimulationEventHandler()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<ISimulationEventHandler>().Should().BeOfType<SimulationAppService>();
    }

    [Fact]
    public void AddApplication_RegistersSimulationStatusService()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<SimulationStatusService>().Should().NotBeNull();
    }

    [Fact]
    public void AddApplication_RegistersAllEventHandlers()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<SystemPingHandler>().Should().NotBeNull();
        provider.GetRequiredService<InitMapConfigHandler>().Should().NotBeNull();
        provider.GetRequiredService<InitAgentLayerHandler>().Should().NotBeNull();
        provider.GetRequiredService<InitAgentEofHandler>().Should().NotBeNull();
        provider.GetRequiredService<FrameStartHandler>().Should().NotBeNull();
        provider.GetRequiredService<EyeSetStateLayerHandler>().Should().NotBeNull();
        provider.GetRequiredService<FrameEndHandler>().Should().NotBeNull();
        provider.GetRequiredService<InitEofHandler>().Should().NotBeNull();
        provider.GetRequiredService<EyeFrameSyncHandler>().Should().NotBeNull();
        provider.GetRequiredService<SimEndHandler>().Should().NotBeNull();
    }
}
