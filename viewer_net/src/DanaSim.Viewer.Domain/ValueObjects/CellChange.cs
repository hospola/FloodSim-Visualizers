using DanaSim.Viewer.Domain.Enums;

namespace DanaSim.Viewer.Domain.ValueObjects;

/// <summary>
/// A single cell state update received in an EYE_SetState_Layer event.
/// Index is the flat cell index: row * numCols + col.
/// </summary>
public readonly record struct CellChange(int Index, FloodState State, float WaterDepthM);
