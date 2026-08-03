# Performance Telemetry

Diagnostic timing instrumentation for diagnosing slow battle performance and request latency.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `N20_DEBUG_TIMING` | `0` | Set to `1` to emit `[timing]` and `[path_timing]` log lines for per-step diagnostics |
| `PERF_SLOW_MS` | `250` | Threshold (ms) at which requests are logged as `[perf] slow` (existing behavior) |
| `N20_PATH_MAX_NODES` | `1024` | Maximum number of nodes A* will explore per pass before bailing out. Prevents 30+ second runs on unreachable targets. |
| `N20_PATH_MAX_MS` | `5000` | Maximum wall-clock time (ms) per A* pass before bailing out. Set to `0` to disable. |

## Enabling

```bash
export N20_DEBUG_TIMING=1
./start_web.sh wild_sheep_chase
```

Or inline for a single session:

```bash
N20_DEBUG_TIMING=1 python -m webapp.app
```

## What Gets Logged

### `/path` endpoint (`compute_path`)

When `N20_DEBUG_TIMING=1`, each path query emits `[timing]` lines breaking down the latency:

```
[timing] path:entity_resolve=2.3ms entity=aldric pos=(6,22)
[timing] path:cache_miss=0.1ms
[timing] path:movement=1.2ms
[timing] path:pathcompute=0.4ms
[timing] path:target_map=0.1ms target=town_market
[timing] path:a_star_pass1=45230.5ms found=yes
[timing] path:post_process=12.4ms path_len=47 total=45245.8ms
```

Key timing buckets:
- `entity_resolve` — `battle_map.entity_at()` + fallback `_resolve_path_source()`
- `cache_hit` / `cache_miss` — LRU cache lookup for repeated queries
- `movement` — `entity.available_movement(battle)` call
- `pathcompute` — `PathCompute()` constructor
- `target_map` — cross-map or stack-descent map resolution
- `a_star_pass1` — First A* run (no door navigation)
- `a_star_pass2` — Second A* run (with `door_navigation=True`)
- `post_process` — `movement_cost()`, `placeable()`, terrain info collection

### `/update` endpoint

```
[timing] update:entity_lookup=1.8ms
[timing] update:pov_resolve=45.2ms entity_count=3
[timing] update:render=42150.3ms
[timing] update:template=1234.5ms
[timing] update:total=43650.1ms battle=yes
```

Key timing buckets:
- `entity_lookup` — `battle_map.entity_by_uid()` or `entity_at()`
- `pov_resolve` — POV entity resolution and filtering
- `render` — `_render_tiles_for_user()` (JSON tile rendering)
- `template` — Jinja2 `render_template('map.html')`
- `total` — Full request time

### `/conversation_presence` endpoint

```
[timing] conv_presence:cache_hit entity=aldric age=2.3s
[timing] conv_presence:normalization=1.2ms entity=aldric volume=normal dist=30ft
[timing] conv_presence:rag_lookup=342.1ms entity=aldric audible_count=8
```

Key timing buckets:
- `cache_hit` — Cache hit with age in seconds
- `normalization` — Speech mode + distance calculation
- `rag_lookup` — `entity_rag_handler.get_nearby_entities()` call

### Pathfinding (`PathCompute.compute_path`)

When `N20_DEBUG_TIMING=1`, the A* algorithm emits summary statistics:

```
[path_timing] compute_path:done entity=polymorph_bear map=town_market path_len=12 explored=45892 neighbors=183568 pq_pushes=42150 astart_ms=42350.2 total_ms=42389.7
[path_timing] compute_path:unreachable entity=polymorph_wolf map=town_market size=80x60 explored=120000 neighbors=480000 pq_pushes=115000 total_ms=38920.1
```

Key diagnostics:
- `explored` — Number of nodes popped from the priority queue
- `neighbors` — Total neighbor evaluations (should be ~4× explored for 4-connected, ~8× for 8-connected)
- `pq_pushes` — Items pushed to the priority queue (higher = more backtracking)
- `astart_ms` — Pure A* loop time
- `total_ms` — Full method time including setup and path reconstruction

### Entity Materialization

Materialization failures now include timing:

```
[timing] materialize_failed entity=shorvalu user=shorvalu lookup_ms=1250.3
```

## Interpreting Results

### Slow `/path` (>5 seconds)

1. Check `a_star_pass1` vs `a_star_pass2` — if pass1 is slow and pass2 runs, the first path failed and a second attempt was made.
2. Look at `explored` count in path_timing — >50,000 nodes suggests a large, complex map with many obstacles.
3. `neighbors` / `explored` ratio > 6 suggests many non-passable tiles being checked.

### Slow `/update` (>5 seconds)

1. `render` timing reveals tile rendering cost — high values indicate expensive `_render_tiles_for_user()`.
2. `template` timing reveals Jinja2 template rendering — high values suggest large tile arrays.
3. `pov_resolve` with many `entity_count` may indicate excessive entity filtering.

### Slow `/conversation_presence` (>500ms)

1. `rag_lookup` dominates when `entity_rag_handler.get_nearby_entities()` needs to compute pathfinding for reachability checks.
2. High `audible_count` with many reachability checks will increase this time.

### Entity Materialization Delays

High `lookup_ms` in materialize_failed logs suggests `ensure_character_entity_loaded()` is slow — check for YAML parsing overhead or missing cached entities.

## Disabling

Set `N20_DEBUG_TIMING=0` (default). The existing `[perf] slow` logging via `PERF_SLOW_MS` continues to work independently.

## perf Stats Endpoint

The DM-facing `/admin/perf-stats` endpoint (from `webapp/blueprints/dm.py`) exposes aggregate statistics:

```json
{
  "slow_threshold_ms": 250,
  "routes": {
    "navigation.compute_path": {
      "count": 1247,
      "total_ms": 458920.3,
      "max_ms": 79563.5,
      "last_ms": 123.4,
      "slow": 34
    }
  },
  "socket_emits": {
    "message": 8934,
    "map_update": 2341
  },
  "recent_slow": [...]
}
```

Clear stats with `POST /admin/perf-stats?clear=1`.
