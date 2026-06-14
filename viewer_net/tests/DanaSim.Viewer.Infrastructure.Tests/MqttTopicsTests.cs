using DanaSim.Viewer.Infrastructure.Mqtt;
using FluentAssertions;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class MqttTopicsTests
{
    private const string Scenario = "scenario_29_10_2024";

    [Fact]
    public void Events_BuildsScenarioEventsTopic()
    {
        MqttTopics.Events(Scenario).Should().Be("FloodSim/scenario_29_10_2024/events");
    }

    [Fact]
    public void PingIn_BuildsHandshakePingTopic()
    {
        MqttTopics.PingIn(Scenario).Should().Be("FloodSim/scenario_29_10_2024/system/handshake/ping");
    }

    [Fact]
    public void PongOut_BuildsHandshakePongTopic()
    {
        MqttTopics.PongOut(Scenario).Should().Be("FloodSim/scenario_29_10_2024/system/handshake/pong");
    }

    [Fact]
    public void ControlEvents_BuildsControlEventsTopic()
    {
        MqttTopics.ControlEvents(Scenario).Should().Be("FloodSim/scenario_29_10_2024/control/events");
    }

    [Fact]
    public void Topics_AreScopedPerScenario()
    {
        MqttTopics.Events("a").Should().NotBe(MqttTopics.Events("b"));
    }
}
