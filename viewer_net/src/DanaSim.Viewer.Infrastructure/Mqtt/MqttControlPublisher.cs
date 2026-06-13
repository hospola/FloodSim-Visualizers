using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using MQTTnet;
using MQTTnet.Protocol;

namespace DanaSim.Viewer.Infrastructure.Mqtt;

public sealed class MqttControlPublisher(
    IMqttClient client,
    IOptions<MqttOptions> options,
    ILogger<MqttControlPublisher> logger) : IControlPublisher
{
    private readonly MqttOptions _opts = options.Value;

    public Task PublishChunkAckAsync(CancellationToken ct = default) =>
        PublishAsync(MqttTopics.ControlEvents(_opts.Scenario), """{"process":"ChunkAck"}""", ct);

    public Task PublishPongAsync(CancellationToken ct = default) =>
        PublishAsync(
            MqttTopics.PongOut(_opts.Scenario),
            """{"process":"System_Pong","source":"DanaSim_NetViewer"}""",
            ct);

    private async Task PublishAsync(string topic, string payload, CancellationToken ct)
    {
        if (!client.IsConnected)
        {
            logger.LogWarning("Cannot publish to '{Topic}': client not connected", topic);
            return;
        }

        var message = new MqttApplicationMessageBuilder()
            .WithTopic(topic)
            .WithPayload(payload)
            .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)
            .Build();

        await client.PublishAsync(message, ct);
        logger.LogDebug("Published to '{Topic}': {Payload}", topic, payload);
    }
}
