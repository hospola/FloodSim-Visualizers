using Microsoft.AspNetCore.SignalR;

namespace DanaSim.Viewer.Infrastructure.SignalR;

/// <summary>
/// SignalR hub: browser clients join a scenario group to receive push notifications.
/// Server-to-client messages: FrameReady(stepName), SimulationEnded.
/// </summary>
public sealed class SimulationHub : Hub
{
    public async Task JoinScenario(string scenario)
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, scenario);
    }
}
