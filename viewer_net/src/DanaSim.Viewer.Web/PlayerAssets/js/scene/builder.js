// Pure geometry builder. No DOM access, no fetch, no global state.
//
// Geometry is produced in two stages so that the terrain (which never
// changes between frames or layer toggles) can be computed once and reused:
//
//   1. ``buildTerrainOnly(cxi, czi, cellM)`` — terrain heights and colours
//      for the dry baseline. Cached per chunk × LOD by ``scene.js``.
//
//   2. ``applyFlood(opts, terrain, cxi, czi, cellM)`` — takes that cached
//      terrain plus the current layer opts and produces the final
//      height/colour arrays the X3D nodes consume. Visits cells once and
//      reuses cached values for non-flooded vertices.

import { CHUNK_M, LOD_RANGES, WATER_LIFT } from "../config.js";
import { MAP_W, MAP_D, PNG_COLS, PNG_ROWS, PNG_RES, STATE_COLORS } from "../runtime.js";
import { getTerrainH, terrainColor } from "./terrain.js";

/** Sentinel height (metres) used to push hidden cells well below the camera. */
export const HIDDEN_Z = -99999;

/**
 * @typedef {{
 *   floodPx: Uint8ClampedArray | null,
 *   showTerrain: boolean,
 *   showWater: boolean,
 *   stateMask: boolean[],
 * }} BuildOpts
 *
 * @typedef {{
 *   pts_x: number,
 *   pts_z: number,
 *   heightsArr: number[],
 *   colorsArr: string[],
 * }} ChunkGeometry
 */

function _chunkBounds(cxi, czi) {
  const tx = cxi * CHUNK_M;
  const tz = czi * CHUNK_M;
  const aw = Math.min(CHUNK_M, MAP_W - tx);
  const ad = Math.min(CHUNK_M, MAP_D - tz);
  return { tx, tz, aw, ad };
}

function _gridSize(aw, ad, cellM) {
  return {
    pts_x: Math.floor(aw / cellM) + 1,
    pts_z: Math.floor(ad / cellM) + 1,
  };
}

/**
 * Compute the dry-only height and colour arrays for one LOD level inside one
 * chunk. Heights are kept as numbers (not pre-formatted strings) so callers
 * can join them once at render time, avoiding per-cell ``toFixed`` cost.
 *
 * @param {number} cxi
 * @param {number} czi
 * @param {number} cellM
 * @returns {ChunkGeometry}
 */
export function buildTerrainOnly(cxi, czi, cellM) {
  const { tx, tz, aw, ad } = _chunkBounds(cxi, czi);
  const { pts_x, pts_z } = _gridSize(aw, ad, cellM);
  const n = pts_x * pts_z;
  const heightsArr = new Array(n);
  const colorsArr = new Array(n);

  let i = 0;
  for (let lz = 0; lz < pts_z; lz++) {
    for (let lx = 0; lx < pts_x; lx++) {
      const px = Math.min(Math.floor((tx + lx * cellM) / PNG_RES), PNG_COLS - 1);
      const pz = Math.min(Math.floor((tz + lz * cellM) / PNG_RES), PNG_ROWS - 1);
      const h = getTerrainH(px, pz);
      heightsArr[i] = h;
      colorsArr[i] = terrainColor(h);
      i++;
    }
  }

  return { pts_x, pts_z, heightsArr, colorsArr };
}

/**
 * Apply the current layer opts on top of pre-computed terrain. Only flooded
 * cells trigger image lookups; dry cells are filled by copying the cached
 * terrain values, so the bulk of the inner loop is plain array copies.
 *
 * Visibility rules:
 *   - water off (or no floodPx): no flood overlay; dry cells use terrain or
 *     are sunk to ``HIDDEN_Z`` if ``showTerrain`` is false.
 *   - water on: flooded cells whose state passes ``stateMask`` are lifted by
 *     ``WATER_LIFT[state]`` and recoloured. Cells filtered out by the mask
 *     fall back to the dry rule.
 *
 * @param {BuildOpts} opts
 * @param {ChunkGeometry} terrain  cached output of ``buildTerrainOnly``
 * @param {number} cxi
 * @param {number} czi
 * @param {number} cellM
 * @returns {ChunkGeometry}
 */
