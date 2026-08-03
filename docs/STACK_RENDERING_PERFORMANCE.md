# Stack Rendering Performance Optimization

## Problem

When viewing an overlay floor (e.g., upstairs) with compositing enabled, the `stack_layers_ms` metric for a small 9x9 map could reach 4-5 seconds. This was dominated by repeated stack LOS calculations across multiple functions.

## Root Cause

The `build_stack_render_layers()` function calls several functions that perform expensive stack-aware line-of-sight computations:

1. **`_reveal_base_surround_for_overlay_view()`** - calls `stack_base_visible_from_overlay()` per base-map tile (called with same viewer+world-coords repeatedly)
2. **`build_base_peek_underlay()`** - calls `_viewer_can_peek_through()` per overlay-floor tile (100s of redundant calls)
3. **`_viewer_can_peek_through()`** - calls `_peek_underlay_world_target()` + `stack_base_visible_from_overlay()` per tile
4. **`_annotate_stack_tiles()`** - calls `_peek_candidate_at()` + `_viewer_can_peek_through()` per overlay tile
5. **`_peek_underlay_world_target()`** - computes `_outdoor_cell_beyond_window()` + `_edge_peek_world_target()` per tile

Each `stack_base_visible_from_overlay()` call performs:
- `entity_squares()` lookup
- `bresenham_line_of_sight()` ray casting
- `_overlay_outdoor_egress_allowed()` ray tracing through overlay footprint
- `_parapet_blocks_outdoor_sight()` perimeter checks
- `_overlay_footprint_ray_blocks()` interior wall checks
- `_base_outdoor_ray_blocks()` ground-level geometry checks

These functions were called thousands of times with identical `(stack, viewer, viewer_map, base_map, wx, wy)` keys during a single render, with no caching between calls.

## Solution

Added `RenderCache` class (`natural20/web/stack_renderer.py`) that provides per-request memoization for:

- **`stack_los`** - Caches `stack_base_visible_from_overlay(stack, viewer, viewer_map, base_map, wx, wy)` results
- **`peek_target`** - Caches `_peek_underlay_world_target(stack, base_floor, overlay_floor, viewer_map, entity, lx, ly)` results  
- **`peek_candidate`** - Caches `_peek_candidate_at(stack, floor, lx, ly)` results

The cache is created in `build_stack_render_layers()` and threaded through the call chain via an optional `cache` keyword argument to:

- `_reveal_base_surround_for_overlay_view(..., cache=None)`
- `build_base_peek_underlay(..., cache=None)`
- `_viewer_can_peek_through(..., cache=None)`
- `_peek_underlay_world_target(..., cache=None)`
- `_peek_candidate_at(..., cache=None)`
- `_is_edge_peek_cell(..., cache=None)`
- `_annotate_stack_tiles(..., cache=None)`

## Key Implementation Details

### Cache Key Structure

- **Stack LOS**: `('los', id(stack), id(viewer), viewer_map_name, target_map_name, wx, wy)`
- **Peek Target**: `('peek_tgt', stack_key, base_map_name, overlay_map_name, lx, ly)`
- **Peek Candidate**: `('peek_cand', stack_key, map_name, lx, ly)`

### Cache-Aware Wrapper

`_cached_stack_base_visible()` wraps `stack_base_visible_from_overlay()` with cache lookup/set, ensuring the expensive function is only called once per unique key.

### Backward Compatibility

All cache parameters are optional keyword-only arguments (`cache=None`), maintaining backward compatibility with any external callers that invoke these functions directly.

## Expected Performance Impact

For a typical composite render with:
- 9x9 base map + 15x15 overlay map
- 1 POV entity
- 29 base tiles + 225 overlay tiles

The cache should eliminate 80-95% of redundant LOS calculations, reducing `stack_layers_ms` from ~4-5 seconds to <500ms.

## Files Modified

- `natural20/web/stack_renderer.py` - Added `RenderCache` class, updated function signatures, added `_cached_stack_base_visible()` wrapper

## Testing

All existing stack-related tests pass (22 tests in `tests/test_map_stack.py` and `tests/test_map_stack_los.py`).

## Future Optimizations

1. **Cross-request caching**: For rapid successive renders (e.g., mouse movement), consider a short-lived LRU cache keyed on stack+map+entity changes
2. **Tile-level memoization**: Cache individual tile render results in `JsonRenderer` when stack state hasn't changed
3. **Batch bresenham**: Pre-compute all bresenham rays for a viewer position and reuse across tiles
