using DanaSim.Viewer.Application.Handlers;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using Microsoft.Extensions.DependencyInjection;

namespace DanaSim.Viewer.Application.Extensions;

public static class ApplicationServiceExtensions
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        // Handlers (Strategy pattern — one per MQTT event type)
        services.AddSingleton<SystemPingHandler>();
        services.AddSingleton<InitMapConfigHandler>();
        services.AddSingleton<InitAgentLayerHandler>();
        services.AddSingleton<InitAgentEofHandler>();
        services.AddSingleton<FrameStartHandler>();
        services.AddSingleton<EyeSetStateLayerHandler>();
        services.AddSingleton<FrameEndHandler>();
        services.AddSingleton<InitEofHandler>();
        services.AddSingleton<EyeFrameSyncHandler>();
        services.AddSingleton<SimEndHandler>();

        // Status tracker (feeds the API status endpoint)
        services.AddSingleton<SimulationStatusService>();

        // Orchestrator
        services.AddSingleton<ISimulationEventHandler, SimulationAppService>();
        services.Configure<SimulationAppServiceOptions>(_ => { });

        return services;
    }
}
