"""
Data structures and custom types for the flood simulator pipeline.

This module defines the foundational data classes used across the pipeline,
including spatial contexts, bounding boxes, static/dynamic raster representations,
and visualization configurations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

import numpy as np
from affine import Affine
from pyproj import CRS
from rasterio.transform import array_bounds


@dataclass
class Position:
    """
    Represents a specific geographical coordinate point.

    Attributes:
        x (float): The X coordinate (e.g., Longitude or UTM Easting).
        y (float): The Y coordinate (e.g., Latitude or UTM Northing).
        crs (CRS): The Coordinate Reference System of the point.
    """
    x: float
    y: float
    crs: CRS


@dataclass
class Bounds:
    """
    Represents the spatial bounding box of a geographical area.

    Attributes:
        min_x (float): The westernmost X coordinate.
        max_x (float): The easternmost X coordinate.
        min_y (float): The southernmost Y coordinate.
        max_y (float): The northernmost Y coordinate.
    """
    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass
class SpatialContext:
    """
    Defines the spatial properties and metadata of a raster layer.

    Attributes:
        crs (CRS): The Coordinate Reference System.
        transform (Affine): The affine transformation matrix mapping pixel 
            coordinates to spatial coordinates.
        width (int): The number of columns (pixels) in the raster.
        height (int): The number of rows (pixels) in the raster.
        nodata_value (float): The value representing 'no data' or missing pixels.
        bounds (Bounds): The calculated spatial bounding box of the raster.
        cell_size (float): The spatial resolution (pixel size) in map units.
    """
    crs: CRS
    transform: Affine
    width: int
    height: int
    nodata_value: float = field(init=False)
    bounds: Bounds = field(init=False)
    cell_size: float = field(init=False)

    def __post_init__(self) -> None:
        # Assuming square pixels, transform.a represents pixel width
        self.cell_size = self.transform.a

        """Calculates the bounding box based on dimensions and transform."""
        left, bottom, right, top = array_bounds(self.height, self.width, self.transform)

        self.bounds = Bounds(
            min_x=left,
            max_x=right,
            min_y=bottom,
            max_y=top
        )


@dataclass
class StaticRaster:
    """
    Data structure for static 2D maps (e.g., Elevation, Roughness).

    Attributes:
        data (np.ndarray): The 2D numpy array containing the raster values.
        spatial_context (SpatialContext): The spatial metadata for the raster.
        x_coords (np.ndarray): The calculated X coordinates for the cell centers.
        y_coords (np.ndarray): The calculated Y coordinates for the cell centers.
    """
    data: np.ndarray
    spatial_context: SpatialContext
    x_coords: np.ndarray = field(init=False)
    y_coords: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        """Initializes derived spatial properties and coordinate grids."""
        # Calculate coordinates for cell centers
        self.x_coords = np.linspace(
            self.spatial_context.bounds.min_x + self.spatial_context.cell_size / 2, 
            self.spatial_context.bounds.max_x - self.spatial_context.cell_size / 2, 
            self.spatial_context.width
        )
        self.y_coords = np.linspace(
            self.spatial_context.bounds.max_y - self.spatial_context.cell_size / 2,
            self.spatial_context.bounds.min_y + self.spatial_context.cell_size / 2, 
            self.spatial_context.height
        )

        if self.data.dtype == np.int8:
            self.spatial_context.nodata_value = -128.0
        else:
            self.spatial_context.nodata_value = -9999.0

    def get_data_value(self, x: float, y: float) -> float:
        """
        Retrieves the raster value (e.g., elevation) for a specific spatial coordinate.
        
        Args:
            x (float): The X coordinate (e.g., UTM Easting).
            y (float): The Y coordinate (e.g., UTM Northing).
            
        Returns:
            float: The data value at the specified coordinate.
            
        Raises:
            ValueError: If the provided coordinates fall outside the raster bounds.
        """
        bounds = self.spatial_context.bounds
        if not (bounds.min_x <= x <= bounds.max_x) or not (bounds.min_y <= y <= bounds.max_y):
            raise ValueError(f"Coordinate ({x}, {y}) is out of bounds.")

        # Rasters are indexed with row 0 = North (Max Y)
        row = int((bounds.max_y - y) / self.spatial_context.cell_size)
        col = int((x - bounds.min_x) / self.spatial_context.cell_size)

        # Clamping to prevent index out of bounds on exact edges
        col = min(col, self.spatial_context.width - 1)
        row = min(row, self.spatial_context.height - 1)

        return float(self.data[row, col])


@dataclass
class DynamicRaster:
    """
    Data structure for 3D spatiotemporal data cubes (e.g., Hourly rainfall).

    Attributes:
        data (np.ndarray): The 3D numpy array containing the raster values over time.
        timestamps (List[datetime]): A list of datetime objects corresponding 
            to the temporal dimension of the data.
        downgrade_factor (int): The reduction factor (e.g., 2 reduces resolution by half).
        spatial_context (SpatialContext): The spatial metadata for the raster.
    """
    data: np.ndarray 
    timestamps: List[datetime]
    downgrade_factor: int
    spatial_context: SpatialContext

    def __post_init__(self) -> None:
        if self.data.dtype == np.int8:
            self.spatial_context.nodata_value = -128.0
        else:
            self.spatial_context.nodata_value = -9999.0


@dataclass
class VisualConfig:
    """
    Configuration settings for layer visualization and plotting.

    Attributes:
        cbar_unit (str): The measurement unit to display on the colorbar.
        cmap (str): The matplotlib colormap name. Defaults to "viridis".
        figsize (Tuple[int, int]): The dimensions of the generated figure.
        dpi (int): The resolution of the generated figure in dots per inch.
    """
    cbar_unit: str
    cmap: str = "viridis"
    figsize: tuple = (10, 8)
    dpi: int = 150