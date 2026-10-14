import pdb

def effective_ac(battle, source, target, weapon=None, thrown=False, spell_attack=False):
    """``[AC with cover, cover bonus]``. Pass the attack's ``weapon`` so feats
    that ignore cover (``weapon_attack_rules`` ``ignore_cover``) apply, and
    ``spell_attack=True`` for gear such as a Wand of the War Mage (item YAML
    ``spell_attack_ignore_cover: [half]``)."""
    cover_ac_adjustments = 0
    if battle:
        cover_ac_adjustments = calculate_cover_ac(battle.map_for(source), source, target)
        if cover_ac_adjustments and weapon is not None:
            from natural20.utils.feat_mechanics import ignored_cover_ac
            if cover_ac_adjustments <= ignored_cover_ac(source, weapon, thrown=bool(thrown)):
                cover_ac_adjustments = 0
        if cover_ac_adjustments and spell_attack:
            from natural20.utils.feat_mechanics import COVER_AC
            ignored = 0
            for level in (source.equipped_item_list('spell_attack_ignore_cover')
                          if hasattr(source, 'equipped_item_list') else []):
                ignored = max(ignored, COVER_AC.get(str(level), 0))
            if cover_ac_adjustments <= ignored:
                cover_ac_adjustments = 0
        ac = target.armor_class() + cover_ac_adjustments  # calculate AC with cover
    else:
        ac = target.armor_class()
    return [ac, cover_ac_adjustments]

def calculate_cover_ac(map, source, target):
    return cover_calculation(map, source, target)

def cover_calculation(map, source, target, entity_1_pos=None, entity_2_pos=None, naturally_stealthy=False):
    source_squares = map.entity_squares_at_pos(source, *entity_1_pos) if entity_1_pos else map.entity_squares(source)
    target_squares = map.entity_squares_at_pos(target, *entity_2_pos) if entity_2_pos else map.entity_squares(target)
    source_position = map.position_of(source)
    source_melee_square = source.melee_squares(map, target_position=source_position, adjacent_only=True)

    max_ac = 0

    for source_pos in source_squares:
        for target_pos in target_squares:
            cover_characteristics = map.line_of_sight(*source_pos, *target_pos, inclusive=True, entity=naturally_stealthy, occupant=target)
            if not cover_characteristics:
                continue

            objs = map.objects_at(*target_pos)

            for obj in objs:
                if obj.can_hide():
                    max_ac = max(max_ac, obj.cover_ac())

            for cover in cover_characteristics:
                cover_type, pos = cover

                if cover_type == "none":
                    continue
                if pos in source_melee_square and cover_type != "total":
                    continue

                if cover_type == "half":
                    max_ac = max(max_ac, 2)
                if cover_type == "three_quarter":
                    max_ac = max(max_ac, 5)

                if isinstance(cover_type, int) and naturally_stealthy and (cover_type - target.size_identifier) >= 1:
                    return 1

            return max_ac

    return 0
