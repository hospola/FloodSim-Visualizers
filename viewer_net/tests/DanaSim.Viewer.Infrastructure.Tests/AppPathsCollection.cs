namespace DanaSim.Viewer.Infrastructure.Tests;

/// <summary>
/// AppPaths and UserConfigService share global static state (AppPaths.Configure mutates
/// a static base directory; UserConfigService caches AppPaths.UserConfigFile in a
/// `static readonly` field on first use). Tests that touch either must run sequentially,
/// not interleaved with xUnit's default parallel test-class execution.
/// </summary>
[CollectionDefinition("AppPaths", DisableParallelization = true)]
public class AppPathsCollection;
