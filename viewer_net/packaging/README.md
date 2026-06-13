# Building the DanaSim Viewer installers

`publish/` is gitignored — installers aren't committed to the repo. To produce
them from a clean checkout, run the steps below from `viewer_net/`.

## 1. Publish the app (single-file, self-contained)

```bash
dotnet publish src/DanaSim.Viewer.Web/DanaSim.Viewer.Web.csproj -c Release -r linux-x64 \
  --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true \
  -o publish/linux-x64

dotnet publish src/DanaSim.Viewer.Web/DanaSim.Viewer.Web.csproj -c Release -r win-x64 \
  --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true \
  -o publish/win-x64
```

**Windows gotcha:** `PublishSingleFile` does NOT copy `aspnetcorev2_inprocess.dll`
into `publish/win-x64/` — it gets bundled into the single-file exe instead, but
IIS needs it as a standalone DLL next to the exe to load the in-process hosting
module (`web.config` points `aspNetCore` at it directly). Copy it manually after
publishing:

```bash
cp src/DanaSim.Viewer.Web/bin/Release/net10.0/win-x64/aspnetcorev2_inprocess.dll publish/win-x64/
```

Without this step, `makensis` fails with `File: ... -> no files found` on the
line that packages `aspnetcorev2_inprocess.dll`, and an installer built without
it would produce a working dashboard but a broken IIS deployment.

## 2. Build the Linux .deb

Requires `dpkg-deb` and `fakeroot`.

```bash
cd packaging
./build-deb.sh                              # lite — no bundled data
./build-deb.sh --with-data ../../../data/data_29_10_2024   # full — bundles the dataset
```

Produces `publish/danasim-viewer_<version>_amd64.deb` (lite) or
`publish/danasim-viewer-full_<version>_amd64.deb` (full, bundles the data
under `/opt/danasim-viewer/data`).

## 3. Build the Windows installer

Requires NSIS (`makensis`) — works fine cross-compiled from Linux, no Wine
needed.

```bash
cd packaging
makensis danasim-viewer.nsi                                                       # lite
makensis -DBUNDLE_DATA -DDATADIR=../../data/data_29_10_2024 danasim-viewer.nsi    # full
```

Note: on Linux, `makensis` only recognizes single-dash options (`-Ddefine[=value]`)
— the `/D...` syntax shown in Windows NSIS docs won't work here. Forward slashes
in `DATADIR` are fine; NSIS normalizes them to backslashes internally.

Produces `publish/DanaSimViewer-Setup-<version>-win64.exe` (lite) or
`publish/DanaSimViewer-Setup-<version>-full-win64.exe` (full, bundles the data
under `$INSTDIR\data`).

## Lite vs. full installers

- **Lite** (~30-45 MB): no data bundled. The admin points `Terrain:BasePath`
  (or the dashboard's "Terrain base path" field) at wherever the dataset lives
  on the target machine.
- **Full** (~1.6 GB+): bundles a complete dataset (e.g. `data/data_29_10_2024/`,
  currently ~1.6 GB) alongside the executable. `Terrain:BasePath` is left empty
  in `appsettings.json`, and `IdrisiTerrainDataReader` resolves an empty
  `BasePath` to `{app directory}/data` — so it finds the bundled folder with
  zero configuration, regardless of how the app is launched (run.sh/run.bat or
  IIS, whose working directory often differs from the install folder).

Pick the dataset to bundle deliberately — check its size and whether it's
appropriate to redistribute before running a full build; it dramatically
changes the installer's size and build time.

## Bumping the version

Edit `VERSION` in `build-deb.sh` and `APPVERSION` in `danasim-viewer.nsi` —
they're independent and must be kept in sync manually.

## When to rebuild

Rebuild and replace these artifacts whenever a change lands in
`DanaSim.Viewer.Web`, `DanaSim.Viewer.Infrastructure`, or
`DanaSim.Viewer.Application` — anything that affects the published binary,
`appsettings.json` defaults, or `web.config`/`run.sh`/`run.bat` (e.g. the
`AppPaths`/`Paths:UserDataDir` deployment-path handling).
