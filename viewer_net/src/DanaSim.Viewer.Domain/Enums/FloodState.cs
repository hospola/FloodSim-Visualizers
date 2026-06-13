namespace DanaSim.Viewer.Domain.Enums;

/// <summary>
/// Risk level for a grid cell. Values 0-5 match the protocol's numeric state field.
/// </summary>
public enum FloodState : byte
{
    Dry = 0,
    Risk1 = 1,
    Risk2 = 2,
    Risk3 = 3,
    Risk4 = 4,
    Risk5 = 5,
    Obstacle = 6,
    ObstacleDestroyed = 7,
}
