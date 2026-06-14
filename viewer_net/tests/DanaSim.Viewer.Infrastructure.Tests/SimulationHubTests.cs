using DanaSim.Viewer.Infrastructure.SignalR;
using Microsoft.AspNetCore.SignalR;
using Moq;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class SimulationHubTests
{
    [Fact]
    public async Task JoinScenario_AddsConnectionToGroup()
    {
        var groups = new Mock<IGroupManager>();
        var context = new Mock<HubCallerContext>();
        context.SetupGet(c => c.ConnectionId).Returns("conn-123");

        var hub = new SimulationHub
        {
            Groups = groups.Object,
            Context = context.Object,
        };

        await hub.JoinScenario("demo");

        groups.Verify(g => g.AddToGroupAsync("conn-123", "demo", default), Times.Once);
    }
}
