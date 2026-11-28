# Pocket dimensions (extradimensional spaces)

`natural20/utils/pocket_dimension.py` is the generic system behind **Rope Trick** and
**Maze**, and the intended home for any future extradimensional effect (Portable Hole, Bag
of Holding interiors, Demiplane, Mordenkainen's Magnificent Mansion): a small map that is
created when the effect begins and torn down when it ends, with a real object on the
origin map serving as the doorway.

## The three pieces

1. **`PocketDimensionZone`** — a `PersistentAoEZone` subclass that owns the space's
   lifetime. Because it is a persistent zone it:
   - ticks in combat (`battle.active_zones`) *and* exploration (`map.environment_zones`),
     self-expiring at `expiration_time` (`tick_environment_zones` snapshots the map list
     so teardown mid-iteration is safe);
   - is a free **Dispel Magic** target: the zone's `squares` hold the *entrance square on
     the outer map*, so `zones_at` / `zone_for_target` find it from a square click or from
     the entrance object's `.zone` back-reference, and `end_spell_zone` routes to the
     caster's `dismiss` via the owner-side `casted_effects` entry whose `target` is the
     zone.
   - stores only uid strings / plain values in slots (`pocket_map_name`,
     `outer_map_name`, `anchor_uid`, `member_uids`, `return_square`, `inner_spawn`,
     `capacity`, `climbable`, `rope_stowed`) — never Entity/Map objects — so the
     `!persistent_zone` serializer never cycles. `relink_persistent_zones` calls
     `zone.relink(session, map_list)` so the zone re-finds its outer map by name and
     prunes members that left while the game was saved.

2. **`PocketEntranceObject`** (`!pocket_entrance` YAML tag) — a doorway `Object` placed on
   both sides. Outside instances show a token (`token_image`, `None` hides it) and offer
   `climb_in` (plus the Rope Trick `pull_rope`/`drop_rope` hide when `climbable`). Inside
   instances offer `climb_out`. `zone.climbable = False` (Maze) removes all walk-through
   verbs: escape needs the spell's own action.

3. **`create_pocket_dimension(...)`** — builds the in-memory
   `Map(session, None, properties=...)`, registers it with the session **in the same map
   set as the entry map** (`session.map_for_entity` filters to the active map set, so POV
   and lookups keep working for creatures inside), places both entrances, registers the
   zone for ticking, and records it under `session.session_state['pocket_dimensions']`.
   `map_properties` overrides the generated open-room grid; `pocket_map_properties` builds
   an open room, `maze_map_properties` builds a procedural labyrinth.

Movement across the boundary uses `natural20.map_set.place_entity_instance` — the same
primitive teleporters use — so the two sides are simply different maps: attacks, spells,
sensing and line of sight never cross.

## Teardown (`on_dismiss`)

Runs for expiry, Dispel Magic, caster dismiss, or escape:

1. `clear_member_effects()` drops the spell's member effects (and `targettable` flags);
2. `eject_members()` moves everyone who joined (`member_uids`) onto the outer map —
   centred on `return_square` when set (Maze's "reappears in the space it left"),
   otherwise the entrance square;
3. any entity **still on the pocket map that never joined as a member** is part of the
   space itself (the Maze's minotaur warden): it is removed from the map and unregistered
   from the session;
4. everyone from a running battle in the set is removed via `battle.remove(...)` so the
   battle can end normally;
5. entrance objects are removed, the pocket map is unregistered
   (`Session.unregister_map`), and the `pocket_dimension_closed` event fires.

## Spell patterns

- **Rope Trick** (`natural20/spell/rope_trick_spell.py`): visible rope token at the
  caster's square, up to `max_creatures` gathered allies auto-enter, members get the
  `rope_trick` marker + `action_restriction` (attack/spell) and `targettable = False`;
  rope pull/drop hides the entrance.
- **Maze** (`natural20/spell/maze_spell.py`): invisible entrance at the victim's square,
  `climbable=False`, victim stays fully targetable and unrestricted (it acts inside), the
  zone's `return_square` is the vacated square, and a `maze_npc` (default `minotaur`,
  `templates/npcs/minotaur.yml`) is spawned at the labyrinth cell farthest from the
  entrance (group `b`). The victim gets the `maze` effect, which grants the
  `maze_escape` action (`natural20/actions/maze_escape_action.py`, registered in
  `class_feature_registry` for PCs; `Npc.available_actions` has a branch for NPC
  targets). Minotaurs/goristras (`auto_escape:`) always succeed.

## Webapp integration (`n20-webapp/webapp/utils.py`)

- `GameManagement.sync_pov_followers()` follows every logged-in user whose POV entity
  changed maps (and evicts viewers of removed maps). Called from the environment tick and
  from `commit_and_update` whenever a result item has type `rope_trick`,
  `pocket_dimension_closed`, `pocket_travel`, `pocket_dimension_travel`, `maze` or
  `maze_escape`.
- After a `maze` cast, the minotaur+victim pair is passed to
  `loop_environment(aggressive_pairs=...)` so combat starts inside the labyrinth even
  though the walls usually block the visibility auto-battle trigger.

## Tests

`tests/test_pocket_dimension.py`, `tests/test_rope_trick_spell.py`,
`tests/test_maze_spell.py`, `tests/test_minotaur_charge.py` (charge trait), plus
save/load round trips in each file.
