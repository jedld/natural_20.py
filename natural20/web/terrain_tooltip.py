"""Build per-tile terrain tooltips for map rendering (used by JsonRenderer)."""

from natural20.item_library.object import Object


def _light_description(tile, battle_map):
    lights = tile.get('light')
    if lights is None and battle_map is not None:
        lights = battle_map.light_at(tile['x'], tile['y'])
    if lights is None:
        lights = 0.0
    if lights == 0.0:
        if battle_map is not None and battle_map.magical_darkness_at(tile['x'], tile['y']):
            return "Magical Darkness (heavily obscured)"
        return "Darkness (heavily obscured)"
    if lights == 0.5:
        return "Dim Light"
    return "Bright Light"


def _thing_descriptions(thing, battle):
    description = [thing.label()]
    if isinstance(thing, Object):
        if thing.dead():
            description.append("Destroyed")
        return description
    if thing.prone():
        description.append("Prone")
    if thing.hidden():
        description.append("Hiding")
    if thing.unconscious() and not thing.stable():
        description.append("Unconscious")
    if thing.dead():
        description.append("Dead")
    if thing.grappled():
        description.append("Grappled")
    if battle and thing.dodge(battle):
        description.append("Dodge")
    if thing.stable():
        description.append("Unconscious (but Stable)")
    for effect in thing.current_effects():
        description.append(str(effect['effect']))
    return description


def build_terrain_tooltip(tile, battle_map=None, battle=None, entity=None, map_objects=None):
    """Return HTML tooltip text for a map tile.

    Prefer passing ``entity`` / ``map_objects`` from JsonRenderer to avoid
    per-tile ``thing_at`` lookups during Jinja rendering.
    """
    description = []
    if tile.get('difficult'):
        description.append("Difficult Terrain")

    things = []
    if entity is not None:
        things.append(entity)
    if map_objects:
        things.extend(map_objects)
    if not things and battle_map is not None:
        things = battle_map.thing_at(tile['x'], tile['y']) or []

    for thing in things:
        description.extend(_thing_descriptions(thing, battle))

    description.append(_light_description(tile, battle_map))
    return "".join(f"<p>{d}</p>" for d in description)
