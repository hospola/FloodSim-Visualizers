
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os

from . import config
from .palette import Palette

class GridVisualizer:
    """
    Guarda el estado del grid como imágenes PNG de alta resolución.
    CORREGIDO: Usa vmin/vmax en lugar de norm para imsave.
    """

    def __init__(self, output_folder="output_frames", palette: Palette | None = None):
        self.output_folder = output_folder
        self.frame_count = 0
        self._last_grid_hash = None
        self._last_saved_step = None

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"Carpeta creada: {self.output_folder}")

        self.cmap, self.vmin, self.vmax = self._build_colormap(palette or Palette.default())

    @staticmethod
    def _build_colormap(palette: Palette):
        return mcolors.ListedColormap(palette.hex_colors()), palette.min_value, palette.max_value

    def save_snapshot(self, grid_data, step_index=None):
        """
        Guarda la matriz actual como una imagen PNG.
        """
        if step_index is None:
            step_index = self.frame_count

        current_hash = hash(grid_data.tobytes())
        if self._last_grid_hash == current_hash and self._last_saved_step == step_index:
            return
        
        filename = os.path.join(self.output_folder, f"sim_{step_index:05d}.png")
        
        plt.imsave(
            filename, 
            grid_data, 
            cmap=self.cmap, 
            vmin=self.vmin,
            vmax=self.vmax,
            origin='upper'
        )
        
        self.frame_count += 1
        self._last_grid_hash = current_hash
        self._last_saved_step = step_index
        # Opcional: imprimir solo cada X frames para no ensuciar la consola
        if config.DEBUG_MODE:
             print(f"Imagen guardada: {filename}")

    def close(self):
        pass
