# Map Sets

A **map set** is a named group of campaign maps that share one player POV world. Maps in the same set stay linked by teleporters and map stacks. Maps in different sets never reference each other. The DM **activates** a set to jump every player camera to that player’s token instance inside the set (Roll20-style party ribbon, adapted to Natural20’s multi-map graphs).

## Why

Use cases:

- Random encounter maps
- Overland / world-map travel
- Adhoc scenes the DM creates during play
- Isolated combat labs (spell/ability testing against dummy NPCs, off the adventure path)

Party tokens can exist on more than one set at once (one live instance per set). HP and inventory stay on the single entity object. Activating Town after a forest fight returns everyone to the market squares they left.

## Backwards compatibility: `root`

Campaigns with no `map_sets:` key behave as today. Every map in `game.yml` `maps:` belongs to the implicit set **`root`**. Teleporters and stacks keep working.

When a second set is created (author YAML or DM UI), persist an explicit `root` listing every unassigned map:

```yaml
maps:
  town_market: maps/town_market
  forest_clearing: maps/forest_clearing
map_sets:
  root:
    label: Amphail
    maps: [town_market, tavern_2nd_floor]
  forest_ambush:
    label: Forest Ambush
    maps: [forest_clearing]
starting_map_set: root   # optional; default is the set that contains starting_map
```

Unlisted maps always fall back into `root`. A map belongs to exactly one set. A map stack must sit entirely inside one set.

## Token instances

Inside a set there is still **one token per `entity_uid`** (teleporters move it). Across sets the same UID may occupy one map in each set.

- Player characters always instance across sets.
- Unique NPCs (authored stable `entity_uid` such as `rose_durst`, not a spawn-time UUID) use the instance on the **active** set as LLM/AI POV. If they have no token there, they are offstage.
- The **NPC Spawner** groups catalog entries by CR. Unique sheets show a Unique badge. Dropping a unique NPC that already exists elsewhere on the **same map set** moves that token (`place_entity_instance`) instead of creating a second instance. Generic monsters still spawn as new creatures.
- Generic spawned NPCs stay on a single map and are not copied by Place Party.

`Session.map_for_entity(entity)` searches only the active set. `Session.maps_for_entity(entity)` returns every placement.

## Same-set references only

Teleporters, trap doors, chasms, event `teleport.map` / `source_map`, map stacks, edit-mode `target_map` dropdowns, `dm.teleport`, and LLM `target_map` may only point at a map in the same set.

Enforced in three places:

1. Campaign validator (`code: cross_map_set`)
2. Runtime (deny the move; do not jump the token)
3. Editor UI (dropdowns and map graph list/hide by set)

The exception is a **party-travel teleporter** (`party_travel: true`). Stepping on it does not move that token across sets. It asks the triggering player to confirm, then instances any missing PCs and in-party sidekicks onto the destination map (spawn points, or the nearest free square if those are full) and **activates** that map set. Tokens already present in the destination set stay put. Blocked while a battle is started.

If the player **cancels** (No / Escape / click outside the prompt), they stay on the pad and are not asked again just for standing there. They can retry immediately with **Interact** (action bar) or the tile **mouseover Travel** button while still on that square. Hovering the pad shows the destination and “Interact to travel with the party”. Adjacent hover offers the same button and walks them onto the pad first.

```yaml
legend:
  T:
    type: teleporter
    party_travel: true
    target_map: forest_clearing      # may be in another map set
    prompt_title: Leave town?
    prompt: |
      The entire party will be transported to the forest clearing.
      Continue?
```

`prompt` / `prompt_title` are optional; the default warning names the destination map. Same-set teleporters without `party_travel` still move a single token as before.

DM-only cross-set travel remains **Activate Map Set** or **Place Party**.

## DM tools (webapp)

Camera **View** (existing Switch Map) does not move tokens. Map modal groups maps by set:

| Action | Effect |
|---|---|
| Click map card | DM camera preview |
| **Activate** | Party POV jumps to instances in that set. Blocked while a battle is started. |
| **Place Party** | Create/update PC (and companion) instances on that map. Does not activate. |
| **New Map Set** | Appends `map_sets:` in campaign `game.yml` |
| **Create New Map** | Same as today, plus optional `map_set` (existing or new id) |

Membership is campaign state (`game.yml`). Which set players are on is session/save state (`session.active_map_set`).

Routes (DM only):

- `GET /admin/map_sets`
- `POST /admin/map_set/activate` `{map_set}`
- `POST /admin/map_set/create` `{id, label?}`
- `POST /admin/map_set/assign_map` `{map_name, map_set}`
- `POST /admin/map_set/place_party` `{map_name, x?, y?}`
- `/create_map` accepts optional `map_set`

MCP: `dm.map_set` with `op=list|activate|create|assign_map|place_party`. `world.list_maps` includes `map_set` and `active`.

DM LLM (in-app assistant) has the same surface as first-class functions:

- `list_map_sets()` — included in the chat context snapshot
- `manage_map_set(op, map_set=..., map_name=..., label=..., x=..., y=...)`

The assistant may also call `mcp("dm.map_set", {...})`. `get_map_info()` reports `map_set` and `active_map_set`.

## Combat, AI, companions

- Starting a battle from the full campaign map dict keeps only maps in the **active** set. Activate Map Set is refused while a battle is started.
- NPC environment ticks and long-rest simulation iterate dialog NPCs on **active-set maps only**.
- Unique-NPC LLM/AI POV is `map_for_entity` (the instance on the active set). Offstage if they have no token there.
- Companions sync within the destination set (teleporter, Place Party, Activate). DM camera **View** (`/switch_map`) does not move companions.

## Engine API

```python
session.map_set_for(map_name)      # 'root' if unlisted
session.same_map_set(a, b)
session.maps_in_set(set_id)
session.map_for_entity(entity, map_set=None)  # default: active set
session.maps_for_entity(entity)
session.active_map_set
```

`natural20/map_set.py` holds `MapSetRegistry`, `place_entity_instance`, `place_party_on_map`, and `persist_map_sets_to_game_yml`.