export function applyFlood(opts, terrain, cxi, czi, cellM) {
  const { floodPx, showTerrain, showWater, stateMask } = opts;
  const { pts_x, pts_z, heightsArr: tHeights, colorsArr: tColors } = terrain;
  const n = pts_x * pts_z;
  const heightsArr = new Array(n);
  const colorsArr = new Array(n);

  // Initialise from terrain cache (or sink to hidden Z if terrain is off).
  if (showTerrain) {
    for (let i = 0; i < n; i++) {
      heightsArr[i] = tHeights[i];
      colorsArr[i] = tColors[i];
    }
  } else {
    for (let i = 0; i < n; i++) {
      heightsArr[i] = HIDDEN_Z;
      colorsArr[i] = tColors[i];
    }
  }

  if (!showWater || !floodPx) {
    return { pts_x, pts_z, heightsArr, colorsArr };
  }

  // Overlay the flooded cells. Cells the mask filters out keep the dry value
  // already written above, so they fall back to terrain colour without a lift.
  const { tx, tz } = _chunkBounds(cxi, czi);
  let i = 0;
  for (let lz = 0; lz < pts_z; lz++) {
    for (let lx = 0; lx < pts_x; lx++) {
      const px = Math.min(Math.floor((tx + lx * cellM) / PNG_RES), PNG_COLS - 1);
      const pz = Math.min(Math.floor((tz + lz * cellM) / PNG_RES), PNG_ROWS - 1);
      const rawSt = floodPx[(pz * PNG_COLS + px) * 4];
      if (rawSt > 0 && stateMask[Math.min(rawSt, stateMask.length - 1)]) {
        const st = Math.min(rawSt, WATER_LIFT.length - 1);
        heightsArr[i] = tHeights[i] + WATER_LIFT[st];
        colorsArr[i] = STATE_COLORS[Math.min(rawSt, STATE_COLORS.length - 1)];
      }
      i++;
    }
  }

  return { pts_x, pts_z, heightsArr, colorsArr };
}

/**
 * X3D markup for one LOD shape inside a chunk.
 *
 * @param {string} def
 * @param {number} cellM
 * @param {ChunkGeometry} geom
 * @returns {string}
 */
export function shapeHTML(def, cellM, geom) {
  const { pts_x, pts_z, heightsArr, colorsArr } = geom;
  return `<Shape>
    <Appearance><Material ambientIntensity="1" diffuseColor="1 1 1"/></Appearance>
    <ElevationGrid DEF="${def}"
      xDimension="${pts_x}" zDimension="${pts_z}"
      xSpacing="${cellM}" zSpacing="${cellM}"
      height="${heightsArr.join(" ")}" solid="false">
      <Color DEF="${def}_C" color="${colorsArr.join(" ")}"/>
    </ElevationGrid>
  </Shape>`;
}

/**
 * Wrap a chunk's LOD shapes in the `<LOD>` markup x_ite consumes. Callers
 * are responsible for appending the `<WorldInfo info="fuera_de_rango"/>`
 * out-of-range marker to ``lodShapesHtml`` beforehand.
 *
 * @param {number} cxi
 * @param {number} czi
 * @param {string} lodShapesHtml  pre-built LOD ``<Shape>`` elements (+ WorldInfo)
 * @returns {string}
 */
export function lodWrapperHTML(cxi, czi, lodShapesHtml) {
  const { aw, ad } = _chunkBounds(cxi, czi);
  return `<LOD range="${LOD_RANGES}" center="${(aw / 2).toFixed(1)} 0 ${(ad / 2).toFixed(1)}">
      ${lodShapesHtml}
    </LOD>`;
}

/**
 * Wrap a chunk's content in the translated, identifiable Transform x_ite
 * consumes. ``innerHtml`` may be a single `<Shape>` (initial coarse build)
 * or the output of ``lodWrapperHTML`` (full multi-LOD set).
 *
 * @param {number} cxi
 * @param {number} czi
 * @param {string} innerHtml
 * @returns {string}
 */
export function chunkMarkup(cxi, czi, innerHtml) {
  const { tx, tz } = _chunkBounds(cxi, czi);
  return `<Transform DEF="Chunk_${cxi}_${czi}" translation="${tx} 0 ${tz}">
    ${innerHtml}
  </Transform>`;
}
