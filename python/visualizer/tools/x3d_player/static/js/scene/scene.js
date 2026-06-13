// Scene assembly — drives the initial bake and incremental updates.
//
// Holds DOM-side state (node cache, async sequence number, the latest flood
// pixel buffer) so consumers only think in terms of "the user changed the
// frame" or "the user toggled a layer".
//
// Performance: the dry-only terrain geometry is computed once per chunk × LOD
// during `buildScene` and kept in `_terrainCache` (numeric arrays plus the
// pre-joined strings used directly when water is off). Subsequent updates
// either swap to those cached strings (fast path) or call `applyFlood` which
// reuses the cached arrays as a baseline, so dry cells never re-trigger the
// terrain image lookup or the colour ramp.

import { CHUNK_M, LOD_SIZES } from "../config.js";
import { MAP_W, MAP_D } from "../runtime.js";
import {
  HIDDEN_Z,
  applyFlood,
  buildTerrainOnly,
  chunkMarkup,
  shapeHTML,
} from "./builder.js";

/** @typedef {import("./builder.js").BuildOpts} BuildOpts */
/** @typedef {import("./builder.js").ChunkGeometry} ChunkGeometry */

/** @typedef {{
 *   geom: ChunkGeometry,
 *   heightsStr: string,
 *   colorsStr: string,
 *   hiddenStr: string,
 * }} TerrainCacheEntry */

/** Cache of `<ElevationGrid DEF=…>` nodes keyed by chunk DEF. */
const _gridNodes = new Map();
/** Cache of `<Color DEF=…>` nodes keyed by chunk DEF (with `_C` suffix). */
const _colorNodes = new Map();
/** Per chunk × LOD pre-computed dry geometry. Populated once at build time. */
/** @type {Map<string, TerrainCacheEntry>} */
const _terrainCache = new Map();

/** Latest flood pixel buffer applied to the scene. Used by `setLayers` so the
 *  caller does not have to re-fetch the PNG when only toggles changed. */
let _floodPx = null;

/** Sequence counter used to cancel stale `_applyOpts` calls when a fresher
 *  one arrives. Each call captures `mySeq` and bails when superseded. */
let _seq = 0;

function _cacheNodes() {
  document.querySelectorAll("ElevationGrid[DEF]").forEach(el =>
    _gridNodes.set(el.getAttribute("DEF"), el));
  document.querySelectorAll("Color[DEF]").forEach(el =>
    _colorNodes.set(el.getAttribute("DEF"), el));
}

function _chunkSteps() {
  return {
    cx: Math.ceil(MAP_W / CHUNK_M),
    cz: Math.ceil(MAP_D / CHUNK_M),
  };
}

function _populateCache(cxi, czi, cellM) {
  const def = `C${cxi}_${czi}_${cellM}`;
  const geom = buildTerrainOnly(cxi, czi, cellM);
  const n = geom.heightsArr.length;
  const hidden = new Array(n);
  for (let i = 0; i < n; i++) hidden[i] = HIDDEN_Z;
  _terrainCache.set(def, {
    geom,
    heightsStr: geom.heightsArr.join(" "),
    colorsStr:  geom.colorsArr.join(" "),
    hiddenStr:  hidden.join(" "),
  });
  return def;
}

/**
 * Build every chunk and inject the resulting markup into the page. Populates
 * the terrain cache as a side-effect so subsequent updates are fast.
 *
 * @param {Uint8ClampedArray | null} initFloodPx initial frame (frame 0)
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 * @param {(message: string) => void} [onProgress] optional progress callback
 */
export async function buildScene(initFloodPx, layerOpts, onProgress) {
  _floodPx = initFloodPx;
  _terrainCache.clear();

  const opts = _withFlood(layerOpts);
  const { cx: cxSteps, cz: czSteps } = _chunkSteps();
  const total = cxSteps * czSteps;
  const parts = [];

  for (let cz = 0; cz < czSteps; cz++) {
    for (let cx = 0; cx < cxSteps; cx++) {
      let lodShapes = "";
      for (const cellM of LOD_SIZES) {
        const def = _populateCache(cx, cz, cellM);
        const cached = _terrainCache.get(def);
        const finalGeom = applyFlood(opts, cached.geom, cx, cz, cellM);
        lodShapes += shapeHTML(def, cellM, finalGeom);
      }
      lodShapes += '<WorldInfo info="fuera_de_rango"/>';
      parts.push(chunkMarkup(cx, cz, lodShapes));
    }
    if (onProgress) {
      onProgress(`Building scene… ${(cz + 1) * cxSteps}/${total} chunks`);
    }
    await new Promise(r => setTimeout(r, 0));
  }

  document.getElementById("terrain_container").innerHTML = parts.join("");
  _cacheNodes();
}

/**
 * Apply a new flood frame, updating the cached pixel buffer.
 * @param {Uint8ClampedArray | null} floodPx
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 */
export function setFrame(floodPx, layerOpts) {
  _floodPx = floodPx;
  return _applyOpts(_withFlood(layerOpts));
}

/**
 * Re-apply the current frame with new layer toggles. No PNG fetch — uses
 * the cached `_floodPx` so toggling is instantaneous.
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 */
export function setLayers(layerOpts) {
  return _applyOpts(_withFlood(layerOpts));
}

function _withFlood(layerOpts) {
  return { ...layerOpts, floodPx: _floodPx };
}

/**
 * Walk cached chunk nodes and rewrite their height/colour attributes.
 * Cancellable: a later call with a fresher request supersedes an in-flight
 * one. Iterates LOD levels coarsest-first (LOD2 → LOD1 → LOD0) so the
 * overview viewer sees the whole map redraw within milliseconds; the dense
 * close-range LOD finishes last but is invisible until the user zooms in.
 *
 * @param {BuildOpts} opts
 */
async function _applyOpts(opts) {
  const mySeq = ++_seq;
  const { cx: cxSteps, cz: czSteps } = _chunkSteps();
  // Coarsest LOD first (largest cellM). LOD_SIZES is [25, 100, 500] — reverse
  // so we iterate [500, 100, 25] = LOD2, LOD1, LOD0.
  const orderedLods = LOD_SIZES.slice().reverse();
  const fastPath = !opts.showWater || !opts.floodPx;

  for (const cellM of orderedLods) {
    for (let czi = 0; czi < czSteps; czi++) {
      for (let cxi = 0; cxi < cxSteps; cxi++) {
        if (mySeq !== _seq) return;  // superseded by a newer request

        const def = `C${cxi}_${czi}_${cellM}`;
        const grid = _gridNodes.get(def);
        const col = _colorNodes.get(def + "_C");
        const cached = _terrainCache.get(def);
        if (!grid || !col || !cached) continue;

        if (fastPath) {
          // Water off — no per-cell work, just swap to pre-joined strings.
          grid.setAttribute("height", opts.showTerrain ? cached.heightsStr : cached.hiddenStr);
          col.setAttribute("color", cached.colorsStr);
        } else {
          const data = applyFlood(opts, cached.geom, cxi, czi, cellM);
          grid.setAttribute("height", data.heightsArr.join(" "));
          col.setAttribute("color", data.colorsArr.join(" "));
        }
      }
      await new Promise(r => setTimeout(r, 0));
    }
  }
}
