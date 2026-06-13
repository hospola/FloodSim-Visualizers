using System.Threading.Channels;
using DanaSim.Viewer.Application.Ports;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Domain.Ports;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using MQTTnet;
using MQTTnet.Protocol;

namespace DanaSim.Viewer.Infrastructure.Mqtt;

/// <summary>
/// Subscribes to the MQTT broker, receives simulation events, and forwards them
/// sequentially to ISimulationEventHandler via a Channel (preserving event order).
///
/// Implements both IHostedService (host lifecycle) and ISimulationController
/// (user-triggered connect / disconnect / reconfigure).  The two concerns use
/// intentionally different method names so there is no ambiguity:
///   IHostedService : StartAsync / StopAsync  — called by the host
///   ISimulationController : ConnectAsync / DisconnectAsync — called by the API
/// </summary>
public sealed class MqttClientAdapter : IHostedService, ISimulationController, IAsyncDisposable
{
    private readonly IMqttClient _client;
    private readonly ISimulationEventHandler _handler;
    private readonly SimulationStatusService _status;
    private readonly ILogger<MqttClientAdapter> _logger;

    // Mutable so ReconfigureAsync can update broker settings at runtime
    private readonly MqttOptions _opts;

    private readonly Channel<string> _messageChannel =
        Channel.CreateUnbounded<string>(new UnboundedChannelOptions { SingleReader = true });

    private MqttClientOptions? _connectOptions;
    private Task? _processingLoop;
    private CancellationTokenSource _cts = new();

    public MqttClientAdapter(
        IMqttClient client,
        ISimulationEventHandler handler,
        IOptions<MqttOptions> options,
        SimulationStatusService status,
        ILogger<MqttClientAdapter> logger)
    {
        _client  = client;
        _handler = handler;
        _opts    = options.Value;
        _status  = status;
        _logger  = logger;

        _client.ApplicationMessageReceivedAsync += OnMessageReceived;
        _client.DisconnectedAsync               += OnDisconnected;
    }

    // ── ISimulationController ────────────────────────────────────────────────

    public bool IsConnected => _client.IsConnected;

    /// <summary>Idempotent: returns immediately if already connected.</summary>
    public async Task ConnectAsync(CancellationToken ct = default)
    {
        if (_client.IsConnected) return;
        _connectOptions = BuildConnectOptions();
        await ConnectWithRetryAsync(ct);
    }

    /// <summary>Graceful disconnect; leaves the processing loop alive.</summary>
    public async Task DisconnectAsync(CancellationToken ct = default)
    {
        if (!_client.IsConnected) return;
        await _client.DisconnectAsync(cancellationToken: ct);
        _status.SetConnection("Disconnected");
    }

    /// <summary>Disconnect → apply new broker settings → reconnect.</summary>
    public async Task ReconfigureAsync(string host, int port, string scenario, CancellationToken ct = default)
    {
        await DisconnectAsync(ct);
        _opts.Host     = host;
        _opts.Port     = port;
        _opts.Scenario = scenario;
        await ConnectAsync(ct);
    }

    // ── IHostedService ────────────────────────────────────────────────────────

    public async Task StartAsync(CancellationToken ct)
    {
        _cts            = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _connectOptions = BuildConnectOptions();

        // Start the processing loop regardless of AutoConnect so messages are
        // dispatched as soon as a connection is established later.
        _processingLoop = ProcessChannelAsync(_cts.Token);

        if (_opts.AutoConnect)
            await ConnectWithRetryAsync(_cts.Token);
    }

    public async Task StopAsync(CancellationToken ct)
    {
        _messageChannel.Writer.TryComplete();
        await _cts.CancelAsync();

        if (_processingLoop is not null)
            await _processingLoop;

        if (_client.IsConnected)
            await _client.DisconnectAsync(cancellationToken: ct);
    }

    public async ValueTask DisposeAsync()
    {
        _cts.Dispose();
        _client.ApplicationMessageReceivedAsync -= OnMessageReceived;
        _client.DisconnectedAsync               -= OnDisconnected;
        _client.Dispose();
    }

    // ── Private ──────────────────────────────────────────────────────────────

    private MqttClientOptions BuildConnectOptions() =>
        new MqttClientOptionsBuilder()
            .WithTcpServer(_opts.Host, _opts.Port)
            .WithClientId("DanaSim_NetViewer")
            .WithKeepAlivePeriod(TimeSpan.FromSeconds(_opts.KeepAliveSeconds))
            .WithWillTopic($"FloodSim/{_opts.Scenario}/system/control")
            .WithWillPayload("""{"process":"System_Disconnected","source":"DanaSim_NetViewer"}""")
            .WithWillQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)
            .WithWillRetain(true)
            .Build();

    /// <summary>
    /// Retry loop: updates status to Connecting, attempts connect+subscribe,
    /// and loops with delay until success or cancellation.
    /// Fixes review issue #2 — initial connect failure is now actually retried.
    /// </summary>
    private async Task ConnectWithRetryAsync(CancellationToken ct)
    {
        _status.SetConnection("Connecting");

        for (var attempt = 1; ; attempt++)
        {
            try
            {
                await _client.ConnectAsync(_connectOptions!, ct);
                await SubscribeAsync(ct);
                _status.SetConnection("Connected");
                _logger.LogInformation(
                    "Connected to MQTT broker at {Host}:{Port}", _opts.Host, _opts.Port);
                return;
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _status.SetConnection("Disconnected", error: ex.Message);
                _logger.LogWarning(ex,
                    "Connect attempt {Attempt} failed — retrying in {Ms}ms",
                    attempt, _opts.ReconnectDelayMs);
                await Task.Delay(_opts.ReconnectDelayMs, ct);
            }
        }
    }

    private async Task SubscribeAsync(CancellationToken ct)
    {
        await _client.SubscribeAsync(new MqttClientSubscribeOptionsBuilder()
            .WithTopicFilter(f => f
                .WithTopic(MqttTopics.Events(_opts.Scenario))
                .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
            .WithTopicFilter(f => f
                .WithTopic(MqttTopics.PingIn(_opts.Scenario))
                .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
            .Build(), ct);

        _logger.LogInformation("Subscribed to scenario '{Scenario}'", _opts.Scenario);
    }

    private async Task OnDisconnected(MqttClientDisconnectedEventArgs e)
    {
        if (_cts.IsCancellationRequested) return;

        _status.SetConnection("Disconnected");
        _logger.LogWarning(
            "Disconnected from broker. Reconnecting in {Ms}ms...", _opts.ReconnectDelayMs);

        try
        {
            await Task.Delay(_opts.ReconnectDelayMs, _cts.Token);
            await ConnectWithRetryAsync(_cts.Token);
        }
        catch (OperationCanceledException) { }
    }

    private Task OnMessageReceived(MqttApplicationMessageReceivedEventArgs e)
    {
        var payload = e.ApplicationMessage.ConvertPayloadToString();
        _messageChannel.Writer.TryWrite(payload);
        return Task.CompletedTask;
    }

    private async Task ProcessChannelAsync(CancellationToken ct)
    {
        await foreach (var rawJson in _messageChannel.Reader.ReadAllAsync(ct))
        {
            try
            {
                await _handler.HandleEventAsync(rawJson, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unhandled error processing MQTT message");
            }
        }
    }
}
