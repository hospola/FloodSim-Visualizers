using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Infrastructure.Extensions;
using DanaSim.Viewer.Infrastructure.FileOutput;
using DanaSim.Viewer.Infrastructure.Mqtt;
using DanaSim.Viewer.Infrastructure.SignalR;
using DanaSim.Viewer.Infrastructure.Terrain;
using FluentAssertions;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using MQTTnet;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class InfrastructureServiceExtensionsTests
{
    private static ServiceProvider BuildProvider()
    {
        var configuration = new ConfigurationBuilder().Build();

        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton<SimulationStatusService>();
        services.AddSingleton<ISimulationEventHandler>(_ => Moq.Mock.Of<ISimulationEventHandler>());
        services.AddSignalR();
        services.AddInfrastructure(configuration);

        return services.BuildServiceProvider();
    }

    [Fact]
    public void AddInfrastructure_RegistersMqttClient()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<IMqttClient>().Should().NotBeNull();
    }

    [Fact]
    public void AddInfrastructure_RegistersControlPublisher()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<IControlPublisher>().Should().BeOfType<MqttControlPublisher>();
    }

    [Fact]
    public void AddInfrastructure_RegistersMqttClientAdapter_AsSharedSingletonAcrossRoles()
    {
        var provider = BuildProvider();

        var adapter = provider.GetRequiredService<MqttClientAdapter>();
        var hostedService = provider.GetServices<IHostedService>().OfType<MqttClientAdapter>().Single();
        var controller = provider.GetRequiredService<ISimulationController>();

        hostedService.Should().BeSameAs(adapter);
        controller.Should().BeSameAs(adapter);
    }

    [Fact]
    public void AddInfrastructure_RegistersTerrainDataReader()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<ITerrainDataReader>().Should().BeOfType<IdrisiTerrainDataReader>();
    }

    [Fact]
    public void AddInfrastructure_RegistersFileBasedBroadcaster()
    {
        var provider = BuildProvider();

        provider.GetRequiredService<ISimulationBroadcaster>().Should().BeOfType<FileBasedBroadcaster>();
    }
}
