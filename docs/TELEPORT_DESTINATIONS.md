# Teleportation destinations (Teleport spell)

The 7th-level **Teleport** spell is destination-driven: every caster keeps a
personal database of destinations and can only cast the spell while that
database is **non-empty**. The DM (or a game event, or an AI agent over MCP)
decides what a caster knows and how well.

- Engine module: `natural20/utils/teleport_destinations.py`
- Spell: `natural20/spell/teleport_spell.py` (YAML `templates/items/spells.yml`,
  `spell_class: Natural20::Teleport`)
- Registry storage: `entity.properties['teleport_destinations']` — plain dicts,
  so destinations persist across save/load and can be authored directly in
  NPC/character YAML.

## Destination shape

```yaml
- id: tower-library          # slug; auto-generated from the name
  name: Tower Library
  kind: coords               # coords | anchor
  map: tower_upper           # coords: campaign map name
  x: 12
  y: 8
  entity_uid: npc_xyz        # anchor: follow that person/object's current spot
  familiarity: seen_casually # see table below
  similar_maps: [...]        # optional: explicit Similar Area candidates
  off_target_map: road       # optional: where Off Target results land
  notes: ...
```

**Empty list = no Teleport.** `requires_known_destination: true` in the spell
YAML makes `SpellAction.can_cast` (and therefore the action bar, the AI option
lists, and direct `/action` calls) refuse the spell until at least one
destination is registered.

## Familiarity and the d100 outcome (PHB)

| familiarity | mishap | similar area | off target | on target |
|---|---|---|---|---|
| `permanent_circle` | — | — | — | 01–00 |
| `linked_object` | — | — | — | 01–00 |
| `very_familiar` | 01–05 | 06–13 | 14–24 | 25–00 |
| `seen_casually` | 01–33 | 34–43 | 44–53 | 54–00 |
| `viewed_once` | 01–43 | 44–53 | 54–73 | 74–00 |
| `false` | 01–50 | 51–00 | — | — |

- **Mishap**: 3d10 force damage to every teleporting creature, then reroll
  (repeatable).
- **Similar Area**: nearest *other* session map sharing an `area_themes:` tag
  (map YAML top-level) with the destination, or an explicit `similar_maps`
  entry.
- **Off Target**: 2d12 "miles" in a rolled 1d8 direction; on the grid this
  lands on a random free square of the destination's `off_target_map`
  (narrative distance/direction is logged).
- The destination **picker in the VTT lists the familiarity rating** with every
  option, e.g. `Tower Library (Seen casually)`.
- Unresolvable destination (deleted map, destroyed anchor) is treated as a
  **false destination**.

## Casting

`build_map` shows one `select_choice` per known destination (label carries the
familiarity), then the caster + up to 8 friendly creatures within 10 ft the
caster can see all arrive together (`max_creatures` / `range` in the YAML).
Cross-map arrival uses `natural20.map_set.place_entity_instance`; the webapp
follows every affected POV via `GameManagement.sync_pov_followers` (result
type `teleport`). Cast VFX: `teleport` renderers in `spell_effects.js` (2D,
violet conjuration rings + column) and the 3D `spellCatalog.js` combo recipe.

## Managing destinations

| Surface | Entry point |
|---|---|
| DM VTT | DM Console → **Teleport** tab (`webapp/static/teleport_destinations.js`, `GET/POST /dm/teleport_destinations`, helper `webapp/blueprints/helpers/teleport_destinations.py`) |
| AI agents | MCP `dm.teleport_destination` (`op=list\|add\|update\|delete\|set_familiarity`) |
| Game events / map triggers | `apply_destination_ops(session, ops, source)` |
| Authored | NPC/character YAML `teleport_destinations:` list; map YAML `triggers:` |

### Map trigger

```yaml
triggers:
  arrival:
    - type: teleport_destinations
      destinations:
        - op: add          # add | remove | set_familiarity
          target: self     # self | party | all_characters | uid:<uid>
          once: true       # per-entity once-gate (persisted)
          destination:
            name: Sunken Temple
            map: temple
            x: 8
            y: 8
            familiarity: viewed once or described
```

### Object events (`events:` vocabulary — scrying pools, shrines, tablets)

Any entry of the documented object-events vocabulary can carry a
`teleport_destinations:` block, so the grant rides the same `events:` list as
`damages:` / `update_state:` / `set_session:` (fires for that entry's event —
`on_enter`, `activate`, `died`, ...):

```yaml
events:
  - event: on_enter
    teleport_destinations:
      - op: add
        target: self
        once: true
        destination: {name: Old Shrine, map: shrine, x: 2, y: 2,
                      familiarity: described}
```

### Map object (`on_enter` pad — scrying pools, ruin markers)

Any placed map object with a `teleport_destinations:` block applies those ops
to whoever steps onto its square (same op vocabulary as above):

```yaml
objects:
  ...
  - type: scrying_pool
    label: Scrying Pool
    teleport_destinations:
      - op: add
        target: self
        once: true
        destination: {name: Dark Ruins, map: ruins, x: 3, y: 3,
                      familiarity: viewed once}
```

Changes are logged (`teleport_destinations` event → DM combat/log) and
persisted with the caster.

## Tests

- Engine: `tests/test_teleport_spell.py` (outcome table, registry CRUD +
  save/load, cross-map cast, anchors, mishap rerolls, triggers, `on_enter`
  objects).
- Webapp: `tests/webapp/test_teleport_destinations_routes.py` (auth, payload,
  ops, validation, empty-database block).
- 3D: `n20-webapp/client-3d/src/fx/spellCatalog.test.js` (recipe coverage).
