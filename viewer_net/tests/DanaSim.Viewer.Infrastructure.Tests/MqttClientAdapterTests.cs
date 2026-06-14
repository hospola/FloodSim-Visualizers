using System.Buffers;
using System.Text;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Infrastructure.Mqtt;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;
using MQTTnet;

namespace DanaSim.Viewer.Infrastructure.Tests;

public class MqttClientAdapterTests
{
    private static (Mock<IMqttClient> client, Func<bool> isConnected) CreateClient(bool startConnected = false)
    {
        var connected = startConnected;
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(() => connected);
        client.Setup(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()))
              .ReturnsAsync((MqttClientConnectResult)null!)
              .Callback(() => connected = true);
        client.Setup(c => c.SubscribeAsync(It.IsAny<MqttClientSubscribeOptions>(), It.IsAny<CancellationToken>()))
              .ReturnsAsync((MqttClientSubscribeResult)null!);
        client.Setup(c => c.DisconnectAsync(It.IsAny<MqttClientDisconnectOptions>(), It.IsAny<CancellationToken>()))
              .Returns(Task.CompletedTask)
              .Callback(() => connected = false);
        return (client, () => connected);
    }

    private static MqttClientAdapter CreateAdapter(
        Mock<IMqttClient> client,
        SimulationStatusService status,
        MqttOptions? opts = null,
        ISimulationEventHandler? handler = null) =>
        new(client.Object,
            handler ?? Mock.Of<ISimulationEventHandler>(),
            Options.Create(opts ?? new MqttOptions()),
            status,
            NullLogger<MqttClientAdapter>.Instance);

    // ── IsConnected ──────────────────────────────────────────────────────────

    [Fact]
    public void IsConnected_ReflectsUnderlyingClient()
    {
        var (client, _) = CreateClient(startConnected: true);
        var adapter = CreateAdapter(client, new SimulationStatusService());

        adapter.IsConnected.Should().BeTrue();
    }

    // ── ConnectAsync ─────────────────────────────────────────────────────────

    [Fact]
    public async Task ConnectAsync_WhenAlreadyConnected_IsNoOp()
    {
        var (client, _) = CreateClient(startConnected: true);
        var adapter = CreateAdapter(client, new SimulationStatusService());

        await adapter.ConnectAsync();

        client.Verify(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ConnectAsync_WhenNotConnected_ConnectsSubscribesAndUpdatesStatus()
    {
        var (client, _) = CreateClient();
        var status = new SimulationStatusService();
        var adapter = CreateAdapter(client, status, new MqttOptions { Host = "broker", Port = 1884, Scenario = "demo" });

        await adapter.ConnectAsync();

        client.Verify(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        client.Verify(c => c.SubscribeAsync(It.IsAny<MqttClientSubscribeOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        status.Get().ConnectionStatus.Should().Be("Connected");
    }

    [Fact]
    public async Task ConnectAsync_RetriesAfterFailure_AndEventuallySucceeds()
    {
        var connected = false;
        var client = new Mock<IMqttClient>();
        client.SetupGet(c => c.IsConnected).Returns(() => connected);

        var attempt = 0;
        client.Setup(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()))
              .Returns(() =>
              {
                  attempt++;
                  if (attempt == 1) throw new InvalidOperationException("boom");
                  connected = true;
                  return Task.FromResult<MqttClientConnectResult>(null!);
              });
        client.Setup(c => c.SubscribeAsync(It.IsAny<MqttClientSubscribeOptions>(), It.IsAny<CancellationToken>()))
              .ReturnsAsync((MqttClientSubscribeResult)null!);

        var status = new SimulationStatusService();
        var adapter = CreateAdapter(client, status, new MqttOptions { ReconnectDelayMs = 1 });

        await adapter.ConnectAsync();

        attempt.Should().Be(2);
        status.Get().ConnectionStatus.Should().Be("Connected");
    }

    // ── DisconnectAsync ──────────────────────────────────────────────────────

    [Fact]
    public async Task DisconnectAsync_WhenNotConnected_IsNoOp()
    {
        var (client, _) = CreateClient(startConnected: false);
        var adapter = CreateAdapter(client, new SimulationStatusService());

        await adapter.DisconnectAsync();

        client.Verify(c => c.DisconnectAsync(It.IsAny<MqttClientDisconnectOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task DisconnectAsync_WhenConnected_DisconnectsAndUpdatesStatus()
    {
        var (client, _) = CreateClient(startConnected: true);
        var status = new SimulationStatusService();
        var adapter = CreateAdapter(client, status);

        await adapter.DisconnectAsync();

        client.Verify(c => c.DisconnectAsync(It.IsAny<MqttClientDisconnectOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        status.Get().ConnectionStatus.Should().Be("Disconnected");
    }

    // ── ReconfigureAsync ─────────────────────────────────────────────────────

    [Fact]
    public async Task ReconfigureAsync_UpdatesOptionsAndReconnects()
    {
        var (client, _) = CreateClient(startConnected: true);
        var opts = new MqttOptions { Host = "old-host", Port = 1, Scenario = "old" };
        var status = new SimulationStatusService();
        var adapter = CreateAdapter(client, status, opts);

        await adapter.ReconfigureAsync("new-host", 1884, "new-scenario");

        opts.Host.Should().Be("new-host");
        opts.Port.Should().Be(1884);
        opts.Scenario.Should().Be("new-scenario");

        client.Verify(c => c.DisconnectAsync(It.IsAny<MqttClientDisconnectOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        client.Verify(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        client.Verify(c => c.SubscribeAsync(It.IsAny<MqttClientSubscribeOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        status.Get().ConnectionStatus.Should().Be("Connected");
    }

    // ── StartAsync / StopAsync ───────────────────────────────────────────────

    [Fact]
    public async Task StartAsync_WithAutoConnectFalse_DoesNotConnect()
    {
        var (client, _) = CreateClient();
        var adapter = CreateAdapter(client, new SimulationStatusService(), new MqttOptions { AutoConnect = false });

        await adapter.StartAsync(CancellationToken.None);
        try
        {
            client.Verify(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()), Times.Never);
        }
        finally
        {
            await adapter.StopAsync(CancellationToken.None);
        }
    }

    [Fact]
    public async Task StartAsync_WithAutoConnectTrue_Connects()
    {
        var (client, _) = CreateClient();
        var status = new SimulationStatusService();
        var adapter = CreateAdapter(client, status, new MqttOptions { AutoConnect = true });

        await adapter.StartAsync(CancellationToken.None);
        try
        {
            client.Verify(c => c.ConnectAsync(It.IsAny<MqttClientOptions>(), It.IsAny<CancellationToken>()), Times.Once);
            status.Get().ConnectionStatus.Should().Be("Connected");
        }
        finally
        {
            await adapter.StopAsync(CancellationToken.None);
        }
    }

    [Fact]
    public async Task StopAsync_WhenConnected_Disconnects()
    {
        var (client, _) = CreateClient(startConnected: true);
        var adapter = CreateAdapter(client, new SimulationStatusService(), new MqttOptions { AutoConnect = false });

        await adapter.StartAsync(CancellationToken.None);
        await adapter.StopAsync(CancellationToken.None);

        client.Verify(c => c.DisconnectAsync(It.IsAny<MqttClientDisconnectOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    // ── Message dispatch ─────────────────────────────────────────────────────

    [Fact]
    public async Task ReceivedMessage_IsForwardedToHandler()
    {
        var (client, _) = CreateClient();
        var handler = new Mock<ISimulationEventHandler>();
        handler.Setup(h => h.HandleEventAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
               .Returns(Task.CompletedTask);

        var adapter = CreateAdapter(client, new SimulationStatusService(), new MqttOptions { AutoConnect = false }, handler.Object);

        await adapter.StartAsync(CancellationToken.None);
        try
        {
            var payload = """{"process":"Sim_End"}""";
            var message = new MqttApplicationMessage
            {
                Topic = "FloodSim/demo/events",
                Payload = new ReadOnlySequence<byte>(Encoding.UTF8.GetBytes(payload)),
            };
            var args = new MqttApplicationMessageReceivedEventArgs(
                "client", message, new MQTTnet.Packets.MqttPublishPacket(), (_, _) => Task.CompletedTask);

            client.Raise(c => c.ApplicationMessageReceivedAsync += null, [args]);

            // Allow the channel's background reader to process the message.
            for (var i = 0; i < 50 && handler.Invocations.Count == 0; i++)
                await Task.Delay(10);

            handler.Verify(h => h.HandleEventAsync(payload, It.IsAny<CancellationToken>()), Times.Once);
        }
        finally
        {
            await adapter.StopAsync(CancellationToken.None);
        }
    }

    // ── DisposeAsync ─────────────────────────────────────────────────────────

    [Fact]
    public async Task DisposeAsync_DisposesUnderlyingClient()
    {
        var (client, _) = CreateClient();
        var adapter = CreateAdapter(client, new SimulationStatusService());

        await adapter.DisposeAsync();

        client.Verify(c => c.Dispose(), Times.Once);
    }
}
