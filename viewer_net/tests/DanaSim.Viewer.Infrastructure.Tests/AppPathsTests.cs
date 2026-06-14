using DanaSim.Viewer.Infrastructure.Config;
using FluentAssertions;

namespace DanaSim.Viewer.Infrastructure.Tests;

/// <summary>
/// AppPaths.Configure mutates shared static state, so each test resets it
/// afterwards (in a finally block) to avoid leaking the override across tests.
/// </summary>
[Collection("AppPaths")]
public class AppPathsTests
{
    [Fact]
    public void Configure_WithOverride_AnchorsUserConfigFileUnderIt()
    {
        var overrideDir = Path.Combine(Path.GetTempPath(), "danasim-viewer-test-" + Guid.NewGuid());
        try
        {
            AppPaths.Configure(overrideDir);

            AppPaths.UserConfigFile.Should().Be(Path.Combine(overrideDir, "user-config.json"));
            AppPaths.LogsDirectory.Should().Be(Path.Combine(overrideDir, "logs"));
        }
        finally
        {
            AppPaths.Configure(null);
        }
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Configure_WithBlankValue_FallsBackToDefaultBase(string? blank)
    {
        AppPaths.Configure(blank);

        var defaultBase = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "danasim-viewer");

        AppPaths.UserConfigFile.Should().Be(Path.Combine(defaultBase, "user-config.json"));
        AppPaths.LogsDirectory.Should().Be(Path.Combine(defaultBase, "logs"));
    }

    [Fact]
    public void EnsureBaseExists_CreatesTheConfiguredDirectory()
    {
        var overrideDir = Path.Combine(Path.GetTempPath(), "danasim-viewer-test-" + Guid.NewGuid());
        try
        {
            AppPaths.Configure(overrideDir);
            Directory.Exists(overrideDir).Should().BeFalse();

            AppPaths.EnsureBaseExists();

            Directory.Exists(overrideDir).Should().BeTrue();
        }
        finally
        {
            AppPaths.Configure(null);
            if (Directory.Exists(overrideDir)) Directory.Delete(overrideDir, recursive: true);
        }
    }
}
