using DanaSim.Viewer.Domain.ValueObjects;

namespace DanaSim.Viewer.Domain.Events;

public sealed record FrameReadyEvent(GridMeta Meta, FrameData Frame);
