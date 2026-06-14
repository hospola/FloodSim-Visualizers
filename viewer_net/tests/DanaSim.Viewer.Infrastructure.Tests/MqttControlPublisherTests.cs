using DanaSim.Viewer.Infrastructure.Mqtt;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;
using MQTTnet;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class MqttControlPublisherTests
{
    private static MqttControlPublisher CreatePublisher(Mock<IMqttClient> client, string scenario = "demo") =>
        new(client.Object,
            Options.Create(new MqttOptions { Scenario = scenario }),
            NullLogger<MqttControlPublisher>.Instance);

    [Fact]
    public async Task PublishChunkAckAsync_WhenConnected_PublishesToControlEventsTopic()
    {
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(true);
        MqttApplicationMessage? published = null;
        client.Setup(c => c.PublishAsync(It.IsAny<MqttApplicationMessage>(), It.IsAny<CancellationToken>()))
              .Callback<MqttApplicationMessage, CancellationToken>((m, _) => published = m)
              .ReturnsAsync((MqttClientPublishResult)null!);

        await CreatePublisher(client, "demo").PublishChunkAckAsync();

        published.Should().NotBeNull();
        published!.Topic.Should().Be("FloodSim/demo/control/events");
        published.ConvertPayloadToString().Should().Be("""{"process":"ChunkAck"}""");
    }

    [Fact]
    public async Task PublishChunkAckAsync_WhenNotConnected_DoesNotPublish()
    {
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(false);

        await CreatePublisher(client).PublishChunkAckAsync();

        client.Verify(c => c.PublishAsync(It.IsAny<MqttApplicationMessage>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task PublishPongAsync_WhenConnected_PublishesToHandshakePongTopic()
    {
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(true);
        MqttApplicationMessage? published = null;
        client.Setup(c => c.PublishAsync(It.IsAny<MqttApplicationMessage>(), It.IsAny<CancellationToken>()))
              .Callback<MqttApplicationMessage, CancellationToken>((m, _) => published = m)
              .ReturnsAsync((MqttClientPublishResult)null!);

        await CreatePublisher(client, "demo").PublishPongAsync();

        published.Should().NotBeNull();
        published!.Topic.Should().Be("FloodSim/demo/system/handshake/pong");
        published.ConvertPayloadToString().Should().Be("""{"process":"System_Pong","source":"DanaSim_NetViewer"}""");
    }

    [Fact]
    public async Task PublishPongAsync_WhenNotConnected_DoesNotPublish()
    {
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(false);

        await CreatePublisher(client).PublishPongAsync();

        client.Verify(c => c.PublishAsync(It.IsAny<MqttApplicationMessage>(), It.IsAny<CancellationToken>()), Times.Never);
    }
}
