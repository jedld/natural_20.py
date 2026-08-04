# Performance Optimizations

This document records performance optimizations applied to the VTT engine and webapp.

---

## 1. Server-Side: `Action.__subclasses__()` Caching

**File:** [`natural20/action.py`](natural20/action.py), [`natural20/battle.py`](natural20/battle.py), [`n20-webapp/webapp/utils.py`](n20-webapp/webapp/utils.py)

**Problem:** `Action.__subclasses__()` was called repeatedly for every result item during action commit, causing unnecessary runtime introspection overhead. This contributed to slow `POST /action` responses (~4676ms in one case).

**Fix:**
- Added cached `get_action_subclasses()` in [`natural20/action.py`](natural20/action.py) with lazy initialization.
- Updated [`natural20/battle.py`](natural20/battle.py) `Battle.commit()` to use the cached list.
- Updated out-of-battle commit path in [`n20-webapp/webapp/utils.py`](n20-webapp/webapp/utils.py) to use the cached list.

---

## 2. Server-Side: Adjacent-Tile LOS Shortcut in `JsonRenderer.render()`

**File:** [`natural20/web/json_renderer.py`](natural20/web/json_renderer.py)

**Problem:** The `JsonRenderer.render()` method iterates over ALL tiles (with padding) and calls `cached_can_see_square()` for each tile per POV entity. The `can_see_square()` method runs a Bresenham line-of-sight walk + many `opaque()` checks per tile. For a 23x30 map with padding and 16 entities, this resulted in `json_render_ms=7869.8ms`.

**Fix:** Pre-compute a set of tiles adjacent (8-way) to any POV position. These tiles are always visible, so we skip the full Bresenham walk for them.

```python
# Pre-compute adjacency cache: tiles adjacent (8-way) to any POV position
# are always visible — skip the full can_see_square Bresenham walk.
_adj_visible: set[tuple[int, int]] = set()
_entity_pov_on_map = [e for e in pov_list if e in self.map.entities]
for _ep in _entity_pov_on_map:
    for _sx, _sy in self.map.entity_squares(_ep):
        for _dx in (-1, 0, 1):
            for _dy in (-1, 0, 1):
                nx, ny = _sx + _dx, _sy + _dy
                if 0 <= nx < self.map.size[0] and 0 <= ny < self.map.size[1]:
                    _adj_visible.add((nx, ny))
```

In the render loop, adjacent tiles skip the `can_see_square()` call:

```python
# Adjacent-tile shortcut: skip full can_see_square Bresenham walk
if (x, y) in _adj_visible:
    pass  # Always visible, skip the "not visible" early-exit block
elif len(entity_pov) > 0:
    if not any(cached_can_see_square(entity, (x, y)) for entity in entity_pov):
        # Handle invisible tiles...
```

**Expected impact:** For typical combat scenarios where POV entities are centrally located, this skips the Bresenham walk for ~9× the number of entity squares (3×3 neighborhood). On a 23x30 map with 16 entities, this can save hundreds of Bresenham walks per render.

---

## 3. Client-Side: Path Request Debounce Increase

**File:** [`n20-webapp/webapp/static/engine.js`](n20-webapp/webapp/static/engine.js)

**Problem:** Clicking attack action triggered 15+ `/path` requests during attack hover. The original 50ms debounce was too aggressive — mouseover events fire rapidly as the cursor moves over tile children (sprites, tooltips, etc.), causing repeated requests even with the debounce.

**Fix:** Increased the debounce timer from 50ms to 100ms.

```javascript
// Line ~7519
}, 100);  // Was 50
```

**Expected impact:** Halves the number of path requests during rapid mouse movement. Combined with the existing cache and abort logic, this should reduce `/path` requests from 15+ to ~5-8 per turn during attack targeting.

---

## 4. Client-Side: Action Post Cooldown for `/update` Polling

**File:** [`n20-webapp/webapp/static/engine.js`](n20-webapp/webapp/static/engine.js)

**Problem:** After the player commits an action (attack, spell, etc.), the server emits multiple `refresh_map`/`refresh_tiles` SocketIO events while the action resolves. Each event triggers `scheduleRefreshMap()`, which fetches `/update` from the server. This caused 6+ `/update` requests per turn, each taking 7-8 seconds due to the rendering bottleneck.

**Fix:** Added an `actionPostTimestamp` variable that records when the player submits an action. The `scheduleRefreshMap()` function now checks a 500ms cooldown window — if called within 500ms of the action post, it returns immediately without making the `/update` request. The cooldown is reset when the server signals `end_of_turn` or `start_of_turn`.

```javascript
// Variable declaration (line ~390)
let actionPostTimestamp = 0; // Monotonic timestamp of the last /action POST for cooldown tracking.

// scheduleRefreshMap cooldown (line ~2297)
if (typeof actionPostTimestamp === 'number' && (Date.now() - actionPostTimestamp) < 500) {
    return Promise.resolve();
}

// Set on action success (line ~8592, ~1083)
actionPostTimestamp = Date.now();

// Reset on turn state changes (line ~6627)
if (data && typeof data === 'object' && (data.type === 'end_of_turn' || data.type === 'start_of_turn')) {
    actionPostTimestamp = 0;
}
```

**Expected impact:** Reduces `/update` requests per turn from 6+ to 1-2 (only the first and any post-cooldown requests). This is especially impactful when combined with the server-side rendering optimizations, as each `/update` will be faster.

---

## 5. Client-Side: Server-Side Caching (Pre-existing)

**File:** [`n20-webapp/webapp/blueprints/navigation.py`](n20-webapp/webapp/blueprints/navigation.py)

The `/update` endpoint already has:
- `render_epoch`-based caching with per-user render epoch tracking
- `render_cache=hit` when the map hasn't changed since the last request
- SocketIO `refresh_map` event batching via `scheduleRefreshMap()` debounce

These mechanisms ensure that if the map state hasn't changed, `/update` returns a cache hit with minimal processing.

---

## Monitoring and Verification

To verify these optimizations:

1. **Browser DevTools Network Tab:** Check the number and timing of `/update` and `/path` requests during a turn.
2. **Server Logs:** Look for `json_render_ms` in the `/update` endpoint logs. Before optimization: ~7870ms. After optimization: expect significant reduction due to adjacent-tile LOS shortcut.
3. **Action Commit Time:** Look for `action_commit_ms` in `POST /action` logs. Before optimization: ~4676ms. After optimization: expect significant reduction due to subclass caching.

### Key Metrics

| Metric | Before | Expected After |
|--------|--------|----------------|
| `POST /action` total time | ~4676ms | ~200-500ms |
| `json_render_ms` per `/update` | ~7870ms | ~500-2000ms |
| `/path` requests per turn | 15+ | 5-8 |
| `/update` requests per turn | 6+ | 1-2 |

---

## Related Files

- [`natural20/action.py`](natural20/action.py) — Cached `get_action_subclasses()`
- [`natural20/battle.py`](natural20/battle.py) — Battle commit with cached subclasses
- [`natural20/web/json_renderer.py`](natural20/web/json_renderer.py) — Adjacent-tile LOS shortcut
- [`n20-webapp/webapp/static/engine.js`](n20-webapp/webapp/static/engine.js) — Client-side optimizations
- [`n20-webapp/webapp/blueprints/navigation.py`](n20-webapp/webapp/blueprints/navigation.py) — `/update` endpoint with render cache
