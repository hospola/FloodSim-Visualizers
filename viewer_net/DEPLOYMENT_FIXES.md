# Viewer deployment fixes — June 2026

Background: a coworker hit several issues deploying the .NET Viewer
(`DanaSim.Viewer.Web`) under IIS with a dedicated service account, and ended up
hand-patching paths directly in the code (`AppPaths.cs`, `appsettings.json`)
to get it running. This document covers the fixes that replace those hand
patches with proper, reusable configuration — so future deployments need only
edit `appsettings.json`, not the source.

## 1. `%APPDATA%` resolution failing under IIS service accounts

**Problem**: `AppPaths` resolved its base directory via
`Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData)`
(`%APPDATA%\danasim-viewer` on Windows, `~/.config/danasim-viewer` on Linux).
Under an IIS app-pool identity (or any service account without a loaded user
profile), this either resolves to an inaccessible/wrong path or throws —
exactly what the coworker hit, and worked around by hardcoding
`AppPaths.Base = "C:\\inetpub\\wwwroot\\danasim\\App_Data\\danasim-viewer"`.

**Fix**: `AppPaths` ([AppPaths.cs](src/DanaSim.Viewer.Infrastructure/Config/AppPaths.cs))
now supports a configurable override:

```csharp
public static class AppPaths
{
    private static string? _overrideDir;

    public static void Configure(string? userDataDir) =>
        _overrideDir = string.IsNullOrWhiteSpace(userDataDir) ? null : userDataDir;

    private static string Base => _overrideDir ?? Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "danasim-viewer");
    ...
}
```

