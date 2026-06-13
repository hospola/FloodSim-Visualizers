using DanaSim.Viewer.Application.Extensions;
using DanaSim.Viewer.Infrastructure.SignalR;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using DanaSim.Viewer.Application.Services;
using DanaSim.Viewer.Infrastructure.Config;
using DanaSim.Viewer.Infrastructure.Extensions;
using DanaSim.Viewer.Web.Logging;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.FileProviders.Embedded;
using Serilog;
using Serilog.Events;
using Serilog.Formatting.Compact;

// ── Resolve user-data directory override (before AppPaths is touched by anything
// below — e.g. Serilog's file sink reads AppPaths.LogsDirectory a few lines down) ─
var bootstrapConfig = new ConfigurationBuilder()
    .SetBasePath(Directory.GetCurrentDirectory())
    .AddJsonFile("appsettings.json", optional: true)
    .AddEnvironmentVariables()
    .Build();

AppPaths.Configure(bootstrapConfig["Paths:UserDataDir"]);

// ── Logging bootstrap (before host so startup errors are captured) ────────────
var inMemorySink = new InMemoryLogSink();

Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Debug()
    .MinimumLevel.Override("Microsoft",                  LogEventLevel.Warning)
    .MinimumLevel.Override("Microsoft.Hosting.Lifetime", LogEventLevel.Information)
    .Enrich.FromLogContext()
    .WriteTo.Console(outputTemplate:
        "[{Timestamp:HH:mm:ss} {Level:u3}] {SourceContext:l} — {Message:lj}{NewLine}{Exception}")
    .WriteTo.File(
        formatter: new CompactJsonFormatter(),
        path: Path.Combine(AppPaths.LogsDirectory, "danasim-.log"),
        rollingInterval: RollingInterval.Day,
        retainedFileCountLimit: 7,
        fileSizeLimitBytes: 50 * 1024 * 1024,
        rollOnFileSizeLimit: true)
    .WriteTo.Sink(inMemorySink)
    .CreateLogger();

try
{
    var builder = WebApplication.CreateBuilder(args);

    builder.Host.UseSerilog();

    // ── User config — load before DI so values override appsettings.json ─────
    var userConfigService = new UserConfigService();
    var userCfg = userConfigService.Load();
    if (userCfg is not null)
    {
        builder.Configuration["Mqtt:Host"]            = userCfg.MqttHost;
        builder.Configuration["Mqtt:Port"]            = userCfg.MqttPort.ToString();
        builder.Configuration["Mqtt:Scenario"]        = userCfg.Scenario;
        builder.Configuration["Terrain:BasePath"]     = userCfg.TerrainBasePath;
        builder.Configuration["FileOutput:OutputDir"] = userCfg.OutputDir;
    }

    if (!userConfigService.IsConfigured())
        builder.Configuration["Mqtt:AutoConnect"] = "false";

    // ── Services ─────────────────────────────────────────────────────────────
    builder.Services.AddSingleton(inMemorySink);
    builder.Services.AddSingleton(userConfigService);

    builder.Services.AddSignalR();
    builder.Services.AddControllersWithViews();
    // Suppress the default 400 ValidationProblemDetails so all error responses
    // use our uniform { "errors": { "field": "msg" } } shape.
    builder.Services.Configure<ApiBehaviorOptions>(o =>
        o.SuppressModelStateInvalidFilter = true);

    builder.Services.Configure<SimulationAppServiceOptions>(
        builder.Configuration.GetSection("Simulation"));

    builder.Services.AddApplication();
    builder.Services.AddInfrastructure(builder.Configuration);

    // ── Pipeline ──────────────────────────────────────────────────────────────
    var app = builder.Build();

    if (!app.Environment.IsDevelopment())
        app.UseExceptionHandler("/Home/Error");

    app.UseStaticFiles();

    // Serve vendored player JS/CSS from the embedded assembly at /player-assets
    app.UseStaticFiles(new StaticFileOptions
    {
        FileProvider = new ManifestEmbeddedFileProvider(
            typeof(Program).Assembly, "PlayerAssets"),
        RequestPath = "/player-assets",
    });

    // Serve simulation output files (player.html, flood/*.png) under /sim-outputs
    // Only mount if OutputDir is configured and writable; skip silently on first launch.
    var simOutputDir = builder.Configuration["FileOutput:OutputDir"] ?? "";
    if (!string.IsNullOrWhiteSpace(simOutputDir))
    {
        // A relative OutputDir must resolve against the app's content root, not the
        // process's current working directory — the latter varies by launch method
        // (run.sh/run.bat vs. IIS, whose working directory often differs from the
        // install folder). ContentRootPath is reliably the deployed app's directory.
        if (!Path.IsPathRooted(simOutputDir))
            simOutputDir = Path.Combine(app.Environment.ContentRootPath, simOutputDir);

        try
        {
            if (!Directory.Exists(simOutputDir))
                Directory.CreateDirectory(simOutputDir);

            app.UseStaticFiles(new StaticFileOptions
            {
                FileProvider          = new PhysicalFileProvider(simOutputDir),
                RequestPath           = "/sim-outputs",
                ServeUnknownFileTypes = true,
            });
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Could not mount output directory '{Dir}' — configure a writable path via the dashboard", simOutputDir);
        }
    }

    app.UseRouting();

    app.MapControllers();
    app.MapHub<SimulationHub>("/simulationHub");
    app.MapControllerRoute(
        name: "default",
        pattern: "{controller=Home}/{action=Index}/{id?}");

    app.Run();
}
catch (Exception ex)
{
    Log.Fatal(ex, "Application terminated unexpectedly");
}
finally
{
    Log.CloseAndFlush();
}
