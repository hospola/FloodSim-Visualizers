using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Domain.Ports;
using DanaSim.Viewer.Infrastructure.FileOutput;
using DanaSim.Viewer.Infrastructure.Mqtt;
using DanaSim.Viewer.Infrastructure.Terrain;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using MQTTnet;

namespace DanaSim.Viewer.Infrastructure.Extensions;

public static class InfrastructureServiceExtensions
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services, IConfiguration configuration)
    {
        // MQTT — one MqttClientAdapter instance registered under three roles
        services.Configure<MqttOptions>(configuration.GetSection("Mqtt"));
        services.AddSingleton<IMqttClient>(_ => new MqttClientFactory().CreateMqttClient());
        services.AddSingleton<IControlPublisher, MqttControlPublisher>();
        services.AddSingleton<MqttClientAdapter>();
        services.AddSingleton<IHostedService>(p => p.GetRequiredService<MqttClientAdapter>());
        services.AddSingleton<ISimulationController>(p => p.GetRequiredService<MqttClientAdapter>());

        // Terrain data
        services.Configure<TerrainOptions>(configuration.GetSection("Terrain"));
        services.AddSingleton<ITerrainDataReader, IdrisiTerrainDataReader>();

        // File-based broadcaster (generates player.html + flood PNGs to disk)
        services.Configure<FileOutputOptions>(configuration.GetSection("FileOutput"));
        services.AddSingleton<ISimulationBroadcaster, FileBasedBroadcaster>();

        return services;
    }
}
