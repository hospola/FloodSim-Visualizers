namespace DanaSim.Viewer.Infrastructure.Config;

/// <summary>
/// User-writable paths for the app's data and config files.
/// Defaults to the OS user-profile directory (~/.config/danasim-viewer on Linux,
/// %APPDATA%\danasim-viewer on Windows), which can be overridden via Configure —
/// e.g. set "Paths:UserDataDir" in appsettings.json on hosts (like IIS app pool
/// identities) where the special-folder lookup doesn't resolve to a writable path.
/// </summary>
public static class AppPaths
{
    private static string? _overrideDir;

    /// <summary>Must be called once at startup, before any other AppPaths member is touched.</summary>
    public static void Configure(string? userDataDir) =>
        _overrideDir = string.IsNullOrWhiteSpace(userDataDir) ? null : userDataDir;

    private static string Base => _overrideDir ?? Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "danasim-viewer");

    public static string UserConfigFile => Path.Combine(Base, "user-config.json");
    public static string LogsDirectory  => Path.Combine(Base, "logs");

    public static void EnsureBaseExists() => Directory.CreateDirectory(Base);
}
