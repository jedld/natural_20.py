# Save serialization and self-reference cycles

Save/load uses `natural20/utils/serialization.py` (`Serialization.serialize/deserialize`)
on a `yaml.SafeDumper` / `SafeLoaderWithConstructors` pair with custom tags
(`!npc`, `!map`, `!spell`, `!effect_object`, …) declared in `CLASS_TAG_MAPPING`
plus multi-representers for spells, zones, tiles and untagged effect objects.

## Entity references in saves

- `Session.to_dict` does not embed entities. Entity *objects* are first
  serialized wherever a map embeds them: as keys of `Map.to_dict`'s
  `entities` mapping (the first map that sees an entity dumps it in full;
  later maps use uid stubs via `Map._serialize_entity_value`).
- All other cross-references between entities should be stored as
  **entity_uid strings** and re-linked on load by
  `relink_spell_entities` / `relink_battle_log` / `Map.from_dict`.
- Effect descriptors (`entity.effects` lists and `entity.casted_effects`)
  store `source`/`target` as uid strings (`Entity._dump_effect_descriptor`
  used by `Entity.to_dict` and `PlayerCharacter.to_dict`). After load,
  `relink_spell_entities` resolves both keys on both stores (scalar and list
  values) back to live entities via `session.entity_by_uid`
  (`EntityRegistry` keys are normalized `str(uid)`).

## The self-reference cycle problem (and fix)

When an entity is self-linked — e.g. Strahd's Mirror Image descriptor with
`target`/`source` pointing back at Strahd — and that entity is also the first
full dump of itself (a map `entities` key), the dumper emits one node whose
subtree *aliases itself* (`&idX` + `*idX`). PyYAML's Constructor refuses any
cycle that passes through a custom-tagged node
(`ConstructorError: found unconstructable recursive node`); only map/seq
cycles in deferred *value* position are constructible.

Two layers address this:

1. **Dump side** (current saves): `Entity.to_dict` /
   `PlayerCharacter.to_dict` never embed live entity objects in effect
   descriptors, so entity nodes cannot reference themselves.
2. **Load side** (legacy saves, e.g. saves written before the dump fix):
   `SafeLoaderWithConstructors.get_single_data` runs
   `break_recursive_object_refs` on the composed node graph before
   construction. Any alias pointing at one of its own custom-tagged ancestors
   is replaced by a scalar node holding that ancestor's `entity_uid` (empty
   string if the node has none). Native map/seq cycles are left untouched.
   `relink_spell_entities` then turns the uid strings back into live entity
   references.

Regression tests: `tests/test_self_reference_serialization.py`.

## Checklist for new persisted data

- Never store live entity objects in persisted attributes or effect
  descriptors; store `entity_uid` strings (registry lookups normalize to
  `str(uid)`) and make sure `relink_spell_entities` (or your own relink pass)
  resolves them after load.
- Anything self-referential that must survive a save should rely on the uid
  string pattern, not on YAML anchors.
- Give effect classes a dedicated tag/representer when they need more than
  the generic `!effect_object` fallback; effects relying on entity event hooks
  must implement `restore_hooks()` (see `AGENTS.md`).