[Program.cs](src/DanaSim.Viewer.Web/Program.cs) reads `Paths:UserDataDir` from a
minimal bootstrap config and calls `AppPaths.Configure(...)` *before* anything
else (notably Serilog's file sink) touches `AppPaths.LogsDirectory`:

```csharp
var bootstrapConfig = new ConfigurationBuilder()
    .SetBasePath(Directory.GetCurrentDirectory())
    .AddJsonFile("appsettings.json", optional: true)
    .AddEnvironmentVariables()
    .Build();

AppPaths.Configure(bootstrapConfig["Paths:UserDataDir"]);
```

**How an admin uses it**: edit the deployed `appsettings.json` (no rebuild):

```json
"Paths": { "UserDataDir": "C:\\inetpub\\wwwroot\\danasim\\App_Data\\danasim-viewer" }
```

Leave it `""` (the shipped default) to keep the original `%APPDATA%`/`~/.config`
behavior — existing deployments that don't set it are unaffected. The folder
must be writable by whatever account runs the app (same `App_Data`-permissions
step admins already do for the Framework 4.8 apps).

This is the generalized, config-driven version of what the coworker hardcoded
into `AppPaths.cs` — same outcome, but no code edits on future deploys/updates.

## 2. Bundling the terrain dataset — `Terrain:BasePath` empty fallback

To let an installer ship with the dataset already in place (no manual
`Terrain:BasePath` configuration needed), an empty `BasePath` now resolves to
`{app directory}/data`:

[IdrisiTerrainDataReader.cs](src/DanaSim.Viewer.Infrastructure/Terrain/IdrisiTerrainDataReader.cs):
```csharp
private readonly string _basePath = string.IsNullOrWhiteSpace(options.Value.BasePath)
    ? Path.Combine(AppContext.BaseDirectory, "data")
    : options.Value.BasePath;
```

`AppContext.BaseDirectory` is used (not `Directory.GetCurrentDirectory()`)
because the process's working directory varies by launch method — `run.sh`/
`run.bat` `cd` into the exe's directory first, but IIS's working directory is
often something unrelated (e.g. `C:\Windows\System32`). `AppContext.BaseDirectory`
reliably points at the published binaries directory regardless of how the app
was launched.

This is the mechanism the **"full" installer variant** (§5) relies on: it
bundles a `data/` folder next to the executable and ships with
`Terrain:BasePath: ""`, so it works with zero configuration.

### ⚠️ Path-construction convention — avoid double-nesting

`IdrisiTerrainDataReader` builds file paths as `Path.Combine(BasePath, dataPath)`,
where `dataPath` comes from the `InitAgent_Layer` MQTT event and **already
includes the dataset folder name** (e.g. `data_29_10_2024/topo_bathy`).

So `Terrain:BasePath` must point at the *parent* `data` directory — e.g.
`C:\inetpub\wwwroot\danasim\App_Data\data` — **not** the dataset folder itself
(`...\App_Data\data\data_29_10_2024`). Setting it one level too deep produces
a doubled segment and a "metadata not found" warning like:

```
IDRISI metadata not found: C:\...\App_Data\data\data_29_10_2024\data_29_10_2024\topo_bathy\topo_bathy.doc
```

## 3. `FileOutput:OutputDir` resolved against the wrong directory

**Problem**: a relative `OutputDir` was used as-is, so it resolved against
`Directory.GetCurrentDirectory()` — the same "CWD varies by launch method" trap
as §1/§2, just for a different setting.

**Fix** ([Program.cs](src/DanaSim.Viewer.Web/Program.cs)):
```csharp
var simOutputDir = builder.Configuration["FileOutput:OutputDir"] ?? "";
if (!string.IsNullOrWhiteSpace(simOutputDir))
{
    if (!Path.IsPathRooted(simOutputDir))
        simOutputDir = Path.Combine(app.Environment.ContentRootPath, simOutputDir);
    ...
}
```
`Path.IsPathRooted` leaves absolute paths (Linux `/...` or Windows `C:\...`)
untouched and only resolves relative ones against `ContentRootPath` (reliably
the deployed app's directory under both launch methods, including IIS).

## 4. Dashboard config validation blocked the empty-`BasePath` feature

**Problem**: `POST /api/config` required `TerrainBasePath` to be non-blank
(`"Required"`), and `UserConfigService.IsConfigured()` did the same — making it
*impossible* to actually save the blank value that §2's bundled-data fallback
depends on.

**Fix**: removed the `Required` check on `TerrainBasePath` in both
[ApiController.cs](src/DanaSim.Viewer.Web/Controllers/ApiController.cs) and
[UserConfigService.cs](src/DanaSim.Viewer.Infrastructure/Config/UserConfigService.cs)
(`OutputDir` is still required — that one has no "use a bundled default"
fallback). The dashboard's "Terrain folder" field can now be left blank.

> **Note**: `TerrainOptions`/`IdrisiTerrainDataReader._basePath` is resolved
> once at startup from `IOptions<TerrainOptions>`. Saving a new value via the
> dashboard persists it to `user-config.json`, but the running process keeps
> using the value it started with — **restart the app** for a changed
> `Terrain:BasePath` (or `Paths:UserDataDir`) to take effect.

## 5. Two installer variants — lite and full (bundled data)

`packaging/build-deb.sh` and `packaging/danasim-viewer.nsi` now support an
optional data-bundling mode, producing distinctly-named artifacts:

| Variant | Linux | Windows | Contents |
|---|---|---|---|
| Lite  | `danasim-viewer_<ver>_amd64.deb` (~32M)      | `DanaSimViewer-Setup-<ver>-win64.exe` (~45M)      | binaries only — admin points `Terrain:BasePath` at an existing dataset |
| Full  | `danasim-viewer-full_<ver>_amd64.deb` (~259M)| `DanaSimViewer-Setup-<ver>-full-win64.exe` (~237M)| binaries **+ bundled `data/` folder**, `Terrain:BasePath` ships empty → zero-config (§2) |

Build commands and full details are in [packaging/README.md](packaging/README.md).

```bash
# from viewer_net/packaging/
./build-deb.sh                                                                     # lite
./build-deb.sh --with-data ../../data/data_29_10_2024                             # full
makensis danasim-viewer.nsi                                                        # lite
makensis -DBUNDLE_DATA -DDATADIR=../../data/data_29_10_2024 danasim-viewer.nsi    # full
```

> Linux `makensis` only accepts single-dash `-Ddefine[=value]` options — the
> Windows-only `/D...` syntax shown in some NSIS docs will fail with
> `Can't open script "/D..."`.

## 6. Manually testing the bundled-data resolution

The bundled `data/` folder is only read in response to an `InitAgent_Layer`
MQTT event (handled by `InitAgentLayerHandler` →
`IdrisiTerrainDataReader.ReadHeightsAsync`) — nothing reads it eagerly at
startup. The repo's test publisher
(`python/tests/visualizer/publish_test_events.py`) does **not** send this
event, so to exercise the bundled-data path directly, inject one manually:

```bash
mosquitto_pub -h localhost -p 1883 -t "FloodSim/<scenario>/events" -m '{
  "process": "InitAgent_Layer",
  "id": "terrain",
  "data_path": "topo_bathy",
  "data_filename": "topo_bathy"
}'
```

Expect a log line like:
```
Loaded terrain 'topo_bathy' — 5577x9403 (52440531 cells)
```
with no `IDRISI metadata not found` / `Terrain data not found` warnings —
confirming `_basePath` resolved to `{install dir}/data`. (A subsequent
`Terrain height array length ... does not match grid size 0` error is expected
and harmless here — it's because this manual single-event injection skips the
preceding `InitMap_Config` event that normally sizes the grid first; not a
bug in the path-resolution code.)

Verified end-to-end on 2026-06-08 against the freshly-built full `.deb`,
installed via `sudo dpkg -i danasim-viewer-full_1.0.0_amd64.deb`.

## 7. Related: ASP.NET Core Data Protection warnings under IIS

Not fixed (out of scope, flagged for awareness): logs from an IIS deployment
show

```
XmlKeyManager: Neither user profile nor HKLM registry available.
Using an ephemeral key repository. Protected data will be unavailable when
application exits.
```

This is the **same root cause** as §1 — the IIS app-pool identity has no
loadable user profile — surfacing in a different ASP.NET Core subsystem (Data
Protection key storage) than the one we patched. The standard fixes are either
enabling `LoadUserProfile` on the app pool, or explicitly configuring
`services.AddDataProtection().PersistKeysToFileSystem(...)` — conceptually the
same class of fix as `Paths:UserDataDir`, just for a different piece of the
framework.
