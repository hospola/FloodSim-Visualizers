"""
Input/Output operations for IDRISI raster formats.

This module provides utilities to read and write raster data in the IDRISI ASCII 
format (.doc and .img files), facilitating the conversion between standard 
numpy-based data structures (like StaticRaster) and disk storage.
"""

from pathlib import Path
from typing import List, Optional

import numpy as np
import rasterio
from loguru import logger
from pyproj import CRS
from rasterio.transform import from_bounds

from .types import SpatialContext, StaticRaster


class IdrisiIO:
    """Handler for reading and writing IDRISI ASCII raster files.

    Provides static methods to interact with raster data, parsing the metadata 
    from `.doc` files and the raw numeric matrices from `.img` files, as well 
    as generating these files from in-memory objects.
    """

    @staticmethod
    def _write_doc(path: Path, data: np.ndarray, spatial_context: SpatialContext) -> None:
        """
        Writes the IDRISI metadata (.doc) file for a given raster.

        Generates the necessary metadata fields required by the IDRISI ASCII
        format, calculating dynamic values like min/max directly from the array.

        Args:
            path (Path): The absolute or relative path where the .doc file will be saved.
            data (np.ndarray): The 2D numpy array containing the raster data.
            spatial_context (SpatialContext): The spatial metadata associated
                with the raster.
        """
        # Safely evaluate data types using numpy's built-in type hierarchy
        if data.dtype == np.int8:
            data_type = 'byte'
        elif np.issubdtype(data.dtype, np.integer):
            data_type = 'integer'
        else:
            data_type = 'real'

        min_val = np.nanmin(data)
        max_val = np.nanmax(data)

        doc_content = (
            f"file format : IDRISI Raster A.1\n"
            f"file title  : \n"
            f"data type   : {data_type}\n"
            f"file type   : ascii\n"
            f"columns     : {spatial_context.width}\n"
            f"rows        : {spatial_context.height}\n"
            f"ref. system : {spatial_context.crs.to_string()}\n"
            f"ref. units  : m\n"
            f"unit dist.  : 1.0\n"
            f"min. X      : {spatial_context.bounds.min_x}\n"
            f"max. X      : {spatial_context.bounds.max_x}\n"
            f"min. Y      : {spatial_context.bounds.min_y}\n"
            f"max. Y      : {spatial_context.bounds.max_y}\n"
            f"pos'n error : unknown\n"
            f"resolution  : {spatial_context.cell_size}\n"
            f"min. value  : {min_val}\n"
            f"max. value  : {max_val}\n"
            f"display min : {min_val}\n"
            f"display max : {max_val}\n"
            f"value units : unspecified\n"
            f"nodata value: {spatial_context.nodata_value}\n"
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(doc_content)

    @staticmethod
    def save(folder_path: Path, filename: str, data: np.ndarray, spatial_context: SpatialContext, save_metadata: bool = True) -> None:
        """
        Saves a raster array and its spatial context to IDRISI ASCII format.

        This creates two files: a .doc file containing the metadata and an .img
        file containing the raw ASCII values of the raster matrix.

        Args:
            folder_path (Path): The directory path where the files will be saved.
            filename (str): The base name for the generated files (without extension).
            data (np.ndarray): The 2D numpy array containing the raster values.
            spatial_context (SpatialContext): The spatial metadata for the raster.
            save_metadata (bool): Indicates whether an additional file should be generated with the spatial context metadata.
        """
        # Ensure output directory exists to prevent FileNotFoundError
        folder_path.mkdir(parents=True, exist_ok=True)

        img_path = folder_path / f"{filename}.img"

        logger.info(f"Saving IDRISI raster to: {folder_path / filename}")

        if(save_metadata):
            doc_path = folder_path / f"{filename}.doc"
            IdrisiIO._write_doc(doc_path, data, spatial_context)

        # Determine appropriate format specifier based on data type hierarchy
        fmt = '%f' if np.issubdtype(data.dtype, np.floating) else '%d'
        np.savetxt(img_path, data, fmt=fmt)

    @staticmethod
    def read(
        folder_path: Path, 
        filename: str, 
        read_metadata: bool = True, 
        spatial_context: Optional[SpatialContext] = None, 
        data_type: str = 'real'
    ) -> StaticRaster:
        """Reads a raster in IDRISI ASCII format from disk.

        This method can read both the metadata (.doc) and the data (.img) files 
        to fully reconstruct a StaticRaster. Alternatively, it can read just the 
        .img file if an external spatial context is provided (useful for 3D cubes).

        Args:
            folder_path (Path): The directory path containing the raster files.
            filename (str): The base name of the files (without extension).
            read_metadata (bool, optional): If True, parses the .doc file to extract 
                spatial context and data type. Defaults to True.
            spatial_context (Optional[SpatialContext], optional): An external spatial 
                context to use if `read_metadata` is False. Defaults to None.
            data_type (str, optional): The expected data type ('real' or 'integer') 
                if `read_metadata` is False. Defaults to 'real'.

        Returns:
            StaticRaster: An object containing the 2D data matrix and its 
                associated spatial context.

        Raises:
            FileNotFoundError: If the required .img or .doc files are not found.
            ValueError: If `read_metadata` is False but no `spatial_context` is provided.
        """
        img_path = folder_path / f"{filename}.img"
        if not img_path.exists():
            raise FileNotFoundError(f"Data file not found: {img_path}")

        if read_metadata:
            # Standard logic: parse the .doc metadata file
            doc_path = folder_path / f"{filename}.doc"
            if not doc_path.exists():
                raise FileNotFoundError(f"Metadata file not found: {doc_path}")

            metadata = {}
            with open(doc_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        metadata[key.strip()] = val.strip()

            cols = int(metadata.get('columns', 0))
            rows = int(metadata.get('rows', 0))
            min_x = float(metadata.get('min. X', 0.0))
            max_x = float(metadata.get('max. X', 0.0))
            min_y = float(metadata.get('min. Y', 0.0))
            max_y = float(metadata.get('max. Y', 0.0))
            data_type = metadata.get('data type', 'real')
            crs_string = metadata.get('ref. system', '')
            
            try:
                crs = CRS.from_string(crs_string)
            except Exception:
                crs = None

            transform = from_bounds(min_x, min_y, max_x, max_y, cols, rows)
            
            ctx = SpatialContext(
                crs=crs, transform=transform, width=cols, height=rows
            )
        else:
            # Delegated logic: context is already provided by a higher-level class
            if spatial_context is None:
                raise ValueError("If read_metadata is False, a spatial_context must be provided.")
            ctx = spatial_context
            rows, cols = ctx.height, ctx.width

        # Read the .img file using the dimensions obtained
        if data_type == 'real':
            dtype = np.float32
        elif data_type == 'byte':
            dtype = np.int8
        else:
            dtype = np.int32

        data = np.loadtxt(img_path, dtype=dtype)
        data = data.reshape((rows, cols))

        return StaticRaster(data=data, spatial_context=ctx)