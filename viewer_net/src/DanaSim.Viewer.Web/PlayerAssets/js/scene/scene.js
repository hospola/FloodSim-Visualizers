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
  lodWrapperHTML,
  shapeHTML,
} from "./builder.js";

/** Coarsest LOD — used for the fast first-paint pass in `buildScene`. */
const COARSE_LOD = LOD_SIZES[LOD_SIZES.length - 1];
/** Finer LODs, built progressively afterwards by `_refineDetail`. */
const FINE_LODS = LOD_SIZES.slice(0, -1);

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
/** Per-chunk `<Transform DEF="Chunk_{cx}_{cz}">` nodes, populated by stage 1
 *  of `buildScene` so `_refineDetail` can replace their content in place. */
const _chunkNodes = new Map();

/** Latest flood pixel buffer applied to the scene. Used by `setLayers` so the
 *  caller does not have to re-fetch the PNG when only toggles changed. */
let _floodPx = null;

/** Latest layer toggles, used by `_refineDetail` for chunks it builds after
 *  the user has changed frame/layers since `buildScene` was called. */
let _layerOpts = {};

/** Sequence counter used to cancel stale `_applyOpts` calls when a fresher
 *  one arrives. Each call captures `mySeq` and bails when superseded. */
let _seq = 0;

function _cacheNodesWithin(root) {
  root.querySelectorAll("ElevationGrid[DEF]").forEach(el =>
    _gridNodes.set(el.getAttribute("DEF"), el));
  root.querySelectorAll("Color[DEF]").forEach(el =>
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
 * Stage 1 of the build: inject only the coarsest LOD for every chunk so the
 * page becomes interactive almost immediately. Stage 2 (`_refineDetail`)
 * fills in the finer LODs afterwards in the background.
 *
 * @param {Uint8ClampedArray | null} initFloodPx initial frame (frame 0)
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 * @param {(message: string) => void} [onProgress] optional progress callback
 */
export async function buildScene(initFloodPx, layerOpts, onProgress) {
  const t0 = performance.now();
  _floodPx = initFloodPx;
  _layerOpts = layerOpts;
  _terrainCache.clear();
  _gridNodes.clear();
  _colorNodes.clear();
  _chunkNodes.clear();

  const opts = _withFlood(layerOpts);
  const { cx: cxSteps, cz: czSteps } = _chunkSteps();
  const total = cxSteps * czSteps;
  const parts = [];

  for (let cz = 0; cz < czSteps; cz++) {
    for (let cx = 0; cx < cxSteps; cx++) {
      const def = _populateCache(cx, cz, COARSE_LOD);
      const cached = _terrainCache.get(def);
      const finalGeom = applyFlood(opts, cached.geom, cx, cz, COARSE_LOD);
      parts.push(chunkMarkup(cx, cz, shapeHTML(def, COARSE_LOD, finalGeom)));
    }
  }

  document.getElementById("terrain_container").innerHTML = parts.join("");
  _cacheNodesWithin(document);
  document.querySelectorAll("[DEF^='Chunk_']").forEach(el =>
    _chunkNodes.set(el.getAttribute("DEF"), el));

  console.log(
    `[PERF] buildScene stage1: total=${(performance.now() - t0).toFixed(0)}ms ` +
    `(${total} chunks @ ${COARSE_LOD}m)`);

  // Fire-and-forget — refines every chunk to full LOD detail in the background.
  _refineDetail(cxSteps, czSteps, total, onProgress);
}

/**
 * Stage 2: progressively replace each chunk's coarse-only content with the
 * full multi-LOD `<LOD>` set, ordered from the map center outward so the
 * default view sharpens first. Yields between chunks to keep the page
 * responsive instead of blocking on one giant scene compile.
 *
 * @param {number} cxSteps
 * @param {number} czSteps
 * @param {number} total
 * @param {(message: string) => void} [onProgress]
 */
async function _refineDetail(cxSteps, czSteps, total, onProgress) {
  // Yield immediately so the synchronous part of this function (which would
  // otherwise run before the first `await`, inside buildScene's call stack)
  // doesn't delay buildScene's caller.
  await new Promise(r => setTimeout(r, 0));

  const t0 = performance.now();
  const centerX = MAP_W / 2;
  const centerZ = MAP_D / 2;

  const chunks = [];
  for (let cz = 0; cz < czSteps; cz++) {
    for (let cx = 0; cx < cxSteps; cx++) {
      const dx = (cx + 0.5) * CHUNK_M - centerX;
      const dz = (cz + 0.5) * CHUNK_M - centerZ;
      chunks.push({ cx, cz, dist: dx * dx + dz * dz });
    }
  }
  chunks.sort((a, b) => a.dist - b.dist);

  let done = 0;
  let computeMsTotal = 0;
  let domMsTotal = 0;
  let maxChunkMs = 0;
  let over16 = 0;
  let over50 = 0;
  for (const { cx, cz } of chunks) {
    const cT0 = performance.now();
    const opts = _withFlood(_layerOpts);
    let lodShapes = "";
    for (const cellM of LOD_SIZES) {
      const def = cellM === COARSE_LOD
        ? `C${cx}_${cz}_${cellM}`
        : _populateCache(cx, cz, cellM);
      const cached = _terrainCache.get(def);
      const finalGeom = applyFlood(opts, cached.geom, cx, cz, cellM);
      lodShapes += shapeHTML(def, cellM, finalGeom);
    }
    lodShapes += '<WorldInfo info="fuera_de_rango"/>';
    const cT1 = performance.now();

    const chunkEl = _chunkNodes.get(`Chunk_${cx}_${cz}`);
    if (chunkEl) {
      chunkEl.innerHTML = lodWrapperHTML(cx, cz, lodShapes);
      _cacheNodesWithin(chunkEl);
    }
    const cT2 = performance.now();
    const chunkMs = cT2 - cT0;
    computeMsTotal += cT1 - cT0;
    domMsTotal += cT2 - cT1;
    maxChunkMs = Math.max(maxChunkMs, chunkMs);
    if (chunkMs > 16) over16++;
    if (chunkMs > 50) over50++;
    if (chunkMs > 30) {
      console.log(`[PERF] refineDetail chunk ${cx}_${cz}: compute=${(cT1 - cT0).toFixed(0)}ms dom=${(cT2 - cT1).toFixed(0)}ms`);
    }

    done++;
    if (onProgress && (done % Math.ceil(total / 4) === 0 || done === total)) {
      onProgress(`Refining detail… ${done}/${total} chunks`);
    }
    await new Promise(r => setTimeout(r, 0));
  }

  console.log(
    `[PERF] refineDetail: total=${(performance.now() - t0).toFixed(0)}ms (${total} chunks, ` +
    `compute=${computeMsTotal.toFixed(0)}ms, dom=${domMsTotal.toFixed(0)}ms, ` +
    `maxChunk=${maxChunkMs.toFixed(0)}ms, chunks>16ms=${over16}, chunks>50ms=${over50})`);
}

/**
 * Apply a new flood frame, updating the cached pixel buffer.
 * @param {Uint8ClampedArray | null} floodPx
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 */
export function setFrame(floodPx, layerOpts) {
  _floodPx = floodPx;
  _layerOpts = layerOpts;
  return _applyOpts(_withFlood(layerOpts));
}

/**
 * Re-apply the current frame with new layer toggles. No PNG fetch — uses
 * the cached `_floodPx` so toggling is instantaneous.
 * @param {Omit<BuildOpts, "floodPx">} layerOpts
 */
export function setLayers(layerOpts) {
  _layerOpts = layerOpts;
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
  const t0 = performance.now();
  const { cx: cxSteps, cz: czSteps } = _chunkSteps();
  // Coarsest LOD first (largest cellM). LOD_SIZES is [25, 100, 500] — reverse
  // so we iterate [500, 100, 25] = LOD2, LOD1, LOD0.
  const orderedLods = LOD_SIZES.slice().reverse();
  const fastPath = !opts.showWater || !opts.floodPx;
  let updated = 0;

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
        updated++;
      }
      await new Promise(r => setTimeout(r, 0));
    }
  }

  if (mySeq === _seq) {
    console.log(
      `[PERF] _applyOpts: total=${(performance.now() - t0).toFixed(0)}ms ` +
      `(${updated} nodes updated, fastPath=${fastPath})`);
  }
}
